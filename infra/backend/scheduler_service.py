from datetime import datetime
from threading import Lock
from typing import Any, Callable, Dict, Iterable, Optional


class SchedulerService:
    def __init__(
        self,
        fetch_all: Callable[..., Any],
        fetch_one: Callable[..., Any],
        execute_one: Callable[..., Any],
        ensure_schema: Callable[[], Any],
        normalize_text: Callable[..., str],
        json_time: Callable[[Any], Any],
        json_dumps: Callable[[Any], str],
        fetch_irrigation_schedules: Callable[[], Any],
        fetch_climate_schedule_rules: Callable[[], Any],
        x10_scheduler_entries: Callable[[], Any],
        x10_day_mask_index_by_hc_day: Callable[[], Any],
        scheduler_modes: Iterable[str],
        v2_execution_enabled: bool,
        v2_allow_irrigation: bool,
        v2_allow_x10: bool,
        v2_allow_climate: bool,
        evaluate_irrigation_pilot: Optional[Callable[..., Dict[str, Any]]] = None,
        fetch_irrigation_v2_session: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
        irrigation_command_topic: Optional[Callable[[], str]] = None,
        x10_schedule_clean_topic: str = "",
        x10_weekly_schedule_topic: str = "",
        climate_command_topic: str = "",
        climate_state_payload: Optional[Callable[[], Dict[str, Any]]] = None,
        publish_mqtt: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        sync_auto_climate_power_wall: Optional[Callable[[str], Any]] = None,
        x10_monitor_value: Optional[Callable[[str], Any]] = None,
        check_db: Optional[Callable[[], bool]] = None,
        check_mqtt: Optional[Callable[..., bool]] = None,
        manual_valve_scheduler_guard: Optional[Callable[[], Dict[str, Any]]] = None,
        running_irrigation_session: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
        execute_sql: Optional[Callable[[str], Any]] = None,
        now: Optional[Callable[[Any], datetime]] = None,
    ):
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.execute_one = execute_one
        self.ensure_schema_callback = ensure_schema
        self.execute_sql = execute_sql
        self._schema_ready = False
        self._schema_lock = Lock()
        self.normalize_text = normalize_text
        self.json_time = json_time
        self.json_dumps = json_dumps
        self.fetch_irrigation_schedules = fetch_irrigation_schedules
        self.fetch_climate_schedule_rules = fetch_climate_schedule_rules
        self.x10_scheduler_entries = x10_scheduler_entries
        self.x10_day_mask_index_by_hc_day = x10_day_mask_index_by_hc_day
        self.x10_monitor_value = x10_monitor_value
        self.scheduler_modes = set(scheduler_modes)
        self.v2_execution_enabled = bool(v2_execution_enabled)
        self.v2_allow_irrigation = bool(v2_allow_irrigation)
        self.v2_allow_x10 = bool(v2_allow_x10)
        self.v2_allow_climate = bool(v2_allow_climate)
        self.evaluate_irrigation_pilot = evaluate_irrigation_pilot
        self.fetch_irrigation_v2_session = fetch_irrigation_v2_session
        self.irrigation_command_topic = irrigation_command_topic
        self.x10_schedule_clean_topic = x10_schedule_clean_topic
        self.x10_weekly_schedule_topic = x10_weekly_schedule_topic
        self.climate_command_topic = climate_command_topic
        self.climate_state_payload = climate_state_payload
        self.publish_mqtt = publish_mqtt
        self.sync_auto_climate_power_wall = sync_auto_climate_power_wall
        self.check_db = check_db
        self.check_mqtt = check_mqtt
        self.manual_valve_scheduler_guard = manual_valve_scheduler_guard
        self.running_irrigation_session = running_irrigation_session
        self.now = now or (lambda tz=None: datetime.now(tz))

    @staticmethod
    def normalized_segment_list(value: Any):
        if isinstance(value, list):
            items = value
        else:
            items = str(value or "").split(",")
        result = []
        for item in items:
            try:
                number = int(str(item).strip())
            except Exception:
                continue
            if number:
                result.append(number)
        return result

    @staticmethod
    def climate_command_from_payload(payload: Dict[str, Any]):
        command = {
            "power": payload.get("power") or "on",
            "mode": payload.get("climate_mode") or "heat",
            "target_temperature": payload.get("target_temperature"),
            "fan_speed": payload.get("fan_speed") or "auto",
            "light": payload.get("light") or "off",
            "shadow_only": True,
        }
        if not command.get("mode"):
            command["mode"] = payload.get("schedule_mode") or "heat"
        if command.get("target_temperature") is None:
            command["target_temperature"] = 23
        return command

    @staticmethod
    def normalize_x10_scalar(value: Any):
        if value is None:
            return None
        text = str(value).strip()
        if text.lower() in {"none", "null", "undefined", "unknown_none", "unknown_null"}:
            return None
        return text if text != "" else None

    @classmethod
    def normalize_x10_int_text(cls, value: Any):
        text = cls.normalize_x10_scalar(value)
        if text is None:
            return None
        try:
            return str(int(float(text)))
        except Exception:
            return text

    @classmethod
    def x10_command_expected(cls, command_payload: Dict[str, Any]):
        return {
            "start_time": cls.normalize_x10_scalar(command_payload.get("start_time") or command_payload.get("time")),
            "days": cls.normalize_x10_scalar(command_payload.get("days")),
            "enabled": cls.normalize_x10_int_text(command_payload.get("enabled")),
            "map_id": cls.normalize_x10_int_text(command_payload.get("map_id")),
            "mode": cls.normalize_x10_int_text(command_payload.get("mode") or command_payload.get("clean_mode")),
            "suction": cls.normalize_x10_int_text(command_payload.get("suction")),
            "water_level": cls.normalize_x10_int_text(command_payload.get("water_level") or command_payload.get("clean_param")),
            "segments": cls.normalized_segment_list(command_payload.get("segments")),
        }

    @classmethod
    def x10_entry_observed(cls, entry: Dict[str, Any]):
        return {
            "task_id": cls.normalize_x10_scalar(entry.get("task_id")),
            "start_time": cls.normalize_x10_scalar(entry.get("time") or entry.get("start_time")),
            "days": cls.normalize_x10_scalar(entry.get("days")),
            "enabled": cls.normalize_x10_int_text(entry.get("enabled")),
            "map_id": cls.normalize_x10_int_text(entry.get("map_id")),
            "mode": cls.normalize_x10_int_text(entry.get("clean_mode") or entry.get("flag")),
            "suction": cls.normalize_x10_int_text(entry.get("suction")),
            "water_level": cls.normalize_x10_int_text(entry.get("water_level") or entry.get("clean_param")),
            "segments": cls.normalized_segment_list(entry.get("segments")),
            "raw": entry.get("raw"),
        }

    @classmethod
    def x10_entry_matches_command(cls, entry: Dict[str, Any], expected: Dict[str, Any]):
        observed = cls.x10_entry_observed(entry)
        checks = {
            "start_time": observed["start_time"] == expected["start_time"],
            "days": not expected["days"] or observed["days"] == expected["days"],
            "enabled": not expected["enabled"] or observed["enabled"] == expected["enabled"],
            "map_id": not expected["map_id"] or observed["map_id"] == expected["map_id"],
            "mode": not expected["mode"] or observed["mode"] == expected["mode"],
            "suction": not expected["suction"] or observed["suction"] == expected["suction"],
            "water_level": not expected["water_level"] or observed["water_level"] == expected["water_level"],
            "segments": not expected["segments"] or observed["segments"] == expected["segments"],
        }
        return all(checks.values()), checks, observed

    def _monitor_value(self, key: str):
        return self.x10_monitor_value(key) if self.x10_monitor_value else None

    def _to_int(self, value: Any, default: int = 0) -> int:
        if value is None or value == "":
            return default
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return int(round(number))

    def _normalize_climate_text(self, value: Any):
        return self.normalize_text(value, "").lower() or None

    def ensure_scheduler_schema(self):
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            if not self.execute_sql:
                self.ensure_schema_callback()
                self._schema_ready = True
                return
            self.execute_sql(
                """
                create table if not exists hc.scheduler_config (
                  id smallint primary key default 1 check (id = 1),
                  mode text not null default 'v2_execute_all' check (mode in ('v2_execute_irrigation', 'v2_execute_x10', 'v2_execute_climate', 'v2_execute_x10_climate', 'v2_execute_all')),
                  updated_at timestamptz not null default now(),
                  updated_by text not null default 'system',
                  notes text
                );

                update hc.scheduler_config
                set mode = 'v2_execute_all'
                where mode in ('legacy', 'v2_shadow', 'v2_plan_only', 'unified_shadow');

                do $$
                begin
                  alter table hc.scheduler_config
                    drop constraint if exists scheduler_config_mode_check;
                  alter table hc.scheduler_config
                    alter column mode set default 'v2_execute_all';
                  alter table hc.scheduler_config
                    add constraint scheduler_config_mode_check
                    check (mode in ('v2_execute_irrigation', 'v2_execute_x10', 'v2_execute_climate', 'v2_execute_x10_climate', 'v2_execute_all'));
                end $$;

                insert into hc.scheduler_config (id)
                values (1)
                on conflict (id) do nothing;

                create table if not exists hc.scheduler_job (
                  id bigserial primary key,
                  domain text not null,
                  action text not null,
                  label text not null,
                  schedule_kind text not null default 'weekly',
                  day_of_week smallint check (day_of_week between 0 and 6),
                  start_time time,
                  stop_time time,
                  is_enabled boolean not null default false,
                  source text not null default 'unified',
                  source_ref text,
                  payload jsonb not null default '{}'::jsonb,
                  created_at timestamptz not null default now(),
                  updated_at timestamptz not null default now(),
                  unique (domain, source, source_ref)
                );

                create table if not exists hc.scheduler_run (
                  id bigserial primary key,
                  job_id bigint references hc.scheduler_job(id) on delete set null,
                  domain text not null,
                  action text not null,
                  status text not null default 'pending',
                  attempt integer not null default 0,
                  requested_at timestamptz not null default now(),
                  started_at timestamptz,
                  confirmed_started_at timestamptz,
                  stop_requested_at timestamptz,
                  confirmed_stopped_at timestamptz,
                  completed_at timestamptz,
                  error text,
                  payload jsonb not null default '{}'::jsonb,
                  confirmation jsonb not null default '{}'::jsonb
                );

                alter table hc.scheduler_run
                  add column if not exists idempotency_key text;

                create index if not exists ix_scheduler_job_due
                  on hc.scheduler_job (is_enabled, day_of_week, start_time);

                create index if not exists ix_scheduler_run_requested
                  on hc.scheduler_run (requested_at desc);

                create unique index if not exists ux_scheduler_run_idempotency
                  on hc.scheduler_run (idempotency_key)
                  where idempotency_key is not null;

                create table if not exists hc.climate_schedule_rule (
                  id bigserial primary key,
                  label text not null,
                  day_of_week smallint check (day_of_week between 0 and 6),
                  start_time time not null,
                  is_enabled boolean not null default false,
                  power text not null default 'on' check (power in ('on', 'off')),
                  mode text not null default 'heat' check (mode in ('auto', 'cool', 'dry', 'fan', 'heat')),
                  target_temperature integer not null default 23 check (target_temperature between 8 and 30),
                  fan_speed text not null default 'auto' check (fan_speed in ('auto', 'low', 'mediumlow', 'medium', 'mediumhigh', 'high')),
                  light text not null default 'off' check (light in ('on', 'off')),
                  rule_engine jsonb not null default '{}'::jsonb,
                  created_at timestamptz not null default now(),
                  updated_at timestamptz not null default now()
                );

                alter table hc.climate_schedule_rule
                  drop constraint if exists climate_schedule_rule_label_day_of_week_start_time_key;

                insert into hc.climate_schedule_rule (
                  label,
                  day_of_week,
                  start_time,
                  is_enabled,
                  power,
                  mode,
                  target_temperature,
                  fan_speed,
                  light,
                  rule_engine
                )
                select
                  seed.label,
                  seed.day_of_week,
                  seed.start_time,
                  false,
                  'on',
                  'heat',
                  23,
                  'auto',
                  'off',
                  '{"stage":"bootstrap","rule_engine":"manual_schedule"}'::jsonb
                from (values
                  ('Monday', 0::smallint, '06:30'::time),
                  ('Tuesday', 1::smallint, '06:30'::time),
                  ('Wednesday', 2::smallint, '06:30'::time),
                  ('Thursday', 3::smallint, '06:30'::time),
                  ('Friday', 4::smallint, '06:30'::time),
                  ('Saturday', 5::smallint, '06:30'::time),
                  ('Sunday', 6::smallint, '06:30'::time)
                ) as seed(label, day_of_week, start_time)
                where not exists (
                  select 1
                  from hc.climate_schedule_rule existing
                  where existing.day_of_week = seed.day_of_week
                );

                with previous_rule as (
                  select distinct on (day_of_week)
                    day_of_week,
                    start_time,
                    is_enabled,
                    power,
                    mode,
                    target_temperature,
                    fan_speed,
                    light,
                    rule_engine
                  from hc.climate_schedule_rule
                  where label = 'Climate morning comfort'
                  order by day_of_week, id
                ),
                canonical as (
                  select r.id, r.day_of_week
                  from hc.climate_schedule_rule r
                  where r.label in ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
                )
                update hc.climate_schedule_rule target
                set start_time = previous_rule.start_time,
                    is_enabled = previous_rule.is_enabled,
                    power = previous_rule.power,
                    mode = previous_rule.mode,
                    target_temperature = previous_rule.target_temperature,
                    fan_speed = previous_rule.fan_speed,
                    light = previous_rule.light,
                    rule_engine = previous_rule.rule_engine,
                    updated_at = now()
                from canonical
                join previous_rule on previous_rule.day_of_week = canonical.day_of_week
                where target.id = canonical.id;

                delete from hc.climate_schedule_rule old
                where old.label = 'Climate morning comfort'
                  and exists (
                    select 1
                    from hc.climate_schedule_rule keep
                    where keep.day_of_week = old.day_of_week
                      and keep.label in ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
                  );

                drop index if exists hc.ux_climate_schedule_rule_day;

                create index if not exists ix_climate_schedule_rule_day_time
                  on hc.climate_schedule_rule (day_of_week, start_time);
                """
            )
            self._schema_ready = True

    def config(self):
        self.ensure_schema_callback()
        return self.fetch_one("select * from hc.scheduler_config where id = 1")

    def update_config(self, mode: Any, updated_by: str = "admin", notes: str = ""):
        self.ensure_schema_callback()
        mode = self.normalize_text(mode, "v2_execute_all")
        if mode in {"legacy", "v2_shadow", "v2_plan_only", "unified_shadow"}:
            mode = "v2_execute_all"
        if mode not in self.scheduler_modes:
            raise ValueError("mode must be one of: v2_execute_irrigation, v2_execute_x10, v2_execute_climate, v2_execute_x10_climate, v2_execute_all")
        return self.execute_one(
            """
            update hc.scheduler_config
            set mode = %s,
                updated_by = %s,
                notes = %s,
                updated_at = now()
            where id = 1
            returning *
            """,
            (mode, updated_by or "admin", notes or None),
        )

    def shadow_jobs(self):
        self.ensure_schema_callback()
        irrigation_rows = self.fetch_irrigation_schedules()
        irrigation_jobs = [
            {
                "domain": "irrigation",
                "action": "water",
                "label": row.get("label") or f"Day {row.get('day_of_week')}",
                "source": "hc_irrigation",
                "source_ref": str(row.get("id")),
                "day_of_week": row.get("day_of_week"),
                "start_time": row.get("start_time"),
                "stop_time": row.get("stop_time"),
                "is_enabled": bool(row.get("is_active")),
                "status": row.get("schedule_status"),
                "duration_minutes": row.get("duration_minutes"),
                "payload": {
                    "last_started_on": self.json_time(row.get("last_started_on")),
                    "last_stopped_on": self.json_time(row.get("last_stopped_on")),
                },
            }
            for row in irrigation_rows
        ]

        x10_entries = self.x10_scheduler_entries() or []
        x10_jobs = []
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for entry in x10_entries if isinstance(x10_entries, list) else []:
            raw_days = str(entry.get("days") or "").ljust(7, "0")[:7]
            enabled = str(entry.get("enabled", "0")) == "1"
            active_days = [
                index
                for index, robot_index in enumerate(self.x10_day_mask_index_by_hc_day())
                if robot_index < len(raw_days) and raw_days[robot_index] == "1"
            ]
            x10_jobs.append(
                {
                    "domain": "xiaomi_x10",
                    "action": "clean",
                    "label": f"X10 task {entry.get('task_id', '-')}",
                    "source": "hc_x10",
                    "source_ref": str(entry.get("task_id") or entry.get("raw") or len(x10_jobs)),
                    "day_of_week": active_days[0] if len(active_days) == 1 else None,
                    "days": active_days,
                    "days_label": ", ".join(day_names[index] for index in active_days) if active_days else "-",
                    "start_time": entry.get("time"),
                    "stop_time": None,
                    "is_enabled": enabled,
                    "status": "armed" if enabled else "disabled",
                    "duration_minutes": None,
                    "payload": {
                        "map_id": entry.get("map_id"),
                        "segments": entry.get("segments"),
                        "mode": entry.get("clean_mode") or entry.get("flag"),
                        "suction": entry.get("suction"),
                        "water_level": entry.get("water_level") or entry.get("clean_param"),
                        "days": raw_days,
                    },
                }
            )

        climate_jobs = [
            {
                "domain": "climate",
                "action": "set_state",
                "label": row.get("label") or f"Climate rule {row.get('id')}",
                "source": "hc_climate",
                "source_ref": str(row.get("id")),
                "day_of_week": row.get("day_of_week"),
                "start_time": row.get("start_time"),
                "stop_time": None,
                "is_enabled": bool(row.get("is_enabled")),
                "status": row.get("schedule_status"),
                "duration_minutes": None,
                "payload": {
                    "power": row.get("power"),
                    "mode": row.get("mode"),
                    "target_temperature": row.get("target_temperature"),
                    "fan_speed": row.get("fan_speed"),
                    "light": row.get("light"),
                    "rule_engine": row.get("rule_engine") if isinstance(row.get("rule_engine"), dict) else {},
                },
            }
            for row in self.fetch_climate_schedule_rules()
        ]
        return irrigation_jobs + x10_jobs + climate_jobs

    def clock_snapshot(self):
        row = self.fetch_one(
            """
            select
              current_date::text as today,
              extract(isodow from now())::int - 1 as day_of_week,
              to_char(localtime, 'HH24:MI') as local_minute
            """
        )
        return row or {"today": "", "day_of_week": None, "local_minute": ""}

    def history_rows(self, limit: int = 100):
        self.ensure_schema_callback()
        rows = self.fetch_all(
            """
            select *
            from hc.scheduler_run
            order by requested_at desc
            limit %s
            """,
            (max(1, min(int(limit or 100), 250)),),
        )
        history = []
        for row in rows:
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            source = payload.get("source") or ""
            source_ref = payload.get("source_ref") or ""
            domain = row.get("domain") or ""
            action = row.get("action") or ""
            label = payload.get("label") or f"{domain} {source_ref}".strip() or "-"
            event_time = payload.get("event_time") or payload.get("start_time") or payload.get("observed_minute")
            history.append(
                {
                    "id": row.get("id"),
                    "requested_at": row.get("requested_at"),
                    "domain": domain,
                    "domain_label": "X10" if domain == "xiaomi_x10" else "Irrigation" if domain == "irrigation" else "Climate" if domain == "climate" else domain,
                    "action": action,
                    "action_label": action.replace("_", " ").title() if action else "-",
                    "status": row.get("status"),
                    "status_label": str(row.get("status") or "-").replace("_", " "),
                    "job_label": label,
                    "source": source,
                    "source_ref": source_ref,
                    "mode": payload.get("mode"),
                    "shadow_only": bool(payload.get("shadow_only")),
                    "event_time": event_time,
                    "observed_date": payload.get("observed_date"),
                    "day_of_week": payload.get("day_of_week"),
                    "days": payload.get("days"),
                    "start_time": payload.get("start_time"),
                    "stop_time": payload.get("stop_time"),
                    "legacy_status": payload.get("legacy_status"),
                    "error": row.get("error"),
                    "payload": payload,
                }
            )
        return history

    def engine_state(self, config: Optional[Dict[str, Any]] = None):
        mode = (config or {}).get("mode") or "v2_execute_all"
        requested_domains = []
        if mode == "v2_execute_irrigation":
            requested_domains = ["irrigation"]
        elif mode == "v2_execute_x10":
            requested_domains = ["xiaomi_x10"]
        elif mode == "v2_execute_climate":
            requested_domains = ["climate"]
        elif mode == "v2_execute_x10_climate":
            requested_domains = ["xiaomi_x10", "climate"]
        elif mode == "v2_execute_all":
            requested_domains = ["irrigation", "xiaomi_x10", "climate"]
        requested_domain = requested_domains[0] if len(requested_domains) == 1 else None
        domain_allowed = {
            "irrigation": self.v2_allow_irrigation,
            "xiaomi_x10": self.v2_allow_x10,
            "climate": self.v2_allow_climate,
        }
        publish_domains = [domain for domain in requested_domains if domain_allowed.get(domain)]
        publish_enabled = bool(self.v2_execution_enabled and publish_domains and len(publish_domains) == len(requested_domains))
        return {
            "enabled": self.v2_execution_enabled,
            "publish_enabled": publish_enabled,
            "mode": mode,
            "requested_domain": requested_domain,
            "requested_domains": requested_domains,
            "publish_domains": publish_domains,
            "allowed_domains": [domain for domain, allowed in domain_allowed.items() if allowed],
            "command_owner": "v2" if publish_enabled else "blocked",
            "reason": "enabled" if publish_enabled else "disabled_by_feature_flags",
            "feature_flags": {
                "HC_V2_EXECUTION_ENABLED": self.v2_execution_enabled,
                "HC_V2_EXECUTION_ALLOW_IRRIGATION": self.v2_allow_irrigation,
                "HC_V2_EXECUTION_ALLOW_X10": self.v2_allow_x10,
                "HC_V2_EXECUTION_ALLOW_CLIMATE": self.v2_allow_climate,
            },
        }

    def execution_decision(self, chain: Dict[str, Any], engine: Dict[str, Any]):
        domain = chain.get("domain")
        if not chain.get("execution_id"):
            return {"can_publish": False, "reason": "missing_execution_record"}
        if not engine.get("enabled"):
            return {"can_publish": False, "reason": "execution_engine_disabled"}
        if domain not in (engine.get("requested_domains") or []):
            return {"can_publish": False, "reason": "mode_does_not_allow_domain"}
        if domain not in (engine.get("publish_domains") or []):
            return {"can_publish": False, "reason": "domain_publish_flag_disabled"}
        return {"can_publish": True, "reason": "would_publish_if_executor_were_called"}

    def irrigation_confirmation_diagnostics(self, command_payload: Dict[str, Any]):
        rows = self.fetch_all(
            """
            select s.key, s.ts, s.v_num, s.v_bool, s.v_text, s.v_json
            from hc.entity_state s
            join hc.entity e on e.id = s.entity_id
            where e.topic_base = 'homecontrol/tele/irrigation/esp-irrigation-1'
              and s.key in ('valve_state', 'manual_valve_state', 'pump_running', 'valve_current_a')
            """
        )
        state = {row["key"]: row for row in rows}
        valve = self.normalize_text((state.get("valve_state") or {}).get("v_text"), "UNKNOWN").upper()
        manual = self.normalize_text((state.get("manual_valve_state") or {}).get("v_text"), "UNKNOWN").upper()
        expected_value = self.normalize_text(command_payload.get("value"), "").lower()
        if expected_value == "open":
            matches = "OPEN" in valve and "CLOSED" not in valve
            expected = "valve open"
        elif expected_value in {"close", "closed"}:
            matches = "CLOSED" in valve
            expected = "valve closed"
        else:
            matches = False
            expected = f"command value {expected_value or '-'}"
        return {
            "strategy": "entity_state",
            "expected": expected,
            "status": "matches_current_state" if matches else "not_confirmed_by_current_state",
            "observed": {
                "valve_state": valve,
                "manual_valve_state": manual,
                "pump_running": (state.get("pump_running") or {}).get("v_bool"),
                "valve_current_a": (state.get("valve_current_a") or {}).get("v_num"),
            },
            "read_only": True,
        }

    def x10_confirmation_diagnostics(self, command_payload: Dict[str, Any]):
        entries = self.x10_scheduler_entries() or []
        command_result = self._monitor_value("command_result")
        room_clean_status = self._monitor_value("room_clean/status")
        expected = self.x10_command_expected(command_payload)
        matching_entry = None
        partial_entry = None
        match_checks = {}
        observed_entry = None
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            matched, checks, observed = self.x10_entry_matches_command(entry, expected)
            if matched:
                matching_entry = entry
                match_checks = checks
                observed_entry = observed
                break
            if not partial_entry and checks.get("start_time") and checks.get("segments"):
                partial_entry = entry
                match_checks = checks
                observed_entry = observed
        return {
            "strategy": "mqtt_cached_scheduler_entries",
            "expected": "scheduler entry matching time, day mask, enabled, map, mode, suction, water and segments",
            "status": "matching_scheduler_entry_seen" if matching_entry else "partial_scheduler_entry_seen" if partial_entry else "not_confirmed_by_cached_entries",
            "observed": {
                "matching_entry": matching_entry,
                "partial_entry": partial_entry,
                "match_checks": match_checks,
                "observed_entry": observed_entry,
                "command_result": command_result,
                "room_clean_status": room_clean_status,
            },
            "wanted": expected,
            "read_only": True,
        }

    def climate_confirmation_diagnostics(self, command_payload: Dict[str, Any]):
        state = self.climate_state_payload() if self.climate_state_payload else {}
        command_result = state.get("command_result")
        wanted = {
            "power": self._normalize_climate_text(command_payload.get("power")),
            "mode": self._normalize_climate_text(command_payload.get("mode")),
            "target_temperature": self._to_int(command_payload.get("target_temperature"), 0) if command_payload.get("target_temperature") is not None else None,
            "fan_speed": self._normalize_climate_text(command_payload.get("fan_speed")),
            "light": self._normalize_climate_text(command_payload.get("light")),
        }
        observed = {
            "power": self._normalize_climate_text(state.get("power")),
            "mode": self._normalize_climate_text(state.get("mode")),
            "target_temperature": self._to_int(state.get("target_temperature"), 0) if state.get("target_temperature") is not None else None,
            "fan_speed": self._normalize_climate_text(state.get("fan_speed")),
            "light": self._normalize_climate_text(state.get("light")),
            "bridge_online": state.get("bridge_online"),
            "updated_at": state.get("updated_at"),
            "error": state.get("error"),
            "command_result": command_result,
        }
        checks = {key: value is None or observed.get(key) == value for key, value in wanted.items()}
        matches = bool(state.get("ok")) and all(checks.values())
        return {
            "strategy": "mqtt_cached_climate_state",
            "expected": "cached climate state matching desired power, mode, target temperature, fan speed and light",
            "status": "matching_climate_state_seen" if matches else "not_confirmed_by_cached_state",
            "observed": observed,
            "wanted": wanted,
            "checks": checks,
            "read_only": True,
        }

    def confirmation_diagnostics(self, chain: Dict[str, Any]):
        command_payload = chain.get("command_payload") if isinstance(chain.get("command_payload"), dict) else {}
        if chain.get("domain") == "irrigation":
            return self.irrigation_confirmation_diagnostics(command_payload)
        if chain.get("domain") == "xiaomi_x10":
            return self.x10_confirmation_diagnostics(command_payload)
        if chain.get("domain") == "climate":
            return self.climate_confirmation_diagnostics(command_payload)
        return {
            "strategy": "none",
            "expected": "-",
            "status": "unsupported_domain",
            "observed": {},
            "read_only": True,
        }

    @staticmethod
    def parse_dt(value: Any):
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def irrigation_legacy_stop_drift(self, session: Optional[Dict[str, Any]]):
        if not session:
            return None
        start_payload = session.get("start_payload") if isinstance(session.get("start_payload"), dict) else {}
        requested_stop_at = self.parse_dt(session.get("requested_stop_at"))
        stopped_at = self.parse_dt(session.get("stopped_at"))
        if not requested_stop_at or not stopped_at:
            return None
        drift_seconds = abs((requested_stop_at - stopped_at).total_seconds())
        if drift_seconds < 120:
            return None
        return {
            "kind": "legacy_stop_drift",
            "severity": "warn",
            "message": "Historical requested_stop_at differs from actual stopped_at; V2 uses one effective stop policy instead of competing stop times.",
            "requested_stop_at": session.get("requested_stop_at"),
            "stopped_at": session.get("stopped_at"),
            "drift_minutes": round(drift_seconds / 60, 1),
            "schedule_duration_minutes": start_payload.get("schedule_duration_minutes"),
            "legacy_duration_minutes": start_payload.get("duration_minutes"),
            "pilot_final_duration": start_payload.get("pilot_final_duration"),
        }

    def irrigation_legacy_comparison(self, chain: Dict[str, Any]):
        command_payload = chain.get("command_payload") if isinstance(chain.get("command_payload"), dict) else {}
        schedule_id = self.normalize_text(command_payload.get("schedule_id"), "")
        expected_value = self.normalize_text(command_payload.get("value"), "").lower()
        session = None
        if schedule_id:
            session = self.fetch_one(
                """
                select
                  id, status, started_by, started_at, stopped_at, requested_stop_at,
                  start_payload, stop_payload, error
                from hc.irrigation_manual_session
                where start_payload ->> 'schedule_id' = %s
                order by started_at desc
                limit 1
                """,
                (schedule_id,),
            )
        confirmation = self.confirmation_diagnostics(chain)
        if not session:
            return {
                "status": "no_legacy_evidence",
                "summary": "No matching irrigation session was found for this schedule ref.",
                "v2_wanted": command_payload,
                "legacy_observed": None,
                "evidence": {"schedule_id": schedule_id, "confirmation": confirmation},
                "warnings": [],
                "read_only": True,
            }

        session_status = self.normalize_text(session.get("status"), "")
        warnings = []
        stop_drift = self.irrigation_legacy_stop_drift(session)
        if stop_drift:
            warnings.append(stop_drift)
        if expected_value == "open":
            matched = session_status in {"running", "starting", "auto_stopped", "stopped", "failed_no_watering"}
            status = "match" if matched else "pending"
            summary = f"Observed irrigation session exists with status {session_status}."
        elif expected_value in {"close", "closed"}:
            matched = bool(session.get("stopped_at")) or session_status in {"auto_stopped", "stopped", "failed_no_watering", "start_failed"}
            status = "match" if matched else "pending"
            summary = f"Observed irrigation stop evidence is {'present' if matched else 'not complete yet'}."
            if stop_drift:
                summary = f"{summary} Historical stop drift: {stop_drift['drift_minutes']} min."
        else:
            status = "pending"
            summary = f"Unsupported irrigation command value {expected_value or '-'}."
        return {
            "status": status,
            "summary": summary,
            "v2_wanted": command_payload,
            "legacy_observed": session,
            "evidence": {"schedule_id": schedule_id, "confirmation": confirmation},
            "warnings": warnings,
            "read_only": True,
        }

    def x10_legacy_comparison(self, chain: Dict[str, Any]):
        command_payload = chain.get("command_payload") if isinstance(chain.get("command_payload"), dict) else {}
        confirmation = self.x10_confirmation_diagnostics(command_payload)
        observed = confirmation.get("observed") or {}
        matching_entry = observed.get("matching_entry")
        partial_entry = observed.get("partial_entry")
        if matching_entry:
            status = "match"
            summary = "Cached X10 scheduler entries contain a strict matching task."
        elif partial_entry:
            status = "mismatch"
            summary = "X10 has a task with matching time/segments, but strict schedule fields differ."
        elif observed.get("command_result") or observed.get("room_clean_status"):
            status = "pending"
            summary = "X10 has command/status evidence, but no matching cached scheduler entry yet."
        else:
            status = "no_legacy_evidence"
            summary = "No cached X10 scheduler evidence is available yet."
        return {
            "status": status,
            "summary": summary,
            "v2_wanted": command_payload,
            "legacy_observed": observed,
            "evidence": {"confirmation": confirmation},
            "warnings": [] if matching_entry else [{"kind": "x10_strict_mismatch", "severity": "warn", "checks": observed.get("match_checks") or {}}] if partial_entry else [],
            "read_only": True,
        }

    def climate_legacy_comparison(self, chain: Dict[str, Any]):
        command_payload = chain.get("command_payload") if isinstance(chain.get("command_payload"), dict) else {}
        confirmation = self.climate_confirmation_diagnostics(command_payload)
        if confirmation.get("status") == "matching_climate_state_seen":
            status = "match"
            summary = "Cached climate state matches the desired scheduler state."
            warnings = []
        elif (confirmation.get("observed") or {}).get("command_result"):
            status = "pending"
            summary = "Climate bridge has command evidence, but cached state does not match yet."
            warnings = [{"kind": "climate_state_mismatch", "severity": "warn", "checks": confirmation.get("checks") or {}}]
        else:
            status = "no_legacy_evidence"
            summary = "No climate bridge command/state evidence is available yet."
            warnings = []
        return {
            "status": status,
            "summary": summary,
            "v2_wanted": command_payload,
            "legacy_observed": confirmation.get("observed"),
            "evidence": {"confirmation": confirmation},
            "warnings": warnings,
            "read_only": True,
        }

    def legacy_comparison(self, chain: Dict[str, Any]):
        if chain.get("domain") == "irrigation":
            return self.irrigation_legacy_comparison(chain)
        if chain.get("domain") == "xiaomi_x10":
            return self.x10_legacy_comparison(chain)
        if chain.get("domain") == "climate":
            return self.climate_legacy_comparison(chain)
        return {
            "status": "unsupported_domain",
            "summary": "No observed-state comparison is available for this domain.",
            "v2_wanted": chain.get("command_payload"),
            "legacy_observed": None,
            "evidence": {},
            "read_only": True,
        }

    def insert_run_once(
        self,
        idempotency_key: str,
        domain: str,
        action: str,
        status: str,
        payload: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.ensure_schema_callback()
        return self.execute_one(
            """
            insert into hc.scheduler_run (
              domain,
              action,
              status,
              requested_at,
              completed_at,
              error,
              payload,
              idempotency_key
            )
            values (%s, %s, %s, now(), now(), %s, %s::jsonb, %s)
            on conflict do nothing
            returning *
            """,
            (domain, action, status, error, self.json_dumps(payload or {}), idempotency_key),
        )

    def insert_v2_event_once(
        self,
        idempotency_key: str,
        domain: str,
        action: str,
        status: str,
        payload: Dict[str, Any],
    ):
        exists = self.fetch_one("select to_regclass('hc.event') is not null as available") or {}
        if not exists.get("available"):
            return None

        event_type = f"scheduler.{action}.shadow"
        metadata = {
            "model": "HC_V2",
            "component": "v2_scheduler_shadow",
            "command_owner": "v2_audit",
            "side_effects": False,
        }
        return self.execute_one(
            """
            insert into hc.event (
              type,
              source,
              domain,
              occurred_at,
              idempotency_key,
              payload,
              metadata,
              status
            )
            values (%s, %s, %s, now(), %s, %s::jsonb, %s::jsonb, %s)
            on conflict do nothing
            returning *
            """,
            (
                event_type,
                "v2_scheduler_shadow",
                domain,
                idempotency_key,
                self.json_dumps(payload),
                self.json_dumps(metadata),
                status,
            ),
        )

    def shadow_audit_events(
        self,
        config: Optional[Dict[str, Any]] = None,
        clock: Optional[Dict[str, Any]] = None,
        jobs: Optional[Iterable[Dict[str, Any]]] = None,
    ):
        config = config or self.config() or {}
        mode = config.get("mode") or "v2_execute_all"
        clock = clock or self.clock_snapshot()
        today = str(clock.get("today") or "")
        day_of_week = clock.get("day_of_week")
        local_minute = str(clock.get("local_minute") or "")
        events = []

        for job in jobs if jobs is not None else self.shadow_jobs():
            if not job.get("is_enabled"):
                continue

            domain = job.get("domain") or "unknown"
            source = job.get("source") or "unknown"
            source_ref = job.get("source_ref") or job.get("label") or "unknown"
            job_payload = job.get("payload", {}) if isinstance(job.get("payload"), dict) else {}
            payload = dict(job_payload)
            payload.update(
                {
                    "mode": mode,
                    "shadow_only": True,
                    "source": source,
                    "source_ref": source_ref,
                    "label": job.get("label"),
                    "day_of_week": job.get("day_of_week"),
                    "days": job.get("days"),
                    "start_time": job.get("start_time"),
                    "stop_time": job.get("stop_time"),
                    "observed_date": today,
                    "observed_minute": local_minute,
                    "legacy_status": job.get("status"),
                    "duration_minutes": job.get("duration_minutes"),
                    "map_id": job_payload.get("map_id"),
                    "segments": job_payload.get("segments"),
                    "suction": job_payload.get("suction"),
                    "water_level": job_payload.get("water_level"),
                    "clean_mode": job_payload.get("mode"),
                    "power": job_payload.get("power"),
                    "climate_mode": job_payload.get("mode"),
                    "target_temperature": job_payload.get("target_temperature"),
                    "fan_speed": job_payload.get("fan_speed"),
                    "light": job_payload.get("light"),
                    "days_mask": job_payload.get("days"),
                }
            )

            job_events = []
            if domain == "irrigation":
                if job.get("status") == "due_now":
                    if self.evaluate_irrigation_pilot:
                        try:
                            decision = self.evaluate_irrigation_pilot(base_duration=job.get("duration_minutes"))
                            effective_duration = decision["final_duration"] if decision.get("mode") == "pilot" else job.get("duration_minutes")
                            payload.update(
                                {
                                    "schedule_duration_minutes": job.get("duration_minutes"),
                                    "duration_minutes": effective_duration,
                                    "effective_duration_minutes": effective_duration,
                                    "stop_authority": "v2_rule_effective_stop" if decision.get("mode") == "pilot" else "schedule_stop_event",
                                    "rule_engine": {
                                        "mode": decision.get("mode"),
                                        "reason": decision.get("reason"),
                                        "triggered_rules": decision.get("triggered_rules", []),
                                        "base_duration": decision.get("base_duration"),
                                        "final_duration": decision.get("final_duration"),
                                        "weather_snapshot": decision.get("weather_snapshot", {}),
                                    },
                                }
                            )
                        except Exception as exc:
                            payload["rule_engine"] = {"error": str(exc)}
                    job_events.append(("water_start", "shadow_would_start", job.get("start_time")))
                elif job.get("status") == "done_today" and payload.get("last_stopped_on") != today:
                    stop_event_time = job.get("stop_time")
                    if mode == "v2_execute_irrigation" and self.fetch_irrigation_v2_session:
                        v2_session = self.fetch_irrigation_v2_session(str(source_ref))
                        requested_stop_at = (v2_session or {}).get("requested_stop_at")
                        if requested_stop_at and requested_stop_at > self.now(requested_stop_at.tzinfo):
                            continue
                        if requested_stop_at:
                            stop_event_time = requested_stop_at.strftime("%H:%M")
                            payload["effective_stop_at"] = requested_stop_at
                    job_events.append(("water_stop", "shadow_would_stop", stop_event_time))
            elif domain == "xiaomi_x10":
                active_days = job.get("days") or []
                if day_of_week in active_days and str(job.get("start_time") or "") == local_minute:
                    job_events.append(("clean_start", "shadow_would_start", job.get("start_time")))
            elif domain == "climate":
                if job.get("day_of_week") == day_of_week and str(job.get("start_time") or "") == local_minute:
                    job_events.append(("climate_set", "shadow_would_set", job.get("start_time")))

            for action, status, event_time in job_events:
                event_payload = dict(payload)
                event_payload["event_time"] = event_time
                key = f"shadow:{domain}:{source}:{source_ref}:{action}:{today}:{event_time or local_minute}"
                events.append(
                    {
                        "key": key,
                        "domain": domain,
                        "source": source,
                        "source_ref": source_ref,
                        "action": action,
                        "status": status,
                        "event_time": event_time,
                        "payload": event_payload,
                    }
                )
        return events

    def _table_available(self, table_name: str):
        row = self.fetch_one(f"select to_regclass('hc.{table_name}') is not null as available") or {}
        return bool(row.get("available"))

    @staticmethod
    def _irrigation_stop_policy(payload: Dict[str, Any], duration: Any, rule_engine: Dict[str, Any]):
        return {
            "stop_authority": payload.get("stop_authority") or ("v2_rule_effective_stop" if rule_engine.get("mode") == "pilot" else "schedule_stop_event"),
            "scheduled_start": payload.get("start_time"),
            "scheduled_stop": payload.get("stop_time"),
            "scheduled_duration_minutes": payload.get("schedule_duration_minutes") or duration,
            "effective_duration_minutes": payload.get("effective_duration_minutes") or duration,
            "effective_stop_at": payload.get("effective_stop_at"),
            "rule_engine_mode": rule_engine.get("mode"),
            "rule_engine_reason": rule_engine.get("reason"),
            "triggered_rules": rule_engine.get("triggered_rules", []),
            "legacy_requested_stop_at_is_diagnostic": True,
        }

    def insert_v2_irrigation_plan_once(self, event_row: Optional[Dict[str, Any]], action: str, payload: Dict[str, Any]):
        if not event_row or (event_row.get("domain") or "") != "irrigation":
            return None
        if not self._table_available("plan"):
            return None

        event_id = event_row.get("id")
        duration = payload.get("duration_minutes")
        rule_engine = payload.get("rule_engine") if isinstance(payload.get("rule_engine"), dict) else {}
        stop_policy = self._irrigation_stop_policy(payload, duration, rule_engine)
        target_ref = payload.get("source_ref") or payload.get("label") or "irrigation"
        if action == "water_start":
            plan_type = "irrigation.water_start.shadow_plan"
            actions = [
                {
                    "capability": "irrigation.valve.open",
                    "target": target_ref,
                    "duration_minutes": duration,
                    "scheduled_start": payload.get("start_time"),
                    "scheduled_stop": payload.get("stop_time"),
                    "stop_policy": stop_policy,
                    "side_effects": False,
                }
            ]
        elif action == "water_stop":
            plan_type = "irrigation.water_stop.shadow_plan"
            actions = [
                {
                    "capability": "irrigation.valve.close",
                    "target": target_ref,
                    "scheduled_stop": payload.get("stop_time") or payload.get("event_time"),
                    "stop_policy": stop_policy,
                    "side_effects": False,
                }
            ]
        else:
            return None

        inputs = {
            "scheduler": {
                "mode": payload.get("mode"),
                "source": payload.get("source"),
                "source_ref": payload.get("source_ref"),
                "label": payload.get("label"),
                "day_of_week": payload.get("day_of_week"),
                "event_time": payload.get("event_time"),
                "start_time": payload.get("start_time"),
                "stop_time": payload.get("stop_time"),
                "duration_minutes": duration,
                "schedule_duration_minutes": payload.get("schedule_duration_minutes"),
                "effective_duration_minutes": payload.get("effective_duration_minutes") or duration,
                "rule_engine": rule_engine,
                "stop_policy": stop_policy,
                "legacy_status": payload.get("legacy_status"),
            },
            "shadow": {"command_owner": "v2_audit", "side_effects": False},
        }
        metadata = {
            "model": "HC_V2",
            "component": "v2_scheduler_shadow",
            "event_type": event_row.get("type"),
            "scheduler_run_id": payload.get("scheduler_run_id"),
        }
        return self.execute_one(
            """
            insert into hc.plan (
              event_id, domain, type, target_type, target_ref, status, intended_start_at,
              reasoning, inputs, actions, metadata, created_by
            )
            select
              %s, 'irrigation', %s, 'schedule', %s, 'shadow_planned', null,
              %s, %s::jsonb, %s::jsonb, %s::jsonb, 'v2_scheduler_shadow'
            where not exists (select 1 from hc.plan where event_id = %s)
            returning *
            """,
            (
                event_id,
                plan_type,
                target_ref,
                "Audit plan generated from the irrigation scheduler source. Domain V2 executors own device publishing; this plan record has no side effects.",
                self.json_dumps(inputs),
                self.json_dumps(actions),
                self.json_dumps(metadata),
                event_id,
            ),
        )

    def insert_v2_irrigation_execution_once(self, plan_row: Optional[Dict[str, Any]], action: str, payload: Dict[str, Any]):
        if not plan_row or (plan_row.get("domain") or "") != "irrigation":
            return None
        if not self._table_available("execution"):
            return None

        plan_id = plan_row.get("id")
        duration = payload.get("duration_minutes")
        target_ref = plan_row.get("target_ref") or payload.get("source_ref") or "irrigation"
        rule_engine = payload.get("rule_engine") if isinstance(payload.get("rule_engine"), dict) else {}
        stop_policy = self._irrigation_stop_policy(payload, duration, rule_engine)
        if action == "water_start":
            command_payload = {
                "cmd": "set",
                "value": "open",
                "source": "v2_scheduler_audit",
                "schedule_id": target_ref,
                "schedule_label": payload.get("label"),
                "duration_minutes": duration,
                "rule_engine": rule_engine,
                "stop_policy": stop_policy,
                "shadow_only": True,
            }
        elif action == "water_stop":
            command_payload = {
                "cmd": "set",
                "value": "close",
                "source": "v2_scheduler_audit",
                "schedule_id": target_ref,
                "schedule_label": payload.get("label"),
                "reason": "v2_scheduler_audit_stop",
                "stop_policy": stop_policy,
                "shadow_only": True,
            }
        else:
            return None

        metadata = {
            "model": "HC_V2",
            "component": "v2_scheduler_shadow",
            "command_owner": "v2_audit",
            "side_effects": False,
            "scheduler_run_id": payload.get("scheduler_run_id"),
        }
        result = {"shadow": True, "would_publish": True, "published": False, "reason": "v2_domain_executor_handles_publish"}
        topic = self.irrigation_command_topic() if self.irrigation_command_topic else None
        return self.execute_one(
            """
            insert into hc.execution (
              plan_id, event_id, domain, executor, status, attempt, command_topic,
              command_payload, confirmation, result, metadata
            )
            select
              %s, %s, 'irrigation', 'v2_irrigation_audit', 'shadow_ready', 0,
              %s, %s::jsonb, '{}'::jsonb, %s::jsonb, %s::jsonb
            where not exists (select 1 from hc.execution where plan_id = %s)
            returning *
            """,
            (
                plan_id,
                plan_row.get("event_id"),
                topic,
                self.json_dumps(command_payload),
                self.json_dumps(result),
                self.json_dumps(metadata),
                plan_id,
            ),
        )

    def insert_v2_x10_plan_once(self, event_row: Optional[Dict[str, Any]], action: str, payload: Dict[str, Any]):
        if not event_row or (event_row.get("domain") or "") != "xiaomi_x10" or action != "clean_start":
            return None
        if not self._table_available("plan"):
            return None

        event_id = event_row.get("id")
        target_ref = payload.get("source_ref") or payload.get("label") or "xiaomi_x10"
        segments = self.normalized_segment_list(payload.get("segments"))
        command = {
            "map_id": payload.get("map_id"),
            "segments": segments,
            "start_time": payload.get("start_time") or payload.get("event_time"),
            "days": payload.get("days_mask") or payload.get("raw_days") or payload.get("days"),
            "enabled": 1,
            "mode": payload.get("clean_mode"),
            "suction": payload.get("suction"),
            "water_level": payload.get("water_level"),
            "shadow_only": True,
        }
        actions = [{"capability": "vacuum.schedule.clean", "target": target_ref, "command": command, "side_effects": False}]
        inputs = {
            "scheduler": {
                "mode": payload.get("mode"),
                "source": payload.get("source"),
                "source_ref": payload.get("source_ref"),
                "label": payload.get("label"),
                "days": payload.get("days"),
                "days_mask": payload.get("days_mask") or payload.get("raw_days"),
                "event_time": payload.get("event_time"),
                "start_time": payload.get("start_time"),
                "map_id": payload.get("map_id"),
                "segments": segments,
                "suction": payload.get("suction"),
                "water_level": payload.get("water_level"),
                "clean_mode": payload.get("clean_mode"),
                "legacy_status": payload.get("legacy_status"),
            },
            "shadow": {"command_owner": "v2_audit", "side_effects": False},
        }
        metadata = {
            "model": "HC_V2",
            "component": "v2_scheduler_shadow",
            "event_type": event_row.get("type"),
            "scheduler_run_id": payload.get("scheduler_run_id"),
        }
        return self.execute_one(
            """
            insert into hc.plan (
              event_id, domain, type, target_type, target_ref, status, intended_start_at,
              reasoning, inputs, actions, metadata, created_by
            )
            select
              %s, 'xiaomi_x10', 'xiaomi_x10.clean_start.shadow_plan', 'schedule', %s,
              'shadow_planned', null,
              'Audit plan generated from the X10 scheduler source. The V2 X10 scheduler owns weekly schedule publishing; this plan record has no side effects.',
              %s::jsonb, %s::jsonb, %s::jsonb, 'v2_scheduler_shadow'
            where not exists (select 1 from hc.plan where event_id = %s)
            returning *
            """,
            (event_id, target_ref, self.json_dumps(inputs), self.json_dumps(actions), self.json_dumps(metadata), event_id),
        )

    def insert_v2_x10_execution_once(self, plan_row: Optional[Dict[str, Any]], payload: Dict[str, Any]):
        if not plan_row or (plan_row.get("domain") or "") != "xiaomi_x10":
            return None
        if not self._table_available("execution"):
            return None

        actions = plan_row.get("actions") if isinstance(plan_row.get("actions"), list) else []
        first_action = actions[0] if actions and isinstance(actions[0], dict) else {}
        command_payload = dict(first_action.get("command") or {})
        command_payload["shadow_only"] = True
        metadata = {
            "model": "HC_V2",
            "component": "v2_scheduler_shadow",
            "command_owner": "v2_audit",
            "side_effects": False,
            "scheduler_run_id": payload.get("scheduler_run_id"),
        }
        result = {"shadow": True, "would_publish": True, "published": False, "reason": "v2_x10_scheduler_handles_weekly_publish"}
        return self.execute_one(
            """
            insert into hc.execution (
              plan_id, event_id, domain, executor, status, attempt, command_topic,
              command_payload, confirmation, result, metadata
            )
            select
              %s, %s, 'xiaomi_x10', 'v2_x10_audit', 'shadow_ready', 0,
              %s, %s::jsonb, '{}'::jsonb, %s::jsonb, %s::jsonb
            where not exists (select 1 from hc.execution where plan_id = %s)
            returning *
            """,
            (
                plan_row.get("id"),
                plan_row.get("event_id"),
                self.x10_schedule_clean_topic,
                self.json_dumps(command_payload),
                self.json_dumps(result),
                self.json_dumps(metadata),
                plan_row.get("id"),
            ),
        )

    def insert_v2_climate_plan_once(self, event_row: Optional[Dict[str, Any]], action: str, payload: Dict[str, Any]):
        if not event_row or (event_row.get("domain") or "") != "climate" or action != "climate_set":
            return None
        if not self._table_available("plan"):
            return None

        event_id = event_row.get("id")
        target_ref = payload.get("source_ref") or payload.get("label") or "gree_climate"
        command = self.climate_command_from_payload(payload)
        rule_engine = payload.get("rule_engine") if isinstance(payload.get("rule_engine"), dict) else {}
        actions = [
            {
                "capability": "climate.set_state",
                "target": target_ref,
                "command": command,
                "rule_engine": rule_engine,
                "side_effects": False,
            }
        ]
        inputs = {
            "scheduler": {
                "mode": payload.get("mode"),
                "source": payload.get("source"),
                "source_ref": payload.get("source_ref"),
                "label": payload.get("label"),
                "day_of_week": payload.get("day_of_week"),
                "event_time": payload.get("event_time"),
                "start_time": payload.get("start_time"),
                "legacy_status": payload.get("legacy_status"),
            },
            "climate": {
                "current_state": self.climate_state_payload() if self.climate_state_payload else {},
                "desired_state": command,
            },
            "rule_engine": rule_engine,
            "shadow": {"command_owner": "v2_audit", "side_effects": False},
        }
        metadata = {
            "model": "HC_V2",
            "component": "v2_scheduler_shadow",
            "event_type": event_row.get("type"),
            "scheduler_run_id": payload.get("scheduler_run_id"),
        }
        return self.execute_one(
            """
            insert into hc.plan (
              event_id, domain, type, target_type, target_ref, status, intended_start_at,
              reasoning, inputs, actions, metadata, created_by
            )
            select
              %s, 'climate', 'climate.set_state.shadow_plan', 'schedule', %s,
              'shadow_planned', null,
              'Audit plan generated from the HC climate scheduler. V2 owns publishing when climate execution is enabled.',
              %s::jsonb, %s::jsonb, %s::jsonb, 'v2_scheduler_shadow'
            where not exists (select 1 from hc.plan where event_id = %s)
            returning *
            """,
            (event_id, target_ref, self.json_dumps(inputs), self.json_dumps(actions), self.json_dumps(metadata), event_id),
        )

    def insert_v2_climate_execution_once(self, plan_row: Optional[Dict[str, Any]], payload: Dict[str, Any]):
        if not plan_row or (plan_row.get("domain") or "") != "climate":
            return None
        if not self._table_available("execution"):
            return None

        existing = self.fetch_one("select * from hc.execution where plan_id = %s", (plan_row.get("id"),))
        if existing:
            return existing

        actions = plan_row.get("actions") if isinstance(plan_row.get("actions"), list) else []
        first_action = actions[0] if actions and isinstance(actions[0], dict) else {}
        command_payload = dict(first_action.get("command") or {})
        engine = self.engine_state(self.config())
        can_publish = "climate" in (engine.get("publish_domains") or [])
        command_payload["shadow_only"] = not can_publish
        metadata = {
            "model": "HC_V2",
            "component": "v2_scheduler_executor" if can_publish else "v2_scheduler_shadow",
            "command_owner": "v2" if can_publish else "blocked",
            "side_effects": bool(can_publish),
            "scheduler_run_id": payload.get("scheduler_run_id"),
        }
        ok = False
        message = "v2_publish_blocked_by_engine"
        auto_power_wall = []
        if can_publish and self.publish_mqtt:
            ok, message = self.publish_mqtt(self.climate_command_topic, command_payload)
            if ok and command_payload.get("power") in {"on", "off"} and self.sync_auto_climate_power_wall:
                auto_power_wall = self.sync_auto_climate_power_wall(command_payload["power"])
        result = {
            "shadow": not can_publish,
            "would_publish": True,
            "published": bool(ok),
            "publish_attempted": bool(can_publish),
            "message": message,
            "reason": "v2_command_owner" if can_publish else "v2_publish_blocked_by_engine",
            "auto_power_wall": auto_power_wall,
        }
        return self.execute_one(
            """
            insert into hc.execution (
              plan_id, event_id, domain, executor, status, attempt, command_topic,
              command_payload, confirmation, result, metadata
            )
            select
              %s, %s, 'climate', %s, %s, 0,
              %s, %s::jsonb, '{}'::jsonb, %s::jsonb, %s::jsonb
            where not exists (select 1 from hc.execution where plan_id = %s)
            returning *
            """,
            (
                plan_row.get("id"),
                plan_row.get("event_id"),
                "v2_gree_climate" if can_publish else "v2_gree_climate_audit",
                "confirmed" if ok else "failed" if can_publish else "shadow_ready",
                self.climate_command_topic,
                self.json_dumps(command_payload),
                self.json_dumps(result),
                self.json_dumps(metadata),
                plan_row.get("id"),
            ),
        )

    @staticmethod
    def _preflight_result(domain: str, checks: Iterable[Dict[str, Any]]):
        check_list = list(checks)
        block_count = sum(1 for check in check_list if check["status"] == "block")
        warn_count = sum(1 for check in check_list if check["status"] == "warn")
        overall = "BLOCKED" if block_count else "WARN" if warn_count else "READY"
        return {
            "domain": domain,
            "overall": overall,
            "ready": overall == "READY",
            "block_count": block_count,
            "warn_count": warn_count,
            "checks": check_list,
            "read_only": True,
        }

    def _db_check(self):
        if not self.check_db:
            return False
        return bool(self.check_db())

    def _mqtt_check(self):
        if not self.check_mqtt:
            return False
        return bool(self.check_mqtt(timeout_s=1.5))

    def _add_common_preflight_checks(self, checks: list, engine: Dict[str, Any]):
        def add_check(key: str, status: str, message: str, detail: Optional[Dict[str, Any]] = None):
            checks.append({"key": key, "status": status, "message": message, "detail": detail or {}})

        try:
            db_ok = self._db_check()
            add_check("db", "pass" if db_ok else "block", "Postgres connectivity is OK." if db_ok else "Postgres connectivity failed.")
        except Exception as exc:
            add_check("db", "block", "Postgres connectivity check raised an error.", {"error": str(exc)})

        try:
            mqtt_ok = self._mqtt_check()
            add_check("mqtt", "pass" if mqtt_ok else "block", "MQTT connectivity is OK." if mqtt_ok else "MQTT connectivity failed.")
        except Exception as exc:
            add_check("mqtt", "block", "MQTT connectivity check raised an error.", {"error": str(exc)})

    def v2_irrigation_preflight(self, engine: Dict[str, Any], chains: Iterable[Dict[str, Any]]):
        checks = []

        def add_check(key: str, status: str, message: str, detail: Optional[Dict[str, Any]] = None):
            checks.append({"key": key, "status": status, "message": message, "detail": detail or {}})

        mode = engine.get("mode") or "v2_execute_all"
        if mode in {"v2_execute_irrigation", "v2_execute_all"}:
            add_check("mode", "pass", "Scheduler mode requests V2 irrigation execution.", {"mode": mode})
        else:
            add_check("mode", "block", "Scheduler mode is not v2_execute_irrigation or v2_execute_all.", {"mode": mode})

        if engine.get("enabled"):
            add_check("engine_enabled", "pass", "V2 execution feature flag is enabled.", engine.get("feature_flags"))
        else:
            add_check("engine_enabled", "block", "HC_V2_EXECUTION_ENABLED is disabled.", engine.get("feature_flags"))

        if self.v2_allow_irrigation:
            add_check("irrigation_allowed", "pass", "Irrigation publishing flag is enabled.", engine.get("feature_flags"))
        else:
            add_check("irrigation_allowed", "block", "HC_V2_EXECUTION_ALLOW_IRRIGATION is disabled.", engine.get("feature_flags"))

        self._add_common_preflight_checks(checks, engine)

        guard = self.manual_valve_scheduler_guard() if self.manual_valve_scheduler_guard else {}
        add_check(
            "manual_valve",
            "block" if guard.get("blocked") else "pass",
            f"Manual valve state is {guard.get('state') or 'UNKNOWN'}.",
            guard,
        )

        session = self.running_irrigation_session() if self.running_irrigation_session else None
        add_check(
            "active_session",
            "block" if session else "pass",
            "An irrigation session is currently active." if session else "No active irrigation session.",
            session or {},
        )

        recent_chains = [chain for chain in chains if chain.get("domain") == "irrigation"][:5]
        if not recent_chains:
            add_check("recent_v2_chains", "warn", "No recent irrigation V2 audit chains are available yet.")
        else:
            statuses = [(chain.get("legacy_comparison") or {}).get("status") for chain in recent_chains]
            if all(status == "match" for status in statuses):
                add_check("recent_v2_chains", "pass", f"Latest {len(recent_chains)} irrigation V2 diagnostics match observed state.", {"statuses": statuses})
            else:
                add_check("recent_v2_chains", "warn", "Some recent irrigation V2 diagnostics are not confirmed matches.", {"statuses": statuses})

        drift_warnings = []
        for chain in recent_chains:
            comparison = chain.get("legacy_comparison") or {}
            for warning in comparison.get("warnings") or []:
                if warning.get("kind") == "legacy_stop_drift":
                    drift_warnings.append(
                        {
                            "event_id": chain.get("event_id"),
                            "schedule_id": (comparison.get("v2_wanted") or {}).get("schedule_id"),
                            **warning,
                        }
                    )
        if drift_warnings:
            add_check(
                "legacy_stop_drift",
                "warn",
                "Historical stop timing drift was detected; V2 will use one effective stop policy as the close authority.",
                {"warnings": drift_warnings},
            )
        else:
            add_check("legacy_stop_drift", "pass", "No historical stop timing drift detected in recent irrigation chains.")

        return self._preflight_result("irrigation", checks)

    def x10_desired_weekly_schedules(self):
        rows = self.fetch_all(
            """
            select
              day_index,
              task_id,
              is_enabled,
              start_time,
              clean_mode,
              map_id,
              suction,
              water_level,
              segments
            from hc.x10_schedule_day
            where is_hc_owned = true
            order by day_index
            """
        )
        schedules = []
        for row in rows:
            schedules.append(
                {
                    "day_index": row.get("day_index"),
                    "task_id": row.get("task_id"),
                    "enabled": 1 if row.get("is_enabled") else 0,
                    "start_time": row.get("start_time"),
                    "mode": row.get("clean_mode"),
                    "map_id": row.get("map_id"),
                    "suction": row.get("suction"),
                    "water_level": row.get("water_level"),
                    "clean_param": row.get("water_level"),
                    "segments": self.normalized_segment_list(row.get("segments")),
                }
            )
        return schedules

    def x10_expected_from_schedule(self, item: Dict[str, Any]):
        day_index = int(item.get("day_index") or 0)
        chars = ["0"] * 7
        robot_index = self.x10_day_mask_index_by_hc_day()[day_index]
        chars[robot_index] = "1"
        return self.x10_command_expected(
            {
                "start_time": item.get("start_time"),
                "days": "".join(chars),
                "enabled": item.get("enabled"),
                "map_id": item.get("map_id"),
                "mode": item.get("mode"),
                "suction": item.get("suction"),
                "water_level": item.get("water_level") or item.get("clean_param"),
                "segments": item.get("segments"),
            }
        )

    def x10_schedule_diff(self, desired: Iterable[Dict[str, Any]], entries: Iterable[Dict[str, Any]]):
        entry_list = [entry for entry in entries if isinstance(entry, dict)]
        diffs = []
        matches = []
        for item in desired:
            expected = self.x10_expected_from_schedule(item)
            matched_entry = None
            best_checks = {}
            best_observed = None
            for entry in entry_list:
                matched, checks, observed = self.x10_entry_matches_command(entry, expected)
                if matched:
                    matched_entry = entry
                    best_checks = checks
                    best_observed = observed
                    break
                if not best_observed and checks.get("start_time") and checks.get("segments"):
                    best_checks = checks
                    best_observed = observed
            if matched_entry:
                matches.append({"schedule": item, "entry": matched_entry})
            else:
                diffs.append({"schedule": item, "expected": expected, "checks": best_checks, "observed": best_observed})
        return {"matches": matches, "diffs": diffs, "match_count": len(matches), "diff_count": len(diffs)}

    def x10_active_cleaning_state(self):
        state_text = self.normalize_text(self._monitor_value("robot_state_text"), "").lower()
        room_clean_status = self._monitor_value("room_clean/status") or {}
        status_text = self.normalize_text(room_clean_status.get("status") if isinstance(room_clean_status, dict) else "", "").lower()
        active = any(part in state_text for part in ("cleaning", "room_cleaning")) or status_text in {"scheduled", "active"}
        return {"active": active, "robot_state_text": state_text, "room_clean_status": room_clean_status}

    def mark_v2_x10_executions(self, status: str, result: Dict[str, Any], error: Optional[str] = None):
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
            where domain = 'xiaomi_x10'
              and created_at >= now() - interval '2 days'
              and status in ('shadow_ready', 'pending')
            returning *
            """,
            (
                status,
                self.json_dumps(result),
                error,
                self.json_dumps({"command_owner": "v2", "executed_by": "v2_x10_scheduler_executor"}),
            ),
        )

    def publish_x10_weekly_schedule(self, desired: Iterable[Dict[str, Any]]):
        desired_list = list(desired)
        map_id = next((item.get("map_id") for item in desired_list if item.get("map_id") is not None), 3)
        payload = {"map_id": map_id, "schedules": desired_list, "source": "v2_scheduler"}
        topic = self.x10_weekly_schedule_topic
        if not self.publish_mqtt or not topic:
            return False, "x10_weekly_publish_not_configured", {"topic": topic, "payload": payload}
        ok, message = self.publish_mqtt(topic, payload)
        return ok, message, {"topic": topic, "payload": payload}

    def validate_x10_weekly_schedules(self, desired: Iterable[Dict[str, Any]]):
        errors = []
        validated = []
        for index, item in enumerate(desired):
            row_errors = []
            required = {
                "day_index": item.get("day_index"),
                "map_id": item.get("map_id"),
                "start_time": item.get("start_time"),
                "mode": item.get("mode", item.get("clean_mode")),
                "suction": item.get("suction"),
                "water_level": item.get("water_level", item.get("clean_param")),
            }
            for key, value in required.items():
                if self.normalize_x10_scalar(value) is None:
                    row_errors.append(f"missing_{key}")
            segments = self.normalized_segment_list(item.get("segments"))
            if not segments:
                row_errors.append("missing_segments")
            normalized = dict(item)
            normalized["segments"] = segments
            validated.append(normalized)
            if row_errors:
                errors.append({"index": index, "task_id": item.get("task_id"), "errors": row_errors, "schedule": item})
        return {"ok": not errors, "errors": errors, "schedules": validated}

    def x10_scheduler_tick(self):
        engine = self.engine_state(self.config())
        if "xiaomi_x10" not in (engine.get("publish_domains") or []):
            return {"ok": True, "skipped": True, "reason": "x10_publish_not_enabled", "engine": engine}

        desired_all = self.x10_desired_weekly_schedules()
        desired = [item for item in desired_all if str(item.get("enabled")) == "1" or item.get("enabled") is True]
        entries = self.x10_scheduler_entries() or []
        if not desired:
            result = {"published": False, "publish_attempted": False, "reason": "no_enabled_hc_owned_schedule", "total_hc_owned": len(desired_all)}
            self.mark_v2_x10_executions("confirmed", result)
            return {"ok": True, "status": "skipped", "result": result}
        validation = self.validate_x10_weekly_schedules(desired)
        if not validation["ok"]:
            result = {"published": False, "publish_attempted": False, "reason": "invalid_x10_schedule_payload", "validation": validation}
            self.mark_v2_x10_executions("blocked", result, "invalid_x10_schedule_payload")
            print("[V2 X10] blocked: invalid schedule payload", flush=True)
            return {"ok": False, "status": "blocked", "result": result}
        desired = validation["schedules"]
        diff = self.x10_schedule_diff(desired, entries)
        if diff["diff_count"] == 0:
            result = {"published": False, "publish_attempted": False, "reason": "robot_schedule_already_matches", "diff": diff}
            self.mark_v2_x10_executions("confirmed", result)
            return {"ok": True, "status": "confirmed", "result": result}

        active = self.x10_active_cleaning_state()
        if active.get("active"):
            result = {"published": False, "publish_attempted": False, "reason": "x10_active_cleaning", "active": active}
            self.mark_v2_x10_executions("blocked", result, "x10_active_cleaning")
            print("[V2 X10] blocked: robot appears active", flush=True)
            return {"ok": False, "status": "blocked", "result": result}

        ok, message, publish_info = self.publish_x10_weekly_schedule(desired)
        result = {
            "published": bool(ok),
            "publish_attempted": True,
            "message": message,
            "diff": diff,
            **publish_info,
        }
        self.mark_v2_x10_executions("confirmed" if ok else "failed", result, None if ok else message)
        print(f"[V2 X10] weekly schedule publish ok={ok} message={message}", flush=True)
        return {"ok": bool(ok), "status": "confirmed" if ok else "failed", "result": result}

    def v2_x10_preflight(self, engine: Dict[str, Any], chains: Iterable[Dict[str, Any]]):
        checks = []

        def add_check(key: str, status: str, message: str, detail: Optional[Dict[str, Any]] = None):
            checks.append({"key": key, "status": status, "message": message, "detail": detail or {}})

        mode = engine.get("mode") or "v2_execute_all"
        if mode in {"v2_execute_x10", "v2_execute_x10_climate", "v2_execute_all"}:
            add_check("mode", "pass", "Scheduler mode requests V2 X10 execution.", {"mode": mode})
        else:
            add_check("mode", "block", "Scheduler mode is not v2_execute_x10, v2_execute_x10_climate, or v2_execute_all.", {"mode": mode})

        if engine.get("enabled"):
            add_check("engine_enabled", "pass", "V2 execution feature flag is enabled.", engine.get("feature_flags"))
        else:
            add_check("engine_enabled", "block", "HC_V2_EXECUTION_ENABLED is disabled.", engine.get("feature_flags"))

        if self.v2_allow_x10:
            add_check("x10_allowed", "pass", "X10 publishing flag is enabled.", engine.get("feature_flags"))
        else:
            add_check("x10_allowed", "block", "HC_V2_EXECUTION_ALLOW_X10 is disabled.", engine.get("feature_flags"))

        self._add_common_preflight_checks(checks, engine)

        bridge_online = bool(self._monitor_value("bridge/online"))
        add_check("bridge_online", "pass" if bridge_online else "block", "X10 bridge is online." if bridge_online else "X10 bridge is offline.")

        entries = self.x10_scheduler_entries() or []
        if entries:
            add_check("scheduler_cache", "pass", f"X10 scheduler cache has {len(entries)} entries.", {"entry_count": len(entries)})
        else:
            add_check("scheduler_cache", "block", "X10 scheduler cache is empty.")

        active_state = self.x10_active_cleaning_state()
        add_check(
            "active_cleaning",
            "block" if active_state.get("active") else "pass",
            "X10 appears to be active or scheduled." if active_state.get("active") else "X10 is not reporting active cleaning.",
            active_state,
        )

        desired = self.x10_desired_weekly_schedules()
        if desired:
            add_check("hc_owned_schedule", "pass", f"HC-owned X10 weekly schedule has {len(desired)} day rows.", {"schedule_count": len(desired)})
        else:
            add_check("hc_owned_schedule", "block", "No HC-owned X10 weekly schedule rows are available.")

        diff = self.x10_schedule_diff(desired, entries)
        if desired and diff["diff_count"] == 0:
            add_check("robot_schedule_match", "pass", "Robot weekly schedule matches HC-owned X10 schedule.", {"match_count": diff["match_count"]})
        elif desired:
            add_check("robot_schedule_match", "warn", "Robot weekly schedule differs from HC-owned X10 schedule.", diff)

        x10_chains = [chain for chain in chains if chain.get("domain") == "xiaomi_x10"][:5]
        if not x10_chains:
            add_check("recent_v2_chains", "warn", "No recent X10 V2 audit chains are available yet.")
        else:
            statuses = [(chain.get("legacy_comparison") or {}).get("status") for chain in x10_chains]
            if all(status == "match" for status in statuses):
                add_check("recent_v2_chains", "pass", f"Latest {len(x10_chains)} X10 V2 diagnostics match cached scheduler state.", {"statuses": statuses})
            else:
                add_check("recent_v2_chains", "warn", "Some recent X10 V2 diagnostics are not strict matches.", {"statuses": statuses})

        return self._preflight_result("xiaomi_x10", checks)

    def v2_climate_preflight(self, engine: Dict[str, Any], chains: Iterable[Dict[str, Any]]):
        checks = []

        def add_check(key: str, status: str, message: str, detail: Optional[Dict[str, Any]] = None):
            checks.append({"key": key, "status": status, "message": message, "detail": detail or {}})

        mode = engine.get("mode") or "v2_execute_all"
        if mode in {"v2_execute_climate", "v2_execute_x10_climate", "v2_execute_all"}:
            add_check("mode", "pass", "Scheduler mode requests V2 climate execution.", {"mode": mode})
        else:
            add_check("mode", "block", "Scheduler mode is not v2_execute_climate, v2_execute_x10_climate, or v2_execute_all.", {"mode": mode})

        if engine.get("enabled"):
            add_check("engine_enabled", "pass", "V2 execution feature flag is enabled.", engine.get("feature_flags"))
        else:
            add_check("engine_enabled", "block", "HC_V2_EXECUTION_ENABLED is disabled.", engine.get("feature_flags"))

        if self.v2_allow_climate:
            add_check("climate_allowed", "pass", "Climate publishing flag is enabled.", engine.get("feature_flags"))
        else:
            add_check("climate_allowed", "block", "HC_V2_EXECUTION_ALLOW_CLIMATE is disabled.", engine.get("feature_flags"))

        self._add_common_preflight_checks(checks, engine)

        climate_state = self.climate_state_payload() if self.climate_state_payload else {}
        add_check(
            "bridge_online",
            "pass" if climate_state.get("bridge_online") else "block",
            "Gree climate bridge is online." if climate_state.get("bridge_online") else "Gree climate bridge is offline.",
            {"base_topic": climate_state.get("base_topic"), "mqtt": climate_state.get("mqtt")},
        )
        add_check(
            "cached_state",
            "pass" if climate_state.get("ok") else "warn",
            "Cached climate state is available." if climate_state.get("ok") else "Cached climate state is missing or not confirmed.",
            {
                "power": climate_state.get("power"),
                "mode": climate_state.get("mode"),
                "target_temperature": climate_state.get("target_temperature"),
                "fan_speed": climate_state.get("fan_speed"),
                "light": climate_state.get("light"),
                "error": climate_state.get("error"),
                "updated_at": climate_state.get("updated_at"),
            },
        )

        schedules = self.fetch_climate_schedule_rules()
        enabled = [row for row in schedules if row.get("is_enabled")]
        if schedules:
            add_check("schedule_rows", "pass", f"Climate scheduler has {len(schedules)} rule rows.", {"enabled_count": len(enabled)})
        else:
            add_check("schedule_rows", "block", "No climate schedule rule rows are available.")
        if enabled:
            add_check("enabled_rules", "pass", f"{len(enabled)} climate schedule rules are enabled.", {"enabled_count": len(enabled)})
        else:
            add_check("enabled_rules", "warn", "No climate schedule rules are enabled yet.")

        climate_chains = [chain for chain in chains if chain.get("domain") == "climate"][:5]
        if not climate_chains:
            add_check("recent_v2_chains", "warn", "No recent climate V2 audit chains are available yet.")
        else:
            statuses = [(chain.get("legacy_comparison") or {}).get("status") for chain in climate_chains]
            if all(status == "match" for status in statuses):
                add_check("recent_v2_chains", "pass", f"Latest {len(climate_chains)} climate V2 diagnostics match cached state.", {"statuses": statuses})
            else:
                add_check("recent_v2_chains", "warn", "Some recent climate V2 diagnostics are not confirmed matches.", {"statuses": statuses})

        return self._preflight_result("climate", checks)

    def core_summary(self, limit: int = 50):
        tables = self.fetch_one(
            """
            select
              to_regclass('hc.event') is not null as has_event,
              to_regclass('hc.plan') is not null as has_plan,
              to_regclass('hc.execution') is not null as has_execution
            """
        ) or {}
        if not (tables.get("has_event") and tables.get("has_plan") and tables.get("has_execution")):
            return {
                "available": False,
                "counts": {"events": 0, "plans": 0, "executions": 0},
                "activity": [],
                "chains": [],
                "execution_engine": self.engine_state(),
            }

        safe_limit = max(1, min(int(limit or 50), 100))
        counts = self.fetch_one(
            """
            select
              (select count(*) from hc.event)::int as events,
              (select count(*) from hc.plan)::int as plans,
              (select count(*) from hc.execution)::int as executions
            """
        ) or {"events": 0, "plans": 0, "executions": 0}
        activity = self.fetch_all(
            """
            with activity as (
              select
                'event' as kind,
                id::text as id,
                occurred_at as ts,
                coalesce(domain, '-') as domain,
                type as label,
                source as detail,
                status,
                correlation_id::text as correlation_id
              from hc.event
              union all
              select
                'plan' as kind,
                id::text as id,
                created_at as ts,
                domain,
                type as label,
                case
                  when target_type is not null and target_ref is not null then target_type || ':' || target_ref
                  else coalesce(target_ref, target_type, '-')
                end as detail,
                status,
                correlation_id::text as correlation_id
              from hc.plan
              union all
              select
                'execution' as kind,
                id::text as id,
                created_at as ts,
                domain,
                executor as label,
                coalesce(command_topic, '-') as detail,
                status,
                correlation_id::text as correlation_id
              from hc.execution
            )
            select *
            from activity
            order by ts desc
            limit %s
            """,
            (safe_limit,),
        )
        chains = self.fetch_all(
            """
            select
              e.id::text as event_id,
              e.occurred_at as event_ts,
              e.domain,
              e.type as event_type,
              e.status as event_status,
              e.source as event_source,
              e.payload as event_payload,
              e.metadata as event_metadata,
              p.id::text as plan_id,
              p.type as plan_type,
              p.status as plan_status,
              p.target_type,
              p.target_ref,
              p.reasoning,
              p.inputs as plan_inputs,
              p.actions as plan_actions,
              p.metadata as plan_metadata,
              x.id::text as execution_id,
              x.executor,
              x.status as execution_status,
              x.command_topic,
              x.command_payload,
              x.confirmation,
              x.result as execution_result,
              x.metadata as execution_metadata
            from hc.event e
            left join hc.plan p on p.event_id = e.id
            left join hc.execution x on x.plan_id = p.id
            order by e.occurred_at desc
            limit %s
            """,
            (safe_limit,),
        )
        engine = self.engine_state(self.config())
        for chain in chains:
            chain["execution_engine"] = self.execution_decision(chain, engine)
            chain["confirmation_diagnostics"] = self.confirmation_diagnostics(chain)
            chain["legacy_comparison"] = self.legacy_comparison(chain)
        preflight = {
            "irrigation": self.v2_irrigation_preflight(engine, chains),
            "xiaomi_x10": self.v2_x10_preflight(engine, chains),
            "climate": self.v2_climate_preflight(engine, chains),
        }
        return {
            "available": True,
            "counts": counts,
            "activity": activity,
            "chains": chains,
            "execution_engine": engine,
            "preflight": preflight,
            "modes": [
                {"value": "v2_execute_irrigation", "label": "V2 execute irrigation", "command_owner": engine.get("command_owner")},
                {"value": "v2_execute_x10", "label": "V2 execute X10", "command_owner": engine.get("command_owner")},
                {"value": "v2_execute_climate", "label": "V2 execute Climate", "command_owner": engine.get("command_owner")},
                {"value": "v2_execute_x10_climate", "label": "V2 execute X10 + Climate", "command_owner": engine.get("command_owner")},
                {"value": "v2_execute_all", "label": "V2 execute all", "command_owner": engine.get("command_owner")},
            ],
        }

    def simulation_payload(self, data: Dict[str, Any]):
        domain = self.normalize_text(data.get("domain"), "irrigation")
        action = self.normalize_text(data.get("action"), "water_start")
        if domain not in {"irrigation", "xiaomi_x10", "climate"}:
            raise ValueError("domain must be irrigation, xiaomi_x10 or climate")
        if domain == "irrigation" and action not in {"water_start", "water_stop"}:
            raise ValueError("irrigation action must be water_start or water_stop")
        if domain == "xiaomi_x10" and action != "clean_start":
            raise ValueError("xiaomi_x10 action must be clean_start")
        if domain == "climate" and action != "climate_set":
            raise ValueError("climate action must be climate_set")

        now_text = self.now().strftime("%Y-%m-%d")
        source_ref = self.normalize_text(data.get("schedule_id") or data.get("source_ref"), "simulation")
        payload = {
            "mode": self.normalize_text(data.get("mode"), "simulation"),
            "shadow_only": True,
            "source": "simulation",
            "source_ref": source_ref,
            "label": self.normalize_text(data.get("label"), "Simulation"),
            "day_of_week": data.get("day_of_week"),
            "days": data.get("days"),
            "start_time": self.normalize_text(data.get("start_time"), "17:00" if domain == "irrigation" else "14:00"),
            "stop_time": data.get("stop_time"),
            "observed_date": self.normalize_text(data.get("observed_date"), now_text),
            "observed_minute": self.normalize_text(data.get("observed_minute"), data.get("start_time") or "00:00"),
            "legacy_status": "simulation",
            "duration_minutes": data.get("duration_minutes"),
            "map_id": data.get("map_id"),
            "segments": data.get("segments"),
            "suction": data.get("suction"),
            "water_level": data.get("water_level"),
            "clean_mode": data.get("clean_mode"),
            "power": self.normalize_text(data.get("power"), "on"),
            "climate_mode": self.normalize_text(data.get("climate_mode") or data.get("climateMode"), "heat"),
            "target_temperature": data.get("target_temperature") or data.get("targetTemperature") or 23,
            "fan_speed": self.normalize_text(data.get("fan_speed") or data.get("fanSpeed"), "auto"),
            "light": self.normalize_text(data.get("light"), "off"),
            "rule_engine": data.get("rule_engine") if isinstance(data.get("rule_engine"), dict) else {"mode": "simulation", "stage": "bootstrap"},
            "days_mask": data.get("days_mask"),
            "event_time": self.normalize_text(data.get("event_time"), data.get("start_time") or "00:00"),
            "simulation": True,
        }
        if domain == "irrigation":
            if action == "water_start":
                payload["stop_time"] = self.normalize_text(payload.get("stop_time"), "18:30")
                payload["duration_minutes"] = payload.get("duration_minutes") or 90
            else:
                payload["stop_time"] = self.normalize_text(payload.get("stop_time"), payload.get("event_time") or "18:30")
                payload["event_time"] = payload["stop_time"]
        elif domain == "xiaomi_x10":
            payload["map_id"] = payload.get("map_id") or 3
            payload["segments"] = self.normalized_segment_list(payload.get("segments") or [1])
            payload["suction"] = payload.get("suction") or 3
            payload["water_level"] = payload.get("water_level") or 2
            payload["days_mask"] = payload.get("days_mask") or "0000000"
        else:
            payload["target_temperature"] = self._to_int(payload.get("target_temperature"), 23)
        return domain, action, payload

    def simulate_v2_scheduler_chain(self, data: Dict[str, Any]):
        domain, action, payload = self.simulation_payload(data)
        status = "shadow_would_start" if action in {"water_start", "clean_start"} else "shadow_would_set" if action == "climate_set" else "shadow_would_stop"
        event_type = f"scheduler.{action}.shadow"
        event = {
            "id": "simulation-event",
            "domain": domain,
            "type": event_type,
            "source": "v2_scheduler_simulation",
            "status": status,
            "payload": payload,
            "metadata": {
                "model": "HC_V2",
                "component": "v2_scheduler_simulation",
                "command_owner": "v2_audit",
                "side_effects": False,
                "simulated": True,
            },
        }

        stop_policy = None
        if domain == "irrigation":
            target_ref = payload.get("source_ref") or "simulation"
            stop_policy = {
                "stop_authority": "schedule_stop_event",
                "scheduled_start": payload.get("start_time"),
                "scheduled_stop": payload.get("stop_time"),
                "scheduled_duration_minutes": payload.get("duration_minutes"),
                "legacy_requested_stop_at_is_diagnostic": True,
            }
            if action == "water_start":
                plan_type = "irrigation.water_start.shadow_plan"
                command_payload = {
                    "cmd": "set",
                    "value": "open",
                "source": "v2_scheduler_audit",
                    "schedule_id": target_ref,
                    "schedule_label": payload.get("label"),
                    "duration_minutes": payload.get("duration_minutes"),
                    "stop_policy": stop_policy,
                    "shadow_only": True,
                }
                actions = [
                    {
                        "capability": "irrigation.valve.open",
                        "target": target_ref,
                        "duration_minutes": payload.get("duration_minutes"),
                        "scheduled_start": payload.get("start_time"),
                        "scheduled_stop": payload.get("stop_time"),
                        "stop_policy": stop_policy,
                        "side_effects": False,
                    }
                ]
            else:
                plan_type = "irrigation.water_stop.shadow_plan"
                command_payload = {
                    "cmd": "set",
                    "value": "close",
                    "source": "v2_scheduler_audit",
                    "schedule_id": target_ref,
                    "schedule_label": payload.get("label"),
                    "reason": "v2_scheduler_audit_stop",
                    "stop_policy": stop_policy,
                    "shadow_only": True,
                }
                actions = [
                    {
                        "capability": "irrigation.valve.close",
                        "target": target_ref,
                        "scheduled_stop": payload.get("stop_time") or payload.get("event_time"),
                        "stop_policy": stop_policy,
                        "side_effects": False,
                    }
                ]
            executor = "v2_irrigation_audit"
            command_topic = self.irrigation_command_topic() if self.irrigation_command_topic else None
        elif domain == "xiaomi_x10":
            target_ref = payload.get("source_ref") or "simulation"
            plan_type = "xiaomi_x10.clean_start.shadow_plan"
            command_payload = {
                "map_id": payload.get("map_id"),
                "segments": self.normalized_segment_list(payload.get("segments")),
                "start_time": payload.get("start_time") or payload.get("event_time"),
                "days": payload.get("days_mask"),
                "enabled": 1,
                "mode": payload.get("clean_mode"),
                "suction": payload.get("suction"),
                "water_level": payload.get("water_level"),
                "shadow_only": True,
            }
            actions = [
                {
                    "capability": "vacuum.schedule.clean",
                    "target": target_ref,
                    "command": command_payload,
                    "side_effects": False,
                }
            ]
            executor = "v2_x10_audit"
            command_topic = self.x10_schedule_clean_topic
        else:
            target_ref = payload.get("source_ref") or "simulation"
            plan_type = "climate.set_state.shadow_plan"
            command_payload = self.climate_command_from_payload(payload)
            actions = [
                {
                    "capability": "climate.set_state",
                    "target": target_ref,
                    "command": command_payload,
                    "rule_engine": payload.get("rule_engine"),
                    "side_effects": False,
                }
            ]
            executor = "v2_gree_climate_audit"
            command_topic = self.climate_command_topic

        plan_inputs = {
            "scheduler": {
                "mode": payload.get("mode"),
                "source": payload.get("source"),
                "source_ref": payload.get("source_ref"),
                "label": payload.get("label"),
                "day_of_week": payload.get("day_of_week"),
                "days": payload.get("days"),
                "days_mask": payload.get("days_mask"),
                "event_time": payload.get("event_time"),
                "start_time": payload.get("start_time"),
                "stop_time": payload.get("stop_time"),
                "duration_minutes": payload.get("duration_minutes"),
                "stop_policy": stop_policy if domain == "irrigation" else None,
                "map_id": payload.get("map_id"),
                "segments": payload.get("segments"),
                "suction": payload.get("suction"),
                "water_level": payload.get("water_level"),
                "clean_mode": payload.get("clean_mode"),
                "power": payload.get("power"),
                "climate_mode": payload.get("climate_mode"),
                "target_temperature": payload.get("target_temperature"),
                "fan_speed": payload.get("fan_speed"),
                "light": payload.get("light"),
                "rule_engine": payload.get("rule_engine"),
                "legacy_status": payload.get("legacy_status"),
            },
            "shadow": {
                "command_owner": "v2_audit",
                "side_effects": False,
            },
        }
        result = {
            "shadow": True,
            "would_publish": True,
            "published": False,
            "reason": "simulation_does_not_publish",
            "simulated": True,
        }
        chain = {
            "event_id": event["id"],
            "event_ts": self.now().isoformat(),
            "domain": domain,
            "event_type": event_type,
            "event_status": status,
            "event_source": event["source"],
            "event_payload": payload,
            "event_metadata": event["metadata"],
            "plan_id": "simulation-plan",
            "plan_type": plan_type,
            "plan_status": "shadow_planned",
            "target_type": "schedule",
            "target_ref": target_ref,
            "reasoning": "Simulated V2 scheduler chain. No database rows are written and no command is published.",
            "plan_inputs": plan_inputs,
            "plan_actions": actions,
            "plan_metadata": {"model": "HC_V2", "component": "v2_scheduler_simulation", "event_type": event_type, "simulated": True},
            "execution_id": "simulation-execution",
            "executor": executor,
            "execution_status": "shadow_ready",
            "command_topic": command_topic,
            "command_payload": command_payload,
            "confirmation": {},
            "execution_result": result,
            "execution_metadata": {
                "model": "HC_V2",
                "component": "v2_scheduler_simulation",
                "command_owner": "v2_audit",
                "side_effects": False,
                "simulated": True,
            },
        }
        engine = self.engine_state(self.config())
        chain["execution_engine"] = self.execution_decision(chain, engine)
        chain["confirmation_diagnostics"] = self.confirmation_diagnostics(chain)
        chain["legacy_comparison"] = self.legacy_comparison(chain)
        return {
            "ok": True,
            "simulated": True,
            "writes": False,
            "publishes": False,
            "engine": engine,
            "chain": chain,
        }

    def summary_payload(self):
        config = self.config()
        engine = self.engine_state(config)
        core = self.core_summary(limit=5)
        return {
            "ok": True,
            "config": config,
            "engine": engine,
            "v2": {
                "available": core.get("available", False),
                "counts": core.get("counts", {}),
                "preflight": core.get("preflight", {}),
            },
            "summary": {
                "mode": config["mode"] if config else "v2_execute_all",
                "legacy_active": False,
                "command_owner": engine.get("command_owner"),
                "publish_enabled": engine.get("publish_enabled"),
                "publish_domains": engine.get("publish_domains", []),
                "v2_available": core.get("available", False),
                "v2_counts": core.get("counts", {}),
            },
        }

    def ai_summary_payload(self):
        config = self.config()
        engine = self.engine_state(config)
        return {
            "ok": True,
            "config": {
                "mode": config.get("mode") if config else "v2_execute_all",
                "updated_at": config.get("updated_at") if config else None,
                "updated_by": config.get("updated_by") if config else None,
            },
            "engine": {
                "publish_enabled": engine.get("publish_enabled"),
                "publish_domains": engine.get("publish_domains", []),
                "requested_domains": engine.get("requested_domains", []),
                "command_owner": engine.get("command_owner"),
                "v2_execution_enabled": engine.get("v2_execution_enabled"),
            },
            "summary": {
                "mode": config.get("mode") if config else "v2_execute_all",
                "legacy_active": False,
                "audit_enabled": True,
                "shadow_enabled": True,
            },
        }

    def state_payload(self):
        config = self.config()
        jobs = self.shadow_jobs()
        runs = self.history_rows(100)
        v2 = self.core_summary()
        return {
            "ok": True,
            "config": config,
            "jobs": jobs,
            "runs": runs,
            "history": runs,
            "v2": v2,
            "summary": {
                "mode": config["mode"] if config else "v2_execute_all",
                "legacy_active": False,
                "command_owner": v2.get("execution_engine", {}).get("command_owner") or "blocked",
                "audit_enabled": True,
                "shadow_audit_enabled": True,
                "shadow_enabled": True,
                "history_count": len(runs),
                "job_count": len(jobs),
                "enabled_count": sum(1 for job in jobs if job.get("is_enabled")),
                "domains": sorted({job.get("domain") for job in jobs if job.get("domain")}),
                "v2_available": v2.get("available", False),
                "v2_counts": v2.get("counts", {}),
            },
        }
