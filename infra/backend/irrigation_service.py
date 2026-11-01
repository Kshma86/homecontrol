from irrigation_summary_queries import bounded_daily_query
from read_model_cache import ReadModelCache
from runtime_schema_contract import check_runtime_schema
import json
import math
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from irrigation_utils import reaction_current_active, text_upper, validate_schedule_time
from irrigation_recovery import IrrigationSessionRecovery


IRRIGATION_MOISTURE_TOPICS = (
    "zigbee/0xa4c1382abf3f8730",
    "zigbee/0xa4c13844a0908898",
    "zigbee/0xa4c1387594b09c83",
)
PILOT_SOIL_SENSOR_TOPIC = "zigbee/0xa4c13844a0908898"
LOCAL_WEATHER_SENSOR_MAX_AGE_HOURS = 6.0
# Firmware *_sec_ago counters have second resolution. Use the older bound when
# proving that a Nano sample was acquired after a command, including age == 0.
NANO_SAMPLE_AGE_RESOLUTION_SECONDS = 1.0
SCHEDULE_DAY_LABELS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class IrrigationService:
    def __init__(
        self,
        fetch_all: Callable[..., Any],
        fetch_one: Callable[..., Any],
        execute_one: Callable[..., Any],
        execute_sql: Callable[..., Any],
        publish_mqtt: Callable[..., Any],
        normalize_text: Callable[..., str],
        command_topics: Callable[[], Dict[str, str]],
        invalidate_snapshot: Callable[[], Any],
        invalidate_pilot: Callable[[], Any],
        invalidate_weather_summary: Callable[[], Any],
        invalidate_context: Callable[..., Any],
        context_meta: Callable[..., Dict[str, Any]],
        ensure_pilot_schema: Callable[[], Any],
        to_float: Callable[..., Optional[float]],
        to_int: Callable[..., int],
        manual_max_minutes: int,
        api_cache_get: Callable[[str], Any],
        api_cache_set: Callable[[str, Any, float], Any],
        api_cache_delete_prefix: Callable[[str], Any],
        mqtt_snapshot: Callable[[], Dict[str, Any]],
        scheduler_config: Callable[[], Dict[str, Any]],
        v2_execution_engine_state: Callable[[Dict[str, Any]], Dict[str, Any]],
        json_time: Callable[[Any], Any],
        stop_confirm_attempts: int,
        stop_reaction_delay_seconds: int,
        stop_closed_delay_seconds: int,
        open_confirm_attempts: int,
        open_reaction_delay_seconds: int,
        open_ready_delay_seconds: int,
        openweather_api_key: str,
        openweather_lat: str,
        openweather_lon: str,
        openweather_units: str,
        openweather_lang: str,
        weather_poll_seconds: int,
        absolute_humidity_g_m3: Callable[[Any, Any], Any],
        process_binding_topic: Callable[[str], Any] = None,
        process_binding_payload: Callable[[str], Any] = None,
        pilot_cache_ttl: float = 300.0,
        weather_summary_cache_ttl: float = 300.0,
        daily_summary_days: int = 35,
        daily_summary_refresh_sec: float = 300.0,
        snapshot_ttl: float = 10.0,
        control_allowed: Callable[[], bool] = None,
        capability_allowed: Callable[[str], bool] = None,
        active_season_profile: Callable[[], Dict[str, Any]] = None,
        valve_tele_max_age_seconds: float = 25.0,
        valve_status_max_age_seconds: float = 70.0,
        nano_online_max_age_seconds: float = 40.0,
        start_recovery_grace_seconds: float = 120.0,
        recovery_retry_seconds: float = 60.0,
        recovery_max_attempts: int = 3,
        reserve_session: Optional[Callable[..., Any]] = None,
        cached_api_payload: Callable[..., Any] = None,
    ):
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.execute_one = execute_one
        self.execute_sql = execute_sql
        self.reserve_session = reserve_session
        self.publish_mqtt = publish_mqtt
        self.normalize_text = normalize_text
        self.command_topics = command_topics
        self.invalidate_snapshot = invalidate_snapshot
        self.invalidate_pilot = invalidate_pilot
        self.invalidate_weather_summary = invalidate_weather_summary
        self.invalidate_context = invalidate_context
        self.context_meta = context_meta
        self.ensure_pilot_schema = ensure_pilot_schema
        self.to_float = to_float
        self.to_int = to_int
        self.manual_max_minutes = manual_max_minutes
        self.cached_api_payload = cached_api_payload or (lambda key, ttl, builder: builder())
        self.api_cache_get = api_cache_get
        self.api_cache_set = api_cache_set
        self.api_cache_delete_prefix = api_cache_delete_prefix
        self.mqtt_snapshot = mqtt_snapshot
        self.scheduler_config = scheduler_config
        self.v2_execution_engine_state = v2_execution_engine_state
        self.json_time = json_time
        self.stop_confirm_attempts = stop_confirm_attempts
        self.stop_reaction_delay_seconds = stop_reaction_delay_seconds
        self.stop_closed_delay_seconds = stop_closed_delay_seconds
        self.open_confirm_attempts = open_confirm_attempts
        self.open_reaction_delay_seconds = open_reaction_delay_seconds
        self.open_ready_delay_seconds = open_ready_delay_seconds
        self.openweather_api_key = openweather_api_key
        self.openweather_lat = openweather_lat
        self.openweather_lon = openweather_lon
        self.openweather_units = openweather_units
        self.openweather_lang = openweather_lang
        self.weather_poll_seconds = weather_poll_seconds
        self.absolute_humidity_g_m3 = absolute_humidity_g_m3
        self.process_binding_topic = process_binding_topic
        self.process_binding_payload = process_binding_payload
        self.pilot_cache_ttl = max(1.0, float(pilot_cache_ttl))
        self.weather_summary_cache_ttl = max(1.0, float(weather_summary_cache_ttl))
        self.daily_summary_days = int(daily_summary_days)
        self.daily_summary_refresh_sec = max(1.0, float(daily_summary_refresh_sec))
        self.snapshot_ttl = max(1.0, float(snapshot_ttl))
        self.control_allowed = control_allowed or (lambda: True)
        self.capability_allowed = capability_allowed or (lambda capability: self.control_allowed())
        self.active_season_profile = active_season_profile or (lambda: {"profile": "summer", "settings": {}})
        self.valve_tele_max_age_seconds = float(valve_tele_max_age_seconds)
        self.valve_status_max_age_seconds = float(valve_status_max_age_seconds)
        self.nano_online_max_age_seconds = float(nano_online_max_age_seconds)
        if any(not math.isfinite(age) or age <= 0 for age in (
            self.valve_tele_max_age_seconds, self.valve_status_max_age_seconds, self.nano_online_max_age_seconds,
        )):
            raise ValueError("valve telemetry max ages must be finite and positive")
        self._read_cache = ReadModelCache()
        self._summary_schema_ready = False

        self._summary_schema_lock = threading.Lock()
        self._daily_summary_refresh = {"next_at": 0.0}
        self._daily_summary_lock = threading.Lock()
        # Process-local command ordering only; durable session admission is HC-04.
        self._valve_publish_lock = threading.RLock()
        self._valve_stop_lock = threading.Lock()
        self._valve_intent_lock = threading.Lock()
        self._valve_stop_generation = 0
        self._valve_stops_pending = 0
        if any(not math.isfinite(float(value)) or float(value) <= 0 for value in (start_recovery_grace_seconds, recovery_retry_seconds)):
            raise ValueError("recovery delays must be finite and positive")
        if type(recovery_max_attempts) is not int or not 1 <= recovery_max_attempts <= 100:
            raise ValueError("recovery max attempts must be an integer between 1 and 100")
        self.session_recovery = IrrigationSessionRecovery(
            self, max(float(start_recovery_grace_seconds), max(1, self.open_confirm_attempts) * max(0, self.open_ready_delay_seconds, self.open_reaction_delay_seconds) + 30),
            float(recovery_retry_seconds), recovery_max_attempts,
        )

    @staticmethod
    def filter_isolated_tank_level_spikes(rows, threshold_percent: float = 20.0, neighbor_tolerance_percent: float = 8.0, max_gap_minutes: float = 20.0):
        cleaned = [dict(row) for row in (rows or [])]
        filtered = 0

        def level(row):
            value = row.get("level_percent") if isinstance(row, dict) else None
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def timestamp(row):
            value = row.get("ts") if isinstance(row, dict) else None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return None
            return None

        def minutes_between(first, second):
            first_ts = timestamp(first)
            second_ts = timestamp(second)
            if first_ts is None or second_ts is None:
                return 0
            return abs((second_ts - first_ts).total_seconds()) / 60.0

        for index in range(1, len(cleaned) - 1):
            previous_value = level(cleaned[index - 1])
            current_value = level(cleaned[index])
            next_value = level(cleaned[index + 1])
            if previous_value is None or current_value is None or next_value is None:
                continue
            if minutes_between(cleaned[index - 1], cleaned[index]) > max_gap_minutes:
                continue
            if minutes_between(cleaned[index], cleaned[index + 1]) > max_gap_minutes:
                continue
            if abs(previous_value - next_value) > neighbor_tolerance_percent:
                continue
            if current_value - previous_value < threshold_percent or current_value - next_value < threshold_percent:
                continue
            cleaned[index]["level_percent_raw"] = cleaned[index].get("level_percent")
            cleaned[index]["level_percent"] = None
            filtered += 1

        return cleaned, filtered

    def invalidate_snapshot_cache(self):
        self._read_cache.invalidate("snapshot")

    def invalidate_pilot_cache(self):
        self._read_cache.invalidate("pilot")

    def invalidate_weather_summary_cache(self):
        self._read_cache.invalidate("weather")

    def invalidate_pilot_inputs(self):
        with self._read_cache.condition:
            self.invalidate_pilot_cache()
            self.invalidate_weather_summary_cache()

    def ensure_summary_schema(self):
        if self._summary_schema_ready:
            return
        with self._summary_schema_lock:
            if self._summary_schema_ready:
                return
            check_runtime_schema(self.execute_sql, "summaries")
            self._summary_schema_ready = True

    def refresh_daily_summaries(self, force: bool = False):
        self.ensure_summary_schema()
        # Only the summary worker calls this; readers never refresh or write.
        if not self._daily_summary_lock.acquire(blocking=False):
            return False
        try:
            if not force and self._daily_summary_refresh["next_at"] > time.monotonic():
                return False
            days = max(14, self.daily_summary_days)
            self.execute_sql(f"""
            insert into hc.irrigation_daily_energy_summary (
              day, current_samples, avg_current_a, max_current_a, measured_hours,
              active_minutes, amp_hours, voltage_samples, avg_voltage_v, watt_hours, refreshed_at
            )
            select day, current_samples, avg_current_a, max_current_a, measured_hours,
              active_minutes, amp_hours, voltage_samples, avg_voltage_v, watt_hours, now()
            from ({bounded_daily_query("irrigation_daily_energy", days)}) as daily
            where day >= current_date - ({days}::int - 1)
            on conflict (day) do update set
              current_samples = excluded.current_samples,
              avg_current_a = excluded.avg_current_a,
              max_current_a = excluded.max_current_a,
              measured_hours = excluded.measured_hours,
              active_minutes = excluded.active_minutes,
              amp_hours = excluded.amp_hours,
              voltage_samples = excluded.voltage_samples,
              avg_voltage_v = excluded.avg_voltage_v,
              watt_hours = excluded.watt_hours,
              refreshed_at = now();

            insert into hc.irrigation_pump_daily_summary (
              day, pump_running_minutes, measured_hours, state_samples, refreshed_at
            )
            select day, pump_running_minutes, measured_hours, state_samples, now()
            from ({bounded_daily_query("irrigation_pump_daily", days)}) as daily
            where day >= current_date - ({days}::int - 1)
            on conflict (day) do update set
              pump_running_minutes = excluded.pump_running_minutes,
              measured_hours = excluded.measured_hours,
              state_samples = excluded.state_samples,
              refreshed_at = now();

            insert into hc.irrigation_solar_daily_summary (
              day, avg_battery_voltage_v, min_battery_voltage_v, max_battery_voltage_v,
              avg_charge_current_a, max_charge_current_a, avg_pv_voltage_v, max_pv_voltage_v,
              avg_pv_current_a, max_pv_current_a, avg_solar_controller_temp_c,
              max_solar_controller_temp_c, samples, charge_amp_hours, measured_hours, refreshed_at
            )
            select day, avg_battery_voltage_v, min_battery_voltage_v, max_battery_voltage_v,
              avg_charge_current_a, max_charge_current_a, avg_pv_voltage_v, max_pv_voltage_v,
              avg_pv_current_a, max_pv_current_a, avg_solar_controller_temp_c,
              max_solar_controller_temp_c, samples, charge_amp_hours, measured_hours, now()
            from ({bounded_daily_query("irrigation_solar_daily", days)}) as daily
            where day >= current_date - ({days}::int - 1)
            on conflict (day) do update set
              avg_battery_voltage_v = excluded.avg_battery_voltage_v,
              min_battery_voltage_v = excluded.min_battery_voltage_v,
              max_battery_voltage_v = excluded.max_battery_voltage_v,
              avg_charge_current_a = excluded.avg_charge_current_a,
              max_charge_current_a = excluded.max_charge_current_a,
              avg_pv_voltage_v = excluded.avg_pv_voltage_v,
              max_pv_voltage_v = excluded.max_pv_voltage_v,
              avg_pv_current_a = excluded.avg_pv_current_a,
              max_pv_current_a = excluded.max_pv_current_a,
              avg_solar_controller_temp_c = excluded.avg_solar_controller_temp_c,
              max_solar_controller_temp_c = excluded.max_solar_controller_temp_c,
              samples = excluded.samples,
              charge_amp_hours = excluded.charge_amp_hours,
              measured_hours = excluded.measured_hours,
              refreshed_at = now();

            insert into hc.irrigation_tank_daily_summary (
              day, avg_level_percent, min_level_percent, max_level_percent, avg_depth_m, refreshed_at
            )
            select day, avg_level_percent, min_level_percent, max_level_percent, avg_depth_m, now()
            from ({bounded_daily_query("irrigation_tank_daily", days)}) as daily
            where day >= current_date - ({days}::int - 1)
            on conflict (day) do update set
              avg_level_percent = excluded.avg_level_percent,
              min_level_percent = excluded.min_level_percent,
              max_level_percent = excluded.max_level_percent,
              avg_depth_m = excluded.avg_depth_m,
              refreshed_at = now();

            insert into hc.irrigation_controller_temp_daily_summary (
              day, avg_controller_temp_c, min_controller_temp_c, max_controller_temp_c, samples, refreshed_at
            )
            select day, avg_controller_temp_c, min_controller_temp_c, max_controller_temp_c, samples, now()
            from ({bounded_daily_query("irrigation_controller_temp_daily", days)}) as daily
            where day >= current_date - ({days}::int - 1)
            on conflict (day) do update set
              avg_controller_temp_c = excluded.avg_controller_temp_c,
              min_controller_temp_c = excluded.min_controller_temp_c,
              max_controller_temp_c = excluded.max_controller_temp_c,
              samples = excluded.samples,
              refreshed_at = now();

            delete from hc.irrigation_daily_energy_summary where day < current_date - ({days}::int - 1);
            delete from hc.irrigation_pump_daily_summary where day < current_date - ({days}::int - 1);
            delete from hc.irrigation_solar_daily_summary where day < current_date - ({days}::int - 1);
            delete from hc.irrigation_tank_daily_summary where day < current_date - ({days}::int - 1);
            delete from hc.irrigation_controller_temp_daily_summary where day < current_date - ({days}::int - 1);
            """)
            self._daily_summary_refresh["next_at"] = time.monotonic() + self.daily_summary_refresh_sec
            self.invalidate_snapshot()
            self.api_cache_delete_prefix("irrigation_statistics")
            return True
        finally:
            self._daily_summary_lock.release()

    def running_session(self):
        return self.fetch_one(
            """
            select *
            from hc.irrigation_manual_session
            where status in ('running', 'starting', 'stop_failed')
            order by (status = 'stop_failed') desc, started_at desc
            limit 1
            """
        )

    def manual_valve_scheduler_guard(self):
        row = self.fetch_one(
            """
            select s.ts, s.v_text
            from hc.entity_state s
            join hc.entity e on e.id = s.entity_id
            where e.topic_base = 'homecontrol/tele/irrigation/esp-irrigation-1'
              and s.key = 'manual_valve_state'
            order by s.ts desc
            limit 1
            """
        )
        state = self.normalize_text(row["v_text"] if row else "", "UNKNOWN").upper()
        blocked = any(part in state for part in ("OPEN", "OPENING", "BETWEEN", "MOVING"))
        if "CLOSED" in state:
            blocked = False
        return {
            "blocked": blocked,
            "state": state,
            "ts": row["ts"] if row else None,
        }

    def fetch_schedules(self):
        return self.fetch_all(
            """
            with schedule_state as (
              select
                *,
                day_of_week = extract(isodow from now())::int - 1 as is_today,
                is_active
                  and day_of_week = extract(isodow from now())::int - 1
                  and localtime >= start_time
                  and localtime < stop_time
                  and (last_started_on is distinct from current_date) as should_run_now,
                is_active
                  and day_of_week = extract(isodow from now())::int - 1
                  and localtime >= stop_time
                  and last_started_on = current_date as is_done_today
              from hc.irrigation_schedule
            )
            select
              id,
              day_of_week,
              label,
              to_char(start_time, 'HH24:MI') as start_time,
              to_char(stop_time, 'HH24:MI') as stop_time,
              is_active,
              is_today,
              should_run_now,
              is_done_today,
              case
                when should_run_now then 'due_now'
                when is_active and is_today and localtime >= start_time and localtime < stop_time and last_started_on = current_date then 'attempted_today'
                when is_done_today then 'done_today'
                when is_active and is_today then 'armed_today'
                when is_active then 'armed'
                else 'disabled'
              end as schedule_status,
              last_started_on,
              last_stopped_on,
              updated_at,
              round(extract(epoch from (stop_time - start_time)) / 60)::int as duration_minutes,
              row_number() over (partition by day_of_week order by start_time, id)::int as window_index,
              count(*) over (partition by day_of_week)::int as day_window_count,
              count(*) over (partition by day_of_week) > 1 as can_delete
            from schedule_state
            order by day_of_week, start_time, id
            """
        )

    def fetch_schedule(self, schedule_id: int):
        return self.fetch_one(
            """
            select *
            from (
              select
                id,
                day_of_week,
                label,
                to_char(start_time, 'HH24:MI') as start_time,
                to_char(stop_time, 'HH24:MI') as stop_time,
                is_active,
                day_of_week = extract(isodow from now())::int - 1 as is_today,
                is_active
                  and day_of_week = extract(isodow from now())::int - 1
                  and localtime >= start_time
                  and localtime < stop_time
                  and (last_started_on is distinct from current_date) as should_run_now,
                is_active
                  and day_of_week = extract(isodow from now())::int - 1
                  and localtime >= stop_time
                  and last_started_on = current_date as is_done_today,
                case
                  when is_active
                    and day_of_week = extract(isodow from now())::int - 1
                    and localtime >= start_time
                    and localtime < stop_time
                    and (last_started_on is distinct from current_date) then 'due_now'
                  when is_active
                    and day_of_week = extract(isodow from now())::int - 1
                    and localtime >= start_time
                    and localtime < stop_time
                    and last_started_on = current_date then 'attempted_today'
                  when is_active
                    and day_of_week = extract(isodow from now())::int - 1
                    and localtime >= stop_time
                    and last_started_on = current_date then 'done_today'
                  when is_active and day_of_week = extract(isodow from now())::int - 1 then 'armed_today'
                  when is_active then 'armed'
                  else 'disabled'
                end as schedule_status,
                last_started_on,
                last_stopped_on,
                updated_at,
                round(extract(epoch from (stop_time - start_time)) / 60)::int as duration_minutes,
                row_number() over (partition by day_of_week order by start_time, id)::int as window_index,
                count(*) over (partition by day_of_week)::int as day_window_count,
                count(*) over (partition by day_of_week) > 1 as can_delete
              from hc.irrigation_schedule
            ) schedules
            where id = %s
            """,
            (schedule_id,),
        )

    def validate_schedule_time(self, value: Any, field: str) -> str:
        return validate_schedule_time(value, field, self.normalize_text)

    def stop_payload(self, reason: str) -> Dict[str, Any]:
        return {"cmd": "set", "value": "close", "reason": reason}

    def _text_upper(self, value: Any) -> str:
        return text_upper(value)

    def live_valve_state(self, after_monotonic: Optional[float] = None):
        live = self.mqtt_snapshot()
        topics = live.get("topics") or {}
        now = time.monotonic()
        candidates = []
        sources = {}

        def finite_number(value):
            try:
                number = float(value) if value is not None and not isinstance(value, bool) else None
            except (TypeError, ValueError, OverflowError):
                return None
            return number if number is not None and math.isfinite(number) else None

        for name, age_key, max_age in (
            ("pump_metrics", "last_tele_sec_ago", self.valve_tele_max_age_seconds),
            ("esp_nano_status", "last_status_sec_ago", self.valve_status_max_age_seconds),
        ):
            item = topics.get(name) or {}
            payload = item.get("json")
            received = finite_number(item.get("received_monotonic"))
            timestamp = finite_number(item.get("timestamp"))
            receive_age = now - received if received is not None else None
            source_age = finite_number(payload.get(age_key)) if isinstance(payload, dict) else None
            age_known = source_age is not None and source_age >= 0 and receive_age is not None and receive_age >= 0
            sample_age = source_age + receive_age if age_known else None
            sample_time = received - source_age if age_known else None
            sample_time_lower = sample_time - NANO_SAMPLE_AGE_RESOLUTION_SECONDS if age_known else None
            reason = None
            if not item:
                reason = "not_available"
            elif not isinstance(payload, dict):
                reason = "invalid_payload"
            elif live.get("mqtt_connected") is not True:
                reason = "mqtt_disconnected"
            elif item.get("retain") is not False:
                reason = "retained_or_unknown"
            elif not live.get("connection_generation") or item.get("connection_generation") != live["connection_generation"]:
                reason = "previous_or_unknown_connection"
            elif not age_known or sample_age > max_age:
                reason = "stale_or_unknown_sample"
            elif timestamp is None:
                reason = "unknown_receipt_time"
            fresh = reason is None if item else None
            if reason is None and after_monotonic is not None and sample_time_lower <= after_monotonic:
                reason = "sample_not_proven_after_command"
            evidence = {
                "source": name,
                "topic": item.get("topic"),
                "timestamp": timestamp,
                "received_monotonic": received,
                "receive_age_sec": receive_age,
                "source_age_key": age_key,
                "source_age_sec": source_age,
                "age_sec": sample_age,
                "sample_monotonic": sample_time,
                "sample_monotonic_lower_bound": sample_time_lower,
                "sample_timestamp_lower_bound": timestamp - source_age - NANO_SAMPLE_AGE_RESOLUTION_SECONDS if timestamp is not None and age_known else None,
                "max_age_sec": max_age,
                "present": bool(item),
                "fresh": fresh,
                "retain": item.get("retain"),
                "connection_generation": item.get("connection_generation"),
                "usable": reason is None,
                "rejected_reason": reason,
            }
            sources[name] = evidence
            if reason is None:
                candidates.append((payload, evidence))

        # UART liveness and STATUS/TELE sample ages are separate facts. Only the
        # current nano_status.online flag can establish Nano liveness; TELE cannot.
        status_item = topics.get("esp_nano_status") or {}
        status_payload = status_item.get("json")
        status_receipt = sources["esp_nano_status"]
        online = status_payload.get("online") if isinstance(status_payload, dict) else None
        online_receipt_valid = (
            live.get("mqtt_connected") is True
            and status_item.get("retain") is False
            and bool(live.get("connection_generation"))
            and status_item.get("connection_generation") == live.get("connection_generation")
            and status_receipt["timestamp"] is not None
            and status_receipt["receive_age_sec"] is not None
            and 0 <= status_receipt["receive_age_sec"] <= self.nano_online_max_age_seconds
        )
        nano_online = online if online_receipt_valid and isinstance(online, bool) else None
        if nano_online is not True:
            for _, evidence in candidates:
                evidence["usable"] = False
                evidence["rejected_reason"] = "nano_offline" if nano_online is False else "nano_online_unknown"
            candidates = []
        # A recent ESP republication must not make an older Nano sample win.
        candidates.sort(key=lambda candidate: candidate[1]["sample_monotonic"], reverse=True)
        observations = {}

        def field(key, default=None):
            for payload, evidence in candidates:
                if payload.get(key) is not None:
                    observations[key] = evidence
                    return payload[key]
            return default

        valve = self._text_upper(field("valve", ""))
        manual = self._text_upper(field("manual_valve", ""))
        valve_current = finite_number(field("valve_current"))
        return {
            "valve": valve,
            "manual_valve": manual,
            "valve_current_a": valve_current,
            "motor_open": valve in {"OPEN", "OPENING", "BETWEEN", "MOVING_OPEN"},
            "motor_fully_open": valve == "OPEN",
            "manual_open": manual in {"OPEN", "OPENING", "BETWEEN", "MOVING_OPEN"},
            "motor_closed": valve == "CLOSED",
            "manual_closed": manual == "CLOSED",
            "motor_closing": valve in {"CLOSED", "CLOSING", "MOVING_CLOSE", "CLOSE"},
            "mqtt_connected": live.get("mqtt_connected") is True,
            "nano_online": nano_online,
            "nano_online_observation": {
                "source": "esp_nano_status.online",
                "reported_value": online if isinstance(online, bool) else None,
                "timestamp": status_receipt["timestamp"],
                "receive_age_sec": status_receipt["receive_age_sec"],
                "max_age_sec": self.nano_online_max_age_seconds,
                "receipt_valid": online_receipt_valid,
            },
            "freshness_basis": "nano_sample_age_plus_mqtt_elapsed",
            "tele_fresh": sources["pump_metrics"]["fresh"],
            "status_fresh": sources["esp_nano_status"]["fresh"],
            "after_monotonic": after_monotonic,
            "sources": sources,
            "observations": observations,
        }

    def stop_reaction_seen(self, state: Dict[str, Any]) -> bool:
        return bool(
            state.get("motor_closed")
            or state.get("motor_closing")
            or reaction_current_active(self.to_float, state.get("valve_current_a"))
        )

    def open_reaction_seen(self, state: Dict[str, Any]) -> bool:
        return bool(
            state.get("motor_open")
            or reaction_current_active(self.to_float, state.get("valve_current_a"))
        )

    @contextmanager
    def _valve_stop_request(self):
        # Invalidate OPEN before waiting for an in-flight publication/other stop.
        with self._valve_intent_lock:
            self._valve_stop_generation += 1
            self._valve_stops_pending += 1
        try:
            with self._valve_stop_lock:
                yield
        finally:
            with self._valve_intent_lock:
                self._valve_stops_pending -= 1

    def _open_cancelled(self, generation):
        with self._valve_intent_lock:
            return self._valve_stops_pending > 0 or generation != self._valve_stop_generation

    def _open_request_generation(self):
        with self._valve_intent_lock:
            return -1 if self._valve_stops_pending else self._valve_stop_generation

    def _cancel_open_requests(self):
        with self._valve_intent_lock:
            self._valve_stop_generation += 1

    @staticmethod
    def _cancelled_open(details):
        return False, "open cancelled by stop request", {**details, "blocked_by": "stop_request"}

    def publish_open_with_confirmation(self, open_payload: Dict[str, Any], *, stop_generation=None) -> Tuple[bool, str, Dict[str, Any]]:
        source = str(open_payload.get("source") or "")
        capability = "manual_watering" if source in {"homecontrol-admin", "admin", "manual"} else "scheduled_watering"
        if not self.capability_allowed(capability):
            return False, "irrigation controls disabled by active seasonal profile", {
                "attempts": [],
                "blocked_by": "season_profile",
            }
        self.session_recovery.initialize()
        if self.session_recovery.blocked:
            return False, "unresolved irrigation session requires recovery", {"attempts": [], "blocked_by": "session_recovery"}
        attempts = max(1, self.open_confirm_attempts)
        reaction_delay = max(0, self.open_reaction_delay_seconds)
        ready_delay = max(reaction_delay, self.open_ready_delay_seconds)
        details = {"attempts": []}
        generation = self._open_request_generation() if stop_generation is None else stop_generation

        for attempt in range(1, attempts + 1):
            with self._valve_publish_lock:
                if self._open_cancelled(generation):
                    return self._cancelled_open(details)
                command_started = time.monotonic()
                ok, message = self.publish_mqtt(self.command_topics()["valve"], open_payload)
            attempt_info = {
                "attempt": attempt,
                "command_started_monotonic": command_started,
                "publish_ok": ok,
                "publish_message": message,
            }
            if not ok:
                details["attempts"].append(attempt_info)
                print(f"[OPEN] attempt={attempt}/{attempts} publish failed message={message}", flush=True)
                continue

            if reaction_delay:
                time.sleep(reaction_delay)
            if self._open_cancelled(generation):
                details["attempts"].append(attempt_info)
                return self._cancelled_open(details)
            reaction_state = self.live_valve_state(after_monotonic=command_started)
            attempt_info["reaction_state"] = reaction_state
            if self._open_cancelled(generation):
                details["attempts"].append(attempt_info)
                return self._cancelled_open(details)
            if reaction_state["motor_fully_open"]:
                details["attempts"].append(attempt_info)
                return True, f"open confirmed on attempt {attempt}", details

            reacted = self.open_reaction_seen(reaction_state)
            attempt_info["reaction_seen"] = reacted
            print(
                f"[OPEN] attempt={attempt}/{attempts} reaction_seen={reacted} "
                f"valve={reaction_state['valve']} current={reaction_state['valve_current_a']}",
                flush=True,
            )

            remaining_delay = ready_delay - reaction_delay
            if remaining_delay > 0:
                time.sleep(remaining_delay)
            if self._open_cancelled(generation):
                details["attempts"].append(attempt_info)
                return self._cancelled_open(details)
            open_state = self.live_valve_state(after_monotonic=command_started)
            attempt_info["open_state"] = open_state
            details["attempts"].append(attempt_info)
            if self._open_cancelled(generation):
                return self._cancelled_open(details)

            if open_state["motor_fully_open"]:
                return True, f"open confirmed on attempt {attempt}", details

            print(
                f"[OPEN] attempt={attempt}/{attempts} not open "
                f"valve={open_state['valve']} current={open_state['valve_current_a']}",
                flush=True,
            )

        last = details["attempts"][-1] if details["attempts"] else {}
        last_state = last.get("open_state") or last.get("reaction_state") or {}
        last_valve = last_state.get("valve") or "UNKNOWN"
        return False, f"open confirmation failed after {attempts} attempts; valve={last_valve}", details

    def publish_stop_with_confirmation(self, reason: str, *, attempt_limit=None) -> Tuple[bool, str, Dict[str, Any]]:
        with self._valve_stop_request():
            return self._publish_stop_with_confirmation(reason, attempt_limit=attempt_limit)

    def _publish_stop_with_confirmation(self, reason: str, *, attempt_limit=None) -> Tuple[bool, str, Dict[str, Any]]:
        stop_payload = self.stop_payload(reason)
        attempts = max(1, self.stop_confirm_attempts)
        if attempt_limit is not None:
            attempts = min(attempts, max(1, int(attempt_limit)))
        reaction_delay = max(0, self.stop_reaction_delay_seconds)
        closed_delay = max(reaction_delay, self.stop_closed_delay_seconds)
        details = {"attempts": []}

        for attempt in range(1, attempts + 1):
            with self._valve_publish_lock:
                command_started = time.monotonic()
                ok, message = self.publish_mqtt(self.command_topics()["valve"], stop_payload)
            attempt_info = {
                "attempt": attempt,
                "command_started_monotonic": command_started,
                "publish_ok": ok,
                "publish_message": message,
            }
            if not ok:
                details["attempts"].append(attempt_info)
                print(f"[STOP] attempt={attempt}/{attempts} publish failed message={message}", flush=True)
                continue

            if reaction_delay:
                time.sleep(reaction_delay)
            reaction_state = self.live_valve_state(after_monotonic=command_started)
            attempt_info["reaction_state"] = reaction_state
            if reaction_state["motor_closed"]:
                details["attempts"].append(attempt_info)
                return True, f"closed confirmed on attempt {attempt}", details

            reacted = self.stop_reaction_seen(reaction_state)
            attempt_info["reaction_seen"] = reacted
            print(
                f"[STOP] attempt={attempt}/{attempts} reaction_seen={reacted} "
                f"valve={reaction_state['valve']} current={reaction_state['valve_current_a']}",
                flush=True,
            )

            remaining_delay = closed_delay - reaction_delay
            if remaining_delay > 0:
                time.sleep(remaining_delay)
            closed_state = self.live_valve_state(after_monotonic=command_started)
            attempt_info["closed_state"] = closed_state
            details["attempts"].append(attempt_info)

            if closed_state["motor_closed"]:
                return True, f"closed confirmed on attempt {attempt}", details

            print(
                f"[STOP] attempt={attempt}/{attempts} not closed "
                f"valve={closed_state['valve']} current={closed_state['valve_current_a']}",
                flush=True,
            )

        last = details["attempts"][-1] if details["attempts"] else {}
        last_state = last.get("closed_state") or last.get("reaction_state") or {}
        last_valve = last_state.get("valve") or "UNKNOWN"
        return False, f"stop confirmation failed after {attempts} attempts; valve={last_valve}", details

    def stop_manual_session(self, session_id: int, reason: str):
        stop_payload = self.stop_payload(reason)
        ok, message, details = self.publish_stop_with_confirmation(reason)
        status = ("stopped" if reason == "manual_stop" else "auto_stopped") if ok else "stop_failed"
        stored_payload = {
            **stop_payload,
            "confirmation": {
                "ok": ok,
                "message": message,
                **details,
            },
        }
        row = self.execute_one(
            """
            update hc.irrigation_manual_session
            set stopped_at = now(),
                status = %s,
                stop_payload = coalesce(stop_payload, '{}'::jsonb) || %s::jsonb || jsonb_build_object(
                  'recovery', jsonb_build_object('origin_status', status) || coalesce(stop_payload -> 'recovery', '{}'::jsonb)
                    || jsonb_build_object('state', case when %s then 'confirmed' else 'pending' end)),
                error = %s
            where id = %s and status in ('running', 'starting', 'stop_failed')
              and started_by <> 'physical_manual'
            returning *
            """,
            (status, json.dumps(stored_payload), ok, None if ok else message, session_id),
        )
        if not ok and row and row.get("started_by") == "pilot":
            payload = row.get("start_payload") or {}
            schedule_id = payload.get("schedule_id") if isinstance(payload, dict) else None
            if schedule_id:
                self.execute_one(
                    """
                    update hc.irrigation_pilot_decision
                    set executed = false,
                        execution_status = 'stop_failed'
                    where schedule_id = %s
                      and execution_status in ('command_sent', 'command_confirmed')
                      and timestamp >= %s - interval '2 minutes'
                    returning id
                    """,
                    (schedule_id, row["started_at"]),
                )
        if ok and row and row.get("started_by") == "pilot" and status == "auto_stopped":
            payload = row.get("start_payload") or {}
            schedule_id = payload.get("schedule_id") if isinstance(payload, dict) else None
            if schedule_id:
                self.execute_one(
                    """
                    update hc.irrigation_pilot_decision
                    set executed = true,
                        execution_status = 'completed'
                    where schedule_id = %s
                      and execution_status in ('command_sent', 'command_confirmed')
                      and timestamp >= %s - interval '2 minutes'
                    returning id
                    """,
                    (schedule_id, row["started_at"]),
                )
        return ok, message, row

    def stop_overdue_sessions(self):
        rows = self.fetch_all(
            """
            select id
            from hc.irrigation_manual_session
            where status = 'running'
              and started_by <> 'physical_manual'
              and least(requested_stop_at, safety_stop_at) <= now()
            order by id
            """
        )
        for row in rows:
            self.stop_manual_session(int(row["id"]), "auto_timeout")

    def fail_sessions_without_physical_watering(self):
        state = self.live_valve_state()
        if not (state["motor_closed"] and state["manual_closed"]):
            return
        rows = self.fetch_all(
            """
            select id, started_by, started_at, start_payload
            from hc.irrigation_manual_session
            where status = 'running'
              and started_by <> 'physical_manual'
              and started_at <= now() - interval '90 seconds'
            order by id
            """
        )
        for row in rows:
            # A recent observation must also postdate this session's start.
            started_at = row.get("started_at")
            if not isinstance(started_at, datetime):
                continue
            if any(
                (state["observations"].get(key) or {}).get("sample_timestamp_lower_bound", 0) <= started_at.timestamp()
                for key in ("valve", "manual_valve")
            ):
                continue
            error = "session command sent but motorized and manual valves are both reported CLOSED"
            self.execute_one(
                """
                update hc.irrigation_manual_session
                set status = 'failed_no_watering',
                    stopped_at = now(),
                    error = %s
                where id = %s and status = 'running'
                returning id
                """,
                (error, row["id"]),
            )
            payload = row.get("start_payload") or {}
            schedule_id = payload.get("schedule_id") if isinstance(payload, dict) else None
            if schedule_id:
                self.execute_one(
                    """
                    update hc.irrigation_pilot_decision
                    set executed = false,
                        execution_status = 'no_physical_watering'
                    where schedule_id = %s
                      and execution_status in ('command_sent', 'command_confirmed')
                      and timestamp >= %s - interval '2 minutes'
                    returning id
                    """,
                    (schedule_id, row["started_at"]),
                )
            print(f"[SAFETY] session id={row['id']} failed_no_watering valve={state['valve']} manual={state['manual_valve']}", flush=True)

    def _reserve_start(self, minutes, started_by, start_payload, schedule_id=None):
        if self.reserve_session is None:
            raise RuntimeError('atomic irrigation session admission is not configured')
        return self.reserve_session(
            minutes=minutes, safety_minutes=self.manual_max_minutes,
            started_by=started_by, start_payload=start_payload, schedule_id=schedule_id,
        )

    def start_manual(self, data: Dict[str, Any]):
        stop_generation = self._open_request_generation()
        if not self.capability_allowed("manual_watering"):
            return {
                "ok": False,
                "error": "irrigation controls disabled by active seasonal profile",
                "blocked_by": "season_profile",
            }, 423
        minutes = int(data.get("duration_minutes") or 20)
        minutes = max(1, min(minutes, self.manual_max_minutes))
        started_by = data.get("started_by") or "admin"
        if started_by == "physical_manual":
            return {"ok": False, "error": "physical_manual is reserved for physical valve observations"}, 400
        self.session_recovery.initialize()
        running = self.running_session()
        if running:
            return {
                "ok": False,
                "error": "irrigation session already running",
                "session": running,
            }, 409
        if self.session_recovery.blocked:
            return {"ok": False, "error": "session recovery has not cleared the start interlock", "blocked_by": "session_recovery"}, 409

        valve_payload = {"cmd": "set", "value": "open", "source": "homecontrol-admin", "duration_minutes": minutes}
        reservation = self._reserve_start(minutes, started_by, valve_payload)
        row = reservation.get("session")
        if not row:
            return {"ok": False, "error": "irrigation session admission rejected",
                    "blocked_by": reservation.get("blocked_by"),
                    "session": reservation.get("blocking_session")}, 409
        valve_ok, valve_message, valve_details = self.publish_open_with_confirmation(valve_payload, stop_generation=stop_generation)
        confirmed_payload = {
            **valve_payload,
            "confirmation": {
                "ok": valve_ok,
                "message": valve_message,
                **valve_details,
            },
        }
        if valve_ok:
            row = self.execute_one(
                """
                update hc.irrigation_manual_session
                set status = 'running',
                    start_payload = %s::jsonb
                where id = %s and status = 'starting'
                returning *
                """,
                (json.dumps(confirmed_payload), row["id"]),
            )
            self.invalidate_snapshot()
            if not row:
                return {"ok": False, "error": "start reconciled or stopped before confirmation could commit"}, 409
            return {
                "ok": True,
                "session": row,
                "duration_minutes": minutes,
                "message": valve_message,
                "context": self.context_meta("irrigation"),
            }, 200

        if row:
            self.session_recovery.blocked = True
            self.execute_one(
                """
                update hc.irrigation_manual_session
                set status = 'stop_failed',
                    stopped_at = null,
                    start_payload = %s::jsonb,
                    error = %s,
                    stop_payload = coalesce(stop_payload, '{}'::jsonb) || jsonb_build_object(
                      'recovery', jsonb_build_object('origin_status', 'starting', 'state', 'pending')
                        || coalesce(stop_payload -> 'recovery', '{}'::jsonb))
                where id = %s and status = 'starting'
                returning id
                """,
                (json.dumps(confirmed_payload), f"valve={valve_message}", row["id"]),
            )
        self.invalidate_snapshot()
        return {"ok": False, "error": f"valve={valve_message}", "confirmation": valve_details}, 502

    def command(self, data: Dict[str, Any]):
        name = self.normalize_text(data.get("name"))
        commands = {
            "valve_close": ("valve", {"cmd": "set", "value": "close"}),
            "valve_stop": ("valve", {"cmd": "set", "value": "stop"}),
            "valve_home": ("valve", {"cmd": "home"}),
            "valve_status": ("valve", {"cmd": "status"}),
            "valve_cal_zero": ("valve", {"cmd": "cal_zero"}),
            "fault_reset": ("system", {"cmd": "reset_fault"}),
            "diag_now": ("system", {"cmd": "diag_now"}),
            "nano_status_now": ("system", {"cmd": "nano_status_now"}),
            "ping": ("system", {"cmd": "ping"}),
            "mode_auto": ("mode", {"cmd": "set", "value": "auto"}),
            "mode_manual": ("mode", {"cmd": "set", "value": "manual"}),
            "pump_on": ("pump", {"cmd": "set", "value": "on"}),
            "pump_off": ("pump", {"cmd": "set", "value": "off"}),
            "nano_get": ("config", {"cmd": "nano_get"}),
            "nano_save": ("config", {"cmd": "nano_save"}),
            "nano_load": ("config", {"cmd": "nano_load"}),
            "nano_defaults": ("config", {"cmd": "nano_reset_defaults"}),
        }
        if name not in commands:
            return {"ok": False, "error": "unknown command"}, 400
        if name in {"pump_on", "mode_auto", "mode_manual", "valve_home"} and not self.capability_allowed("maintenance_controls"):
            return {
                "ok": False,
                "error": "irrigation controls disabled by active seasonal profile",
                "blocked_by": "season_profile",
            }, 423
        if name == "valve_close":
            ok, message, details = self.publish_stop_with_confirmation("manual_command")
            self.invalidate_snapshot()
            return {
                "ok": ok,
                "message": message,
                "confirmation": details,
                "context": self.context_meta("irrigation"),
            }, 200 if ok else 502

        topic_key, payload = commands[name]
        if name == "valve_stop":
            with self._valve_stop_request(), self._valve_publish_lock:
                ok, message = self.publish_mqtt(self.command_topics()[topic_key], payload)
        else:
            ok, message = self.publish_mqtt(self.command_topics()[topic_key], payload)
        self.invalidate_snapshot()
        return {"ok": ok, "message": message, "context": self.context_meta("irrigation")}, 200 if ok else 502

    def nano_config(self, data: Dict[str, Any]):
        key = self.normalize_text(data.get("key"))
        value = self.normalize_text(data.get("value"))
        if not key:
            return {"ok": False, "error": "missing key"}, 400
        ok, message = self.publish_mqtt(self.command_topics()["config"], {"cmd": "nano_set", "key": key, "value": value})
        self.invalidate_snapshot()
        return {"ok": ok, "message": message, "context": self.context_meta("irrigation")}, 200 if ok else 502

    def fetch_solar_pump_config(self):
        self.ensure_pilot_schema()
        return self.fetch_one("select * from hc.irrigation_solar_pump_config where id = 1")

    def update_solar_pump_config(self, data: Dict[str, Any]):
        self.ensure_pilot_schema()
        row = self.execute_one(
            """
            update hc.irrigation_solar_pump_config
            set enabled = %s,
                batch_minutes = %s,
                cooldown_minutes = %s,
                min_charge_current_a = %s,
                min_pv_voltage_v = %s,
                min_battery_voltage_v = %s,
                stop_battery_voltage_v = %s,
                max_telemetry_age_seconds = %s,
                updated_at = now()
            where id = 1
            returning *
            """,
            (
                bool(data.get("enabled", False)),
                max(1, min(self.to_int(data.get("batch_minutes"), 5), 60)),
                max(0, min(self.to_int(data.get("cooldown_minutes"), 10), 240)),
                self.to_float(data.get("max_charge_current_a"), data.get("min_charge_current_a", 0.8)),
                self.to_float(data.get("min_pv_voltage_v"), 15),
                self.to_float(data.get("min_battery_voltage_v"), 12.2),
                self.to_float(data.get("stop_battery_voltage_v"), 11.8),
                max(10, min(self.to_int(data.get("max_telemetry_age_seconds"), 180), 3600)),
            ),
        )
        self.api_cache_delete_prefix("irrigation_statistics")
        self.invalidate_snapshot()
        self.invalidate_context("irrigation", "irrigation_statistics")
        return {"ok": True, "config": row, "context": self.context_meta("irrigation", "irrigation_statistics")}, 200

    def _live_topic_payload(self, name: str):
        item = (self.mqtt_snapshot().get("topics") or {}).get(name) or {}
        payload = item.get("json") if isinstance(item, dict) else None
        return payload if isinstance(payload, dict) else {}, item if isinstance(item, dict) else {}

    def pump_current_live_snapshot(self):
        metrics, metrics_item = self._live_topic_payload("pump_metrics")
        current_value = metrics.get("current_a") if metrics.get("current_a") is not None else metrics.get("pump_current_a")
        current = self.to_float(current_value) if current_value is not None else None
        voltage_value = metrics.get("voltage_12v")
        temp_value = metrics.get("temp_c")
        age_value = metrics_item.get("age_sec") if metrics_item else None
        source_received_at = metrics_item.get("timestamp") if metrics_item else None
        sample_time = datetime.fromtimestamp(float(source_received_at)).astimezone() if source_received_at is not None else datetime.now().astimezone()
        return {
            "type": "irrigation_pump_current",
            "ok": current is not None,
            "ts": sample_time.isoformat(timespec="milliseconds"),
            "server_ts": time.time(),
            "source_received_at_epoch": self.to_float(source_received_at) if source_received_at is not None else None,
            "pump_current_a": current,
            "max_pump_current_a": current,
            "pump": self.to_int(metrics.get("pump"), 0) if metrics.get("pump") is not None else None,
            "voltage_12v": self.to_float(voltage_value) if voltage_value is not None else None,
            "temp_c": self.to_float(temp_value) if temp_value is not None else None,
            "valve": self.normalize_text(metrics.get("valve")),
            "manual_valve": self.normalize_text(metrics.get("manual_valve")),
            "age_sec": self.to_float(age_value) if age_value is not None else None,
            "topic": metrics_item.get("topic") if isinstance(metrics_item, dict) else None,
        }

    def solar_pump_live_snapshot(self):
        solar, solar_item = self._live_topic_payload("solar")
        nano, nano_item = self._live_topic_payload("esp_nano_status")
        metrics, metrics_item = self._live_topic_payload("pump_metrics")
        tank, tank_item = self._live_topic_payload("tank_level")

        def first_float(*values):
            for value in values:
                if value is None:
                    continue
                parsed = self.to_float(value)
                if parsed is not None:
                    return parsed
            return None

        def first_text(*values):
            for value in values:
                text = self.normalize_text(value)
                if text:
                    return text
            return ""

        def first_bool(*values):
            for value in values:
                if value is None:
                    continue
                if isinstance(value, bool):
                    return value
                text = str(value).strip().upper()
                if text in {"1", "ON", "TRUE", "HIGH", "ACTIVE", "YES"}:
                    return True
                if text in {"0", "OFF", "FALSE", "LOW", "INACTIVE", "NO"}:
                    return False
            return None

        pump_raw = first_text(metrics.get("pump"), nano.get("pump"), metrics.get("pump_running"), nano.get("pump_running")).upper()
        pump_running = pump_raw in {"1", "ON", "TRUE", "RUNNING", "FILLING"}
        mode = first_text(nano.get("mode"), nano.get("current_mode"), metrics.get("mode")).upper()
        low_signal = first_bool(nano.get("low"), tank.get("low"), metrics.get("low"), nano.get("low_signal"), tank.get("low_signal"))
        high_signal = first_bool(nano.get("high"), tank.get("high"), metrics.get("high"), nano.get("high_signal"), tank.get("high_signal"))
        battery_voltage = first_float(solar.get("battery_voltage"), solar.get("battery_voltage_v"), metrics.get("voltage_12v"))
        charge_current = first_float(solar.get("charge_current"), solar.get("charge_current_a"))
        pv_voltage = first_float(solar.get("pv_voltage"), solar.get("pv_voltage_v"))
        pv_current = first_float(solar.get("pv_current"), solar.get("pv_current_a"))
        ages = [
            self.to_float(solar_item.get("age_sec")) if solar_item else None,
            self.to_float(nano_item.get("age_sec")) if nano_item else None,
            self.to_float(metrics_item.get("age_sec")) if metrics_item else None,
            self.to_float(tank_item.get("age_sec")) if tank_item else None,
        ]
        age_sec = min([age for age in ages if age is not None], default=None)
        return {
            "mode": mode or None,
            "remote_mode": "REMOTE" in mode,
            "pump_running": pump_running,
            "low_signal": low_signal,
            "high_signal": high_signal,
            "tank_full_stop": low_signal is True and high_signal is True,
            "battery_voltage_v": battery_voltage,
            "charge_current_a": charge_current,
            "pv_voltage_v": pv_voltage,
            "pv_current_a": pv_current,
            "telemetry_age_sec": age_sec,
            "solar_age_sec": self.to_float(solar_item.get("age_sec")) if solar_item else None,
            "nano_age_sec": self.to_float(nano_item.get("age_sec")) if nano_item else None,
            "pump_age_sec": self.to_float(metrics_item.get("age_sec")) if metrics_item else None,
            "tank_age_sec": self.to_float(tank_item.get("age_sec")) if tank_item else None,
        }

    def solar_pump_completed_minutes_today(self):
        row = self.fetch_one(
            """
            select coalesce(sum(
              extract(epoch from (coalesce(stopped_at, now()) - started_at)) / 60.0
            ), 0) as minutes
            from hc.irrigation_solar_pump_run
            where started_at >= current_date
              and status in ('running', 'completed', 'stopped')
            """
        )
        return self.to_float(row.get("minutes"), 0) if row else 0

    def active_solar_pump_run(self):
        return self.fetch_one(
            """
            select *
            from hc.irrigation_solar_pump_run
            where status = 'running'
            order by started_at desc
            limit 1
            """
        )

    def solar_pump_config_payload(self, config: Dict[str, Any]):
        config = config or {}
        return {
            "enabled": bool(config.get("enabled")),
            "batch_minutes": self.to_int(config.get("batch_minutes"), 5),
            "cooldown_minutes": self.to_int(config.get("cooldown_minutes"), 10),
            "max_charge_current_a": self.to_float(config.get("min_charge_current_a"), 0.8),
            "min_pv_voltage_v": self.to_float(config.get("min_pv_voltage_v"), 15),
            "min_battery_voltage_v": self.to_float(config.get("min_battery_voltage_v"), 12.2),
            "stop_battery_voltage_v": self.to_float(config.get("stop_battery_voltage_v"), 11.8),
            "max_telemetry_age_seconds": self.to_int(config.get("max_telemetry_age_seconds"), 180),
            "updated_at": self.json_time(config.get("updated_at")),
        }

    def solar_pump_run_payload(self, row: Optional[Dict[str, Any]]):
        if not row:
            return None
        return {
            "id": row.get("id"),
            "started_at": self.json_time(row.get("started_at")),
            "planned_stop_at": self.json_time(row.get("planned_stop_at")),
            "stopped_at": self.json_time(row.get("stopped_at")),
            "status": row.get("status"),
            "error": row.get("error"),
        }

    def latest_solar_pump_runs(self, limit: int = 12):
        return self.fetch_all(
            f"""
            select
              *,
              round(extract(epoch from (coalesce(stopped_at, now()) - started_at)) / 60.0, 1) as duration_minutes,
              start_payload #>> '{{decision,reason}}' as decision_reason,
              start_payload #>> '{{decision,state}}' as decision_state,
              (start_payload #>> '{{decision,live,battery_voltage_v}}')::numeric as battery_voltage_v,
              (start_payload #>> '{{decision,live,charge_current_a}}')::numeric as charge_current_a,
              (start_payload #>> '{{decision,live,pv_voltage_v}}')::numeric as pv_voltage_v,
              (start_payload #>> '{{decision,live,pv_current_a}}')::numeric as pv_current_a,
              start_payload #>> '{{decision,live,mode}}' as nano_mode,
              (start_payload #>> '{{decision,live,remote_mode}}')::boolean as remote_mode,
              (start_payload #>> '{{decision,live,low_signal}}')::boolean as low_signal,
              (start_payload #>> '{{decision,live,high_signal}}')::boolean as high_signal,
              (start_payload #>> '{{decision,live,tank_full_stop}}')::boolean as tank_full_stop,
              (start_payload #>> '{{decision,live,telemetry_age_sec}}')::numeric as telemetry_age_sec
            from hc.irrigation_solar_pump_run
            order by started_at desc
            limit {max(1, min(int(limit), 100))}
            """
        )

    def evaluate_solar_pump_scheduler(self):
        self.ensure_pilot_schema()
        config = self.fetch_solar_pump_config() or {}
        config_payload = self.solar_pump_config_payload(config)
        live = self.solar_pump_live_snapshot()
        completed = self.solar_pump_completed_minutes_today()
        running = self.active_solar_pump_run()
        reasons = []
        state = "ready"

        if not config.get("enabled"):
            state = "disabled"
            reasons.append("Solar pump scheduler is disabled.")
        if running:
            state = "running"
            reasons.append("A solar pump batch is already running.")
        if live.get("pump_running") and not running:
            state = "waiting_pump"
            reasons.append("Pump is already running outside the solar scheduler.")
        if live.get("tank_full_stop"):
            if state == "ready":
                state = "waiting_tank_full"
            reasons.append("Tank L and H sensors are both active; pump must stay off.")
        age = live.get("telemetry_age_sec")
        max_age = self.to_float(config.get("max_telemetry_age_seconds"), 180) if config else 180
        if age is None or age > max_age:
            if state == "ready":
                state = "waiting_telemetry"
            reasons.append("Solar/Nano telemetry is missing or stale.")
        pv_voltage = live.get("pv_voltage_v")
        battery = live.get("battery_voltage_v")
        charge = live.get("charge_current_a")
        max_charge = self.to_float(config.get("min_charge_current_a"), 0.8)
        if charge is None:
            if state == "ready":
                state = "waiting_charge"
            reasons.append("Charge current telemetry is missing.")
        elif charge > max_charge:
            if state == "ready":
                state = "waiting_battery_full"
            reasons.append(f"Charge current is still above the full-battery threshold ({charge:.2f} A > {max_charge:.2f} A).")
        if pv_voltage is None or pv_voltage < self.to_float(config.get("min_pv_voltage_v"), 15):
            if state == "ready":
                state = "waiting_sun"
            reasons.append("PV voltage is below the sunny-window threshold.")
        if battery is None or battery < self.to_float(config.get("min_battery_voltage_v"), 12.2):
            if state == "ready":
                state = "waiting_battery"
            reasons.append("Battery voltage is below the start threshold.")
        latest = self.fetch_one(
            """
            select stopped_at
            from hc.irrigation_solar_pump_run
            where stopped_at is not null
            order by stopped_at desc
            limit 1
            """
        )
        if latest and latest.get("stopped_at") and config:
            cooldown = self.to_int(config.get("cooldown_minutes"), 10)
            cooldown_row = self.fetch_one(
                """
                select extract(epoch from (now() - %s::timestamptz)) / 60.0 as age_min
                """,
                (latest["stopped_at"],),
            )
            cooldown_age = self.to_float(cooldown_row.get("age_min")) if cooldown_row else None
            if cooldown_age is not None and cooldown_age < cooldown:
                if state == "ready":
                    state = "cooldown"
                reasons.append(f"Cooling down after the last pump run ({cooldown_age:.1f}/{cooldown} min).")

        can_start = bool(config and config.get("enabled") and not running and state == "ready")
        batch = self.to_int(config.get("batch_minutes"), 5) if config else 5
        decision = {
            "state": state,
            "can_start": can_start,
            "reason": " ".join(reasons) if reasons else "Sunny window is available; pump can run.",
            "completed_minutes_today": round(completed, 1),
            "next_batch_minutes": batch,
            "live": live,
            "config": config_payload,
            "active_run": self.solar_pump_run_payload(running),
        }
        return decision

    def start_solar_pump_batch(self, decision: Dict[str, Any]):
        if not self.capability_allowed("solar_pump_automation"):
            return False, "irrigation controls disabled by active seasonal profile"
        config = decision.get("config") or {}
        minutes = max(1, min(self.to_int(decision.get("next_batch_minutes"), 5), 60))
        payload = {
            "cmd": "set",
            "value": "on",
            "source": "solar_pump_scheduler",
            "duration_minutes": minutes,
            "reason": decision.get("reason"),
        }
        ok, message = self.publish_mqtt(self.command_topics()["pump"], payload)
        if not ok:
            return False, message
        self.execute_one(
            """
            insert into hc.irrigation_solar_pump_run (planned_stop_at, status, start_payload)
            values (now() + (%s::text || ' minutes')::interval, 'running', %s::jsonb)
            returning id
            """,
            (minutes, json.dumps({**payload, "decision": decision, "cooldown_minutes": config.get("cooldown_minutes")})),
        )
        self.api_cache_delete_prefix("irrigation_statistics")
        self.invalidate_context("irrigation", "irrigation_statistics")
        return True, message

    def stop_solar_pump_batch(self, run_id: int, reason: str):
        payload = {"cmd": "set", "value": "off", "source": "solar_pump_scheduler", "reason": reason}
        ok, message = self.publish_mqtt(self.command_topics()["pump"], payload)
        self.execute_one(
            """
            update hc.irrigation_solar_pump_run
            set status = %s,
                stopped_at = now(),
                stop_payload = %s::jsonb,
                error = %s
            where id = %s and status = 'running'
            returning id
            """,
            ("completed" if ok else "stop_failed", json.dumps({**payload, "message": message}), None if ok else message, run_id),
        )
        self.api_cache_delete_prefix("irrigation_statistics")
        self.invalidate_context("irrigation", "irrigation_statistics")
        return ok, message

    def solar_pump_scheduler_tick(self):
        self.ensure_pilot_schema()
        running = self.active_solar_pump_run()
        if running:
            live = self.solar_pump_live_snapshot()
            config = self.fetch_solar_pump_config()
            battery = live.get("battery_voltage_v")
            stop_battery = self.to_float(config.get("stop_battery_voltage_v"), 11.8) if config else 11.8
            if live.get("tank_full_stop"):
                ok, message = self.stop_solar_pump_batch(int(running["id"]), "tank_full")
                print(f"[SOLAR PUMP] tank-full stop run={running['id']} ok={ok} message={message}", flush=True)
            elif running.get("planned_stop_at") and running["planned_stop_at"] <= datetime.now(running["planned_stop_at"].tzinfo):
                ok, message = self.stop_solar_pump_batch(int(running["id"]), "batch_complete")
                print(f"[SOLAR PUMP] stop run={running['id']} ok={ok} message={message}", flush=True)
            elif battery is not None and battery < stop_battery:
                ok, message = self.stop_solar_pump_batch(int(running["id"]), "battery_low")
                print(f"[SOLAR PUMP] safety stop run={running['id']} ok={ok} message={message}", flush=True)
            return

        decision = self.evaluate_solar_pump_scheduler()
        if not decision.get("can_start"):
            return
        ok, message = self.start_solar_pump_batch(decision)
        print(f"[SOLAR PUMP] start ok={ok} message={message} duration={decision.get('next_batch_minutes')}", flush=True)

    def update_schedule(self, schedule_id: int, data: Dict[str, Any]):
        try:
            start_time = self.validate_schedule_time(data.get("start_time"), "start_time")
            stop_time = self.validate_schedule_time(data.get("stop_time"), "stop_time")
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}, 400
        if start_time >= stop_time:
            return {"ok": False, "error": "start_time must be before stop_time"}, 400

        is_active = bool(data.get("is_active"))
        row = self.execute_one(
            """
            update hc.irrigation_schedule
            set last_started_on = case
                  when day_of_week = extract(isodow from now())::int - 1
                    and (
                      start_time is distinct from %s::time
                      or stop_time is distinct from %s::time
                      or is_active is distinct from %s
                    )
                  then null
                  else last_started_on
                end,
                last_stopped_on = case
                  when day_of_week = extract(isodow from now())::int - 1
                    and (
                      start_time is distinct from %s::time
                      or stop_time is distinct from %s::time
                      or is_active is distinct from %s
                    )
                  then null
                  else last_stopped_on
                end,
                start_time = %s::time,
                stop_time = %s::time,
                is_active = %s,
                updated_at = now()
            where id = %s
            returning
              id,
              day_of_week,
              label,
              to_char(start_time, 'HH24:MI') as start_time,
              to_char(stop_time, 'HH24:MI') as stop_time,
              is_active,
              day_of_week = extract(isodow from now())::int - 1 as is_today,
              is_active
                and day_of_week = extract(isodow from now())::int - 1
                and localtime >= start_time
                and localtime < stop_time
                and (last_started_on is distinct from current_date) as should_run_now,
              is_active
                and day_of_week = extract(isodow from now())::int - 1
                and localtime >= stop_time
                and last_started_on = current_date as is_done_today,
              case
                when is_active
                  and day_of_week = extract(isodow from now())::int - 1
                  and localtime >= start_time
                  and localtime < stop_time
                  and (last_started_on is distinct from current_date) then 'due_now'
                when is_active
                  and day_of_week = extract(isodow from now())::int - 1
                  and localtime >= start_time
                  and localtime < stop_time
                  and last_started_on = current_date then 'attempted_today'
                when is_active
                  and day_of_week = extract(isodow from now())::int - 1
                  and localtime >= stop_time
                  and last_started_on = current_date then 'done_today'
                when is_active and day_of_week = extract(isodow from now())::int - 1 then 'armed_today'
                when is_active then 'armed'
                else 'disabled'
              end as schedule_status,
              last_started_on,
              last_stopped_on,
              updated_at,
              round(extract(epoch from (stop_time - start_time)) / 60)::int as duration_minutes
            """,
            (
                start_time,
                stop_time,
                is_active,
                start_time,
                stop_time,
                is_active,
                start_time,
                stop_time,
                is_active,
                schedule_id,
            ),
        )
        if not row:
            return {"ok": False, "error": "schedule not found"}, 404
        self.invalidate_snapshot()
        self.invalidate_pilot()
        return {"ok": True, "schedule": self.fetch_schedule(schedule_id) or row, "context": self.context_meta("irrigation", "irrigation_pilot")}, 200

    def create_schedule(self, data: Dict[str, Any]):
        try:
            day_of_week = int(data.get("day_of_week"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "day_of_week must be between 0 and 6"}, 400
        if day_of_week < 0 or day_of_week > 6:
            return {"ok": False, "error": "day_of_week must be between 0 and 6"}, 400
        try:
            start_time = self.validate_schedule_time(data.get("start_time"), "start_time")
            stop_time = self.validate_schedule_time(data.get("stop_time"), "stop_time")
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}, 400
        if start_time >= stop_time:
            return {"ok": False, "error": "start_time must be before stop_time"}, 400

        label = self.normalize_text(data.get("label"), SCHEDULE_DAY_LABELS[day_of_week])
        row = self.execute_one(
            """
            insert into hc.irrigation_schedule
              (day_of_week, label, start_time, stop_time, is_active)
            values (%s, %s, %s::time, %s::time, %s)
            returning id
            """,
            (day_of_week, label, start_time, stop_time, bool(data.get("is_active"))),
        )
        schedule_id = int(row["id"]) if row else 0
        self.invalidate_snapshot()
        self.invalidate_pilot()
        return {
            "ok": True,
            "schedule": self.fetch_schedule(schedule_id),
            "schedules": self.fetch_schedules(),
            "context": self.context_meta("irrigation", "irrigation_pilot"),
        }, 201

    def delete_schedule(self, schedule_id: int):
        existing = self.fetch_one(
            """
            select id, day_of_week
            from hc.irrigation_schedule
            where id = %s
            """,
            (schedule_id,),
        )
        if not existing:
            return {"ok": False, "error": "schedule not found"}, 404
        sibling_count = self.fetch_one(
            """
            select count(*)::int as count
            from hc.irrigation_schedule
            where day_of_week = %s
            """,
            (existing["day_of_week"],),
        )
        if int((sibling_count or {}).get("count") or 0) <= 1:
            return {"ok": False, "error": "cannot delete the last schedule for a day; disable it instead"}, 400

        row = self.execute_one(
            """
            delete from hc.irrigation_schedule
            where id = %s
            returning id
            """,
            (schedule_id,),
        )
        if not row:
            return {"ok": False, "error": "schedule not found"}, 404
        self.invalidate_snapshot()
        self.invalidate_pilot()
        return {
            "ok": True,
            "deleted_id": schedule_id,
            "schedules": self.fetch_schedules(),
            "context": self.context_meta("irrigation", "irrigation_pilot"),
        }, 200

    def stop_manual(self, data: Dict[str, Any]):
        session_id = data.get("session_id")
        if session_id is None:
            row = self.fetch_one(
                """
                select id
                from hc.irrigation_manual_session
                where status in ('running', 'starting', 'stop_failed')
                  and started_by <> 'physical_manual'
                order by started_at desc
                limit 1
                """
            )
            session_id = row["id"] if row else None
        if session_id is None:
            return {"ok": False, "error": "no running session"}, 404
        ok, message, row = self.stop_manual_session(int(session_id), "manual_stop")
        self.invalidate_snapshot()
        return {"ok": ok, "message": message, "session": row, "context": self.context_meta("irrigation")}, 200 if ok else 502

    def fetch_pilot_config(self):
        self.ensure_pilot_schema()
        return self.fetch_one("select * from hc.irrigation_pilot_config where id = 1")

    def fetch_pilot_base_schedule(self):
        return self.fetch_one(
            """
            with active_schedule as (
              select
                id,
                day_of_week,
                label,
                to_char(start_time, 'HH24:MI') as start_time,
                to_char(stop_time, 'HH24:MI') as stop_time,
                round(extract(epoch from (stop_time - start_time)) / 60)::int as duration_minutes,
                day_of_week = extract(isodow from now())::int - 1 as is_today,
                is_active
                  and day_of_week = extract(isodow from now())::int - 1
                  and localtime >= start_time
                  and localtime < stop_time
                  and (last_started_on is distinct from current_date) as should_run_now,
                ((day_of_week - (extract(isodow from now())::int - 1) + 7) %% 7) as day_distance
              from hc.irrigation_schedule
              where is_active = true
            )
            select
              id,
              day_of_week,
              label,
              start_time,
              stop_time,
              duration_minutes,
              is_today,
              should_run_now
            from active_schedule
            order by
              case when should_run_now then 0 else 1 end,
              day_distance,
              start_time,
              id
            limit 1
            """
        )

    def latest_weather_observation(self):
        self.ensure_pilot_schema()
        return self.fetch_one(
            """
            select *
            from hc.weather_observation
            order by ts desc
            limit 1
            """
        )

    def openweather_ready(self):
        return bool(self.openweather_api_key and self.openweather_lat and self.openweather_lon)

    def openweather_url(self, path: str, extra: Dict[str, Any]):
        params = urlencode(
            {
                "lat": self.openweather_lat,
                "lon": self.openweather_lon,
                "appid": self.openweather_api_key,
                "units": self.openweather_units,
                "lang": self.openweather_lang,
                **extra,
            }
        )
        return f"https://api.openweathermap.org/data/{path}?{params}"

    def fetch_openweather_json(self, path: str, extra: Dict[str, Any]):
        with urlopen(self.openweather_url(path, extra), timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))

    def insert_weather_observation(
        self,
        current: Dict[str, Any],
        rain_mm: float,
        pop_percent: float,
        uv_index: Any,
        forecast_rain: float,
        forecast_pop: float,
        forecast_temp_max: Any,
        sunrise: Any,
        sunset: Any,
        raw: Dict[str, Any],
    ):
        main = current.get("main") or current
        wind = current.get("wind") or current
        clouds = current.get("clouds") or current
        return self.execute_one(
            """
            insert into hc.weather_observation (
              temperature_c,
              humidity_percent,
              wind_speed_mps,
              wind_deg,
              rain_mm,
              pop_percent,
              uv_index,
              cloudiness_percent,
              pressure_hpa,
              sunrise,
              sunset,
              forecast_rain_24h_mm,
              forecast_pop_max_percent,
              forecast_temp_max_c,
              raw
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s, %s, %s, %s::jsonb)
            returning *
            """,
            (
                main.get("temp"),
                main.get("humidity"),
                wind.get("speed") if "speed" in wind else wind.get("wind_speed"),
                wind.get("deg") if "deg" in wind else wind.get("wind_deg"),
                rain_mm,
                pop_percent,
                uv_index,
                clouds.get("all") if "all" in clouds else clouds.get("clouds"),
                main.get("pressure"),
                sunrise,
                sunset,
                round(forecast_rain, 2),
                round(forecast_pop, 1),
                forecast_temp_max,
                json.dumps(raw),
            ),
        )

    def store_openweather_onecall_snapshot(self):
        payload = self.fetch_openweather_json("3.0/onecall", {"exclude": "minutely,alerts"})
        current = payload.get("current") or {}
        hourly = payload.get("hourly") or []
        daily = payload.get("daily") or []
        today = daily[0] if daily else {}
        rain_now = current.get("rain") or {}
        next_24h = hourly[:24]
        forecast_rain = sum(self.to_float((item.get("rain") or {}).get("1h"), 0) or 0 for item in next_24h)
        forecast_pop = max([self.to_float(item.get("pop"), 0) or 0 for item in next_24h] or [0]) * 100
        daily_temp = today.get("temp") or {}

        return self.insert_weather_observation(
            current=current,
            rain_mm=self.to_float(rain_now.get("1h"), 0) or 0,
            pop_percent=(self.to_float(today.get("pop"), 0) or 0) * 100,
            uv_index=current.get("uvi"),
            forecast_rain=forecast_rain,
            forecast_pop=forecast_pop,
            forecast_temp_max=daily_temp.get("max"),
            sunrise=current.get("sunrise"),
            sunset=current.get("sunset"),
            raw={"endpoint": "onecall_3_0", "payload": payload},
        )

    def store_openweather_forecast_snapshot(self):
        current_payload = self.fetch_openweather_json("2.5/weather", {})
        forecast_payload = self.fetch_openweather_json("2.5/forecast", {})
        current = current_payload or {}
        now_ts = int(time.time())
        next_24h = [
            item
            for item in forecast_payload.get("list", [])
            if now_ts <= self.to_int(item.get("dt"), 0) <= now_ts + 86400
        ]
        if not next_24h:
            next_24h = forecast_payload.get("list", [])[:8]

        forecast_rain = sum(self.to_float((item.get("rain") or {}).get("3h"), 0) or 0 for item in next_24h)
        forecast_pop = max([self.to_float(item.get("pop"), 0) or 0 for item in next_24h] or [0]) * 100
        temp_values = [self.to_float((item.get("main") or {}).get("temp_max")) for item in next_24h]
        temp_values = [value for value in temp_values if value is not None]
        rain_now = current.get("rain") or {}
        sys_info = current.get("sys") or {}

        return self.insert_weather_observation(
            current=current,
            rain_mm=self.to_float(rain_now.get("1h"), rain_now.get("3h")) or 0,
            pop_percent=forecast_pop,
            uv_index=None,
            forecast_rain=forecast_rain,
            forecast_pop=forecast_pop,
            forecast_temp_max=max(temp_values) if temp_values else (current.get("main") or {}).get("temp"),
            sunrise=sys_info.get("sunrise"),
            sunset=sys_info.get("sunset"),
            raw={
                "endpoint": "weather_2_5_forecast_2_5",
                "current": current_payload,
                "forecast": forecast_payload,
            },
        )

    def store_openweather_snapshot(self):
        self.ensure_pilot_schema()
        if not self.openweather_ready():
            raise RuntimeError("OPENWEATHER_API_KEY, OPENWEATHER_LAT and OPENWEATHER_LON are required")
        try:
            return self.store_openweather_onecall_snapshot()
        except HTTPError as exc:
            if exc.code not in {401, 403}:
                raise
            return self.store_openweather_forecast_snapshot()

    def weather_summary(self):
        self.ensure_pilot_schema()
        latest = self.latest_weather_observation()
        rain_24h = self.fetch_one(
            """
            select coalesce(round(sum(hour_rain)::numeric, 2), 0) as rain_24h_mm
            from (
              select date_trunc('hour', observed_ts) as hour_bucket,
                     max(coalesce(rain_mm, 0)) as hour_rain
              from (
                select
                  coalesce(
                    case
                      when raw->'current'->>'dt' ~ '^[0-9]+$'
                      then to_timestamp((raw->'current'->>'dt')::double precision)
                    end,
                    case
                      when raw->'payload'->'current'->>'dt' ~ '^[0-9]+$'
                      then to_timestamp((raw->'payload'->'current'->>'dt')::double precision)
                    end,
                    ts
                  ) as observed_ts,
                  rain_mm
                from hc.weather_observation
                where ts >= now() - interval '24 hours'
              ) observed
              where observed_ts >= now() - interval '24 hours'
              group by 1
            ) hourly
            """
        )
        history_24h = self.fetch_all(
            """
            select
              date_trunc('hour', ts) as ts,
              round(avg(temperature_c)::numeric, 2) as temperature_c,
              round(avg(humidity_percent)::numeric, 2) as humidity_percent,
              round(avg(wind_speed_mps)::numeric, 2) as wind_speed_mps,
              round(avg(wind_deg)::numeric, 0) as wind_deg,
              round(avg(pressure_hpa)::numeric, 1) as pressure_hpa,
              round(max(rain_mm)::numeric, 2) as rain_mm,
              round(max(forecast_rain_24h_mm)::numeric, 2) as forecast_rain_24h_mm
            from hc.weather_observation
            where ts >= now() - interval '24 hours'
            group by date_trunc('hour', ts)
            order by date_trunc('hour', ts)
            """
        )
        return {
            "latest": latest,
            "history_24h": history_24h,
            "rain_24h_mm": float(rain_24h["rain_24h_mm"] or 0) if rain_24h else 0,
            "openweather_configured": self.openweather_ready(),
            "poll_seconds": self.weather_poll_seconds,
        }

    def latest_outdoor_sensor_snapshot(self):
        rows = self.fetch_all(
            """
            select
              s.key,
              s.ts,
              s.v_num,
              extract(epoch from (now() - s.ts)) / 3600.0 as age_hours
            from hc.entity_state s
            join hc.entity e on e.id = s.entity_id
            where e.name = 'Udvar'
              and s.key in ('temperature', 'humidity')
            order by s.key
            """
        )
        values = {row["key"]: row for row in rows}
        temp = values.get("temperature")
        humidity = values.get("humidity")
        latest_ts = None
        latest_age_hours = None
        for row in rows:
            if latest_ts is None or row["ts"] > latest_ts:
                latest_ts = row["ts"]
                latest_age_hours = row.get("age_hours")
        temp_age_hours = self.to_float(temp.get("age_hours")) if temp and temp.get("age_hours") is not None else None
        humidity_age_hours = self.to_float(humidity.get("age_hours")) if humidity and humidity.get("age_hours") is not None else None
        temperature_c = self.to_float(temp.get("v_num")) if temp else None
        humidity_percent = self.to_float(humidity.get("v_num")) if humidity else None
        temperature_usable = temperature_c is not None and temp_age_hours is not None and temp_age_hours <= LOCAL_WEATHER_SENSOR_MAX_AGE_HOURS
        humidity_usable = humidity_percent is not None and humidity_age_hours is not None and humidity_age_hours <= LOCAL_WEATHER_SENSOR_MAX_AGE_HOURS
        return {
            "name": "Udvar",
            "temperature_c": temperature_c,
            "humidity_percent": humidity_percent,
            "absolute_humidity_g_m3": self.absolute_humidity_g_m3(temp.get("v_num") if temp else None, humidity.get("v_num") if humidity else None),
            "ts": self.json_time(latest_ts),
            "age_hours": self.to_float(latest_age_hours) if latest_age_hours is not None else None,
            "temperature_age_hours": temp_age_hours,
            "humidity_age_hours": humidity_age_hours,
            "max_age_hours": LOCAL_WEATHER_SENSOR_MAX_AGE_HOURS,
            "temperature_usable": temperature_usable,
            "humidity_usable": humidity_usable,
            "usable": temperature_usable or humidity_usable,
        }

    def latest_rain_sensor_snapshot(self):
        rows = self.fetch_all(
            """
            select s.key, s.ts, s.v_num, s.v_bool
            from hc.entity_state s
            join hc.entity e on e.id = s.entity_id
            where e.topic_base = 'zigbee/0xa4c138479ed598c1'
              and s.key in ('water_leak', 'battery', 'battery_low', 'linkquality')
            order by s.key
            """
        )
        values = {row["key"]: row for row in rows}
        water = values.get("water_leak")
        latest_ts = None
        for row in rows:
            if latest_ts is None or row["ts"] > latest_ts:
                latest_ts = row["ts"]
        last_wet = self.fetch_one(
            """
            select ts
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            where e.topic_base = 'zigbee/0xa4c138479ed598c1'
              and m.key = 'water_leak'
              and m.v_bool = true
            order by ts desc
            limit 1
            """
        )
        return {
            "name": "Rain sensor",
            "water_leak": bool(water["v_bool"]) if water and water.get("v_bool") is not None else None,
            "is_wet": bool(water["v_bool"]) if water and water.get("v_bool") is not None else None,
            "battery_percent": self.to_float(values.get("battery", {}).get("v_num")) if values.get("battery") else None,
            "battery_low": bool(values["battery_low"]["v_bool"]) if values.get("battery_low") and values["battery_low"].get("v_bool") is not None else None,
            "linkquality": self.to_float(values.get("linkquality", {}).get("v_num")) if values.get("linkquality") else None,
            "ts": self.json_time(latest_ts),
            "last_wet_ts": self.json_time(last_wet["ts"]) if last_wet else None,
        }

    def latest_soil_moisture_snapshot(self, topic_base: str):
        latest = self.fetch_one(
            """
            select
              e.name as entity_name,
              e.topic_base,
              s.ts,
              s.v_num,
              extract(epoch from (now() - s.ts)) / 3600.0 as age_hours
            from hc.entity e
            join hc.entity_metric em on em.entity_id = e.id and em.metric_key = 'soil_moisture'
            left join hc.entity_state s on s.entity_id = e.id and s.key = 'soil_moisture'
            where e.topic_base = %s
              and e.is_active
              and em.is_enabled
            limit 1
            """,
            (topic_base,),
        )
        summary = self.fetch_one(
            """
            select
              count(*)::int as sample_count_24h,
              round(avg(m.v_num)::numeric, 2) as avg_24h_percent,
              round(min(m.v_num)::numeric, 2) as min_24h_percent,
              round(max(m.v_num)::numeric, 2) as max_24h_percent
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            where e.topic_base = %s
              and m.key = 'soil_moisture'
              and m.ts >= now() - interval '24 hours'
            """,
            (topic_base,),
        )
        return {
            "name": latest.get("entity_name") if latest else None,
            "topic_base": topic_base,
            "soil_moisture_percent": self.to_float(latest.get("v_num")) if latest and latest.get("v_num") is not None else None,
            "ts": self.json_time(latest.get("ts")) if latest else None,
            "age_hours": self.to_float(latest.get("age_hours")) if latest and latest.get("age_hours") is not None else None,
            "sample_count_24h": int(summary.get("sample_count_24h") or 0) if summary else 0,
            "avg_24h_percent": self.to_float(summary.get("avg_24h_percent")) if summary and summary.get("avg_24h_percent") is not None else None,
            "min_24h_percent": self.to_float(summary.get("min_24h_percent")) if summary and summary.get("min_24h_percent") is not None else None,
            "max_24h_percent": self.to_float(summary.get("max_24h_percent")) if summary and summary.get("max_24h_percent") is not None else None,
        }

    def build_weather_snapshot(self, soil_sensor_topic: str = PILOT_SOIL_SENSOR_TOPIC):
        summary = self.weather_summary()
        latest = summary["latest"] or {}
        outdoor = self.latest_outdoor_sensor_snapshot()
        rain_sensor = self.latest_rain_sensor_snapshot()
        soil_sensor = self.latest_soil_moisture_snapshot(soil_sensor_topic)
        openweather_temperature = self.to_float(latest.get("forecast_temp_max_c"), latest.get("temperature_c"))
        openweather_humidity = self.to_float(latest.get("humidity_percent"))
        local_temperature = outdoor.get("temperature_c")
        local_humidity = outdoor.get("humidity_percent")
        use_local_temperature = bool(outdoor.get("temperature_usable") and local_temperature is not None)
        use_local_humidity = bool(outdoor.get("humidity_usable") and local_humidity is not None)
        return {
            "rain_24h_mm": summary["rain_24h_mm"],
            "forecast_rain_24h_mm": self.to_float(latest.get("forecast_rain_24h_mm"), 0) or 0,
            "pop_percent": self.to_float(latest.get("forecast_pop_max_percent"), latest.get("pop_percent")) or 0,
            "temperature_c": local_temperature if use_local_temperature else openweather_temperature,
            "humidity_percent": local_humidity if use_local_humidity else openweather_humidity,
            "temperature_source": "local_sensor" if use_local_temperature else "openweather",
            "humidity_source": "local_sensor" if use_local_humidity else "openweather",
            "forecast_temperature_c": openweather_temperature,
            "openweather_humidity_percent": openweather_humidity,
            "wind_speed_mps": self.to_float(latest.get("wind_speed_mps")),
            "uv_index": self.to_float(latest.get("uv_index")),
            "cloudiness_percent": self.to_float(latest.get("cloudiness_percent")),
            "pressure_hpa": self.to_float(latest.get("pressure_hpa")),
            "sunrise": self.json_time(latest.get("sunrise")),
            "sunset": self.json_time(latest.get("sunset")),
            "weather_ts": self.json_time(latest.get("ts")),
            "local_sensor": outdoor,
            "rain_sensor": rain_sensor,
            "soil_moisture_sensor": soil_sensor,
        }

    def evaluate_pilot(self, base_duration: Optional[int] = None, mode: Optional[str] = None):
        config = self.fetch_pilot_config()
        soil_sensor_topic = (self.process_binding_topic("irrigation_soil_moisture") if self.process_binding_topic
                             else config.get("soil_sensor_topic_base") or PILOT_SOIL_SENSOR_TOPIC)
        snapshot = self.build_weather_snapshot(soil_sensor_topic)
        base_schedule = None
        base_source = "schedule"
        if base_duration is None:
            base_schedule = self.fetch_pilot_base_schedule()
            if base_schedule and base_schedule.get("duration_minutes") is not None:
                base = int(base_schedule["duration_minutes"])
            else:
                base = int(config["base_duration_minutes"])
                base_source = "config_fallback"
        else:
            base = int(base_duration)
            base_source = "scheduler_run"
        final = base
        triggered = []
        corrections = []
        multiplier_terms = [{"rule": "base", "delta": 1.0, "multiplier": 1.0}]
        multiplier = 1.0
        applied_multiplier = 1.0
        reason = f"Today's watering remains unchanged at {base} minutes."

        rain_24h = snapshot["rain_24h_mm"]
        forecast_rain = snapshot["forecast_rain_24h_mm"]
        pop = snapshot["pop_percent"]
        temp = snapshot["temperature_c"]
        temp_source = "yard sensor" if snapshot.get("temperature_source") == "local_sensor" else "weather forecast"
        soil = snapshot["soil_moisture_sensor"]
        soil_percent = soil["soil_moisture_percent"]
        soil_age_hours = soil["age_hours"]
        soil_enabled = bool(config.get("soil_moisture_enabled", True))
        soil_max_age = float(config.get("soil_sample_max_age_hours") or 12)
        soil_usable = bool(
            soil_enabled
            and soil_percent is not None
            and soil_age_hours is not None
            and soil_age_hours <= soil_max_age
        )
        def add_multiplier(rule: str, delta: float, meta: Optional[Dict[str, Any]] = None):
            nonlocal multiplier
            if not delta:
                return
            multiplier += delta
            item = {
                "rule": rule,
                "delta": round(delta, 4),
                "multiplier": round(multiplier, 4),
            }
            if meta:
                item.update(meta)
            multiplier_terms.append(item)
            triggered.append(rule)

        def temperature_steps(value: float, threshold: float, step: float):
            step = max(0.1, step)
            return max(1, int(math.floor(abs(value - threshold) / step)) + 1)

        def config_float(key: str, default: float):
            value = config.get(key)
            return float(value) if value is not None else default

        min_multiplier = max(0.0, config_float("min_duration_multiplier", 0.2))
        max_multiplier = max(min_multiplier, config_float("max_duration_multiplier", 1.5))

        if rain_24h > float(config["rain_24h_threshold_mm"]):
            final = 0
            triggered.append("rain_skip")
            reason = f"Today's watering skipped. Rainfall in the last 24 hours was {rain_24h:.1f} mm."
        elif pop > float(config["pop_threshold_percent"]) and forecast_rain > float(config["forecast_rain_threshold_mm"]):
            final = 0
            triggered.append("forecast_skip")
            reason = f"Today's watering skipped. Expected rainfall is {forecast_rain:.1f} mm with {pop:.0f}% precipitation probability."
        elif soil_usable and soil_percent >= config_float("soil_wet_skip_threshold_percent", 85):
            final = 0
            triggered.append("soil_wet_skip")
            reason = f"Today's watering skipped. {soil['name'] or 'Soil sensor'} reports {soil_percent:.0f}% soil moisture."
        else:
            if temp is not None and temp > float(config["heat_threshold_c"]):
                heat_step = config_float("heat_step_c", 5)
                steps = temperature_steps(temp, float(config["heat_threshold_c"]), heat_step)
                delta = steps * config_float("heat_multiplier_step", 0.1)
                add_multiplier(
                    "heat_increase",
                    delta,
                    {"steps": steps, "temperature_c": temp, "step_c": heat_step, "source": snapshot.get("temperature_source")},
                )
            elif temp is not None and temp < float(config["cold_threshold_c"]):
                cold_step = config_float("cold_step_c", 5)
                steps = temperature_steps(temp, float(config["cold_threshold_c"]), cold_step)
                delta = steps * config_float("cold_multiplier_step", -0.1)
                add_multiplier(
                    "cold_decrease",
                    delta,
                    {"steps": steps, "temperature_c": temp, "step_c": cold_step, "source": snapshot.get("temperature_source")},
                )

            if soil_usable:
                wet_adjust = config_float("soil_wet_adjust_threshold_percent", 65)
                if soil_percent >= wet_adjust:
                    add_multiplier(
                        "soil_wet_reduce",
                        config_float("soil_wet_multiplier_delta", -0.5),
                        {"soil_moisture_percent": soil_percent, "threshold_percent": wet_adjust},
                    )
                elif soil_percent <= config_float("soil_dry_threshold_percent", 45):
                    add_multiplier(
                        "soil_dry_increase",
                        config_float("soil_dry_multiplier_delta", config_float("soil_dry_correction_percent", 15) / 100.0),
                        {"soil_moisture_percent": soil_percent, "threshold_percent": config_float("soil_dry_threshold_percent", 45)},
                    )

            raw_multiplier = multiplier
            applied_multiplier = min(max(raw_multiplier, min_multiplier), max_multiplier)
            if applied_multiplier != raw_multiplier:
                triggered.append("multiplier_clamped")
                multiplier_terms.append({
                    "rule": "multiplier_clamped",
                    "delta": 0,
                    "multiplier": round(applied_multiplier, 4),
                    "raw_multiplier": round(raw_multiplier, 4),
                    "min_multiplier": min_multiplier,
                    "max_multiplier": max_multiplier,
                })
            final = max(1, int(round(base * applied_multiplier)))
            for item in multiplier_terms:
                if item["rule"] == "base":
                    continue
                item["minutes"] = int(round(base * item.get("delta", 0)))
                corrections.append(item)
            if corrections:
                reason = f"Today's watering adjusted from {base} to {final} minutes. Multiplier {raw_multiplier:.2f}x"
                if applied_multiplier != raw_multiplier:
                    reason += f" capped to {applied_multiplier:.2f}x"
                if temp is not None:
                    reason += f"; {temp_source} temperature is {temp:.1f} C"
                if soil_usable:
                    reason += f"; {soil['name'] or 'Soil sensor'} reports {soil_percent:.0f}% soil moisture"
                reason += "."

        return {
            "mode": mode or config["mode"],
            "base_duration": base,
            "base_source": base_source,
            "base_schedule": base_schedule,
            "final_duration": final,
            "executed": False,
            "reason": reason,
            "triggered_rules": triggered,
            "weather_snapshot": snapshot,
            "details": {
                "inputs": {
                    "Rain24h": rain_24h,
                    "ForecastRain": forecast_rain,
                    "POP": pop,
                    "Temperature": temp,
                    "Humidity": snapshot["humidity_percent"],
                    "TemperatureSource": snapshot.get("temperature_source"),
                    "HumiditySource": snapshot.get("humidity_source"),
                    "ForecastTemperature": snapshot.get("forecast_temperature_c"),
                    "OpenWeatherHumidity": snapshot.get("openweather_humidity_percent"),
                    "Wind": snapshot["wind_speed_mps"],
                    "LocalTemperature": snapshot["local_sensor"]["temperature_c"],
                    "LocalHumidity": snapshot["local_sensor"]["humidity_percent"],
                    "LocalAbsoluteHumidity": snapshot["local_sensor"]["absolute_humidity_g_m3"],
                    "LocalSensorAgeHours": snapshot["local_sensor"].get("age_hours"),
                    "LocalTemperatureAgeHours": snapshot["local_sensor"].get("temperature_age_hours"),
                    "LocalHumidityAgeHours": snapshot["local_sensor"].get("humidity_age_hours"),
                    "LocalSensorMaxAgeHours": snapshot["local_sensor"].get("max_age_hours"),
                    "LocalTemperatureUsable": snapshot["local_sensor"].get("temperature_usable"),
                    "LocalHumidityUsable": snapshot["local_sensor"].get("humidity_usable"),
                    "RainSensorWet": snapshot["rain_sensor"]["is_wet"],
                    "RainSensorLastWet": snapshot["rain_sensor"]["last_wet_ts"],
                    "RainSensorBattery": snapshot["rain_sensor"]["battery_percent"],
                    "RainSensorLinkquality": snapshot["rain_sensor"]["linkquality"],
                    "SoilSensor": soil["name"],
                    "SoilMoisture": soil_percent,
                    "SoilMoistureAgeHours": soil_age_hours,
                    "SoilMoistureSampleCount24h": soil["sample_count_24h"],
                    "SoilMoistureAvg24h": soil["avg_24h_percent"],
                    "SoilMoistureMin24h": soil["min_24h_percent"],
                    "SoilMoistureMax24h": soil["max_24h_percent"],
                    "SoilMoistureUsable": soil_usable,
                    "MinDurationMultiplier": min_multiplier,
                    "MaxDurationMultiplier": max_multiplier,
                },
                "rules": {
                    "rain_skip": "rain_skip" in triggered,
                    "forecast_skip": "forecast_skip" in triggered,
                    "soil_wet_skip": "soil_wet_skip" in triggered,
                    "soil_wet_reduce": "soil_wet_reduce" in triggered,
                    "soil_dry_increase": "soil_dry_increase" in triggered,
                    "heat_increase": "heat_increase" in triggered,
                    "cold_decrease": "cold_decrease" in triggered,
                    "multiplier_clamped": "multiplier_clamped" in triggered,
                },
                "result": {
                    "base_duration": base,
                    "base_source": base_source,
                    "base_schedule": base_schedule,
                    "corrections": corrections,
                    "multiplier_terms": multiplier_terms,
                    "raw_multiplier": round(multiplier, 4),
                    "applied_multiplier": 0 if final == 0 else round(applied_multiplier, 4),
                    "min_multiplier": min_multiplier,
                    "max_multiplier": max_multiplier,
                    "final_duration": final,
                },
            },
        }

    def log_pilot_decision(self, decision: Dict[str, Any], schedule_id: Optional[int] = None, execution_status: str = "not_executed"):
        self.ensure_pilot_schema()
        return self.execute_one(
            """
            insert into hc.irrigation_pilot_decision (
              mode,
              base_duration,
              final_duration,
              executed,
              reason,
              triggered_rules,
              weather_snapshot,
              details,
              schedule_id,
              execution_status
            )
            values (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
            returning *
            """,
            (
                decision["mode"],
                decision["base_duration"],
                decision["final_duration"],
                bool(decision.get("executed")),
                decision["reason"],
                json.dumps(decision["triggered_rules"]),
                json.dumps(decision["weather_snapshot"]),
                json.dumps(decision["details"]),
                schedule_id,
                execution_status,
            ),
        )

    def cached_weather_summary(self, force: bool = False):
        return self._read_cache.cached_payload(
            "weather", self.weather_summary_cache_ttl, self.weather_summary, force=force)

    def cached_pilot_recommendation(self, force: bool = False):
        return self._read_cache.cached_payload(
            "pilot", self.pilot_cache_ttl, self.evaluate_pilot, force=force)

    def pilot_payload(self):
        self.ensure_pilot_schema()
        soil_binding = self.process_binding_payload("irrigation_soil_moisture") if self.process_binding_payload else None
        return {
            "ok": True,
            "config": self.fetch_pilot_config(),
            "process_bindings": {"irrigation_soil_moisture": soil_binding} if soil_binding else {},
            "weather": self.cached_weather_summary(),
            "recommendation": self.cached_pilot_recommendation(),
            "latest_decision": self.fetch_one(
                """
                select *
                from hc.irrigation_pilot_decision
                order by timestamp desc
                limit 1
                """
            ),
            "today_decision": self.fetch_one(
                """
                select *
                from hc.irrigation_pilot_decision
                where timestamp >= current_date
                order by timestamp desc
                limit 1
                """
            ),
            "decisions": self.fetch_all(
                """
                select *
                from hc.irrigation_pilot_decision
                order by timestamp desc
                limit 50
                """
            ),
        }

    def update_pilot_config(self, data: Dict[str, Any]):
        mode = self.normalize_text(data.get("mode"), "navigator")
        if mode not in {"navigator", "pilot"}:
            return {"ok": False, "error": "mode must be navigator or pilot"}, 400
        row = self.execute_one(
            """
            update hc.irrigation_pilot_config
            set mode = %s,
                rain_24h_threshold_mm = %s,
                forecast_rain_threshold_mm = %s,
                pop_threshold_percent = %s,
                heat_threshold_c = %s,
                heat_correction_percent = %s,
                heat_step_c = %s,
                heat_multiplier_step = %s,
                cold_threshold_c = %s,
                cold_correction_percent = %s,
                cold_step_c = %s,
                cold_multiplier_step = %s,
                soil_moisture_enabled = %s,
                soil_wet_skip_threshold_percent = %s,
                soil_wet_adjust_threshold_percent = %s,
                soil_wet_multiplier_delta = %s,
                soil_dry_threshold_percent = %s,
                soil_dry_correction_percent = %s,
                soil_dry_multiplier_delta = %s,
                soil_sample_max_age_hours = %s,
                min_duration_multiplier = %s,
                max_duration_multiplier = %s,
                updated_at = now()
            where id = 1
            returning *
            """,
            (
                mode,
                self.to_float(data.get("rain_24h_threshold_mm"), 5),
                self.to_float(data.get("forecast_rain_threshold_mm"), 5),
                self.to_int(data.get("pop_threshold_percent"), 70),
                self.to_float(data.get("heat_threshold_c"), 32),
                self.to_int(data.get("heat_correction_percent"), 20),
                self.to_float(data.get("heat_step_c"), 5),
                self.to_float(data.get("heat_multiplier_step"), 0.1),
                self.to_float(data.get("cold_threshold_c"), 22),
                self.to_int(data.get("cold_correction_percent"), -20),
                self.to_float(data.get("cold_step_c"), 5),
                self.to_float(data.get("cold_multiplier_step"), -0.1),
                bool(data.get("soil_moisture_enabled", True)),
                self.to_float(data.get("soil_wet_skip_threshold_percent"), 85),
                self.to_float(data.get("soil_wet_adjust_threshold_percent"), 65),
                self.to_float(data.get("soil_wet_multiplier_delta"), -0.5),
                self.to_float(data.get("soil_dry_threshold_percent"), 45),
                self.to_int(data.get("soil_dry_correction_percent"), 15),
                self.to_float(data.get("soil_dry_multiplier_delta"), 0.15),
                self.to_int(data.get("soil_sample_max_age_hours"), 12),
                self.to_float(data.get("min_duration_multiplier"), 0.2),
                self.to_float(data.get("max_duration_multiplier"), 1.5),
            ),
        )
        self.invalidate_pilot()
        self.invalidate_weather_summary()
        self.invalidate_context("irrigation_pilot")
        return {"ok": True, "config": row, "context": self.context_meta("irrigation_pilot")}, 200

    def create_pilot_decision(self):
        decision = self.evaluate_pilot()
        row = self.log_pilot_decision(decision, execution_status="manual_evaluation")
        self.invalidate_pilot()
        self.invalidate_weather_summary()
        self.invalidate_context("irrigation_pilot")
        return {"ok": True, "decision": row, "recommendation": decision, "context": self.context_meta("irrigation_pilot")}, 200

    def fetch_weather(self):
        try:
            row = self.store_openweather_snapshot()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}, 400
        self.invalidate_pilot()
        self.invalidate_weather_summary()
        self.invalidate_context("irrigation_pilot")
        return {"ok": True, "weather": row, "context": self.context_meta("irrigation_pilot", "weather")}, 200

    def snapshot(self, force: bool = False):
        return self._read_cache.cached_payload(
            "snapshot", self.snapshot_ttl, self.build_snapshot, force=force)

    def build_snapshot(self):
        self.ensure_summary_schema()
        moisture_topic_list = ", ".join(f"'{topic}'" for topic in IRRIGATION_MOISTURE_TOPICS)
        latest = self.fetch_all(
            f"""
            select e.name as entity_name, s.key, s.ts, s.v_num, s.v_bool, s.v_text
            from hc.entity_state s
            join hc.entity e on e.id = s.entity_id
            where e.topic_base in (
              'zigbee/0xa4c13880b130079c',
              {moisture_topic_list},
              'homecontrol/tele/irrigation/esp-irrigation-1'
            )
            order by e.name, s.key
            """
        )
        soil_moisture_24h = self.fetch_all(
            f"""
            select
              e.name as entity_name,
              date_trunc('minute', m.ts) as ts,
              round(avg(m.v_num)::numeric, 2) as soil_moisture
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            where m.key = 'soil_moisture'
              and m.ts >= now() - interval '24 hours'
              and e.topic_base in ({moisture_topic_list})
            group by e.name, date_trunc('minute', m.ts)
            order by e.name, date_trunc('minute', m.ts)
            """
        )
        sessions = self.fetch_all(
            """
            select *
            from hc.irrigation_manual_session
            order by created_at desc
            limit 10
            """
        )
        energy = self.fetch_all(
            """
            select *
            from hc.irrigation_daily_energy_summary
            order by day desc
            limit 14
            """
        )
        tank = self.fetch_all(
            """
            select *
            from hc.irrigation_tank_daily_summary
            order by day desc
            limit 14
            """
        )
        pump_daily = self.fetch_all(
            """
            select *
            from hc.irrigation_pump_daily_summary
            order by day desc
            limit 14
            """
        )
        solar_daily = self.fetch_all(
            """
            select *
            from hc.irrigation_solar_daily_summary
            order by day desc
            limit 14
            """
        )
        temp_daily = self.fetch_all(
            """
            select *
            from hc.irrigation_controller_temp_daily_summary
            order by day desc
            limit 14
            """
        )
        session_stats = self.fetch_all(
            """
            select *
            from hc.irrigation_session_stats
            order by started_at desc
            limit 20
            """
        )
        return {
            "manual_max_minutes": self.manual_max_minutes,
            "season_profile": self.active_season_profile(),
            "live": self.mqtt_snapshot(),
            "latest": latest,
            "soil_moisture_24h": soil_moisture_24h,
            "sessions": sessions,
            "session_recovery": self.session_recovery.payload(),
            "session_stats": session_stats,
            "scheduler_guard": self.manual_valve_scheduler_guard(),
            "schedules": self.fetch_schedules(),
            "energy_daily": energy,
            "pump_daily": pump_daily,
            "solar_daily": solar_daily,
            "solar_pump_scheduler": {
                "decision": self.evaluate_solar_pump_scheduler(),
                "runs": self.latest_solar_pump_runs(12),
            },
            "temp_daily": temp_daily,
            "tank_daily": tank,
        }

    def statistics_payload(self, range_key: str = "24h", hours: Any = None):
        custom_hours = None
        try:
            custom_hours = int(hours) if hours not in (None, "") else None
        except (TypeError, ValueError):
            custom_hours = None
        if custom_hours is not None:
            custom_hours = max(1, min(custom_hours, 720))
            range_label = f"{custom_hours}h"
            interval_text = f"{custom_hours} hours"
            bucket_expr = "date_trunc('minute', m.ts)" if custom_hours <= 48 else "date_trunc('hour', m.ts)"
            weather_bucket_expr = "date_trunc('minute', ts)" if custom_hours <= 48 else "date_trunc('hour', ts)"
        else:
            normalized_range = str(range_key or "24h").strip().lower()
            if normalized_range == "1h":
                range_label, interval_text, bucket_expr, weather_bucket_expr = "1h", "1 hour", "date_trunc('minute', m.ts)", "date_trunc('minute', ts)"
            elif normalized_range == "7d":
                range_label, interval_text, bucket_expr, weather_bucket_expr = "7d", "7 days", "date_trunc('hour', m.ts)", "date_trunc('hour', ts)"
            else:
                range_label, interval_text, bucket_expr, weather_bucket_expr = "24h", "24 hours", "date_trunc('minute', m.ts)", "date_trunc('minute', ts)"
        cache_key = f"irrigation_statistics:{range_label}"
        return self.cached_api_payload(cache_key, 60, lambda: self._build_statistics_payload(range_label, interval_text, bucket_expr, weather_bucket_expr))

    def _build_statistics_payload(self, range_label, interval_text, bucket_expr, weather_bucket_expr):
        self.ensure_summary_schema()
        moisture_topic_list = ", ".join(f"'{topic}'" for topic in IRRIGATION_MOISTURE_TOPICS)
        tank_24h = self.fetch_all(
            f"""
            select
              {bucket_expr} as ts,
              round(avg(v_num) filter (where key = 'liquid_level_percent')::numeric, 2) as level_percent,
              round(avg(v_num) filter (where key = 'liquid_depth')::numeric, 3) as depth_m
            from hc.measurement m
            where m.key in ('liquid_level_percent', 'liquid_depth')
              and m.ts >= now() - interval '{interval_text}'
            group by {bucket_expr}
            order by ts
            """
        )
        tank_24h, tank_filtered_spikes = self.filter_isolated_tank_level_spikes(tank_24h)
        soil_moisture_rows_24h = self.fetch_all(
            f"""
            select
              e.id as entity_id,
              e.name as entity_name,
              d.name as device_name,
              {bucket_expr} as ts,
              round(avg(m.v_num)::numeric, 2) as soil_moisture
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            join hc.entity_metric em on em.entity_id = e.id and em.metric_key = m.key
            where m.key = 'soil_moisture'
              and m.ts >= now() - interval '{interval_text}'
              and e.is_active
              and d.is_active
              and em.is_enabled
              and e.topic_base in ({moisture_topic_list})
            group by e.id, e.name, d.name, {bucket_expr}
            order by e.name, {bucket_expr}
            """
        )
        soil_moisture_rows_7d = self.fetch_all(
            f"""
            select
              e.id as entity_id,
              e.name as entity_name,
              d.name as device_name,
              date_trunc('hour', m.ts) + floor(extract(minute from m.ts) / 15) * interval '15 minutes' as ts,
              round(avg(m.v_num)::numeric, 2) as soil_moisture
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            join hc.entity_metric em on em.entity_id = e.id and em.metric_key = m.key
            where m.key = 'soil_moisture'
              and m.ts >= now() - interval '7 days'
              and e.is_active
              and d.is_active
              and em.is_enabled
              and e.topic_base in ({moisture_topic_list})
            group by e.id, e.name, d.name, date_trunc('hour', m.ts) + floor(extract(minute from m.ts) / 15) * interval '15 minutes'
            order by e.name, date_trunc('hour', m.ts) + floor(extract(minute from m.ts) / 15) * interval '15 minutes'
            """
        )
        soil_moisture_sensors = self.fetch_all(
            f"""
            select
              e.id as entity_id,
              e.name as entity_name,
              d.name as device_name,
              e.topic_base,
              s.ts as latest_ts,
              s.v_num as latest_soil_moisture
            from hc.entity e
            join hc.device d on d.id = e.device_id
            join hc.entity_metric em on em.entity_id = e.id and em.metric_key = 'soil_moisture'
            left join hc.entity_state s on s.entity_id = e.id and s.key = 'soil_moisture'
            where e.topic_base in ({moisture_topic_list})
              and e.is_active
              and d.is_active
              and em.is_enabled
            order by case e.topic_base
              when 'zigbee/0xa4c13844a0908898' then 1
              when 'zigbee/0xa4c1387594b09c83' then 2
              when 'zigbee/0xa4c1382abf3f8730' then 3
              else 99
            end, e.name
            """
        )

        def soil_moisture_series(rows):
            sensors_by_id = {}
            for row in soil_moisture_sensors:
                sensors_by_id[row["entity_id"]] = {
                    "entity_id": row["entity_id"],
                    "entity_name": row["entity_name"],
                    "device_name": row["device_name"],
                    "topic_base": row["topic_base"],
                    "latest_state_ts": row["latest_ts"],
                    "latest_state_soil_moisture": row["latest_soil_moisture"],
                    "samples": [],
                }
            for row in rows:
                sensor = sensors_by_id.setdefault(
                    row["entity_id"],
                    {
                        "entity_id": row["entity_id"],
                        "entity_name": row["entity_name"],
                        "device_name": row["device_name"],
                        "topic_base": None,
                        "latest_state_ts": None,
                        "latest_state_soil_moisture": None,
                        "samples": [],
                    },
                )
                sensor["samples"].append({"ts": row["ts"], "soil_moisture": row["soil_moisture"]})

            series = []
            for sensor in sensors_by_id.values():
                latest_sample = next((item for item in reversed(sensor["samples"]) if item["soil_moisture"] is not None), None)
                values = [item["soil_moisture"] for item in sensor["samples"] if item["soil_moisture"] is not None]
                series.append(
                    {
                        **sensor,
                        "latest_soil_moisture": latest_sample["soil_moisture"] if latest_sample else sensor["latest_state_soil_moisture"],
                        "latest_ts": latest_sample["ts"] if latest_sample else sensor["latest_state_ts"],
                        "min_soil_moisture": min(values) if values else None,
                        "max_soil_moisture": max(values) if values else None,
                        "sample_count": len(sensor["samples"]),
                    }
                )
            topic_order = {
                "zigbee/0xa4c13844a0908898": 1,
                "zigbee/0xa4c1387594b09c83": 2,
                "zigbee/0xa4c1382abf3f8730": 3,
            }
            series.sort(key=lambda item: (topic_order.get(item.get("topic_base"), 99), item["entity_name"]))
            return series

        soil_moisture_24h = soil_moisture_series(soil_moisture_rows_24h)
        soil_moisture_7d = soil_moisture_series(soil_moisture_rows_7d)
        battery_voltage_24h = self.fetch_all(
            f"""
            select
              {bucket_expr} as ts,
              round(avg(m.v_num)::numeric, 3) as battery_voltage_v,
              max(m.v_num) as max_battery_voltage_v,
              count(*) as sample_count
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            join hc.entity_metric em on em.entity_id = e.id and em.metric_key = m.key
            where m.key = 'solar_battery_voltage_v'
              and m.ts >= now() - interval '{interval_text}'
              and e.is_active
              and d.is_active
              and em.is_enabled
            group by {bucket_expr}
            order by {bucket_expr}
            """
        )
        pump_current_24h = self.fetch_all(
            f"""
            select
              {bucket_expr} as ts,
              round(avg(m.v_num)::numeric, 3) as pump_current_a,
              max(m.v_num) as max_pump_current_a,
              count(*) as sample_count
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            join hc.entity_metric em on em.entity_id = e.id and em.metric_key = m.key
            where m.key = 'pump_current_a'
              and m.ts >= now() - interval '{interval_text}'
              and e.is_active
              and d.is_active
              and em.is_enabled
            group by {bucket_expr}
            order by {bucket_expr}
            """
        )
        pump_current_7d = self.fetch_all(
            """
            select
              date_trunc('hour', m.ts) + floor(extract(minute from m.ts) / 15) * interval '15 minutes' as ts,
              round(avg(m.v_num)::numeric, 3) as pump_current_a,
              max(m.v_num) as max_pump_current_a,
              count(*) as sample_count
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            join hc.entity_metric em on em.entity_id = e.id and em.metric_key = m.key
            where m.key = 'pump_current_a'
              and m.ts >= now() - interval '7 days'
              and e.is_active
              and d.is_active
              and em.is_enabled
            group by date_trunc('hour', m.ts) + floor(extract(minute from m.ts) / 15) * interval '15 minutes'
            order by date_trunc('hour', m.ts) + floor(extract(minute from m.ts) / 15) * interval '15 minutes'
            """
        )
        pressure_comparison_24h = self.fetch_all(
            f"""
            with local_pressure as (
              select
                {bucket_expr} as ts,
                round(avg(m.v_num)::numeric, 1) as local_pressure_hpa
              from hc.measurement m
              join hc.entity e on e.id = m.entity_id
              join hc.device d on d.id = e.device_id
              join hc.entity_metric em on em.entity_id = e.id and em.metric_key = m.key
              where m.key = 'pressure_hpa'
                and m.ts >= now() - interval '{interval_text}'
                and e.is_active
                and d.is_active
                and em.is_enabled
              group by {bucket_expr}
            ),
            owm_pressure as (
              select
                {weather_bucket_expr} as ts,
                round(avg(pressure_hpa)::numeric, 1) as openweather_pressure_hpa
              from hc.weather_observation
              where pressure_hpa is not null
                and ts >= now() - interval '{interval_text}'
              group by {weather_bucket_expr}
            ),
            source_times as (
              select ts from local_pressure
              union
              select ts from owm_pressure
            )
            select
              st.ts,
              lp.local_pressure_hpa,
              op.openweather_pressure_hpa,
              case
                when lp.local_pressure_hpa is not null and op.openweather_pressure_hpa is not null
                then round((lp.local_pressure_hpa - op.openweather_pressure_hpa)::numeric, 1)
                else null
              end as pressure_delta_hpa
            from source_times st
            left join lateral (
              select local_pressure_hpa
              from local_pressure
              where ts <= st.ts
                and ts >= st.ts - interval '2 hours'
              order by ts desc
              limit 1
            ) lp on true
            left join lateral (
              select openweather_pressure_hpa
              from owm_pressure
              where ts <= st.ts
                and ts >= st.ts - interval '6 hours'
              order by ts desc
              limit 1
            ) op on true
            order by st.ts
            """
        )
        history_limit = max(21, self.daily_summary_days)
        pump_daily = self.fetch_all(
            f"""
            select
              coalesce(e.day, p.day) as day,
              p.pump_running_minutes,
              p.measured_hours as pump_state_measured_hours,
              p.state_samples,
              e.active_minutes as current_active_minutes,
              e.measured_hours as current_measured_hours,
              e.amp_hours,
              e.watt_hours,
              e.avg_current_a,
              e.max_current_a,
              e.avg_voltage_v
            from hc.irrigation_pump_daily_summary p
            full join hc.irrigation_daily_energy_summary e on e.day = p.day
            order by coalesce(e.day, p.day) desc
            limit {history_limit}
            """
        )
        return {
                "range": range_label,
                "bucket": "minute" if "minute" in bucket_expr else "hour",
                "tank_24h": tank_24h,
                "tank_filtered_spikes": tank_filtered_spikes,
                "pump_current_24h": pump_current_24h,
                "battery_voltage_24h": battery_voltage_24h,
                "pump_current_7d": pump_current_7d,
                "pressure_comparison_24h": pressure_comparison_24h,
                "soil_moisture_24h": soil_moisture_24h,
                "soil_moisture_7d": soil_moisture_7d,
                "tank_daily": self.fetch_all(
                    f"""
                    select *
                    from hc.irrigation_tank_daily_summary
                    order by day desc
                    limit {history_limit}
                    """
                ),
                "pump_daily": pump_daily,
                "solar_daily": self.fetch_all(
                    f"""
                    select *
                    from hc.irrigation_solar_daily_summary
                    order by day desc
                    limit {history_limit}
                    """
                ),
                "temp_daily": self.fetch_all(
                    f"""
                    select *
                    from hc.irrigation_controller_temp_daily_summary
                    order by day desc
                    limit {history_limit}
                    """
                ),
                "solar_pump_scheduler": {
                    "decision": self.evaluate_solar_pump_scheduler(),
                    "runs": self.latest_solar_pump_runs(12),
                },
                "sessions": self.fetch_all(
                    """
                    select *
                    from hc.irrigation_session_stats
                    order by started_at desc
                    limit 300
                    """
                ),
            }


    def start_scheduled_session(self, schedule_id: int):
        stop_generation = self._open_request_generation()
        if not self.capability_allowed("scheduled_watering"):
            print(f"[SEASON PROFILE] irrigation schedule_id={schedule_id} blocked", flush=True)
            return
        self.session_recovery.initialize()
        if self.session_recovery.blocked:
            return
        row = self.fetch_one(
            """
            select
              id,
              label,
              to_char(start_time, 'HH24:MI') as start_time,
              to_char(stop_time, 'HH24:MI') as stop_time,
              round(extract(epoch from (stop_time - start_time)) / 60)::int as duration_minutes
            from hc.irrigation_schedule
            where id = %s
              and is_active = true
              and day_of_week = extract(isodow from now())::int - 1
              and localtime >= start_time
              and localtime < stop_time
              and (last_started_on is distinct from current_date)
              and not exists (
                select 1
                from hc.irrigation_manual_session
                where status in ('running', 'starting')
              )
            """,
            (schedule_id,),
        )
        if not row:
            return

        decision = self.evaluate_pilot(base_duration=row["duration_minutes"])
        if decision["mode"] == "navigator":
            self.log_pilot_decision(decision, schedule_id=row["id"], execution_status="navigator_only")
            print(f"[PILOT] navigator schedule_id={row['id']} final={decision['final_duration']} reason={decision['reason']}", flush=True)
        else:
            decision["executed"] = False

        if decision["mode"] == "pilot" and int(decision["final_duration"]) <= 0:
            self.execute_one(
                """
                update hc.irrigation_schedule
                set last_started_on = current_date,
                    updated_at = now()
                where id = %s
                returning id
                """,
                (schedule_id,),
            )
            decision["executed"] = True
            self.log_pilot_decision(decision, schedule_id=row["id"], execution_status="skipped")
            print(f"[PILOT] skipped schedule_id={row['id']} reason={decision['reason']}", flush=True)
            return

        minutes_source = decision["final_duration"] if decision["mode"] == "pilot" else row["duration_minutes"]
        minutes = max(1, min(int(minutes_source or 1), self.manual_max_minutes))
        valve_payload = {
            "cmd": "set",
            "value": "open",
            "source": "pilot" if decision["mode"] == "pilot" else "scheduler",
            "schedule_id": row["id"],
            "schedule_label": row["label"],
            "schedule_duration_minutes": row["duration_minutes"],
            "duration_minutes": minutes,
        }
        if decision["mode"] == "pilot":
            valve_payload.update(
                {
                    "pilot_final_duration": int(decision["final_duration"]),
                    "pilot_triggered_rules": decision.get("triggered_rules", []),
                }
            )
        reservation = self._reserve_start(
            minutes, "pilot" if decision["mode"] == "pilot" else "scheduler", valve_payload, schedule_id=row["id"],
        )
        session = reservation.get("session")
        if not session:
            print(f"[ADMISSION] legacy schedule_id={row['id']} blocked by {reservation.get('blocked_by')}", flush=True)
            return
        valve_ok, valve_message, valve_details = self.publish_open_with_confirmation(valve_payload, stop_generation=stop_generation)
        confirmed_payload = {
            **valve_payload,
            "confirmation": {
                "ok": valve_ok,
                "message": valve_message,
                **valve_details,
            },
        }
        if decision["mode"] == "pilot":
            self.log_pilot_decision(decision, schedule_id=row["id"], execution_status="command_confirmed" if valve_ok else "start_failed")
        if valve_ok and session:
            self.execute_one(
                """
                update hc.irrigation_manual_session
                set status = 'running',
                    start_payload = %s::jsonb
                where id = %s and status = 'starting'
                returning *
                """,
                (json.dumps(confirmed_payload), session["id"]),
            )
        elif session:
            self.execute_one(
                """
                update hc.irrigation_manual_session
                set status = 'start_failed',
                    stopped_at = now(),
                    start_payload = %s::jsonb,
                    error = %s
                where id = %s
                returning id
                """,
                (json.dumps(confirmed_payload), f"valve={valve_message}", session["id"]),
            )
        print(f"[SCHEDULE] start id={row['id']} ok={valve_ok} message={valve_message}", flush=True)

    def run_due_schedules(self):
        guard = self.manual_valve_scheduler_guard()
        if guard["blocked"]:
            print(f"[SCHEDULE] blocked by manual valve state={guard['state']}", flush=True)
            return

        rows = self.fetch_all(
            """
            select id
            from hc.irrigation_schedule
            where is_active = true
              and day_of_week = extract(isodow from now())::int - 1
              and localtime >= start_time
              and localtime < stop_time
              and (last_started_on is distinct from current_date)
            order by start_time, id
            """
        )
        for row in rows:
            self.start_scheduled_session(int(row["id"]))

    def stop_due_schedules(self):
        rows = self.fetch_all(
            """
            select id
            from hc.irrigation_schedule
            where is_active = true
              and day_of_week = extract(isodow from now())::int - 1
              and localtime >= stop_time
              and last_started_on = current_date
              and (last_stopped_on is distinct from current_date)
            order by stop_time, id
            """
        )
        for row in rows:
            session = self.fetch_one(
                """
                select id, status
                from hc.irrigation_manual_session
                where started_by in ('scheduler', 'pilot')
                  and start_payload ->> 'schedule_id' = %s
                  and started_at::date = current_date
                order by started_at desc
                limit 1
                """,
                (str(row["id"]),),
            )
            should_mark_stopped = session is None
            if session and session["status"] == "running":
                ok, message, _ = self.stop_manual_session(int(session["id"]), "schedule_stop")
                print(f"[SCHEDULE] stop id={row['id']} ok={ok} message={message}", flush=True)
                should_mark_stopped = ok
            elif session and session["status"] == "stop_failed":
                print(f"[SCHEDULE] stop id={row['id']} still failed; not marking stopped", flush=True)
            elif session:
                should_mark_stopped = session["status"] in ("stopped", "auto_stopped")

            if should_mark_stopped:
                self.execute_one(
                    """
                    update hc.irrigation_schedule
                    set last_stopped_on = current_date,
                        updated_at = now()
                    where id = %s
                    returning id
                    """,
                    (row["id"],),
                )

    def mark_v2_execution(self, schedule_id: Any, value: str, status: str, result: Dict[str, Any], error: Optional[str] = None):
        return self.execute_one(
            """
            update hc.execution
            set status = %s,
                result = %s::jsonb,
                error = %s,
                started_at = coalesce(started_at, now()),
                ended_at = now(),
                metadata = metadata || %s::jsonb,
                updated_at = now()
            where id = (
              select id
              from hc.execution
              where domain = 'irrigation'
                and command_payload ->> 'schedule_id' = %s
                and command_payload ->> 'value' = %s
                and created_at::date = current_date
              order by created_at desc
              limit 1
            )
            returning *
            """,
            (
                status,
                json.dumps(result),
                error,
                json.dumps({"command_owner": "v2", "executed_by": "v2_irrigation_executor"}),
                str(schedule_id),
                value,
            ),
        )

    def v2_stop_policy(
        self,
        row: Dict[str, Any],
        decision: Optional[Dict[str, Any]] = None,
        effective_duration: Optional[int] = None,
        effective_stop_at: Any = None,
    ):
        decision = decision or {}
        base_duration = row.get("duration_minutes")
        final_duration = effective_duration if effective_duration is not None else decision.get("final_duration", base_duration)
        stop_authority = "v2_rule_effective_stop" if decision.get("mode") == "pilot" else "schedule_stop_event"
        return {
            "stop_authority": stop_authority,
            "scheduled_start": row.get("start_time"),
            "scheduled_stop": row.get("stop_time"),
            "scheduled_duration_minutes": base_duration,
            "effective_duration_minutes": final_duration,
            "effective_stop_at": self.json_time(effective_stop_at) if effective_stop_at else None,
            "rule_engine_mode": decision.get("mode"),
            "rule_engine_reason": decision.get("reason"),
            "triggered_rules": decision.get("triggered_rules", []),
            "legacy_requested_stop_at_is_diagnostic": True,
        }

    def start_v2_scheduled_session(self, schedule_id: int):
        stop_generation = self._open_request_generation()
        if not self.capability_allowed("scheduled_watering"):
            print(f"[SEASON PROFILE] v2 irrigation schedule_id={schedule_id} blocked", flush=True)
            return
        self.session_recovery.initialize()
        if self.session_recovery.blocked:
            print(f"[RECOVERY] v2 schedule_id={schedule_id} blocked by unresolved session", flush=True)
            return
        row = self.fetch_one(
            """
            select
              id,
              label,
              to_char(start_time, 'HH24:MI') as start_time,
              to_char(stop_time, 'HH24:MI') as stop_time,
              round(extract(epoch from (stop_time - start_time)) / 60)::int as duration_minutes,
              (date_trunc('day', now()) + stop_time)::timestamptz as scheduled_stop_at
            from hc.irrigation_schedule
            where id = %s
              and is_active = true
              and day_of_week = extract(isodow from now())::int - 1
              and localtime >= start_time
              and localtime < stop_time
              and (last_started_on is distinct from current_date)
              and not exists (
                select 1
                from hc.irrigation_manual_session
                where status in ('running', 'starting', 'stop_failed')
              )
            """,
            (schedule_id,),
        )
        if not row:
            return

        decision = self.evaluate_pilot(base_duration=row["duration_minutes"])
        if decision["mode"] == "pilot" and int(decision["final_duration"]) <= 0:
            decision["executed"] = True
            self.log_pilot_decision(decision, schedule_id=row["id"], execution_status="v2_skipped")
            self.execute_one(
                """
                update hc.irrigation_schedule
                set last_started_on = current_date,
                    updated_at = now()
                where id = %s
                returning id
                """,
                (schedule_id,),
            )
            self.mark_v2_execution(
                row["id"],
                "open",
                "skipped",
                {
                    "published": False,
                    "publish_attempted": False,
                    "reason": decision["reason"],
                    "triggered_rules": decision.get("triggered_rules", []),
                    "weather_snapshot": decision.get("weather_snapshot", {}),
                },
            )
            print(f"[V2 PILOT] skipped schedule_id={row['id']} reason={decision['reason']}", flush=True)
            return

        minutes_source = decision["final_duration"] if decision["mode"] == "pilot" else row["duration_minutes"]
        minutes = max(1, min(int(minutes_source or 1), self.manual_max_minutes))
        stop_policy = self.v2_stop_policy(row, decision, minutes)
        command_payload = {
            "cmd": "set",
            "value": "open",
            "source": "pilot" if decision["mode"] == "pilot" else "scheduler",
            "schedule_id": row["id"],
            "schedule_label": row["label"],
            "schedule_duration_minutes": row["duration_minutes"],
            "duration_minutes": minutes,
        }
        if decision["mode"] == "pilot":
            command_payload.update(
                {
                    "pilot_final_duration": int(decision["final_duration"]),
                    "pilot_triggered_rules": decision.get("triggered_rules", []),
                }
            )
        session_payload = {
            **command_payload,
            "hc_executor": "v2_scheduler",
            "pilot_final_duration": int(decision["final_duration"]) if decision["mode"] == "pilot" else None,
            "pilot_triggered_rules": decision.get("triggered_rules", []),
            "pilot_reason": decision.get("reason"),
            "weather_snapshot": decision.get("weather_snapshot", {}),
            "stop_policy": stop_policy,
        }
        reservation = self._reserve_start(minutes, "v2_scheduler", session_payload, schedule_id=row["id"])
        session = reservation.get("session")
        if not session:
            print(f"[ADMISSION] v2 schedule_id={row['id']} blocked by {reservation.get('blocked_by')}", flush=True)
            return
        stop_policy = self.v2_stop_policy(row, decision, minutes, session.get("requested_stop_at"))
        session_payload["stop_policy"] = stop_policy
        valve_ok, valve_message, valve_details = self.publish_open_with_confirmation(command_payload, stop_generation=stop_generation)
        confirmed_payload = {
            **session_payload,
            "command_payload": command_payload,
            "confirmation": {
                "ok": valve_ok,
                "message": valve_message,
                **valve_details,
            },
        }
        result = {
            "published": bool(valve_ok),
            "publish_attempted": True,
            "message": valve_message,
            "confirmation": valve_details,
            "rule_engine": {
                "mode": decision.get("mode"),
                "reason": decision.get("reason"),
                "triggered_rules": decision.get("triggered_rules", []),
                "base_duration": decision.get("base_duration"),
                "final_duration": decision.get("final_duration"),
            },
            "stop_policy": stop_policy,
        }
        if valve_ok and session:
            committed = self.execute_one(
                """
                update hc.irrigation_manual_session
                set status = 'running',
                    start_payload = %s::jsonb
                where id = %s and status = 'starting'
                returning *
                """,
                (json.dumps(confirmed_payload), session["id"]),
            )
            if not committed:
                self.mark_v2_execution(row["id"], "open", "failed", result, "start reconciled before confirmation could commit")
                return
            if decision["mode"] == "pilot":
                decision["executed"] = True
                self.log_pilot_decision(decision, schedule_id=row["id"], execution_status="v2_command_confirmed")
            self.mark_v2_execution(row["id"], "open", "confirmed", result)
        elif session:
            self.session_recovery.blocked = True
            if decision["mode"] == "pilot":
                self.log_pilot_decision(decision, schedule_id=row["id"], execution_status="v2_start_failed")
            self.execute_one(
                """
                update hc.irrigation_manual_session
                set status = 'stop_failed',
                    stopped_at = null,
                    start_payload = %s::jsonb,
                    error = %s,
                    stop_payload = coalesce(stop_payload, '{}'::jsonb) || jsonb_build_object(
                      'recovery', jsonb_build_object('origin_status', 'starting', 'state', 'pending')
                        || coalesce(stop_payload -> 'recovery', '{}'::jsonb))
                where id = %s and status = 'starting'
                returning id
                """,
                (json.dumps(confirmed_payload), f"valve={valve_message}", session["id"]),
            )
            self.mark_v2_execution(row["id"], "open", "failed", result, valve_message)
        print(f"[V2 SCHEDULE] start id={row['id']} ok={valve_ok} message={valve_message}", flush=True)

    def run_v2_due_schedules(self):
        guard = self.manual_valve_scheduler_guard()
        if guard["blocked"]:
            print(f"[V2 SCHEDULE] blocked by manual valve state={guard['state']}", flush=True)
            return

        rows = self.fetch_all(
            """
            select id
            from hc.irrigation_schedule
            where is_active = true
              and day_of_week = extract(isodow from now())::int - 1
              and localtime >= start_time
              and localtime < stop_time
              and (last_started_on is distinct from current_date)
            order by start_time, id
            """
        )
        for row in rows:
            self.start_v2_scheduled_session(int(row["id"]))

    def stop_v2_due_schedules(self):
        rows = self.fetch_all(
            """
            select
              s.id,
              s.stop_time,
              m.id as session_id,
              m.status as session_status,
              m.requested_stop_at
            from hc.irrigation_schedule s
            left join lateral (
              select id, status, requested_stop_at
              from hc.irrigation_manual_session
              where started_by = 'v2_scheduler'
                and start_payload ->> 'schedule_id' = s.id::text
                and started_at::date = current_date
              order by started_at desc
              limit 1
            ) m on true
            where s.is_active = true
              and s.day_of_week = extract(isodow from now())::int - 1
              and s.last_started_on = current_date
              and (s.last_stopped_on is distinct from current_date)
              and (
                (m.id is not null and m.requested_stop_at <= now())
                or (m.id is null and localtime >= s.stop_time)
              )
            order by coalesce(m.requested_stop_at, date_trunc('day', now()) + s.stop_time), s.id
            """
        )
        for row in rows:
            should_mark_stopped = row.get("session_id") is None
            if row.get("session_id") and row["session_status"] == "running":
                ok, message, _ = self.stop_manual_session(int(row["session_id"]), "v2_effective_stop")
                self.mark_v2_execution(
                    row["id"],
                    "close",
                    "confirmed" if ok else "failed",
                    {
                        "published": bool(ok),
                        "publish_attempted": True,
                        "message": message,
                        "reason": "v2_effective_stop",
                        "effective_stop_at": row.get("requested_stop_at"),
                    },
                    None if ok else message,
                )
                print(f"[V2 SCHEDULE] stop id={row['id']} ok={ok} message={message}", flush=True)
                should_mark_stopped = ok
            elif row.get("session_id") and row["session_status"] == "stop_failed":
                print(f"[V2 SCHEDULE] stop id={row['id']} still failed; not marking stopped", flush=True)
            elif row.get("session_id"):
                should_mark_stopped = row["session_status"] in ("stopped", "auto_stopped")

            if should_mark_stopped:
                self.execute_one(
                    """
                    update hc.irrigation_schedule
                    set last_stopped_on = current_date,
                        updated_at = now()
                    where id = %s
                    returning id
                    """,
                    (row["id"],),
                )

    def scheduler_tick(self):
        engine = self.v2_execution_engine_state(self.scheduler_config())
        if "irrigation" not in (engine.get("publish_domains") or []):
            return
        self.run_v2_due_schedules()
        self.solar_pump_scheduler_tick()

    def scheduler_stop_tick(self):
        engine = self.v2_execution_engine_state(self.scheduler_config())
        if "irrigation" not in (engine.get("publish_domains") or []):
            return
        self.stop_v2_due_schedules()
