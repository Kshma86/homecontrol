import copy
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Optional


SnapshotBuilder = Callable[[], Dict[str, Any]]
CONTEXT_SCHEMA_VERSION = "context.v1"
AI_CONTEXT_SCHEMA_VERSION = "context.ai.v1"
STATISTICS_SECTIONS = {
    "performance",
    "home_statistics",
    "irrigation_statistics",
    "climate_power_history",
    "climate_history",
    "server_power",
    "ai_chat_audit",
}
EXPENSIVE_REALTIME_SECTIONS = {
    "scheduler",
    "scheduler_ai",
    "irrigation_pilot",
    "climate_schedules",
}


class ContextService:
    """In-memory HC context cache.

    The database and existing domain snapshot builders remain the source of truth.
    This service only keeps prepared read models for UI, AI, mobile, and future
    modules.
    """

    def __init__(
        self,
        builders: Dict[str, SnapshotBuilder],
        *,
        realtime_ttl: float = 5.0,
        statistics_ttl: float = 60.0,
    ):
        self.builders = builders
        self.realtime_ttl = max(1.0, float(realtime_ttl))
        self.statistics_ttl = max(5.0, float(statistics_ttl))
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def snapshot(self, sections: Optional[Iterable[str]] = None, force: bool = False, trace: Optional[list] = None) -> Dict[str, Any]:
        requested = list(sections or self.builders.keys())
        realtime: Dict[str, Any] = {}
        statistics: Dict[str, Any] = {}
        errors: Dict[str, str] = {}

        for section in requested:
            if section not in self.builders:
                errors[section] = "unknown_context_section"
                _append_trace(
                    trace,
                    {
                        "section": section,
                        "started_at": _utc_now(),
                        "duration_ms": 0,
                        "cache_hit": False,
                        "ok": False,
                        "error": "unknown_context_section",
                    },
                )
                continue
            data = self.section(section, force=force, trace=trace)
            if data.get("ok") is False and data.get("error"):
                errors[section] = str(data["error"])
            target = statistics if section in STATISTICS_SECTIONS else realtime
            target[section] = data

        generated_at = _utc_now()
        payload = {
            "ok": not errors,
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "generated_at": generated_at,
            "contract": self.contract_payload(),
            "source": {
                "truth": "postgres",
                "mode": "read_through_memory_cache",
                "realtime_ttl_sec": self.realtime_ttl,
                "statistics_ttl_sec": self.statistics_ttl,
            },
            "house": self._house_state(realtime, statistics, errors, generated_at),
            "realtime": realtime,
            "statistics": statistics,
            "events": self._events_state(realtime, errors),
        }
        if errors:
            payload["errors"] = errors
        return payload

    def section(self, name: str, force: bool = False, trace: Optional[list] = None) -> Dict[str, Any]:
        if name not in self.builders:
            _append_trace(
                trace,
                {
                    "section": name,
                    "started_at": _utc_now(),
                    "duration_ms": 0,
                    "cache_hit": False,
                    "ok": False,
                    "error": "unknown_context_section",
                },
            )
            return {"ok": False, "error": "unknown_context_section", "section": name}

        now = time.monotonic()
        ttl = self.ttl_for_section(name)
        with self._lock:
            cached = self._cache.get(name)
            if not force and cached and cached["expires_at"] > now:
                data = copy.deepcopy(cached["data"])
                meta = data.get("_context") if isinstance(data.get("_context"), dict) else {}
                _append_trace(
                    trace,
                    {
                        "section": name,
                        "started_at": _utc_now(),
                        "duration_ms": 0,
                        "build_ms": meta.get("build_ms"),
                        "built_at": meta.get("built_at"),
                        "ttl_sec": ttl,
                        "cache_hit": True,
                        "ok": data.get("ok", True),
                        "error": data.get("error"),
                    },
                )
                return data

        started_at = _utc_now()
        started = time.perf_counter()
        try:
            data = self.builders[name]()
            if not isinstance(data, dict):
                data = {"value": data}
            data = dict(data)
            data.setdefault("ok", True)
        except Exception as exc:
            data = {"ok": False, "error": str(exc), "section": name}

        data["_context"] = {
            "section": name,
            "built_at": _utc_now(),
            "build_ms": round((time.perf_counter() - started) * 1000, 1),
            "ttl_sec": ttl,
        }
        _append_trace(
            trace,
            {
                "section": name,
                "started_at": started_at,
                "duration_ms": data["_context"]["build_ms"],
                "build_ms": data["_context"]["build_ms"],
                "built_at": data["_context"]["built_at"],
                "ttl_sec": ttl,
                "cache_hit": False,
                "ok": data.get("ok", True),
                "error": data.get("error"),
            },
        )
        with self._lock:
            self._cache[name] = {"expires_at": now + ttl, "data": copy.deepcopy(data)}
        return data

    def invalidate(self, section: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if section:
                existed = section in self._cache
                self._cache.pop(section, None)
                return {"ok": True, "section": section, "invalidated": existed}
            count = len(self._cache)
            self._cache.clear()
        return {"ok": True, "invalidated": count}

    def ttl_for_section(self, name: str) -> float:
        if name in STATISTICS_SECTIONS or name in EXPENSIVE_REALTIME_SECTIONS:
            return self.statistics_ttl
        return self.realtime_ttl

    def warmup(self, sections: Iterable[str], force: bool = False) -> Dict[str, Any]:
        started = time.perf_counter()
        warmed = []
        errors = {}
        for section in sections:
            data = self.section(section, force=force)
            warmed.append(section)
            if data.get("ok") is False and data.get("error"):
                errors[section] = str(data["error"])
        return {
            "ok": not errors,
            "warmed": warmed,
            "errors": errors,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    def contract_payload(self):
        return {
            "name": "hc_context",
            "version": CONTEXT_SCHEMA_VERSION,
            "available_sections": list(self.builders.keys()),
            "statistics_sections": sorted(STATISTICS_SECTIONS),
            "expensive_realtime_sections": sorted(EXPENSIVE_REALTIME_SECTIONS),
        }

    def ai_summary(self, force: bool = False, trace: Optional[list] = None) -> Dict[str, Any]:
        sections = ["weather", "irrigation", "climate", "robot", "power_wall", "solar", "tuya", "scheduler_ai", "backup", "notes"]
        if "irrigation_pilot" in self.builders:
            sections.append("irrigation_pilot")
        if "irrigation_statistics" in self.builders:
            sections.append("irrigation_statistics")
        if "home_statistics" in self.builders:
            sections.append("home_statistics")
        if "climate_power_history" in self.builders:
            sections.append("climate_power_history")
        if "climate_history" in self.builders:
            sections.append("climate_history")
        if "climate_schedules" in self.builders:
            sections.append("climate_schedules")
        if "server_power" in self.builders:
            sections.append("server_power")
        if "ai_chat_audit" in self.builders:
            sections.append("ai_chat_audit")
        ctx = self.snapshot(
            sections=sections,
            force=force,
            trace=trace,
        )
        realtime = ctx.get("realtime", {})
        statistics = ctx.get("statistics", {})
        weather = realtime.get("weather") or {}
        irrigation = realtime.get("irrigation") or {}
        irrigation_statistics = statistics.get("irrigation_statistics") or {}
        home_statistics = statistics.get("home_statistics") or {}
        climate_power = statistics.get("climate_power_history") or {}
        climate_history = statistics.get("climate_history") or {}
        server_power = statistics.get("server_power") or {}
        ai_chat_audit = statistics.get("ai_chat_audit") or {}
        climate = realtime.get("climate") or {}
        climate_schedules = realtime.get("climate_schedules") or {}
        robot = realtime.get("robot") or {}
        power_wall = realtime.get("power_wall") or {}
        solar = realtime.get("solar") or {}
        tuya = realtime.get("tuya") or {}
        scheduler = realtime.get("scheduler_ai") or realtime.get("scheduler") or {}
        irrigation_pilot = realtime.get("irrigation_pilot") or {}
        backup = realtime.get("backup") or {}
        notes = realtime.get("notes") or {}

        irrigation_guard = irrigation.get("scheduler_guard") or {}
        weather_snapshot = {
            "temperature_c": weather.get("temperature_c"),
            "humidity_percent": weather.get("humidity_percent"),
            "rain_24h_mm": weather.get("rain_24h_mm"),
            "forecast_rain_24h_mm": weather.get("forecast_rain_24h_mm"),
            "pop_percent": weather.get("pop_percent"),
            "rain_sensor": weather.get("rain_sensor"),
        }
        irrigation_state = {
            "analysis": _summarize_irrigation_statistics(irrigation_statistics),
            "manual_valve_blocked": irrigation_guard.get("blocked"),
            "manual_valve_state": irrigation_guard.get("state"),
            "sessions": _take(irrigation.get("sessions"), 5),
            "schedules": _take(irrigation.get("schedules"), 14),
            "latest": _summarize_latest_irrigation(irrigation.get("latest") or []),
        }
        climate_state = {
            "bridge_online": climate.get("bridge_online"),
            "power": climate.get("power"),
            "mode": climate.get("mode"),
            "target_temperature": climate.get("target_temperature"),
            "current_temperature": climate.get("current_temperature"),
            "fan_speed": climate.get("fan_speed"),
            "updated_at": climate.get("updated_at"),
            "error": climate.get("error"),
        }
        robot_state = {
            "bridge_online": robot.get("bridge_online"),
            "status": robot.get("robot_state_text") or robot.get("robot_state"),
            "battery": robot.get("battery"),
            "charging": robot.get("charge_status"),
            "task_state": robot.get("task_state"),
            "room_clean_status": robot.get("room_clean_status"),
            "error": robot.get("error"),
        }
        power_summary = power_wall.get("summary") or {}
        solar_summary = solar.get("summary") or {}

        return {
            "ok": ctx.get("ok", False),
            "schema_version": AI_CONTEXT_SCHEMA_VERSION,
            "generated_at": ctx.get("generated_at"),
            "contract": {
                "name": "hc_ai_context",
                "version": AI_CONTEXT_SCHEMA_VERSION,
                "source_version": ctx.get("schema_version"),
            },
            "house": ctx.get("house"),
            "weather": weather_snapshot,
            "irrigation": irrigation_state,
            "irrigation_pilot": _summarize_irrigation_pilot(irrigation_pilot),
            "climate": climate_state,
            "climate_power": _summarize_climate_power(climate_power),
            "climate_history": _summarize_climate_history(climate_history),
            "climate_schedules": _summarize_climate_schedules(climate_schedules),
            "robot": robot_state,
            "power_wall": {
                "summary": power_summary,
                "devices": _summarize_power_devices(power_wall.get("devices") or []),
                "battery_low_count": power_summary.get("battery_low"),
            },
            "solar": {
                "current": solar.get("current") or {},
                "summary": solar_summary,
            },
            "home_statistics": _summarize_home_statistics(home_statistics),
            "server_power": _summarize_server_power(server_power),
            "ai_chat_audit": _summarize_ai_chat_audit(ai_chat_audit),
            "tuya": {
                "summary": tuya.get("summary") or {},
                "devices": _summarize_tuya_devices(tuya.get("devices") or []),
            },
            "scheduler": {
                "config": scheduler.get("config") or {},
                "engine": scheduler.get("engine") or {},
                "preflight": scheduler.get("preflight") or {},
            },
            "backup": {
                "summary": {
                    "backup_count": len(backup.get("backups") or []),
                    "schedule_enabled": (backup.get("settings") or {}).get("schedule_enabled"),
                    "timer_active": (backup.get("timer") or {}).get("active"),
                },
            },
            "open_notes": {
                "issues": [item for item in notes.get("issues", []) if not item.get("done")][:10],
                "requests": [item for item in notes.get("requests", []) if not item.get("done")][:10],
            },
            "errors": ctx.get("errors", {}),
        }

    def _house_state(self, realtime: Dict[str, Any], statistics: Dict[str, Any], errors: Dict[str, str], generated_at: str):
        power_summary = (realtime.get("power_wall") or {}).get("summary") or {}
        performance = statistics.get("performance") or {}
        docker_summary = (performance.get("summary") or {})
        return {
            "system": "homecontrol",
            "status": "degraded" if errors else "ok",
            "generated_at": generated_at,
            "active_errors": [{"section": key, "error": value} for key, value in errors.items()],
            "active_warnings": _warnings(realtime, power_summary),
            "peripherals": {
                "power_wall_total": power_summary.get("total"),
                "power_wall_online": power_summary.get("online"),
                "power_wall_offline": power_summary.get("offline"),
                "battery_low": power_summary.get("battery_low"),
            },
            "runtime": {
                "docker_running": docker_summary.get("docker_running"),
                "docker_total": docker_summary.get("docker_total"),
                "workers_running": docker_summary.get("workers_running"),
                "workers_total": docker_summary.get("workers_total"),
            },
        }

    def _events_state(self, realtime: Dict[str, Any], errors: Dict[str, str]):
        notes = realtime.get("notes") or {}
        issues = [item for item in notes.get("issues", []) if not item.get("done")]
        warnings = _warnings(realtime, (realtime.get("power_wall") or {}).get("summary") or {})
        return {
            "errors": [{"section": key, "error": value} for key, value in errors.items()],
            "warnings": warnings,
            "open_issues": _take(issues, 10),
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _take(value: Any, limit: int):
    if not isinstance(value, list):
        return []
    return value[:limit]


def _number(value: Any):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 2):
    number = _number(value)
    if number is None:
        return None
    return round(number, digits)


def _pick(payload: Any, keys: Iterable[str]):
    if not isinstance(payload, dict):
        return {}
    return {key: payload.get(key) for key in keys if key in payload}


def _summarize_irrigation_pilot(payload: Dict[str, Any]):
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    recommendation = payload.get("recommendation") if isinstance(payload.get("recommendation"), dict) else {}
    latest = payload.get("latest_decision") if isinstance(payload.get("latest_decision"), dict) else {}
    today = payload.get("today_decision") if isinstance(payload.get("today_decision"), dict) else {}
    return {
        "config": _pick(config, [
            "mode",
            "base_duration_minutes",
            "rain_24h_threshold_mm",
            "forecast_rain_threshold_mm",
            "pop_threshold_percent",
            "heat_threshold_c",
            "heat_correction_percent",
            "cold_threshold_c",
            "cold_correction_percent",
            "soil_moisture_enabled",
            "soil_sensor_topic_base",
            "soil_wet_skip_threshold_percent",
            "soil_dry_threshold_percent",
            "soil_dry_correction_percent",
            "soil_sample_max_age_hours",
            "updated_at",
        ]),
        "recommendation": _pick(recommendation, [
            "mode",
            "base_duration",
            "base_source",
            "base_schedule",
            "final_duration",
            "reason",
            "triggered_rules",
            "weather_snapshot",
        ]),
        "latest_decision": _pick(latest, [
            "timestamp",
            "mode",
            "base_duration",
            "final_duration",
            "executed",
            "reason",
            "triggered_rules",
            "schedule_id",
            "execution_status",
        ]),
        "today_decision": _pick(today, [
            "timestamp",
            "mode",
            "base_duration",
            "final_duration",
            "executed",
            "reason",
            "triggered_rules",
            "schedule_id",
            "execution_status",
        ]),
    }


def _summarize_server_power(payload: Dict[str, Any]):
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    device = payload.get("device") if isinstance(payload.get("device"), dict) else {}
    daily = payload.get("daily_30d") if isinstance(payload.get("daily_30d"), list) else []
    power_24h = payload.get("power_24h") if isinstance(payload.get("power_24h"), list) else []

    def avg_energy(rows):
        values = [_number(row.get("energy_kwh")) for row in rows if isinstance(row, dict)]
        values = [value for value in values if value is not None]
        return round(sum(values) / len(values), 3) if values else None

    power_values = [_number(row.get("power_w")) for row in power_24h if isinstance(row, dict)]
    power_values = [value for value in power_values if value is not None]
    return {
        "ok": payload.get("ok"),
        "device": _pick(device, [
            "entity_id",
            "entity_name",
            "device_name",
            "display_name",
            "ext_id",
            "status",
            "last_seen_ts",
        ]),
        "current_power_w": summary.get("current_power_w"),
        "max_power_w_24h": summary.get("max_power_w"),
        "avg_power_w_24h": round(sum(power_values) / len(power_values), 2) if power_values else None,
        "today_energy_kwh": summary.get("today_energy_kwh"),
        "avg_daily_energy_kwh_7d": avg_energy(daily[-7:]),
        "avg_daily_energy_kwh_30d": avg_energy(daily),
        "total_energy_kwh": summary.get("total_energy_kwh"),
        "sample_count_24h": summary.get("power_samples"),
        "daily_days": summary.get("daily_days"),
        "updated_at": summary.get("updated_at"),
        "error": payload.get("error"),
    }


def _summarize_ai_chat_audit(payload: Dict[str, Any]):
    return {
        "ok": payload.get("ok"),
        "sample_size": payload.get("sample_size"),
        "window": payload.get("window") or {},
        "success": payload.get("success") or {},
        "latency": payload.get("latency") or {},
        "top_skills": _take(payload.get("top_skills"), 10),
        "top_data_sources": _take(payload.get("top_data_sources"), 12),
        "slow_context_sections": _take(payload.get("slow_context_sections"), 10),
        "slow_skills": _take(payload.get("slow_skills"), 10),
        "recent_questions": _take(payload.get("recent_questions"), 12),
        "analysis_goal": "Use these audit rows to improve the HomeControl context layer: identify missing context, wrong routing, slow sections, expensive DB paths, and frequently requested data that should become first-class AI context.",
        "error": payload.get("error"),
    }


def _summarize_climate_power(payload: Dict[str, Any]):
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    meter = payload.get("meter") if isinstance(payload.get("meter"), dict) else {}
    daily = payload.get("daily_30d") if isinstance(payload.get("daily_30d"), list) else []
    power_24h = payload.get("power_24h") if isinstance(payload.get("power_24h"), list) else []

    def energy_sum(rows):
        values = [_number(row.get("energy_kwh")) for row in rows if isinstance(row, dict)]
        return round(sum(value for value in values if value is not None), 3)

    def avg_energy(rows):
        values = [_number(row.get("energy_kwh")) for row in rows if isinstance(row, dict)]
        values = [value for value in values if value is not None]
        return round(sum(values) / len(values), 3) if values else None

    month_rows = []
    today = date.today()
    for row in daily:
        day = row.get("day") if isinstance(row, dict) else None
        try:
            parsed = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
        except (TypeError, ValueError):
            continue
        if parsed.year == today.year and parsed.month == today.month:
            month_rows.append(row)

    power_values = [_number(row.get("power_w")) for row in power_24h if isinstance(row, dict)]
    power_values = [value for value in power_values if value is not None]
    return {
        "ok": payload.get("ok"),
        "meter": _pick(meter, [
            "entity_id",
            "entity_name",
            "device_name",
            "ext_id",
            "status",
            "last_seen_ts",
        ]),
        "current_power_w": (meter.get("state") or {}).get("power_w") if isinstance(meter.get("state"), dict) else None,
        "max_power_w_24h": summary.get("max_power_w"),
        "avg_power_w_24h": round(sum(power_values) / len(power_values), 2) if power_values else None,
        "today_energy_kwh": summary.get("today_energy_kwh"),
        "energy_kwh_7d": energy_sum(daily[-7:]),
        "energy_kwh_30d": energy_sum(daily),
        "avg_daily_energy_kwh_7d": avg_energy(daily[-7:]),
        "avg_daily_energy_kwh_30d": avg_energy(daily),
        "month_energy_kwh": energy_sum(month_rows),
        "month_days": len(month_rows),
        "sample_count_24h": summary.get("power_samples"),
        "daily_days": summary.get("daily_days"),
        "error": payload.get("error"),
    }


def _summarize_climate_history(payload: Dict[str, Any]):
    return {
        "ok": payload.get("ok"),
        "device": _pick(payload.get("device") or {}, [
            "entity_id",
            "entity_name",
            "device_name",
            "ext_id",
            "status",
            "last_seen_ts",
        ]),
        "latest": payload.get("latest") or {},
        "latest_ts": payload.get("latest_ts") or {},
        "numeric_24h": payload.get("numeric_24h") or {},
        "numeric_7d": payload.get("numeric_7d") or {},
        "distributions_7d": {
            key: _take(value, 8)
            for key, value in (payload.get("distributions_7d") or {}).items()
        },
        "recent_setting_changes_7d": _take(payload.get("recent_setting_changes_7d"), 30),
        "samples_24h": _take(payload.get("samples_24h"), 80),
        "summary": payload.get("summary") or {},
        "analysis_goal": "Use this history for climate setting questions: typical power/mode/target_temperature/fan_speed usage, current vs target temperature trend, and recent setting changes.",
        "error": payload.get("error"),
    }


def _summarize_climate_schedules(payload: Dict[str, Any]):
    schedules = payload.get("schedules") if isinstance(payload.get("schedules"), list) else []
    compact = []
    for row in schedules[:14]:
        if not isinstance(row, dict):
            continue
        compact.append(_pick(row, [
            "id",
            "label",
            "day_of_week",
            "start_time",
            "is_enabled",
            "is_today",
            "should_run_now",
            "schedule_status",
            "power",
            "mode",
            "target_temperature",
            "fan_speed",
            "light",
            "rule_engine",
            "updated_at",
        ]))
    enabled = [row for row in compact if row.get("is_enabled")]
    return {
        "ok": payload.get("ok"),
        "count": len(schedules),
        "enabled_count": len(enabled),
        "schedules": compact,
        "enabled_schedules": enabled[:7],
        "error": payload.get("error"),
    }


def _trend(first: Any, latest: Any, *, deadband: float = 0.05):
    start = _number(first)
    end = _number(latest)
    if start is None or end is None:
        return "unknown"
    delta = end - start
    if abs(delta) <= deadband:
        return "stable"
    return "rising" if delta > 0 else "falling"


def _first_number(rows: Iterable[Dict[str, Any]], key: str):
    for row in rows:
        if isinstance(row, dict):
            value = _number(row.get(key))
            if value is not None:
                return value
    return None


def _last_number(rows: Iterable[Dict[str, Any]], key: str):
    if not isinstance(rows, list):
        rows = list(rows)
    for row in reversed(rows):
        if isinstance(row, dict):
            value = _number(row.get(key))
            if value is not None:
                return value
    return None


def _average(values: Iterable[Any], digits: int = 2):
    numbers = [_number(value) for value in values]
    clean = [value for value in numbers if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), digits)


def _date_value(value: Any):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _period_daily_rows(rows: list, *, days: Optional[int] = None, start_day: Optional[date] = None):
    today = date.today()
    cutoff = today - timedelta(days=days - 1) if days else start_day
    result = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        day = _date_value(row.get("day"))
        if day and cutoff and day < cutoff:
            continue
        result.append(row)
    return result


def _period_cycle_rows(rows: list, *, days: Optional[int] = None, start_day: Optional[date] = None):
    today = date.today()
    cutoff = today - timedelta(days=days - 1) if days else start_day
    result = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        day = _date_value(row.get("started_at"))
        if day and cutoff and day < cutoff:
            continue
        result.append(row)
    return result


def _duration_distribution(rows: list, *, target_min: float = 90.0, tolerance_min: float = 5.0):
    shorter = []
    near = []
    longer = []
    unknown = 0
    lower = target_min - tolerance_min
    upper = target_min + tolerance_min
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        duration = _number(row.get("duration_minutes"))
        if duration is None:
            unknown += 1
        elif duration < lower:
            shorter.append(duration)
        elif duration > upper:
            longer.append(duration)
        else:
            near.append(duration)
    return {
        "target_min": target_min,
        "tolerance_min": tolerance_min,
        "near_target_count": len(near),
        "shorter_count": len(shorter),
        "longer_count": len(longer),
        "unknown_count": unknown,
        "near_target_avg_min": _average(near, 1),
        "shorter_avg_min": _average(shorter, 1),
        "longer_avg_min": _average(longer, 1),
    }


def _irrigation_period_summary(label: str, pump_rows: list, sessions: list, *, days: Optional[int] = None, start_day: Optional[date] = None):
    pump_period = _period_daily_rows(pump_rows, days=days, start_day=start_day)
    session_period = _period_cycle_rows(sessions, days=days, start_day=start_day)
    active_pump_rows = [row for row in pump_period if (_number(row.get("pump_running_minutes")) or 0) > 0]
    durations = [row.get("duration_minutes") for row in session_period if isinstance(row, dict)]
    start_days = [_date_value(row.get("day")) for row in pump_period if _date_value(row.get("day"))]
    return {
        "label": label,
        "start_day": min(start_days).isoformat() if start_days else (start_day.isoformat() if start_day else None),
        "end_day": max(start_days).isoformat() if start_days else None,
        "daily_sample_days": len(pump_period),
        "pump_active_days": len(active_pump_rows),
        "pump_total_runtime_min": _round(sum(_number(row.get("pump_running_minutes")) or 0 for row in pump_period), 1),
        "pump_avg_runtime_active_day_min": _average([row.get("pump_running_minutes") for row in active_pump_rows], 1),
        "pump_total_wh": _round(sum(_number(row.get("watt_hours")) or 0 for row in pump_period), 1),
        "cycle_count": len(session_period),
        "cycle_avg_duration_min": _average(durations, 1),
        "cycle_duration_distribution_90m": _duration_distribution(session_period, target_min=90.0, tolerance_min=5.0),
        "automatic_start_count": sum(1 for row in session_period if _irrigation_start_source(row) == "automatic"),
        "manual_start_count": sum(1 for row in session_period if _irrigation_start_source(row) == "manual"),
        "automatic_stop_count": sum(1 for row in session_period if _irrigation_stop_source(row) == "automatic"),
        "manual_stop_count": sum(1 for row in session_period if _irrigation_stop_source(row) == "manual"),
    }


def _summarize_irrigation_cycle(row: Dict[str, Any]):
    return {
        "started_at": row.get("started_at"),
        "ended_at": _irrigation_cycle_end(row),
        "duration_min": _round(row.get("duration_minutes"), 1),
        "started_by": row.get("started_by"),
        "start_source": _irrigation_start_source(row),
        "stop_source": _irrigation_stop_source(row),
        "source": row.get("source"),
        "stop_reason": row.get("stop_reason"),
        "status": row.get("status"),
        "avg_current_a": _round(row.get("avg_current_a"), 2),
        "max_current_a": _round(row.get("max_current_a"), 2),
        "watt_hours": _round(row.get("watt_hours"), 1),
    }


def _summarize_irrigation_cycles(rows: list, limit: int):
    return [_summarize_irrigation_cycle(row) for row in rows[:limit] if isinstance(row, dict)]


def _ts(value: Any):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _minutes_between(start: Any, end: Any):
    start_ts = _ts(start)
    end_ts = _ts(end)
    if start_ts is None or end_ts is None:
        return None
    return round((end_ts - start_ts) / 60, 1)


def _sample_points(samples: Iterable[Dict[str, Any]], value_key: str):
    points = []
    for sample in samples or []:
        if not isinstance(sample, dict):
            continue
        ts = _ts(sample.get("ts"))
        value = _number(sample.get(value_key))
        if ts is not None and value is not None:
            points.append({"ts": sample.get("ts"), "_ts": ts, "value": value})
    return sorted(points, key=lambda item: item["_ts"])


def _value_point(points: list, *, start_ts: float, end_ts: float, mode: str):
    window = [point for point in points if start_ts <= point["_ts"] <= end_ts]
    if not window:
        return None
    if mode == "min":
        return min(window, key=lambda item: item["value"])
    if mode == "max":
        return max(window, key=lambda item: item["value"])
    return window[-1]


def _first_present(row: Dict[str, Any], *keys: str):
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _irrigation_cycle_end(row: Dict[str, Any]):
    return _first_present(row, "ended_at", "stopped_at", "stop_at")


def _irrigation_start_source(row: Dict[str, Any]):
    values = " ".join(str(row.get(key) or "").strip().lower() for key in ("started_by", "source"))
    if any(part in values for part in ["scheduler", "pilot", "v2_scheduler"]):
        return "automatic"
    if any(part in values for part in ["admin", "manual", "homecontrol-admin", "user", "dashboard"]):
        return "manual"
    return "unknown"


def _irrigation_stop_source(row: Dict[str, Any]):
    status = str(row.get("status") or "").strip().lower()
    if status in {"stopped", "manual_stopped"}:
        return "manual"
    if status == "auto_stopped":
        return "automatic"
    if status in {"running", "starting"}:
        return "not_stopped"
    return "unknown"


def _watering_response(samples: list, sessions: list):
    points = _sample_points(samples, "soil_moisture")
    responses = []
    for session in sessions[:5]:
        if not isinstance(session, dict):
            continue
        start_ts = _ts(session.get("started_at"))
        ended_at = _irrigation_cycle_end(session)
        end_ts = _ts(ended_at) or start_ts
        if start_ts is None:
            continue
        before = _value_point(points, start_ts=start_ts - 12 * 3600, end_ts=start_ts, mode="min")
        start_value = _value_point(points, start_ts=start_ts - 45 * 60, end_ts=start_ts + 15 * 60, mode="last")
        peak = _value_point(points, start_ts=start_ts, end_ts=end_ts + 6 * 3600, mode="max")
        after = _value_point(points, start_ts=end_ts, end_ts=end_ts + 6 * 3600, mode="last")
        if not before and not peak:
            continue
        rise = _round((peak["value"] - before["value"]) if before and peak else None, 1)
        responses.append(
            {
                "started_at": session.get("started_at"),
                "ended_at": ended_at,
                "cycle_duration_min": _round(session.get("duration_minutes"), 1),
                "status": session.get("status"),
                "started_by": session.get("started_by"),
                "start_source": _irrigation_start_source(session),
                "stop_source": _irrigation_stop_source(session),
                "pre_cycle_min_percent": _round(before["value"], 1) if before else None,
                "pre_cycle_min_ts": before.get("ts") if before else None,
                "near_start_percent": _round(start_value["value"], 1) if start_value else None,
                "peak_after_start_percent": _round(peak["value"], 1) if peak else None,
                "peak_ts": peak.get("ts") if peak else None,
                "rise_from_pre_min_percent": rise,
                "last_within_6h_after_percent": _round(after["value"], 1) if after else None,
                "minutes_start_to_peak": _minutes_between(session.get("started_at"), peak.get("ts")) if peak else None,
                "interpretation": "effective_response" if rise is not None and rise >= 5 else "weak_or_unclear_response" if rise is not None else "insufficient_samples",
            }
        )
    return responses


def _display_name(name: Any):
    translations = {
        "Felső előszoba": "Upstairs Hallway",
        "Felső előszoba konnektor": "Upstairs Hallway Plug",
        "Fenti fürdő": "Upstairs Bathroom",
        "Fehér szoba": "White Room",
        "Udvar": "Yard",
    }
    text = str(name or "").strip()
    return translations.get(text, text)


def _name_aliases(name: Any):
    text = str(name or "").strip()
    display = _display_name(text)
    aliases = []
    for item in [text, display]:
        if item and item not in aliases:
            aliases.append(item)
    return aliases


def _summarize_latest_irrigation(rows: list):
    result = []
    for row in rows[:80]:
        result.append(
            {
                "entity": row.get("entity_name"),
                "key": row.get("key"),
                "value": row.get("v_num") if row.get("v_num") is not None else row.get("v_bool") if row.get("v_bool") is not None else row.get("v_text"),
                "ts": row.get("ts"),
            }
        )
    return result


def _summarize_irrigation_statistics(stats: Dict[str, Any]):
    if not isinstance(stats, dict):
        return {}

    pump_daily = stats.get("pump_daily") or []
    sessions = stats.get("sessions") or []
    tank_24h = stats.get("tank_24h") or []
    soil_sensors = stats.get("soil_moisture_24h") or []
    today_pump = pump_daily[0] if pump_daily else {}
    recent_pump = pump_daily[:7]
    recent_sessions = sessions[:8]
    current_year = date.today().year
    summer_start = date(current_year, 6, 1)
    tank_values = [row.get("level_percent") for row in tank_24h if isinstance(row, dict)]
    latest_tank = next((row for row in reversed(tank_24h) if isinstance(row, dict) and row.get("level_percent") is not None), None)

    moisture = []
    for sensor in soil_sensors[:6]:
        samples = sensor.get("samples") or []
        clean_samples = [sample for sample in samples if isinstance(sample, dict) and sample.get("soil_moisture") is not None]
        first = clean_samples[0] if clean_samples else {}
        latest = clean_samples[-1] if clean_samples else {}
        values = [sample.get("soil_moisture") for sample in clean_samples]
        moisture.append(
            {
                "entity_id": sensor.get("entity_id"),
                "name": sensor.get("entity_name") or sensor.get("device_name"),
                "latest_percent": _round(sensor.get("latest_soil_moisture"), 1),
                "min_24h_percent": _round(sensor.get("min_soil_moisture"), 1),
                "max_24h_percent": _round(sensor.get("max_soil_moisture"), 1),
                "avg_24h_percent": _average(values, 1),
                "trend_24h": _trend(first.get("soil_moisture"), latest.get("soil_moisture"), deadband=1.0),
                "delta_24h_percent": _round((_number(latest.get("soil_moisture")) or 0) - (_number(first.get("soil_moisture")) or 0), 1) if first and latest else None,
                "watering_response": _watering_response(clean_samples, recent_sessions),
                "sample_count": sensor.get("sample_count") or len(clean_samples),
                "latest_ts": sensor.get("latest_ts") or latest.get("ts"),
            }
        )

    session_durations = [row.get("duration_minutes") for row in recent_sessions if isinstance(row, dict)]
    return {
        "tank_24h": {
            "latest_level_percent": _round(latest_tank.get("level_percent") if latest_tank else None, 1),
            "latest_depth_m": _round(latest_tank.get("depth_m") if latest_tank else None, 3),
            "min_level_percent": _round(min([_number(value) for value in tank_values if _number(value) is not None], default=None), 1),
            "max_level_percent": _round(max([_number(value) for value in tank_values if _number(value) is not None], default=None), 1),
            "trend_24h": _trend(tank_values[0] if tank_values else None, tank_values[-1] if tank_values else None, deadband=1.0),
            "sample_count": len(tank_24h),
        },
        "moisture_24h": moisture,
        "pump": {
            "today": {
                "day": today_pump.get("day"),
                "runtime_min": _round(today_pump.get("pump_running_minutes"), 1),
                "watt_hours": _round(today_pump.get("watt_hours"), 1),
                "amp_hours": _round(today_pump.get("amp_hours"), 2),
                "avg_current_a": _round(today_pump.get("avg_current_a"), 2),
                "max_current_a": _round(today_pump.get("max_current_a"), 2),
                "avg_voltage_v": _round(today_pump.get("avg_voltage_v"), 2),
            },
            "last_7d": [
                {
                    "day": row.get("day"),
                    "runtime_min": _round(row.get("pump_running_minutes"), 1),
                    "watt_hours": _round(row.get("watt_hours"), 1),
                    "amp_hours": _round(row.get("amp_hours"), 2),
                    "max_current_a": _round(row.get("max_current_a"), 2),
                }
                for row in recent_pump
                if isinstance(row, dict)
            ],
            "avg_runtime_7d_min": _average([row.get("pump_running_minutes") for row in recent_pump if isinstance(row, dict)], 1),
            "total_runtime_7d_min": _round(sum(_number(row.get("pump_running_minutes")) or 0 for row in recent_pump if isinstance(row, dict)), 1),
            "total_wh_7d": _round(sum(_number(row.get("watt_hours")) or 0 for row in recent_pump if isinstance(row, dict)), 1),
            "available_daily_history_days": len([row for row in pump_daily if isinstance(row, dict)]),
            "periods": {
                "last_7d": _irrigation_period_summary("utolsó 7 nap", pump_daily, sessions, days=7),
                "last_30d": _irrigation_period_summary("utolsó 30 nap", pump_daily, sessions, days=30),
                "last_180d": _irrigation_period_summary("utolsó 180 nap", pump_daily, sessions, days=180),
                "summer_season": _irrigation_period_summary("aktuális nyári szezon", pump_daily, sessions, start_day=summer_start),
            },
        },
        "cycles": {
            "recent": _summarize_irrigation_cycles(recent_sessions, 8),
            "last_30d": _summarize_irrigation_cycles(_period_cycle_rows(sessions, days=30), 120),
            "avg_duration_recent_min": _average(session_durations, 1),
        },
    }


def _summarize_home_statistics(stats: Dict[str, Any]):
    if not isinstance(stats, dict):
        return {}
    sensors = stats.get("temp_humidity_sensors") or []
    result = []
    indoor_temps = []
    indoor_humidity = []
    for sensor in sensors[:30]:
        if not isinstance(sensor, dict):
            continue
        samples = sensor.get("samples") or []
        clean_samples = [sample for sample in samples if isinstance(sample, dict)]
        first = clean_samples[0] if clean_samples else {}
        latest = clean_samples[-1] if clean_samples else {}
        temp_values = [sample.get("temperature") for sample in clean_samples if sample.get("temperature") is not None]
        humidity_values = [sample.get("humidity") for sample in clean_samples if sample.get("humidity") is not None]
        abs_humidity_values = [sample.get("absolute_humidity_g_m3") for sample in clean_samples if sample.get("absolute_humidity_g_m3") is not None]
        name = sensor.get("entity_name") or sensor.get("device_name")
        is_outdoor = str(name or "").strip().lower() in {"udvar", "yard", "outside", "outdoor"}
        latest_temperature = sensor.get("latest_temperature")
        latest_humidity = sensor.get("latest_humidity")
        if not is_outdoor:
            indoor_temps.append(latest_temperature)
            indoor_humidity.append(latest_humidity)
        result.append(
            {
                "entity_id": sensor.get("entity_id"),
                "name": name,
                "display_name": _display_name(name),
                "aliases": _name_aliases(name),
                "latest_temperature_c": _round(latest_temperature, 1),
                "latest_humidity_percent": _round(latest_humidity, 1),
                "latest_absolute_humidity_g_m3": _round(sensor.get("latest_absolute_humidity_g_m3"), 2),
                "temperature": {
                    "min_24h_c": _round(min([_number(value) for value in temp_values if _number(value) is not None], default=None), 1),
                    "max_24h_c": _round(max([_number(value) for value in temp_values if _number(value) is not None], default=None), 1),
                    "avg_24h_c": _average(temp_values, 1),
                    "trend_24h": _trend(_first_number(clean_samples, "temperature"), _last_number(clean_samples, "temperature"), deadband=0.2),
                },
                "humidity": {
                    "min_24h_percent": _round(min([_number(value) for value in humidity_values if _number(value) is not None], default=None), 1),
                    "max_24h_percent": _round(max([_number(value) for value in humidity_values if _number(value) is not None], default=None), 1),
                    "avg_24h_percent": _average(humidity_values, 1),
                    "trend_24h": _trend(_first_number(clean_samples, "humidity"), _last_number(clean_samples, "humidity"), deadband=1.0),
                },
                "absolute_humidity": {
                    "avg_24h_g_m3": _average(abs_humidity_values, 2),
                    "trend_24h": _trend(_first_number(clean_samples, "absolute_humidity_g_m3"), _last_number(clean_samples, "absolute_humidity_g_m3"), deadband=0.15),
                },
                "sample_count": sensor.get("sample_count") or len(clean_samples),
                "latest_ts": sensor.get("latest_ts") or latest.get("ts"),
                "is_outdoor": is_outdoor,
            }
        )

    return {
        "sensor_count": len(sensors),
        "indoor_avg_temperature_c": _average(indoor_temps, 1),
        "indoor_avg_humidity_percent": _average(indoor_humidity, 1),
        "sensors": result,
    }


def _warnings(realtime: Dict[str, Any], power_summary: Dict[str, Any]):
    result = []
    climate = realtime.get("climate") or {}
    robot = realtime.get("robot") or {}
    if climate.get("error"):
        result.append({"domain": "climate", "message": climate["error"]})
    if robot.get("error"):
        result.append({"domain": "robot", "message": robot["error"]})
    if power_summary.get("battery_low"):
        result.append({"domain": "power_wall", "message": f"{power_summary['battery_low']} low battery device(s)"})
    return result


def _summarize_power_devices(devices: list):
    result = []
    for item in devices[:30]:
        state = item.get("state") or {}
        switch = state.get("switch_state") or state.get("state") or {}
        power = state.get("power_w") or state.get("power") or {}
        result.append(
            {
                "entity_id": item.get("entity_id"),
                "name": item.get("display_name") or item.get("entity_name") or item.get("device_name"),
                "platform": item.get("platform"),
                "status": item.get("status"),
                "switch": switch.get("value") if isinstance(switch, dict) else switch,
                "power_w": power.get("value") if isinstance(power, dict) else power,
                "always_on": item.get("always_on"),
                "auto_climate": item.get("auto_climate"),
            }
        )
    return result


def _summarize_tuya_devices(devices: list):
    result = []
    for item in devices[:30]:
        state = item.get("state") or {}
        switch = state.get("switch_state") or {}
        power = state.get("power_w") or {}
        result.append(
            {
                "entity_id": item.get("entity_id"),
                "name": item.get("entity_name") or item.get("device_name"),
                "status": item.get("status"),
                "switch": switch.get("value") if isinstance(switch, dict) else switch,
                "power_w": power.get("value") if isinstance(power, dict) else power,
            }
        )
    return result


def _append_trace(trace: Optional[list], item: Dict[str, Any]) -> None:
    if trace is not None:
        trace.append(item)
