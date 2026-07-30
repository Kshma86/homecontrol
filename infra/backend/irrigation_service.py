import json
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen


IRRIGATION_MOISTURE_TOPICS = (
    "zigbee/0xa4c13844a0908898",
    "zigbee/0xa4c1387594b09c83",
)
PILOT_SOIL_SENSOR_TOPIC = "zigbee/0xa4c13844a0908898"


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
    ):
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.execute_one = execute_one
        self.execute_sql = execute_sql
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
        self.api_cache_get = api_cache_get
        self.api_cache_set = api_cache_set
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
        self._snapshot_cache = {"expires_at": 0.0, "data": None}
        self._snapshot_lock = threading.Lock()
        self._pilot_cache = {"expires_at": 0.0, "recommendation": None}
        self._pilot_lock = threading.Lock()
        self._weather_summary_cache = {"expires_at": 0.0, "data": None}
        self._weather_summary_lock = threading.Lock()
        self._summary_schema_ready = False
        self._summary_schema_lock = threading.Lock()
        self._daily_summary_refresh = {"next_at": 0.0}
        self._daily_summary_lock = threading.Lock()

    def invalidate_snapshot_cache(self):
        with self._snapshot_lock:
            self._snapshot_cache["expires_at"] = 0.0
            self._snapshot_cache["data"] = None

    def invalidate_pilot_cache(self):
        with self._pilot_lock:
            self._pilot_cache["expires_at"] = 0.0
            self._pilot_cache["recommendation"] = None

    def invalidate_weather_summary_cache(self):
        with self._weather_summary_lock:
            self._weather_summary_cache["expires_at"] = 0.0
            self._weather_summary_cache["data"] = None

    def ensure_summary_schema(self):
        if self._summary_schema_ready:
            return
        with self._summary_schema_lock:
            if self._summary_schema_ready:
                return
            self.execute_sql(
                """
                create table if not exists hc.irrigation_daily_energy_summary (
                  day date primary key,
                  current_samples bigint,
                  avg_current_a numeric,
                  max_current_a numeric,
                  measured_hours numeric,
                  active_minutes numeric,
                  amp_hours numeric,
                  voltage_samples bigint,
                  avg_voltage_v numeric,
                  watt_hours numeric,
                  refreshed_at timestamptz not null default now()
                );

                create table if not exists hc.irrigation_pump_daily_summary (
                  day date primary key,
                  pump_running_minutes numeric,
                  measured_hours numeric,
                  state_samples bigint,
                  refreshed_at timestamptz not null default now()
                );

                create table if not exists hc.irrigation_solar_daily_summary (
                  day date primary key,
                  avg_battery_voltage_v numeric,
                  min_battery_voltage_v numeric,
                  max_battery_voltage_v numeric,
                  avg_charge_current_a numeric,
                  max_charge_current_a numeric,
                  avg_pv_voltage_v numeric,
                  max_pv_voltage_v numeric,
                  avg_pv_current_a numeric,
                  max_pv_current_a numeric,
                  avg_solar_controller_temp_c numeric,
                  max_solar_controller_temp_c numeric,
                  samples bigint,
                  charge_amp_hours numeric,
                  measured_hours numeric,
                  refreshed_at timestamptz not null default now()
                );

                create table if not exists hc.irrigation_tank_daily_summary (
                  day date primary key,
                  avg_level_percent numeric,
                  min_level_percent numeric,
                  max_level_percent numeric,
                  avg_depth_m numeric,
                  refreshed_at timestamptz not null default now()
                );

                create table if not exists hc.irrigation_controller_temp_daily_summary (
                  day date primary key,
                  avg_controller_temp_c numeric,
                  min_controller_temp_c numeric,
                  max_controller_temp_c numeric,
                  samples bigint,
                  refreshed_at timestamptz not null default now()
                );
                """
            )
            self._summary_schema_ready = True

    def refresh_daily_summaries(self, force: bool = False):
        self.ensure_summary_schema()
        now = time.monotonic()
        with self._daily_summary_lock:
            if not force and self._daily_summary_refresh["next_at"] > now:
                return
            self._daily_summary_refresh["next_at"] = now + self.daily_summary_refresh_sec
        days = max(14, self.daily_summary_days)
        self.execute_sql(
            f"""
            insert into hc.irrigation_daily_energy_summary (
              day, current_samples, avg_current_a, max_current_a, measured_hours,
              active_minutes, amp_hours, voltage_samples, avg_voltage_v, watt_hours, refreshed_at
            )
            select day, current_samples, avg_current_a, max_current_a, measured_hours,
              active_minutes, amp_hours, voltage_samples, avg_voltage_v, watt_hours, now()
            from hc.irrigation_daily_energy
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
            from hc.irrigation_pump_daily
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
            from hc.irrigation_solar_daily
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
            from hc.irrigation_tank_daily
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
            from hc.irrigation_controller_temp_daily
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
            """
        )

    def running_session(self):
        return self.fetch_one(
            """
            select *
            from hc.irrigation_manual_session
            where status in ('running', 'starting')
            order by started_at desc
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
              round(extract(epoch from (stop_time - start_time)) / 60)::int as duration_minutes
            from schedule_state
            order by day_of_week
            """
        )

    def validate_schedule_time(self, value: Any, field: str) -> str:
        text = self.normalize_text(value)
        try:
            parsed = datetime.strptime(text, "%H:%M")
        except ValueError:
            raise ValueError(f"{field} must be HH:MM")
        return parsed.strftime("%H:%M")

    def stop_payload(self, reason: str) -> Dict[str, Any]:
        return {"cmd": "set", "value": "close", "reason": reason}

    def _text_upper(self, value: Any) -> str:
        return str(value or "").upper()

    def live_valve_state(self):
        live = self.mqtt_snapshot()
        topics = live.get("topics") or {}
        candidates = []
        for name in ("pump_metrics", "esp_nano_status"):
            item = topics.get(name) or {}
            payload = item.get("json")
            if isinstance(payload, dict):
                candidates.append(payload)
        valve = next((self._text_upper(item.get("valve")) for item in candidates if item.get("valve") is not None), "")
        manual = next((self._text_upper(item.get("manual_valve")) for item in candidates if item.get("manual_valve") is not None), "")
        valve_current = next((self.to_float(item.get("valve_current")) for item in candidates if item.get("valve_current") is not None), None)
        return {
            "valve": valve,
            "manual_valve": manual,
            "valve_current_a": valve_current,
            "motor_open": any(part in valve for part in ("OPEN", "OPENING", "BETWEEN")),
            "motor_fully_open": valve == "OPEN",
            "manual_open": any(part in manual for part in ("OPEN", "OPENING", "BETWEEN")),
            "motor_closed": "CLOSED" in valve,
            "manual_closed": "CLOSED" in manual,
            "motor_closing": any(part in valve for part in ("CLOSING", "MOVING_CLOSE", "CLOSE")),
        }

    def stop_reaction_seen(self, state: Dict[str, Any]) -> bool:
        return bool(
            state.get("motor_closed")
            or state.get("motor_closing")
            or (self.to_float(state.get("valve_current_a"), 0) or 0) > 0.01
        )

    def open_reaction_seen(self, state: Dict[str, Any]) -> bool:
        return bool(
            state.get("motor_open")
            or any(part in state.get("valve", "") for part in ("MOVING_OPEN", "OPENING"))
            or (self.to_float(state.get("valve_current_a"), 0) or 0) > 0.01
        )

    def publish_open_with_confirmation(self, open_payload: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        attempts = max(1, self.open_confirm_attempts)
        reaction_delay = max(0, self.open_reaction_delay_seconds)
        ready_delay = max(reaction_delay, self.open_ready_delay_seconds)
        details = {"attempts": []}

        for attempt in range(1, attempts + 1):
            ok, message = self.publish_mqtt(self.command_topics()["valve"], open_payload)
            attempt_info = {
                "attempt": attempt,
                "publish_ok": ok,
                "publish_message": message,
            }
            if not ok:
                details["attempts"].append(attempt_info)
                print(f"[OPEN] attempt={attempt}/{attempts} publish failed message={message}", flush=True)
                continue

            if reaction_delay:
                time.sleep(reaction_delay)
            reaction_state = self.live_valve_state()
            attempt_info["reaction_state"] = reaction_state
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
            open_state = self.live_valve_state()
            attempt_info["open_state"] = open_state
            details["attempts"].append(attempt_info)

            if open_state["motor_fully_open"]:
                return True, f"open confirmed on attempt {attempt}", details

            print(
                f"[OPEN] attempt={attempt}/{attempts} not open "
                f"valve={open_state['valve']} current={open_state['valve_current_a']}",
                flush=True,
            )

        last = details["attempts"][-1] if details["attempts"] else {}
        last_state = last.get("open_state") or last.get("reaction_state") or {}
        last_valve = last_state.get("valve", "UNKNOWN")
        return False, f"open confirmation failed after {attempts} attempts; valve={last_valve}", details

    def publish_stop_with_confirmation(self, reason: str) -> Tuple[bool, str, Dict[str, Any]]:
        stop_payload = self.stop_payload(reason)
        attempts = max(1, self.stop_confirm_attempts)
        reaction_delay = max(0, self.stop_reaction_delay_seconds)
        closed_delay = max(reaction_delay, self.stop_closed_delay_seconds)
        details = {"attempts": []}

        for attempt in range(1, attempts + 1):
            ok, message = self.publish_mqtt(self.command_topics()["valve"], stop_payload)
            attempt_info = {
                "attempt": attempt,
                "publish_ok": ok,
                "publish_message": message,
            }
            if not ok:
                details["attempts"].append(attempt_info)
                print(f"[STOP] attempt={attempt}/{attempts} publish failed message={message}", flush=True)
                continue

            if reaction_delay:
                time.sleep(reaction_delay)
            reaction_state = self.live_valve_state()
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
            closed_state = self.live_valve_state()
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
        last_valve = last_state.get("valve", "UNKNOWN")
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
                stop_payload = %s::jsonb,
                error = %s
            where id = %s and status = 'running'
            returning *
            """,
            (status, json.dumps(stored_payload), None if ok else message, session_id),
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
              and started_at <= now() - interval '90 seconds'
            order by id
            """
        )
        for row in rows:
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

    def start_manual(self, data: Dict[str, Any]):
        minutes = int(data.get("duration_minutes") or 20)
        minutes = max(1, min(minutes, self.manual_max_minutes))
        running = self.running_session()
        if running:
            return {
                "ok": False,
                "error": "irrigation session already running",
                "session": running,
            }, 409

        valve_payload = {"cmd": "set", "value": "open", "source": "homecontrol-admin", "duration_minutes": minutes}
        row = self.execute_one(
            """
            insert into hc.irrigation_manual_session
              (requested_stop_at, safety_stop_at, status, started_by, start_payload)
            values (
              now() + (%s::text || ' minutes')::interval,
              now() + (%s::text || ' minutes')::interval,
              'starting',
              %s,
              %s::jsonb
            )
            returning *
            """,
            (minutes, self.manual_max_minutes, data.get("started_by") or "admin", json.dumps(valve_payload)),
        )
        valve_ok, valve_message, valve_details = self.publish_open_with_confirmation(valve_payload)
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
            return {
                "ok": True,
                "session": row,
                "duration_minutes": minutes,
                "message": valve_message,
                "context": self.context_meta("irrigation"),
            }, 200

        if row:
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
        return {"ok": True, "schedule": row, "context": self.context_meta("irrigation", "irrigation_pilot")}, 200

    def stop_manual(self, data: Dict[str, Any]):
        session_id = data.get("session_id")
        if session_id is None:
            row = self.fetch_one(
                """
                select id
                from hc.irrigation_manual_session
                where status = 'running'
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
            select s.key, s.ts, s.v_num
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
        for row in rows:
            if latest_ts is None or row["ts"] > latest_ts:
                latest_ts = row["ts"]
        return {
            "name": "Udvar",
            "temperature_c": self.to_float(temp.get("v_num")) if temp else None,
            "humidity_percent": self.to_float(humidity.get("v_num")) if humidity else None,
            "absolute_humidity_g_m3": self.absolute_humidity_g_m3(temp.get("v_num") if temp else None, humidity.get("v_num") if humidity else None),
            "ts": self.json_time(latest_ts),
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
        soil_sensor = self.latest_soil_moisture_snapshot(soil_sensor_topic or PILOT_SOIL_SENSOR_TOPIC)
        return {
            "rain_24h_mm": summary["rain_24h_mm"],
            "forecast_rain_24h_mm": self.to_float(latest.get("forecast_rain_24h_mm"), 0) or 0,
            "pop_percent": self.to_float(latest.get("forecast_pop_max_percent"), latest.get("pop_percent")) or 0,
            "temperature_c": self.to_float(latest.get("forecast_temp_max_c"), latest.get("temperature_c")),
            "humidity_percent": self.to_float(latest.get("humidity_percent")),
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
        soil_sensor_topic = None
        if self.process_binding_topic:
            soil_sensor_topic = self.process_binding_topic("irrigation_soil_moisture")
        snapshot = self.build_weather_snapshot(soil_sensor_topic or config.get("soil_sensor_topic_base") or PILOT_SOIL_SENSOR_TOPIC)
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
        reason = f"Today's watering remains unchanged at {base} minutes."

        rain_24h = snapshot["rain_24h_mm"]
        forecast_rain = snapshot["forecast_rain_24h_mm"]
        pop = snapshot["pop_percent"]
        temp = snapshot["temperature_c"]
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

        if rain_24h > float(config["rain_24h_threshold_mm"]):
            final = 0
            triggered.append("rain_skip")
            reason = f"Today's watering skipped. Rainfall in the last 24 hours was {rain_24h:.1f} mm."
        elif pop > float(config["pop_threshold_percent"]) and forecast_rain > float(config["forecast_rain_threshold_mm"]):
            final = 0
            triggered.append("forecast_skip")
            reason = f"Today's watering skipped. Expected rainfall is {forecast_rain:.1f} mm with {pop:.0f}% precipitation probability."
        elif soil_usable and soil_percent > float(config.get("soil_wet_skip_threshold_percent") or 85):
            final = 0
            triggered.append("soil_wet_skip")
            reason = f"Today's watering skipped. {soil['name'] or 'Soil sensor'} reports {soil_percent:.0f}% soil moisture."
        elif soil_usable and soil_percent < float(config.get("soil_dry_threshold_percent") or 45):
            correction = int(config.get("soil_dry_correction_percent") or 15)
            final = max(1, int(round(base * (1 + correction / 100.0))))
            triggered.append("soil_dry_increase")
            corrections.append({"rule": "soil_dry_increase", "percent": correction, "minutes": final - base})
            reason = f"Today's watering increased from {base} to {final} minutes. {soil['name'] or 'Soil sensor'} reports {soil_percent:.0f}% soil moisture."
        elif temp is not None and temp > float(config["heat_threshold_c"]):
            correction = int(config["heat_correction_percent"])
            final = max(1, int(round(base * (1 + correction / 100.0))))
            triggered.append("heat_increase")
            corrections.append({"rule": "heat_increase", "percent": correction, "minutes": final - base})
            reason = f"Today's watering increased from {base} to {final} minutes. The expected maximum temperature is {temp:.1f} C."
        elif temp is not None and temp < float(config["cold_threshold_c"]):
            correction = int(config["cold_correction_percent"])
            final = max(1, int(round(base * (1 + correction / 100.0))))
            triggered.append("cold_decrease")
            corrections.append({"rule": "cold_decrease", "percent": correction, "minutes": final - base})
            reason = f"Today's watering reduced from {base} to {final} minutes. The expected maximum temperature is {temp:.1f} C."

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
                    "Wind": snapshot["wind_speed_mps"],
                    "LocalTemperature": snapshot["local_sensor"]["temperature_c"],
                    "LocalHumidity": snapshot["local_sensor"]["humidity_percent"],
                    "LocalAbsoluteHumidity": snapshot["local_sensor"]["absolute_humidity_g_m3"],
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
                },
                "rules": {
                    "rain_skip": "rain_skip" in triggered,
                    "forecast_skip": "forecast_skip" in triggered,
                    "soil_wet_skip": "soil_wet_skip" in triggered,
                    "soil_dry_increase": "soil_dry_increase" in triggered,
                    "heat_increase": "heat_increase" in triggered,
                    "cold_decrease": "cold_decrease" in triggered,
                },
                "result": {
                    "base_duration": base,
                    "base_source": base_source,
                    "base_schedule": base_schedule,
                    "corrections": corrections,
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
        now = time.monotonic()
        with self._weather_summary_lock:
            if (
                not force
                and self._weather_summary_cache["data"] is not None
                and self._weather_summary_cache["expires_at"] > now
            ):
                return self._weather_summary_cache["data"]
        data = self.weather_summary()
        with self._weather_summary_lock:
            self._weather_summary_cache["data"] = data
            self._weather_summary_cache["expires_at"] = time.monotonic() + self.weather_summary_cache_ttl
        return data

    def cached_pilot_recommendation(self, force: bool = False):
        now = time.monotonic()
        with self._pilot_lock:
            if (
                not force
                and self._pilot_cache["recommendation"] is not None
                and self._pilot_cache["expires_at"] > now
            ):
                return self._pilot_cache["recommendation"]
        recommendation = self.evaluate_pilot()
        with self._pilot_lock:
            self._pilot_cache["recommendation"] = recommendation
            self._pilot_cache["expires_at"] = time.monotonic() + self.pilot_cache_ttl
        return recommendation

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
                cold_threshold_c = %s,
                cold_correction_percent = %s,
                soil_moisture_enabled = %s,
                soil_wet_skip_threshold_percent = %s,
                soil_dry_threshold_percent = %s,
                soil_dry_correction_percent = %s,
                soil_sample_max_age_hours = %s,
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
                self.to_float(data.get("cold_threshold_c"), 22),
                self.to_int(data.get("cold_correction_percent"), -20),
                bool(data.get("soil_moisture_enabled", True)),
                self.to_float(data.get("soil_wet_skip_threshold_percent"), 85),
                self.to_float(data.get("soil_dry_threshold_percent"), 45),
                self.to_int(data.get("soil_dry_correction_percent"), 15),
                self.to_int(data.get("soil_sample_max_age_hours"), 12),
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
        now = time.monotonic()
        with self._snapshot_lock:
            if not force and self._snapshot_cache["data"] is not None and self._snapshot_cache["expires_at"] > now:
                return self._snapshot_cache["data"]
        data = self.build_snapshot()
        with self._snapshot_lock:
            self._snapshot_cache["data"] = data
            self._snapshot_cache["expires_at"] = time.monotonic() + self.snapshot_ttl
        return data

    def build_snapshot(self):
        self.refresh_daily_summaries()
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
            "live": self.mqtt_snapshot(),
            "latest": latest,
            "soil_moisture_24h": soil_moisture_24h,
            "sessions": sessions,
            "session_stats": session_stats,
            "scheduler_guard": self.manual_valve_scheduler_guard(),
            "schedules": self.fetch_schedules(),
            "energy_daily": energy,
            "pump_daily": pump_daily,
            "solar_daily": solar_daily,
            "temp_daily": temp_daily,
            "tank_daily": tank,
        }

    def statistics_payload(self):
        cached = self.api_cache_get("irrigation_statistics")
        if cached is not None:
            return cached
        self.refresh_daily_summaries()
        moisture_topic_list = ", ".join(f"'{topic}'" for topic in IRRIGATION_MOISTURE_TOPICS)
        tank_24h = self.fetch_all(
            """
            select
              date_trunc('minute', ts) as ts,
              round(avg(v_num) filter (where key = 'liquid_level_percent')::numeric, 2) as level_percent,
              round(avg(v_num) filter (where key = 'liquid_depth')::numeric, 3) as depth_m
            from hc.measurement
            where key in ('liquid_level_percent', 'liquid_depth')
              and ts >= now() - interval '24 hours'
            group by date_trunc('minute', ts)
            order by ts
            """
        )
        soil_moisture_rows_24h = self.fetch_all(
            f"""
            select
              e.id as entity_id,
              e.name as entity_name,
              d.name as device_name,
              date_trunc('minute', m.ts) as ts,
              round(avg(m.v_num)::numeric, 2) as soil_moisture
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            join hc.entity_metric em on em.entity_id = e.id and em.metric_key = m.key
            where m.key = 'soil_moisture'
              and m.ts >= now() - interval '24 hours'
              and e.is_active
              and d.is_active
              and em.is_enabled
              and e.topic_base in ({moisture_topic_list})
            group by e.id, e.name, d.name, date_trunc('minute', m.ts)
            order by e.name, date_trunc('minute', m.ts)
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
            series.sort(key=lambda item: item["entity_name"])
            return series

        soil_moisture_24h = soil_moisture_series(soil_moisture_rows_24h)
        soil_moisture_7d = soil_moisture_series(soil_moisture_rows_7d)
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
        return self.api_cache_set(
            "irrigation_statistics",
            {
                "tank_24h": tank_24h,
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
                "sessions": self.fetch_all(
                    """
                    select *
                    from hc.irrigation_session_stats
                    order by started_at desc
                    limit 300
                    """
                ),
            },
            60,
        )

    def start_scheduled_session(self, schedule_id: int):
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
        if decision["mode"] == "navigator":
            self.log_pilot_decision(decision, schedule_id=row["id"], execution_status="navigator_only")
            print(f"[PILOT] navigator schedule_id={row['id']} final={decision['final_duration']} reason={decision['reason']}", flush=True)
        else:
            decision["executed"] = False

        if decision["mode"] == "pilot" and int(decision["final_duration"]) <= 0:
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
        session = self.execute_one(
            """
            insert into hc.irrigation_manual_session
              (requested_stop_at, safety_stop_at, status, started_by, start_payload)
            values (
              now() + (%s::text || ' minutes')::interval,
              now() + (%s::text || ' minutes')::interval,
              'starting',
              %s,
              %s::jsonb
            )
            returning *
            """,
            (minutes, self.manual_max_minutes, "pilot" if decision["mode"] == "pilot" else "scheduler", json.dumps(valve_payload)),
        )
        valve_ok, valve_message, valve_details = self.publish_open_with_confirmation(valve_payload)
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
                where status in ('running', 'starting')
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
        session = self.execute_one(
            """
            insert into hc.irrigation_manual_session
              (requested_stop_at, safety_stop_at, status, started_by, start_payload)
            values (
              now() + (%s::text || ' minutes')::interval,
              now() + (%s::text || ' minutes')::interval,
              'starting',
              'v2_scheduler',
              %s::jsonb
            )
            returning *
            """,
            (minutes, self.manual_max_minutes, json.dumps(session_payload)),
        )
        if session:
            stop_policy = self.v2_stop_policy(row, decision, minutes, session.get("requested_stop_at"))
            session_payload["stop_policy"] = stop_policy
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
        valve_ok, valve_message, valve_details = self.publish_open_with_confirmation(command_payload)
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
            if decision["mode"] == "pilot":
                decision["executed"] = True
                self.log_pilot_decision(decision, schedule_id=row["id"], execution_status="v2_command_confirmed")
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
            self.mark_v2_execution(row["id"], "open", "confirmed", result)
        elif session:
            if decision["mode"] == "pilot":
                self.log_pilot_decision(decision, schedule_id=row["id"], execution_status="v2_start_failed")
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
        self.stop_v2_due_schedules()
