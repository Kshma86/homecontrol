import json
from typing import Any, Callable, Dict


class ClimateService:
    def __init__(
        self,
        fetch_all: Callable[..., Any],
        fetch_one: Callable[..., Any],
        execute_one: Callable[..., Any],
        normalize_text: Callable[..., str],
        validate_schedule_time: Callable[[Any, str], str],
        publish_mqtt: Callable[..., Any],
        invalidate_context: Callable[..., Any],
        context_meta: Callable[..., Dict[str, Any]],
        monitor: Any,
        base_topic: str,
        name: str,
        ip: str,
        port: int,
        mac: str,
        power_meter_ext_id: str,
        power_meter_divisor: float,
        sync_auto_power_wall: Callable[[str], Any],
        process_binding_payload: Callable[[str], Any] = None,
        process_binding_entity_id: Callable[[str], Any] = None,
    ):
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.execute_one = execute_one
        self.normalize_text = normalize_text
        self.validate_schedule_time = validate_schedule_time
        self.publish_mqtt = publish_mqtt
        self.invalidate_context = invalidate_context
        self.context_meta = context_meta
        self.monitor = monitor
        self.base_topic = base_topic.rstrip("/")
        self.name = name
        self.ip = ip
        self.port = port
        self.mac = mac
        self.power_meter_ext_id = power_meter_ext_id
        self.power_meter_divisor = power_meter_divisor
        self.sync_auto_power_wall = sync_auto_power_wall
        self.process_binding_payload = process_binding_payload
        self.process_binding_entity_id = process_binding_entity_id

    def scale_power_w(self, value: Any):
        if value is None:
            return None
        try:
            number = float(value)
            divisor = float(self.power_meter_divisor or 1)
        except (TypeError, ValueError):
            return value
        if divisor <= 0:
            divisor = 1
        return round(number / divisor, 3)

    def power_meter_payload(self):
        binding_entity_id = self.process_binding_entity_id("climate_power_meter") if self.process_binding_entity_id else None
        if not binding_entity_id and not self.power_meter_ext_id:
            return {"ok": False, "error": "climate power meter is not configured"}

        row = self.fetch_one(
            """
            select
              d.id as device_id,
              d.ext_id,
              d.name as device_name,
              d.location,
              d.model,
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              p.status,
              p.last_seen_ts,
              p.updated_at as presence_updated_at
            from hc.device d
            join hc.entity e on e.device_id = d.id
            left join hc.entity_presence p on p.entity_id = e.id
            where (
                (%s::bigint is not null and e.id = %s::bigint)
                or (%s::bigint is null and d.platform = 'tuya' and d.ext_id = %s)
              )
              and d.is_active = true
              and e.is_active = true
            order by e.id
            limit 1
            """,
            (binding_entity_id, binding_entity_id, binding_entity_id, self.power_meter_ext_id),
        )
        if not row:
            return {"ok": False, "error": "climate power meter entity not found", "ext_id": self.power_meter_ext_id, "entity_id": binding_entity_id}

        state_rows = self.fetch_all(
            """
            select key, ts, v_num, v_bool, v_text, v_json, meta
            from hc.entity_state
            where entity_id = %s
              and key in (
                'power_w', 'voltage_v', 'current_a', 'energy_kwh', 'energy_calc_kwh',
                'lag_sec', 'recv_ts', 'src_ts', 'tuya_raw_dps'
              )
            order by key
            """,
            (row["entity_id"],),
        )
        state: Dict[str, Any] = {}
        state_ts: Dict[str, Any] = {}
        for item in state_rows:
            value = item.get("v_num")
            if value is None:
                value = item.get("v_bool")
            if value is None:
                value = item.get("v_text")
            if value is None:
                value = item.get("v_json")
            if item["key"] == "power_w":
                value = self.scale_power_w(value)
            state[item["key"]] = value
            state_ts[item["key"]] = item.get("ts")

        daily = self.fetch_one(
            """
            select
              min(v_num) as first_energy_kwh,
              max(v_num) as last_energy_kwh,
              greatest(coalesce(max(v_num) - min(v_num), 0), 0) as energy_kwh,
              count(*) as sample_count,
              min(ts) as first_ts,
              max(ts) as last_ts
            from hc.measurement
            where entity_id = %s
              and key = 'energy_kwh'
              and ts >= date_trunc('day', now())
            """,
            (row["entity_id"],),
        ) or {}

        latest_ts = max((ts for ts in state_ts.values() if ts), default=None)
        return {
            "ok": True,
            "device_id": row["device_id"],
            "entity_id": row["entity_id"],
            "ext_id": row["ext_id"],
            "device_name": row["device_name"],
            "entity_name": row["entity_name"],
            "location": row.get("location"),
            "model": row.get("model"),
            "topic_base": row["topic_base"],
            "status": row.get("status") or "unknown",
            "last_seen_ts": row.get("last_seen_ts"),
            "presence_updated_at": row.get("presence_updated_at"),
            "updated_at": latest_ts,
            "state": state,
            "state_ts": state_ts,
            "daily": {
                "energy_kwh": daily.get("energy_kwh"),
                "first_energy_kwh": daily.get("first_energy_kwh"),
                "last_energy_kwh": daily.get("last_energy_kwh"),
                "sample_count": daily.get("sample_count") or 0,
                "first_ts": daily.get("first_ts"),
                "last_ts": daily.get("last_ts"),
            },
        }

    def power_history_payload(self):
        meter = self.power_meter_payload()
        if not meter.get("ok"):
            return {"ok": False, "error": meter.get("error") or "climate power meter unavailable", "meter": meter}

        entity_id = meter["entity_id"]
        power_rows = self.fetch_all(
            """
            select ts, v_num as power_w
            from hc.measurement
            where entity_id = %s
              and key = 'power_w'
              and ts >= now() - interval '24 hours'
              and v_num is not null
            order by ts
            """,
            (entity_id,),
        )
        for row in power_rows:
            row["power_w"] = self.scale_power_w(row.get("power_w"))
        daily_rows = self.fetch_all(
            """
            with days as (
              select generate_series(
                date_trunc('day', now()) - interval '29 days',
                date_trunc('day', now()),
                interval '1 day'
              )::date as day
            ),
            energy as (
              select
                date_trunc('day', ts)::date as day,
                min(v_num) as first_energy_kwh,
                max(v_num) as last_energy_kwh,
                greatest(coalesce(max(v_num) - min(v_num), 0), 0) as energy_kwh,
                count(*) as sample_count
              from hc.measurement
              where entity_id = %s
                and key = 'energy_kwh'
                and ts >= date_trunc('day', now()) - interval '29 days'
                and v_num is not null
              group by 1
            )
            select
              d.day,
              coalesce(e.energy_kwh, 0) as energy_kwh,
              e.first_energy_kwh,
              e.last_energy_kwh,
              coalesce(e.sample_count, 0) as sample_count
            from days d
            left join energy e on e.day = d.day
            order by d.day
            """,
            (entity_id,),
        )
        return {
            "ok": True,
            "meter": meter,
            "power_24h": power_rows,
            "daily_30d": daily_rows,
            "summary": {
                "power_samples": len(power_rows),
                "daily_days": len(daily_rows),
                "today_energy_kwh": (daily_rows[-1].get("energy_kwh") if daily_rows else None),
                "max_power_w": max((row.get("power_w") or 0 for row in power_rows), default=0),
            },
        }

    def state_payload(self):
        snapshot = self.monitor.snapshot()
        state = self.monitor.value("state") or {}
        availability = self.monitor.value("availability")
        command_result = self.monitor.value("command_result")
        if not isinstance(state, dict):
            state = {}
        if not state:
            state = self.latest_parameter_state()
        return {
            "ok": bool(state.get("ok")),
            "bridge_online": availability == "online",
            "base_topic": self.base_topic,
            "name": state.get("name") or self.name,
            "ip": state.get("ip") or self.ip,
            "port": state.get("port") or self.port,
            "mac": state.get("mac") or self.mac,
            "power": state.get("power"),
            "mode": state.get("mode"),
            "target_temperature": state.get("target_temperature"),
            "current_temperature": state.get("current_temperature"),
            "fan_speed": state.get("fan_speed"),
            "current_humidity": state.get("current_humidity"),
            "target_humidity": state.get("target_humidity"),
            "light": state.get("light"),
            "raw_properties": state.get("raw_properties") or {},
            "updated_at": state.get("updated_at"),
            "error": state.get("error"),
            "command_result": command_result,
            "power_meter": self.power_meter_payload(),
            "process_bindings": {
                "climate_power_meter": self.process_binding_payload("climate_power_meter") if self.process_binding_payload else None,
                "climate_extra_fan_socket": self.process_binding_payload("climate_extra_fan_socket") if self.process_binding_payload else None,
            },
            "topics": snapshot.get("topics") or {},
            "mqtt": {
                "connected": snapshot.get("mqtt_connected"),
                "last_error": snapshot.get("last_error"),
            },
        }

    def latest_parameter_state(self):
        row = self.fetch_one(
            """
            select e.id as entity_id
            from hc.entity e
            where e.topic_base = %s
              and e.is_active = true
            order by e.id
            limit 1
            """,
            (self.base_topic,),
        )
        if not row:
            return {}
        rows = self.fetch_all(
            """
            select key, ts, v_num, v_bool, v_text, v_json
            from hc.entity_state
            where entity_id = %s
              and key in (
                'climate_ok', 'climate_power', 'climate_mode',
                'climate_target_temperature', 'climate_current_temperature',
                'climate_fan_speed', 'climate_error'
              )
            """,
            (row["entity_id"],),
        )
        values = {item["key"]: _state_value(item) for item in rows}
        timestamps = [item.get("ts") for item in rows if item.get("ts")]
        return {
            "ok": values.get("climate_ok", bool(values)),
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "mac": self.mac,
            "power": values.get("climate_power"),
            "mode": values.get("climate_mode"),
            "target_temperature": values.get("climate_target_temperature"),
            "current_temperature": values.get("climate_current_temperature"),
            "fan_speed": values.get("climate_fan_speed"),
            "updated_at": max(timestamps) if timestamps else None,
            "error": values.get("climate_error"),
        }

    def parameter_history_payload(self):
        entity = self.fetch_one(
            """
            select
              d.id as device_id,
              d.ext_id,
              d.name as device_name,
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              p.status,
              p.last_seen_ts
            from hc.entity e
            join hc.device d on d.id = e.device_id
            left join hc.entity_presence p on p.entity_id = e.id
            where e.topic_base = %s
              and e.is_active = true
              and d.is_active = true
            order by e.id
            limit 1
            """,
            (self.base_topic,),
        )
        if not entity:
            return {"ok": False, "error": "Gree climate history entity not found", "topic_base": self.base_topic}

        entity_id = entity["entity_id"]
        latest_rows = self.fetch_all(
            """
            select key, ts, v_num, v_bool, v_text, v_json
            from hc.entity_state
            where entity_id = %s
              and key in (
                'climate_ok', 'climate_power', 'climate_mode',
                'climate_target_temperature', 'climate_current_temperature',
                'climate_fan_speed', 'climate_error'
              )
            order by key
            """,
            (entity_id,),
        )
        latest = {}
        latest_ts = {}
        for row in latest_rows:
            latest[row["key"]] = _state_value(row)
            latest_ts[row["key"]] = row.get("ts")

        numeric_rows = self.fetch_all(
            """
            select
              key,
              count(*) as sample_count,
              min(v_num) as min_value,
              max(v_num) as max_value,
              avg(v_num) as avg_value,
              min(ts) as first_ts,
              max(ts) as last_ts
            from hc.measurement
            where entity_id = %s
              and key in (
                'climate_target_temperature', 'climate_current_temperature'
              )
              and ts >= now() - interval '7 days'
              and v_num is not null
            group by key
            order by key
            """,
            (entity_id,),
        )
        numeric_24h = self.fetch_all(
            """
            select
              key,
              count(*) as sample_count,
              min(v_num) as min_value,
              max(v_num) as max_value,
              avg(v_num) as avg_value,
              min(ts) as first_ts,
              max(ts) as last_ts
            from hc.measurement
            where entity_id = %s
              and key in (
                'climate_target_temperature', 'climate_current_temperature'
              )
              and ts >= now() - interval '24 hours'
              and v_num is not null
            group by key
            order by key
            """,
            (entity_id,),
        )
        distribution_rows = self.fetch_all(
            """
            select
              key,
              coalesce(v_text, v_bool::text, v_num::text) as value,
              count(*) as sample_count,
              min(ts) as first_ts,
              max(ts) as last_ts
            from hc.measurement
            where entity_id = %s
              and key in ('climate_power', 'climate_mode', 'climate_fan_speed', 'climate_ok')
              and ts >= now() - interval '7 days'
            group by key, coalesce(v_text, v_bool::text, v_num::text)
            order by key, sample_count desc
            """,
            (entity_id,),
        )
        changes = self.fetch_all(
            """
            select
              ts,
              key,
              coalesce(v_text, v_bool::text, v_num::text) as value
            from hc.measurement
            where entity_id = %s
              and key in (
                'climate_power', 'climate_mode', 'climate_target_temperature',
                'climate_fan_speed'
              )
              and ts >= now() - interval '7 days'
            order by ts desc
            limit 80
            """,
            (entity_id,),
        )
        sample_rows = self.fetch_all(
            """
            select ts, key, v_num, v_text, v_bool
            from hc.measurement
            where entity_id = %s
              and key in (
                'climate_current_temperature', 'climate_target_temperature',
                'climate_power', 'climate_mode', 'climate_fan_speed'
              )
              and ts >= now() - interval '24 hours'
            order by ts desc
            limit 160
            """,
            (entity_id,),
        )

        return {
            "ok": True,
            "device": dict(entity),
            "latest": latest,
            "latest_ts": latest_ts,
            "numeric_24h": _summary_by_key(numeric_24h),
            "numeric_7d": _summary_by_key(numeric_rows),
            "distributions_7d": _distribution_by_key(distribution_rows),
            "recent_setting_changes_7d": [dict(row) for row in changes],
            "samples_24h": [_measurement_value(row) for row in sample_rows],
            "summary": {
                "numeric_7d_keys": len(numeric_rows),
                "distribution_rows_7d": len(distribution_rows),
                "recent_setting_changes_7d": len(changes),
                "samples_24h": len(sample_rows),
            },
        }

    def command_payload(self, data: Dict[str, Any]):
        payload = {}
        power = self.normalize_text(data.get("power"))
        if power:
            if power not in {"on", "off"}:
                raise ValueError("power must be on or off")
            payload["power"] = power
        mode = self.normalize_text(data.get("mode"))
        if mode:
            if mode not in {"auto", "cool", "dry", "fan", "heat"}:
                raise ValueError("mode must be one of: auto, cool, dry, fan, heat")
            payload["mode"] = mode
        if data.get("target_temperature") is not None:
            try:
                target_temperature = int(data.get("target_temperature"))
            except (TypeError, ValueError):
                raise ValueError("target_temperature must be a number")
            if target_temperature < 8 or target_temperature > 30:
                raise ValueError("target_temperature must be between 8 and 30")
            payload["target_temperature"] = target_temperature
        fan = self.normalize_text(data.get("fan_speed"))
        if fan:
            if fan not in {"auto", "low", "mediumlow", "medium", "mediumhigh", "high"}:
                raise ValueError("fan_speed must be one of: auto, low, mediumlow, medium, mediumhigh, high")
            payload["fan_speed"] = fan
        light = self.normalize_text(data.get("light"))
        if light:
            if light not in {"on", "off"}:
                raise ValueError("light must be on or off")
            payload["light"] = light
        if not payload:
            payload["refresh"] = True
        return payload

    def queue_command(self, data: Dict[str, Any]):
        payload = self.command_payload(data)
        ok, message = self.publish_mqtt(f"{self.base_topic}/command", payload)
        auto_power_wall = self.sync_auto_power_wall(payload["power"]) if ok and payload.get("power") in {"on", "off"} else []
        self.invalidate_context("climate", "power_wall")
        return {
            "ok": ok,
            "message": message,
            "queued": payload,
            "state": self.state_payload(),
            "auto_power_wall": auto_power_wall,
            "context": self.context_meta("climate", "power_wall"),
        }

    def schedule_payload(self, data: dict, default_light: str = "off"):
        start_time = self.validate_schedule_time(data.get("start_time"), "start_time")
        day_of_week = int(data.get("day_of_week"))
        power = self.normalize_text(data.get("power"), "on")
        mode = self.normalize_text(data.get("mode"), "heat")
        target_temperature = int(data.get("target_temperature"))
        fan_speed = self.normalize_text(data.get("fan_speed"), "auto")
        light = self.normalize_text(data.get("light"), default_light)
        if day_of_week < 0 or day_of_week > 6:
            raise ValueError("day_of_week must be between 0 and 6")
        if power not in {"on", "off"}:
            raise ValueError("power must be on or off")
        if mode not in {"auto", "cool", "dry", "fan", "heat"}:
            raise ValueError("mode must be one of: auto, cool, dry, fan, heat")
        if target_temperature < 8 or target_temperature > 30:
            raise ValueError("target_temperature must be between 8 and 30")
        if fan_speed not in {"auto", "low", "mediumlow", "medium", "mediumhigh", "high"}:
            raise ValueError("fan_speed must be one of: auto, low, mediumlow, medium, mediumhigh, high")
        if light not in {"on", "off"}:
            raise ValueError("light must be on or off")
        enabled_value = data.get("is_enabled")
        rule_engine = data.get("rule_engine") if isinstance(data.get("rule_engine"), dict) else {"rule_engine": "manual_schedule"}
        return {
            "label": self.normalize_text(data.get("label"), "Climate event"),
            "day_of_week": day_of_week,
            "start_time": start_time,
            "is_enabled": enabled_value is True or enabled_value in {"true", "1", "on", 1},
            "power": power,
            "mode": mode,
            "target_temperature": target_temperature,
            "fan_speed": fan_speed,
            "light": light,
            "rule_engine": json.dumps(rule_engine),
        }

    def create_schedule(self, data: Dict[str, Any], fetch_schedules: Callable[[], Any]):
        payload = self.schedule_payload(data)
        row = self.execute_one(
            """
            insert into hc.climate_schedule_rule (
                label, day_of_week, start_time, is_enabled, power, mode,
                target_temperature, fan_speed, light, rule_engine
            )
            values (%s, %s, %s::time, %s, %s, %s, %s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                payload["label"], payload["day_of_week"], payload["start_time"], payload["is_enabled"],
                payload["power"], payload["mode"], payload["target_temperature"], payload["fan_speed"],
                payload["light"], payload["rule_engine"],
            ),
        )
        schedules = fetch_schedules()
        created_id = int(row.get("id")) if row else 0
        created = next((item for item in schedules if int(item.get("id") or 0) == created_id), None)
        self.invalidate_context("climate_schedules")
        return {"ok": True, "schedule": created, "schedules": schedules, "context": self.context_meta("climate_schedules")}

    def update_schedule(self, schedule_id: int, data: Dict[str, Any], fetch_schedules: Callable[[], Any]):
        existing = self.fetch_one("select light from hc.climate_schedule_rule where id = %s", (schedule_id,)) or {}
        payload = self.schedule_payload(data, self.normalize_text(existing.get("light"), "off"))
        row = self.execute_one(
            """
            update hc.climate_schedule_rule
            set label = %s,
                day_of_week = %s,
                start_time = %s::time,
                is_enabled = %s,
                power = %s,
                mode = %s,
                target_temperature = %s,
                fan_speed = %s,
                light = %s,
                rule_engine = %s::jsonb,
                updated_at = now()
            where id = %s
            returning *
            """,
            (
                payload["label"], payload["day_of_week"], payload["start_time"], payload["is_enabled"],
                payload["power"], payload["mode"], payload["target_temperature"], payload["fan_speed"],
                payload["light"], payload["rule_engine"], schedule_id,
            ),
        )
        if not row:
            return None
        schedules = fetch_schedules()
        saved = next((item for item in schedules if int(item.get("id") or 0) == schedule_id), None)
        self.invalidate_context("climate_schedules")
        return {"ok": True, "schedule": saved, "schedules": schedules, "context": self.context_meta("climate_schedules")}

    def delete_schedule(self, schedule_id: int, fetch_schedules: Callable[[], Any]):
        row = self.execute_one("delete from hc.climate_schedule_rule where id = %s returning id", (schedule_id,))
        if not row:
            return None
        self.invalidate_context("climate_schedules")
        return {"ok": True, "deleted_id": schedule_id, "schedules": fetch_schedules(), "context": self.context_meta("climate_schedules")}


def _state_value(row: Dict[str, Any]):
    if row.get("v_num") is not None:
        return row.get("v_num")
    if row.get("v_bool") is not None:
        return row.get("v_bool")
    if row.get("v_text") is not None:
        return row.get("v_text")
    return row.get("v_json")


def _measurement_value(row: Dict[str, Any]):
    value = row.get("v_num")
    if value is None:
        value = row.get("v_text")
    if value is None:
        value = row.get("v_bool")
    return {"ts": row.get("ts"), "key": row.get("key"), "value": value}


def _summary_by_key(rows):
    return {
        row["key"]: {
            "sample_count": row.get("sample_count"),
            "min": _round(row.get("min_value"), 2),
            "max": _round(row.get("max_value"), 2),
            "avg": _round(row.get("avg_value"), 2),
            "first_ts": row.get("first_ts"),
            "last_ts": row.get("last_ts"),
        }
        for row in rows
    }


def _distribution_by_key(rows):
    result: Dict[str, Any] = {}
    for row in rows:
        key = row.get("key")
        if not key:
            continue
        result.setdefault(key, [])
        result[key].append(
            {
                "value": row.get("value"),
                "sample_count": row.get("sample_count"),
                "first_ts": row.get("first_ts"),
                "last_ts": row.get("last_ts"),
            }
        )
    return result


def _round(value: Any, digits: int = 2):
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None
