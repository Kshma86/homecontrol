import json
import random
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional


class PowerWallService:
    def __init__(
        self,
        fetch_all: Callable[..., Any],
        fetch_one: Callable[..., Any],
        execute_one: Callable[..., Any],
        publish_mqtt: Callable[..., Any],
        ensure_schema: Callable[[], Any],
        api_cache_get: Callable[[str], Any],
        api_cache_set: Callable[[str, Any, float], Any],
        api_cache_delete_prefix: Callable[[str], Any],
        normalize_text: Callable[..., str],
        guard_repeat_seconds: int,
        process_binding_payload: Callable[[str], Any] = None,
        process_binding_entity_id: Callable[[str], Any] = None,
    ):
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.execute_one = execute_one
        self.publish_mqtt = publish_mqtt
        self.ensure_schema = ensure_schema
        self.api_cache_get = api_cache_get
        self.api_cache_set = api_cache_set
        self.api_cache_delete_prefix = api_cache_delete_prefix
        self.normalize_text = normalize_text
        self.guard_repeat_seconds = guard_repeat_seconds
        self.process_binding_payload = process_binding_payload
        self.process_binding_entity_id = process_binding_entity_id

    def marten_motion_payload(self):
        self.ensure_schema()
        cache_key = "marten_motion"
        cached = self.api_cache_get(cache_key)
        if cached is not None:
            return cached

        entity_id = None
        binding = None
        if self.process_binding_entity_id:
            entity_id = self.process_binding_entity_id("marten_motion_sensor")
        if self.process_binding_payload:
            binding = self.process_binding_payload("marten_motion_sensor")
            entity_id = entity_id or binding.get("selected_entity_id") or binding.get("selected_entity", {}).get("entity_id")

        if not entity_id:
            payload = {
                "ok": False,
                "error": "marten motion sensor not configured",
                "binding": binding,
                "sensor": None,
                "state": {},
                "events": [],
                "summary": {"motion_24h": 0, "last_motion_at": None},
            }
            return self.api_cache_set(cache_key, payload, 8)

        sensor = self.fetch_one(
            """
            select
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              d.platform,
              d.ext_id,
              d.name as device_name,
              d.location,
              d.model,
              d.manufacturer,
              p.status,
              p.last_seen_ts
            from hc.entity e
            join hc.device d on d.id = e.device_id
            left join hc.entity_presence p on p.entity_id = e.id
            where e.id = %s
              and e.is_active = true
              and d.is_active = true
            """,
            (entity_id,),
        )
        if not sensor:
            payload = {
                "ok": False,
                "error": "marten motion sensor entity not found",
                "binding": binding,
                "sensor": None,
                "state": {},
                "events": [],
                "summary": {"motion_24h": 0, "last_motion_at": None},
            }
            return self.api_cache_set(cache_key, payload, 8)

        state_rows = self.fetch_all(
            """
            select key, ts, v_num, v_bool, v_text, v_json, meta
            from hc.entity_state
            where entity_id = %s
              and key in ('occupancy', 'motion', 'presence', 'battery', 'battery_low', 'linkquality')
            order by key
            """,
            (entity_id,),
        )
        state = {}
        for row in state_rows:
            value = row.get("v_bool")
            if value is None:
                value = row.get("v_num")
            if value is None:
                value = row.get("v_text")
            if value is None:
                value = row.get("v_json")
            state[row["key"]] = {"value": value, "ts": row["ts"], "meta": row.get("meta")}

        events = self.fetch_all(
            """
            select
              m.ts,
              m.key,
              coalesce(m.v_bool, false) as motion,
              m.v_num,
              m.v_text,
              m.meta
            from hc.measurement m
            where m.entity_id = %s
              and m.key in ('occupancy', 'motion', 'presence')
              and m.ts >= now() - interval '7 days'
              and coalesce(m.v_bool, m.v_num <> 0, lower(coalesce(m.v_text, '')) in ('true', 'on', '1', 'yes')) = true
            order by m.ts desc
            limit 200
            """,
            (entity_id,),
        )
        summary = self.fetch_one(
            """
            select
              count(*) filter (where ts >= now() - interval '24 hours')::int as motion_24h,
              max(ts) as last_motion_at
            from hc.measurement
            where entity_id = %s
              and key in ('occupancy', 'motion', 'presence')
              and coalesce(v_bool, v_num <> 0, lower(coalesce(v_text, '')) in ('true', 'on', '1', 'yes')) = true
            """,
            (entity_id,),
        ) or {}

        return self.api_cache_set(cache_key, {
            "ok": True,
            "binding": binding,
            "sensor": sensor,
            "state": state,
            "events": events,
            "summary": {
                "motion_24h": summary.get("motion_24h") or 0,
                "last_motion_at": summary.get("last_motion_at"),
            },
        }, 8)

    def bool_from_request_value(self, value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = self.normalize_text(value, "").lower()
        if text in {"1", "true", "on", "yes"}:
            return True
        if text in {"0", "false", "off", "no"}:
            return False
        return None

    def command_entity(self, entity_id: Any):
        return self.fetch_one(
            """
            select
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              d.platform,
              d.ext_id
            from hc.entity e
            join hc.device d on d.id = e.device_id
            where e.id = %s
              and e.is_active = true
              and d.is_active = true
              and d.platform in ('zigbee', 'tuya')
            """,
            (entity_id,),
        )

    def tuya_command_entity(self, entity_id: Any = None, entity_name: str = ""):
        if entity_id:
            return self.fetch_one(
                """
                select e.id as entity_id, e.name as entity_name, d.ext_id
                from hc.entity e
                join hc.device d on d.id = e.device_id
                where e.id = %s
                  and e.is_active = true
                  and d.is_active = true
                  and d.platform = 'tuya'
                """,
                (entity_id,),
            )
        return self.fetch_one(
            """
            select e.id as entity_id, e.name as entity_name, d.ext_id
            from hc.entity e
            join hc.device d on d.id = e.device_id
            where e.name = %s
              and e.is_active = true
              and d.is_active = true
              and d.platform = 'tuya'
            """,
            (entity_name,),
        )

    def apply_display_names(self, devices: list):
        by_name: Dict[str, list] = {}
        for row in devices:
            key = self.normalize_text(row.get("power_wall_display_name") or row.get("entity_name")).casefold()
            if key:
                by_name.setdefault(key, []).append(row)

        for row in devices:
            entity_name = (
                self.normalize_text(row.get("power_wall_display_name"))
                or self.normalize_text(row.get("entity_name"))
                or self.normalize_text(row.get("device_name"))
                or "Socket"
            )
            duplicates = by_name.get(entity_name.casefold(), [])
            if len(duplicates) <= 1:
                row["display_name"] = entity_name
                continue
            location = self.normalize_text(row.get("location"))
            platform = self.normalize_text(row.get("platform")).upper()
            suffix = location or platform or self.normalize_text(row.get("ext_id"))
            row["display_name"] = f"{entity_name} ({suffix})" if suffix else entity_name
        return devices

    def publish_switch(self, row: Dict[str, Any], value: bool, source: str = "homecontrol-power-wall"):
        if row["platform"] == "tuya":
            topic = f"homecontrol/cmd/tuya/{row['entity_name']}/switch"
            payload = {
                "value": value,
                "entity_id": row["entity_id"],
                "entity_name": row["entity_name"],
                "source": source,
                "ts": int(time.time()),
            }
        else:
            if not row.get("topic_base"):
                return False, "zigbee topic_base is missing", "", {}
            topic = f"{row['topic_base']}/set"
            payload = {"state": "ON" if value else "OFF"}
        ok, message = self.publish_mqtt(topic, payload)
        return ok, message, topic, payload

    def parse_hhmm(self, value: Any, fallback: str = "20:00"):
        text = self.normalize_text(value, fallback)
        try:
            return datetime.strptime(text, "%H:%M").time()
        except ValueError:
            raise ValueError(f"{text} must use HH:MM format")

    @staticmethod
    def int_range_value(value: Any, default: int, minimum: int, maximum: int):
        if value is None or value == "":
            return default
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValueError("value must be an integer")
        return max(minimum, min(maximum, number))

    @staticmethod
    def is_time_in_window(now_time, start_time, end_time):
        if start_time == end_time:
            return True
        if start_time < end_time:
            return start_time <= now_time < end_time
        return now_time >= start_time or now_time < end_time

    @staticmethod
    def random_minutes(row: Dict[str, Any], min_key: str, max_key: str, jitter_key: str = "scheduler_jitter_minutes"):
        low = int(row.get(min_key) or 1)
        high = int(row.get(max_key) or low)
        if high < low:
            high = low
        jitter = max(0, int(row.get(jitter_key) or 0))
        minutes = random.randint(low, high)
        if jitter:
            minutes += random.randint(-jitter, jitter)
        return max(1, minutes)

    def scheduler_rows(self):
        return self.fetch_all(
            """
            select
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              d.platform,
              d.ext_id,
              p.status,
              s.v_bool as switch_bool,
              wp.scheduler_window_start,
              wp.scheduler_window_end,
              wp.scheduler_min_on_minutes,
              wp.scheduler_max_on_minutes,
              wp.scheduler_min_off_minutes,
              wp.scheduler_max_off_minutes,
              wp.scheduler_jitter_minutes,
              active.id as session_id,
              active.status as session_status,
              active.planned_start_at,
              active.planned_end_at,
              active.actual_start_at
            from hc.power_wall_policy wp
            join hc.entity e on e.id = wp.entity_id
            join hc.device d on d.id = e.device_id
            left join hc.entity_presence p on p.entity_id = e.id
            left join hc.entity_state s on s.entity_id = e.id and s.key = 'switch_state'
            left join lateral (
              select *
              from hc.power_wall_schedule_session ps
              where ps.entity_id = e.id
                and ps.status in ('planned', 'running')
              order by ps.planned_start_at desc
              limit 1
            ) active on true
            where wp.scheduler_enabled = true
              and coalesce(wp.always_on, false) = false
              and e.is_active = true
              and d.is_active = true
              and d.platform in ('zigbee', 'tuya')
            order by e.name
            """
        )

    def scheduler_tick(self):
        self.ensure_schema()
        now = datetime.now().astimezone()
        for row in self.scheduler_rows():
            online = (row.get("status") or "unknown") == "online"
            in_window = self.is_time_in_window(now.time(), row["scheduler_window_start"], row["scheduler_window_end"])
            switch_on = row.get("switch_bool") is True
            session_status = row.get("session_status")

            if not in_window:
                if switch_on:
                    ok, message, topic, payload = self.publish_switch(row, False, "homecontrol-power-wall-scheduler")
                    action = json.dumps({"topic": topic, "payload": payload, "ok": ok, "reason": "outside_window"}, ensure_ascii=False)
                    if session_status == "running":
                        self.execute_one(
                            """
                            update hc.power_wall_schedule_session
                            set actual_end_at = now(),
                                status = case when %s then 'completed' else 'failed' end,
                                stop_action = %s::jsonb,
                                error = %s,
                                updated_at = now()
                            where id = %s
                            returning id
                            """,
                            (ok, action, None if ok else message, row["session_id"]),
                        )
                    print(f"[POWER_WALL] scheduler off entity={row['entity_name']} ok={ok} message={message}", flush=True)
                elif session_status in {"planned", "running"}:
                    self.execute_one(
                        """
                        update hc.power_wall_schedule_session
                        set status = 'cancelled',
                            error = 'outside scheduler window',
                            updated_at = now()
                        where id = %s
                        returning id
                        """,
                        (row["session_id"],),
                    )
                continue

            if not online:
                continue

            if session_status == "planned":
                if row["planned_start_at"] and row["planned_start_at"] <= now:
                    duration = self.random_minutes(row, "scheduler_min_on_minutes", "scheduler_max_on_minutes")
                    ok, message, topic, payload = self.publish_switch(row, True, "homecontrol-power-wall-scheduler")
                    action = json.dumps({"topic": topic, "payload": payload, "ok": ok, "duration_minutes": duration}, ensure_ascii=False)
                    self.execute_one(
                        """
                        update hc.power_wall_schedule_session
                        set actual_start_at = now(),
                            planned_end_at = now() + (%s::text || ' minutes')::interval,
                            duration_minutes = %s,
                            status = case when %s then 'running' else 'failed' end,
                            start_action = %s::jsonb,
                            error = %s,
                            updated_at = now()
                        where id = %s
                        returning id
                        """,
                        (duration, duration, ok, action, None if ok else message, row["session_id"]),
                    )
                    print(f"[POWER_WALL] scheduler on entity={row['entity_name']} duration={duration} ok={ok} message={message}", flush=True)
                continue

            if session_status == "running":
                if row["planned_end_at"] and row["planned_end_at"] <= now:
                    ok, message, topic, payload = self.publish_switch(row, False, "homecontrol-power-wall-scheduler")
                    action = json.dumps({"topic": topic, "payload": payload, "ok": ok, "reason": "duration_elapsed"}, ensure_ascii=False)
                    self.execute_one(
                        """
                        update hc.power_wall_schedule_session
                        set actual_end_at = now(),
                            status = case when %s then 'completed' else 'failed' end,
                            stop_action = %s::jsonb,
                            error = %s,
                            updated_at = now()
                        where id = %s
                        returning id
                        """,
                        (ok, action, None if ok else message, row["session_id"]),
                    )
                    print(f"[POWER_WALL] scheduler stop entity={row['entity_name']} ok={ok} message={message}", flush=True)
                continue

            if not switch_on:
                delay = self.random_minutes(row, "scheduler_min_off_minutes", "scheduler_max_off_minutes")
                self.execute_one(
                    """
                    insert into hc.power_wall_schedule_session (entity_id, planned_start_at, status)
                    values (%s, now() + (%s::text || ' minutes')::interval, 'planned')
                    returning id
                    """,
                    (row["entity_id"], delay),
                )
                print(f"[POWER_WALL] scheduler planned entity={row['entity_name']} delay={delay}", flush=True)

    def sync_auto_climate(self, power: str):
        self.ensure_schema()
        if power not in {"on", "off"}:
            return []
        target = power == "on"
        selected_entity_id = self.process_binding_entity_id("climate_extra_fan_socket") if self.process_binding_entity_id else None
        rows = self.fetch_all(
            """
            select
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              d.platform,
              d.ext_id
            from hc.power_wall_policy wp
            join hc.entity e on e.id = wp.entity_id
            join hc.device d on d.id = e.device_id
            where (
                (%s::bigint is not null and e.id = %s::bigint)
                or (%s::bigint is null and wp.auto_climate = true)
              )
              and e.is_active = true
              and d.is_active = true
              and d.platform in ('zigbee', 'tuya')
            order by e.name
            """
            ,
            (selected_entity_id, selected_entity_id, selected_entity_id),
        )
        results = []
        for row in rows:
            ok, message, topic, payload = self.publish_switch(row, target, "homecontrol-climate-auto")
            self.execute_one(
                """
                update hc.power_wall_policy
                set last_action_at = now(),
                    last_action = %s,
                    last_error = %s,
                    updated_at = now()
                where entity_id = %s
                returning entity_id
                """,
                (f"climate_auto_{power}", None if ok else message, row["entity_id"]),
            )
            results.append({
                "ok": ok,
                "message": message,
                "entity_id": row["entity_id"],
                "entity_name": row["entity_name"],
                "topic": topic,
                "payload": payload,
            })
        return results

    def guard_tick(self):
        self.ensure_schema()
        rows = self.fetch_all(
            """
            select
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              d.platform,
              p.status,
              s.v_bool as switch_bool,
              wp.last_action_at
            from hc.power_wall_policy wp
            join hc.entity e on e.id = wp.entity_id
            join hc.device d on d.id = e.device_id
            left join hc.entity_presence p on p.entity_id = e.id
            left join hc.entity_state s on s.entity_id = e.id and s.key = 'switch_state'
            where wp.always_on = true
              and e.is_active = true
              and d.is_active = true
              and d.platform in ('zigbee', 'tuya')
              and coalesce(p.status, 'unknown') = 'online'
              and s.v_bool is false
              and (
                wp.last_action_at is null
                or wp.last_action_at < now() - (%s::text || ' seconds')::interval
              )
            order by wp.last_action_at nulls first, e.name
            """,
            (self.guard_repeat_seconds,),
        )
        for row in rows:
            ok, message, topic, payload = self.publish_switch(row, True, "homecontrol-power-wall-always-on")
            self.execute_one(
                """
                update hc.power_wall_policy
                set last_action_at = now(),
                    last_action = %s,
                    last_error = %s
                where entity_id = %s
                returning entity_id
                """,
                (
                    json.dumps({"topic": topic, "payload": payload, "ok": ok}, ensure_ascii=False),
                    None if ok else message,
                    row["entity_id"],
                ),
            )
            print(
                f"[POWER_WALL] always_on entity={row['entity_name']} platform={row['platform']} ok={ok} message={message}",
                flush=True,
            )

    def state_payload(self):
        self.ensure_schema()
        cached = self.api_cache_get("power_wall_state")
        if cached is not None:
            return cached
        battery_devices = self.fetch_all(
            """
            select
              d.id as device_id,
              d.platform,
              d.ext_id,
              d.name as device_name,
              d.location,
              d.model,
              d.manufacturer,
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              p.status,
              p.last_seen_ts,
              p.updated_at as presence_updated_at,
              b.v_num as battery_percent,
              b.ts as battery_ts,
              bl.v_bool as battery_low,
              bl.ts as battery_low_ts,
              lq.v_num as linkquality,
              lq.ts as linkquality_ts
            from hc.entity e
            join hc.device d on d.id = e.device_id
            left join hc.entity_presence p on p.entity_id = e.id
            left join hc.entity_state b on b.entity_id = e.id and b.key = 'battery'
            left join hc.entity_state bl on bl.entity_id = e.id and bl.key = 'battery_low'
            left join hc.entity_state lq on lq.entity_id = e.id and lq.key = 'linkquality'
            where d.is_active = true
              and e.is_active = true
              and d.platform = 'zigbee'
              and (
                exists (
                  select 1
                  from hc.entity_metric em
                  where em.entity_id = e.id
                    and em.metric_key in ('battery', 'battery_low')
                )
                or b.entity_id is not null
                or bl.entity_id is not null
              )
              and not exists (
                select 1
                from hc.entity_metric em_power
                where em_power.entity_id = e.id
                  and em_power.metric_key in (
                    'switch_state', 'power', 'power_w', 'current', 'current_a',
                    'mains_voltage_v', 'voltage_v', 'energy_kwh', 'energy_calc_kwh'
                  )
              )
            order by
              case
                when coalesce(bl.v_bool, false) then 0
                when b.v_num is null then 1
                when b.v_num <= 15 then 0
                when b.v_num <= 30 then 1
                else 2
              end,
              b.v_num nulls first,
              d.location nulls last,
              e.name
            """
        )
        devices = self.fetch_all(
            """
            select
              d.id as device_id,
              d.platform,
              d.ext_id,
              d.name as device_name,
              d.location,
              d.model,
              d.manufacturer,
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              coalesce(wp.always_on, false) as always_on,
              wp.display_name as power_wall_display_name,
              coalesce(wp.auto_climate, false) as auto_climate,
              coalesce(wp.scheduler_enabled, false) as scheduler_enabled,
              to_char(coalesce(wp.scheduler_window_start, '20:00'::time), 'HH24:MI') as scheduler_window_start,
              to_char(coalesce(wp.scheduler_window_end, '06:00'::time), 'HH24:MI') as scheduler_window_end,
              coalesce(wp.scheduler_min_on_minutes, 12) as scheduler_min_on_minutes,
              coalesce(wp.scheduler_max_on_minutes, 35) as scheduler_max_on_minutes,
              coalesce(wp.scheduler_min_off_minutes, 20) as scheduler_min_off_minutes,
              coalesce(wp.scheduler_max_off_minutes, 90) as scheduler_max_off_minutes,
              coalesce(wp.scheduler_jitter_minutes, 5) as scheduler_jitter_minutes,
              wp.updated_at as policy_updated_at,
              wp.last_action_at as policy_last_action_at,
              wp.last_action as policy_last_action,
              wp.last_error as policy_last_error,
              p.status,
              p.last_seen_ts,
              p.updated_at as presence_updated_at
            from hc.device d
            join hc.entity e on e.device_id = d.id
            left join hc.entity_presence p on p.entity_id = e.id
            left join hc.power_wall_policy wp on wp.entity_id = e.id
            where d.platform in ('zigbee', 'tuya')
              and d.is_active = true
              and e.is_active = true
              and (
                (
                  d.platform = 'tuya'
                  and exists (
                    select 1
                    from hc.entity_metric em
                    where em.entity_id = e.id
                      and em.metric_key = 'switch_state'
                  )
                )
                or (
                  d.platform = 'zigbee'
                  and exists (
                    select 1
                    from hc.entity_metric em
                    where em.entity_id = e.id
                      and em.metric_key in (
                        'switch_state', 'power', 'power_w', 'current', 'current_a',
                        'mains_voltage_v', 'voltage_v', 'energy_kwh'
                      )
                    )
                )
              )
            order by d.platform, e.name
            """
        )
        entity_ids = [row["entity_id"] for row in devices]
        if not entity_ids:
            battery_low_count = sum(
                1 for row in battery_devices
                if row.get("battery_low") is True or (row.get("battery_percent") is not None and float(row["battery_percent"]) <= 30)
            )
            bindings = {}
            if self.process_binding_payload:
                bindings["marten_power_socket"] = self.process_binding_payload("marten_power_socket")
                bindings["marten_motion_sensor"] = self.process_binding_payload("marten_motion_sensor")
                bindings["climate_extra_fan_socket"] = self.process_binding_payload("climate_extra_fan_socket")
            return self.api_cache_set("power_wall_state", {
                "devices": [],
                "battery_devices": battery_devices,
                "state_rows": [],
                "recent_measurements": [],
                "marten_motion": self.marten_motion_payload(),
                "process_bindings": bindings,
                "summary": {
                    "total": 0,
                    "zigbee": 0,
                    "tuya": 0,
                    "battery_total": len(battery_devices),
                    "battery_low": battery_low_count,
                },
            }, 8)

        state_rows = self.fetch_all(
            """
            select
              s.entity_id,
              e.name as entity_name,
              d.platform,
              s.key,
              s.ts,
              s.v_num,
              s.v_bool,
              s.v_text,
              s.v_json,
              s.meta
            from hc.entity_state s
            join hc.entity e on e.id = s.entity_id
            join hc.device d on d.id = e.device_id
            where s.entity_id = any(%s)
              and s.key in (
                'switch_state', 'state', 'power', 'power_w', 'current', 'current_a',
                'mains_voltage_v', 'voltage_v', 'energy_kwh', 'lag_sec'
              )
            order by d.platform, e.name, s.key
            """,
            (entity_ids,),
        )
        recent_measurements = self.fetch_all(
            """
            select
              m.entity_id,
              e.name as entity_name,
              d.platform,
              m.key,
              count(*) as sample_count,
              max(m.ts) as last_ts,
              avg(m.v_num) filter (where m.v_num is not null) as avg_num,
              max(m.v_num) filter (where m.v_num is not null) as max_num,
              min(m.v_num) filter (where m.v_num is not null) as min_num
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            where m.entity_id = any(%s)
              and m.ts > now() - interval '6 hours'
              and m.key in ('power', 'power_w', 'current', 'current_a', 'energy_kwh')
            group by m.entity_id, e.name, d.platform, m.key
            order by d.platform, e.name, m.key
            """,
            (entity_ids,),
        )

        state_by_entity: Dict[int, Dict[str, Any]] = {}
        for row in state_rows:
            value = row.get("v_num")
            if value is None:
                value = row.get("v_bool")
            if value is None:
                value = row.get("v_text")
            if value is None:
                value = row.get("v_json")
            state_by_entity.setdefault(row["entity_id"], {})[row["key"]] = {
                "value": value,
                "ts": row["ts"],
                "meta": row.get("meta"),
            }

        for row in devices:
            row["state"] = state_by_entity.get(row["entity_id"], {})
        self.apply_display_names(devices)
        display_name_by_entity = {row["entity_id"]: row.get("display_name") for row in devices}
        for row in state_rows:
            row["display_name"] = display_name_by_entity.get(row["entity_id"]) or row.get("entity_name")
        for row in recent_measurements:
            row["display_name"] = display_name_by_entity.get(row["entity_id"]) or row.get("entity_name")

        statuses = [(row.get("status") or "unknown") for row in devices]
        summary = {
            "total": len(devices),
            "zigbee": sum(1 for row in devices if row["platform"] == "zigbee"),
            "tuya": sum(1 for row in devices if row["platform"] == "tuya"),
            "online": sum(1 for status in statuses if status == "online"),
            "degraded": sum(1 for status in statuses if status == "degraded"),
            "offline": sum(1 for status in statuses if status == "offline"),
            "unknown": sum(1 for status in statuses if status not in {"online", "degraded", "offline"}),
            "battery_total": len(battery_devices),
            "battery_low": sum(
                1 for row in battery_devices
                if row.get("battery_low") is True or (row.get("battery_percent") is not None and float(row["battery_percent"]) <= 30)
            ),
        }
        bindings = {}
        if self.process_binding_payload:
            bindings["marten_power_socket"] = self.process_binding_payload("marten_power_socket")
            bindings["marten_motion_sensor"] = self.process_binding_payload("marten_motion_sensor")
            bindings["climate_extra_fan_socket"] = self.process_binding_payload("climate_extra_fan_socket")
        return self.api_cache_set("power_wall_state", {
            "devices": devices,
            "battery_devices": battery_devices,
            "state_rows": state_rows,
            "recent_measurements": recent_measurements,
            "marten_motion": self.marten_motion_payload(),
            "process_bindings": bindings,
            "summary": summary,
        }, 8)

    def history_payload(self, entity_id: int):
        self.ensure_schema()
        cache_key = f"power_wall_history:{entity_id}"
        cached = self.api_cache_get(cache_key)
        if cached is not None:
            return cached

        entity = self.fetch_one(
            """
            select
              e.id as entity_id,
              e.name as entity_name,
              d.platform,
              d.ext_id,
              p.status,
              p.last_seen_ts
            from hc.entity e
            join hc.device d on d.id = e.device_id
            left join hc.entity_presence p on p.entity_id = e.id
            where e.id = %s
              and e.is_active = true
              and d.is_active = true
              and d.platform in ('zigbee', 'tuya')
              and exists (
                select 1
                from hc.entity_metric em
                where em.entity_id = e.id
                  and em.metric_key in ('power', 'power_w')
              )
            """,
            (entity_id,),
        )
        if not entity:
            return None

        rows = self.fetch_all(
            """
            select ts, key, v_num as power_w
            from hc.measurement
            where entity_id = %s
              and key in ('power', 'power_w')
              and ts >= now() - interval '24 hours'
              and v_num is not null
            order by ts
            limit 2000
            """,
            (entity_id,),
        )
        return self.api_cache_set(cache_key, {
            "ok": True,
            "entity": entity,
            "power_24h": rows,
            "summary": {
                "samples": len(rows),
                "max_power_w": max((row.get("power_w") or 0 for row in rows), default=0),
                "latest_power_w": rows[-1].get("power_w") if rows else None,
            },
        }, 30)

    def set_policy(self, entity_id: Any, *, always_on_marker: Any = None, auto_climate_marker: Any = None):
        self.ensure_schema()
        has_always_on = always_on_marker is not None
        has_auto_climate = auto_climate_marker is not None
        always_on = self.bool_from_request_value(always_on_marker) if has_always_on else None
        auto_climate = self.bool_from_request_value(auto_climate_marker) if has_auto_climate else None
        if not has_always_on and not has_auto_climate:
            raise ValueError("always_on or auto_climate is required")
        if has_always_on and always_on is None:
            raise ValueError("always_on must be true/false")
        if has_auto_climate and auto_climate is None:
            raise ValueError("auto_climate must be true/false")
        row = self.command_entity(entity_id)
        if not row:
            return None, None
        policy = self.execute_one(
            """
            insert into hc.power_wall_policy (entity_id, always_on, auto_climate, scheduler_enabled, updated_at)
            values (%s, coalesce(%s, false), coalesce(%s, false), false, now())
            on conflict (entity_id) do update set
              always_on = case when %s then excluded.always_on else hc.power_wall_policy.always_on end,
              auto_climate = case when %s then excluded.auto_climate else hc.power_wall_policy.auto_climate end,
              scheduler_enabled = case when %s and excluded.always_on then false else hc.power_wall_policy.scheduler_enabled end,
              updated_at = now()
            returning *
            """,
            (entity_id, always_on, auto_climate, has_always_on, has_auto_climate, has_always_on),
        )
        self.api_cache_delete_prefix("power_wall_state")
        return row, policy

    def set_display_name(self, entity_id: Any, display_name: str):
        self.ensure_schema()
        if display_name is not None and len(display_name) > 80:
            raise ValueError("display_name must be 80 characters or shorter")
        row = self.command_entity(entity_id)
        if not row:
            return None, None
        policy = self.execute_one(
            """
            insert into hc.power_wall_policy (entity_id, display_name, updated_at)
            values (%s, %s, now())
            on conflict (entity_id) do update set
              display_name = excluded.display_name,
              updated_at = now()
            returning *
            """,
            (entity_id, display_name or None),
        )
        self.api_cache_delete_prefix("power_wall_state")
        return row, policy

    def set_scheduler_policy(self, entity_id: Any, data: Dict[str, Any]):
        self.ensure_schema()
        enabled = self.bool_from_request_value(data.get("enabled"))
        if enabled is None:
            raise ValueError("enabled must be true/false")
        window_start = self.parse_hhmm(data.get("window_start"), "20:00")
        window_end = self.parse_hhmm(data.get("window_end"), "06:00")
        min_on = self.int_range_value(data.get("min_on_minutes"), 12, 1, 1440)
        max_on = self.int_range_value(data.get("max_on_minutes"), 35, 1, 1440)
        min_off = self.int_range_value(data.get("min_off_minutes"), 20, 1, 1440)
        max_off = self.int_range_value(data.get("max_off_minutes"), 90, 1, 1440)
        jitter = self.int_range_value(data.get("jitter_minutes"), 5, 0, 240)
        if max_on < min_on:
            raise ValueError("max_on_minutes must be greater than or equal to min_on_minutes")
        if max_off < min_off:
            raise ValueError("max_off_minutes must be greater than or equal to min_off_minutes")

        row = self.command_entity(entity_id)
        if not row:
            return None, None
        policy = self.execute_one(
            """
            insert into hc.power_wall_policy (
              entity_id,
              always_on,
              scheduler_enabled,
              scheduler_window_start,
              scheduler_window_end,
              scheduler_min_on_minutes,
              scheduler_max_on_minutes,
              scheduler_min_off_minutes,
              scheduler_max_off_minutes,
              scheduler_jitter_minutes,
              updated_at
            )
            values (%s, false, %s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (entity_id) do update set
              always_on = case when excluded.scheduler_enabled then false else hc.power_wall_policy.always_on end,
              scheduler_enabled = excluded.scheduler_enabled,
              scheduler_window_start = excluded.scheduler_window_start,
              scheduler_window_end = excluded.scheduler_window_end,
              scheduler_min_on_minutes = excluded.scheduler_min_on_minutes,
              scheduler_max_on_minutes = excluded.scheduler_max_on_minutes,
              scheduler_min_off_minutes = excluded.scheduler_min_off_minutes,
              scheduler_max_off_minutes = excluded.scheduler_max_off_minutes,
              scheduler_jitter_minutes = excluded.scheduler_jitter_minutes,
              updated_at = now()
            returning *
            """,
            (entity_id, enabled, window_start, window_end, min_on, max_on, min_off, max_off, jitter),
        )
        if not enabled:
            self.execute_one(
                """
                update hc.power_wall_schedule_session
                set status = 'cancelled',
                    error = 'scheduler disabled',
                    updated_at = now()
                where entity_id = %s
                  and status = 'planned'
                returning id
                """,
                (entity_id,),
            )
        self.api_cache_delete_prefix("power_wall_state")
        return row, policy

    def scheduler_sessions(self, entity_id: int, limit: int = 40):
        self.ensure_schema()
        row = self.command_entity(entity_id)
        if not row:
            return None, None
        rows = self.fetch_all(
            """
            select
              id,
              entity_id,
              planned_start_at,
              planned_end_at,
              actual_start_at,
              actual_end_at,
              duration_minutes,
              status,
              error,
              created_at,
              updated_at
            from hc.power_wall_schedule_session
            where entity_id = %s
            order by coalesce(actual_start_at, planned_start_at) desc
            limit %s
            """,
            (entity_id, max(1, min(120, int(limit)))),
        )
        return row, rows

    def switch_command(self, entity_id: Any, value: bool):
        self.ensure_schema()
        row = self.command_entity(entity_id)
        if not row:
            return None, None
        ok, message, topic, payload = self.publish_switch(row, value)
        if topic:
            self.api_cache_delete_prefix("power_wall_state")
        return row, {"ok": ok, "message": message, "topic": topic, "payload": payload}

    def tuya_switch_command(self, entity_id: Any, entity_name: str, value: bool):
        row = self.tuya_command_entity(entity_id=entity_id, entity_name=entity_name)
        if not row:
            return None, None
        topic = f"homecontrol/cmd/tuya/{row['entity_name']}/switch"
        payload = {
            "value": value,
            "entity_id": row["entity_id"],
            "entity_name": row["entity_name"],
            "source": "homecontrol-tuya-tab",
            "ts": int(time.time()),
        }
        ok, message = self.publish_mqtt(topic, payload)
        self.api_cache_delete_prefix("power_wall_state")
        self.api_cache_delete_prefix("tuya_state")
        return row, {"ok": ok, "message": message, "topic": topic, "payload": payload}
