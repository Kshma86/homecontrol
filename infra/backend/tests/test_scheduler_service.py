import unittest
import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scheduler_service import SchedulerService


def noop(*args, **kwargs):
    return None


class SchedulerServiceTest(unittest.TestCase):
    def service(self, **overrides):
        rows = []
        defaults = {
            "fetch_all": lambda *args, **kwargs: rows,
            "fetch_one": lambda *args, **kwargs: {"mode": "v2_execute_all"},
            "execute_one": lambda *args, **kwargs: {"mode": args[1][0] if len(args) > 1 and args[1] else "v2_execute_all"},
            "ensure_schema": noop,
            "normalize_text": lambda value, default="": str(value or "").strip() or default,
            "json_time": lambda value: value.isoformat() if hasattr(value, "isoformat") else value,
            "json_dumps": lambda value: json.dumps(value, default=str),
            "fetch_irrigation_schedules": lambda: [],
            "fetch_climate_schedule_rules": lambda: [],
            "x10_scheduler_entries": lambda: [],
            "x10_day_mask_index_by_hc_day": lambda: [1, 2, 3, 4, 5, 6, 0],
            "scheduler_modes": {
                "v2_execute_irrigation",
                "v2_execute_x10",
                "v2_execute_climate",
                "v2_execute_x10_climate",
                "v2_execute_all",
            },
            "v2_execution_enabled": True,
            "v2_allow_irrigation": True,
            "v2_allow_x10": False,
            "v2_allow_climate": True,
        }
        defaults.update(overrides)
        service = SchedulerService(**defaults)
        service.rows = rows
        return service

    def test_engine_state_allows_only_enabled_domains(self):
        service = self.service()

        engine = service.engine_state({"mode": "v2_execute_all"})

        self.assertFalse(engine["publish_enabled"])
        self.assertEqual(engine["requested_domains"], ["irrigation", "xiaomi_x10", "climate"])
        self.assertEqual(engine["publish_domains"], ["irrigation", "climate"])

    def test_ai_summary_payload_does_not_fetch_jobs_or_history(self):
        service = self.service()
        service.shadow_jobs = lambda: self.fail("ai summary must not build full shadow jobs")
        service.history_rows = lambda *args, **kwargs: self.fail("ai summary must not fetch scheduler history")
        service.core_summary = lambda *args, **kwargs: self.fail("ai summary must not fetch V2 core chains")

        payload = service.ai_summary_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["config"]["mode"], "v2_execute_all")

    def test_update_config_normalizes_old_mode_alias(self):
        service = self.service()

        row = service.update_config("unified_shadow", updated_by="test")

        self.assertEqual(row["mode"], "v2_execute_all")

    def test_update_config_rejects_unknown_mode(self):
        service = self.service()

        with self.assertRaises(ValueError):
            service.update_config("space_mode")

    def test_shadow_jobs_combines_irrigation_x10_and_climate(self):
        service = self.service(
            fetch_irrigation_schedules=lambda: [
                {"id": 1, "label": "Garden", "day_of_week": 0, "start_time": "06:00", "stop_time": "06:20", "is_active": True, "schedule_status": "armed", "duration_minutes": 20}
            ],
            x10_scheduler_entries=lambda: [{"task_id": "abc", "days": "0100000", "enabled": "1", "time": "09:00"}],
            fetch_climate_schedule_rules=lambda: [
                {"id": 2, "label": "Heat", "day_of_week": 1, "start_time": "07:00", "is_enabled": True, "schedule_status": "armed", "power": "on", "mode": "heat", "target_temperature": 23, "fan_speed": "auto", "light": "off", "rule_engine": {}}
            ],
        )

        jobs = service.shadow_jobs()

        self.assertEqual([job["domain"] for job in jobs], ["irrigation", "xiaomi_x10", "climate"])
        self.assertEqual(jobs[0]["label"], "Garden")
        self.assertEqual(jobs[1]["days"], [0])
        self.assertEqual(jobs[2]["payload"]["target_temperature"], 23)

    def test_shadow_audit_events_selects_due_x10_and_climate_jobs(self):
        service = self.service(
            fetch_one=lambda *args, **kwargs: {"mode": "v2_execute_all"},
            fetch_irrigation_schedules=lambda: [],
            x10_scheduler_entries=lambda: [{"task_id": "abc", "days": "0100000", "enabled": "1", "time": "09:00"}],
            fetch_climate_schedule_rules=lambda: [
                {"id": 2, "label": "Heat", "day_of_week": 0, "start_time": "09:00", "is_enabled": True, "schedule_status": "armed", "power": "on", "mode": "heat", "target_temperature": 23, "fan_speed": "auto", "light": "off", "rule_engine": {}}
            ],
        )

        events = service.shadow_audit_events(clock={"today": "2026-07-24", "day_of_week": 0, "local_minute": "09:00"})

        self.assertEqual([event["action"] for event in events], ["clean_start", "climate_set"])
        self.assertTrue(events[0]["key"].startswith("shadow:xiaomi_x10:hc_x10:abc:clean_start:2026-07-24"))
        self.assertEqual(events[1]["payload"]["target_temperature"], 23)

    def test_shadow_audit_events_adds_irrigation_pilot_decision(self):
        service = self.service(
            fetch_one=lambda *args, **kwargs: {"mode": "v2_execute_all"},
            fetch_irrigation_schedules=lambda: [
                {"id": 1, "label": "Garden", "day_of_week": 0, "start_time": "06:00", "stop_time": "06:20", "is_active": True, "schedule_status": "due_now", "duration_minutes": 20}
            ],
            evaluate_irrigation_pilot=lambda **kwargs: {
                "mode": "pilot",
                "reason": "dry",
                "triggered_rules": ["extend"],
                "base_duration": 20,
                "final_duration": 30,
                "weather_snapshot": {"rain": 0},
            },
        )

        events = service.shadow_audit_events(clock={"today": "2026-07-24", "day_of_week": 0, "local_minute": "06:00"})

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "water_start")
        self.assertEqual(events[0]["payload"]["duration_minutes"], 30)
        self.assertEqual(events[0]["payload"]["stop_authority"], "v2_rule_effective_stop")

    def test_shadow_audit_events_skips_future_v2_irrigation_stop(self):
        future = datetime(2026, 7, 24, 8, 30, tzinfo=timezone.utc)
        service = self.service(
            fetch_one=lambda *args, **kwargs: {"mode": "v2_execute_irrigation"},
            fetch_irrigation_schedules=lambda: [
                {
                    "id": 1,
                    "label": "Garden",
                    "day_of_week": 0,
                    "start_time": "06:00",
                    "stop_time": "06:20",
                    "is_active": True,
                    "schedule_status": "done_today",
                    "duration_minutes": 20,
                    "last_started_on": "2026-07-24",
                    "last_stopped_on": None,
                }
            ],
            fetch_irrigation_v2_session=lambda source_ref: {"requested_stop_at": future},
            now=lambda tz=None: future - timedelta(minutes=10),
        )

        events = service.shadow_audit_events(clock={"today": "2026-07-24", "day_of_week": 0, "local_minute": "08:20"})

        self.assertEqual(events, [])

    def test_insert_irrigation_plan_and_execution_builds_stop_policy(self):
        def fetch_one(query, params=None):
            if "to_regclass" in query:
                return {"available": True}
            return None

        def execute_one(query, params=None):
            if "insert into hc.plan" in query:
                return {"id": "plan-1", "event_id": params[0], "domain": "irrigation", "target_ref": params[2]}
            if "insert into hc.execution" in query:
                return {"id": "exec-1", "domain": "irrigation", "command_payload": json.loads(params[3])}
            return {}

        service = self.service(
            fetch_one=fetch_one,
            execute_one=execute_one,
            irrigation_command_topic=lambda: "homecontrol/irrigation/valve/set",
        )
        payload = {
            "source_ref": "7",
            "label": "Garden",
            "duration_minutes": 30,
            "start_time": "06:00",
            "stop_time": "06:30",
            "rule_engine": {"mode": "pilot", "reason": "dry"},
            "scheduler_run_id": 42,
        }

        plan = service.insert_v2_irrigation_plan_once({"id": "event-1", "domain": "irrigation", "type": "scheduler.water_start.shadow"}, "water_start", payload)
        execution = service.insert_v2_irrigation_execution_once(plan, "water_start", payload)

        self.assertEqual(plan["target_ref"], "7")
        self.assertEqual(execution["command_payload"]["value"], "open")
        self.assertEqual(execution["command_payload"]["stop_policy"]["stop_authority"], "v2_rule_effective_stop")

    def test_insert_x10_plan_and_execution_uses_schedule_topic(self):
        def fetch_one(query, params=None):
            return {"available": True} if "to_regclass" in query else None

        def execute_one(query, params=None):
            if "insert into hc.plan" in query:
                return {"id": "plan-x10", "event_id": params[0], "domain": "xiaomi_x10", "actions": json.loads(params[3])}
            if "insert into hc.execution" in query:
                return {"id": "exec-x10", "domain": "xiaomi_x10", "command_topic": params[2], "command_payload": json.loads(params[3])}
            return {}

        service = self.service(fetch_one=fetch_one, execute_one=execute_one, x10_schedule_clean_topic="x10/command/schedule_clean")

        plan = service.insert_v2_x10_plan_once(
            {"id": "event-x10", "domain": "xiaomi_x10", "type": "scheduler.clean_start.shadow"},
            "clean_start",
            {"source_ref": "abc", "segments": "1, 2", "start_time": "09:00", "days_mask": "0100000"},
        )
        execution = service.insert_v2_x10_execution_once(plan, {"scheduler_run_id": 1})

        self.assertEqual(plan["actions"][0]["command"]["segments"], [1, 2])
        self.assertEqual(execution["command_topic"], "x10/command/schedule_clean")
        self.assertTrue(execution["command_payload"]["shadow_only"])

    def test_x10_scheduler_tick_publishes_weekly_schedule(self):
        published = []
        execution_updates = []

        def fetch_all(query, params=None):
            if "from hc.x10_schedule_day" in query:
                return [
                    {
                        "day_index": 0,
                        "task_id": "hc-mon",
                        "is_enabled": True,
                        "start_time": "09:00",
                        "clean_mode": 0,
                        "map_id": 3,
                        "suction": 1,
                        "water_level": 1,
                        "segments": [1, 2],
                    }
                ]
            return []

        def execute_one(query, params=None):
            if "update hc.execution" in query:
                execution_updates.append(params)
                return {"status": params[0], "result": json.loads(params[1])}
            return {}

        service = self.service(
            fetch_all=fetch_all,
            fetch_one=lambda *args, **kwargs: {"mode": "v2_execute_x10"},
            execute_one=execute_one,
            v2_allow_x10=True,
            x10_scheduler_entries=lambda: [],
            x10_monitor_value=lambda key: False if key == "bridge/online" else None,
            x10_weekly_schedule_topic="x10/command/schedule_clean_week",
            publish_mqtt=lambda topic, payload: published.append((topic, payload)) or (True, "published"),
        )

        result = service.x10_scheduler_tick()

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(published[0][0], "x10/command/schedule_clean_week")
        self.assertEqual(published[0][1]["schedules"][0]["start_time"], "09:00")
        self.assertEqual(execution_updates[0][0], "confirmed")

    def test_x10_scheduler_tick_blocks_invalid_weekly_schedule_payload(self):
        published = []
        execution_updates = []

        def fetch_all(query, params=None):
            if "from hc.x10_schedule_day" in query:
                return [
                    {
                        "day_index": 0,
                        "task_id": "hc-mon",
                        "is_enabled": True,
                        "start_time": "09:00",
                        "clean_mode": None,
                        "map_id": None,
                        "suction": None,
                        "water_level": None,
                        "segments": [],
                    }
                ]
            return []

        def execute_one(query, params=None):
            if "update hc.execution" in query:
                execution_updates.append(params)
                return {"status": params[0], "result": json.loads(params[1]), "error": params[2]}
            return {}

        service = self.service(
            fetch_all=fetch_all,
            fetch_one=lambda *args, **kwargs: {"mode": "v2_execute_x10"},
            execute_one=execute_one,
            v2_allow_x10=True,
            x10_scheduler_entries=lambda: [],
            x10_weekly_schedule_topic="x10/command/schedule_clean_week",
            publish_mqtt=lambda topic, payload: published.append((topic, payload)) or (True, "published"),
        )

        result = service.x10_scheduler_tick()

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["result"]["reason"], "invalid_x10_schedule_payload")
        self.assertEqual(published, [])
        self.assertEqual(execution_updates[0][0], "blocked")

    def test_insert_climate_execution_publishes_when_domain_enabled(self):
        published = []

        def fetch_one(query, params=None):
            if "to_regclass" in query:
                return {"available": True}
            if "select * from hc.execution" in query:
                return None
            return {"mode": "v2_execute_climate"}

        def execute_one(query, params=None):
            if "insert into hc.plan" in query:
                return {"id": "plan-climate", "event_id": params[0], "domain": "climate", "actions": json.loads(params[3])}
            if "insert into hc.execution" in query:
                return {"id": "exec-climate", "domain": "climate", "status": params[3], "result": json.loads(params[6])}
            return {}

        service = self.service(
            fetch_one=fetch_one,
            execute_one=execute_one,
            v2_allow_x10=True,
            climate_command_topic="climate/command",
            climate_state_payload=lambda: {"power": "off"},
            publish_mqtt=lambda topic, payload: published.append((topic, payload)) or (True, "published"),
            sync_auto_climate_power_wall=lambda power: [{"power": power}],
        )

        plan = service.insert_v2_climate_plan_once(
            {"id": "event-climate", "domain": "climate", "type": "scheduler.climate_set.shadow"},
            "climate_set",
            {"source_ref": "rule-1", "power": "on", "climate_mode": "heat", "target_temperature": 23},
        )
        execution = service.insert_v2_climate_execution_once(plan, {"scheduler_run_id": 2})

        self.assertEqual(published[0][0], "climate/command")
        self.assertEqual(execution["status"], "confirmed")
        self.assertTrue(execution["result"]["published"])

    def test_x10_legacy_comparison_reports_strict_match(self):
        service = self.service(
            x10_scheduler_entries=lambda: [
                {
                    "task_id": "abc",
                    "time": "09:00",
                    "days": "0100000",
                    "enabled": "1",
                    "map_id": "3",
                    "clean_mode": "2",
                    "suction": "3",
                    "water_level": "2",
                    "segments": "1,2",
                }
            ],
        )
        chain = {
            "domain": "xiaomi_x10",
            "command_payload": {
                "start_time": "09:00",
                "days": "0100000",
                "enabled": 1,
                "map_id": 3,
                "mode": 2,
                "suction": 3,
                "water_level": 2,
                "segments": [1, 2],
            },
        }

        comparison = service.legacy_comparison(chain)

        self.assertEqual(comparison["status"], "match")

    def test_climate_confirmation_compares_cached_state(self):
        service = self.service(
            climate_state_payload=lambda: {
                "ok": True,
                "power": "ON",
                "mode": "Heat",
                "target_temperature": 23,
                "fan_speed": "Auto",
                "light": "off",
                "bridge_online": True,
            }
        )

        confirmation = service.climate_confirmation_diagnostics(
            {"power": "on", "mode": "heat", "target_temperature": "23", "fan_speed": "auto", "light": "off"}
        )

        self.assertEqual(confirmation["status"], "matching_climate_state_seen")

    def test_irrigation_legacy_comparison_reports_stop_drift_warning(self):
        requested = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
        stopped = datetime(2026, 7, 24, 8, 5, tzinfo=timezone.utc)

        def fetch_one(query, params=None):
            if "irrigation_manual_session" in query:
                return {
                    "status": "stopped",
                    "stopped_at": stopped,
                    "requested_stop_at": requested,
                    "start_payload": {"duration_minutes": 20},
                }
            return {"mode": "v2_execute_all"}

        service = self.service(fetch_one=fetch_one)

        comparison = service.legacy_comparison({"domain": "irrigation", "command_payload": {"schedule_id": "7", "value": "close"}})

        self.assertEqual(comparison["status"], "match")
        self.assertEqual(comparison["warnings"][0]["kind"], "legacy_stop_drift")

    def test_irrigation_preflight_uses_guard_and_recent_chain_status(self):
        service = self.service(
            check_db=lambda: True,
            check_mqtt=lambda **kwargs: True,
            manual_valve_scheduler_guard=lambda: {"blocked": False, "state": "AUTO"},
            running_irrigation_session=lambda: None,
        )
        engine = service.engine_state({"mode": "v2_execute_irrigation"})

        preflight = service.v2_irrigation_preflight(
            engine,
            [{"domain": "irrigation", "legacy_comparison": {"status": "match", "warnings": []}}],
        )

        self.assertEqual(preflight["domain"], "irrigation")
        self.assertFalse(preflight["block_count"])
        self.assertEqual([check["key"] for check in preflight["checks"][:4]], ["mode", "engine_enabled", "irrigation_allowed", "db"])

    def test_x10_preflight_blocks_active_cleaning(self):
        def fetch_all(query, params=None):
            if "hc.x10_schedule_day" in query:
                return [
                    {
                        "day_index": 0,
                        "task_id": "abc",
                        "is_enabled": True,
                        "start_time": "09:00",
                        "clean_mode": "2",
                        "map_id": "3",
                        "suction": "3",
                        "water_level": "2",
                        "segments": "1,2",
                    }
                ]
            return []

        monitor = {
            "bridge/online": True,
            "robot_state_text": "cleaning",
            "room_clean/status": {"status": "active"},
        }
        service = self.service(
            fetch_all=fetch_all,
            x10_scheduler_entries=lambda: [
                {"task_id": "abc", "time": "09:00", "days": "0100000", "enabled": "1", "clean_mode": "2", "map_id": "3", "suction": "3", "water_level": "2", "segments": "1,2"}
            ],
            x10_monitor_value=lambda key: monitor.get(key),
            v2_allow_x10=True,
            check_db=lambda: True,
            check_mqtt=lambda **kwargs: True,
        )
        engine = service.engine_state({"mode": "v2_execute_x10"})

        preflight = service.v2_x10_preflight(engine, [])

        active_check = next(check for check in preflight["checks"] if check["key"] == "active_cleaning")
        self.assertEqual(active_check["status"], "block")

    def test_climate_preflight_reports_cached_state_and_rules(self):
        service = self.service(
            fetch_climate_schedule_rules=lambda: [{"id": 1, "is_enabled": True}],
            climate_state_payload=lambda: {"ok": True, "bridge_online": True, "power": "on", "mode": "heat", "target_temperature": 23},
            check_db=lambda: True,
            check_mqtt=lambda **kwargs: True,
        )
        engine = service.engine_state({"mode": "v2_execute_climate"})

        preflight = service.v2_climate_preflight(engine, [{"domain": "climate", "legacy_comparison": {"status": "match"}}])

        self.assertEqual(preflight["overall"], "READY")
        self.assertIn("cached_state", [check["key"] for check in preflight["checks"]])

    def test_core_summary_reports_unavailable_when_v2_tables_missing(self):
        service = self.service(fetch_one=lambda *args, **kwargs: {"has_event": False, "has_plan": False, "has_execution": False})

        summary = service.core_summary()

        self.assertFalse(summary["available"])
        self.assertEqual(summary["counts"], {"events": 0, "plans": 0, "executions": 0})

    def test_core_summary_enriches_chains_and_preflight(self):
        def fetch_one(query, params=None):
            if "to_regclass" in query:
                return {"has_event": True, "has_plan": True, "has_execution": True}
            if "count(*) from hc.event" in query:
                return {"events": 1, "plans": 1, "executions": 1}
            if "scheduler_config" in query:
                return {"mode": "v2_execute_irrigation"}
            return {"mode": "v2_execute_irrigation"}

        def fetch_all(query, params=None):
            if "with activity" in query:
                return [{"kind": "event", "id": "event-1"}]
            if "left join hc.plan" in query:
                return [
                    {
                        "event_id": "event-1",
                        "domain": "irrigation",
                        "execution_id": "exec-1",
                        "command_payload": {"schedule_id": "7", "value": "open"},
                    }
                ]
            return []

        service = self.service(
            fetch_one=fetch_one,
            fetch_all=fetch_all,
            check_db=lambda: True,
            check_mqtt=lambda **kwargs: True,
            manual_valve_scheduler_guard=lambda: {"blocked": False, "state": "AUTO"},
            running_irrigation_session=lambda: None,
        )

        summary = service.core_summary()

        self.assertTrue(summary["available"])
        self.assertIn("execution_engine", summary["chains"][0])
        self.assertIn("irrigation", summary["preflight"])

    def test_ensure_scheduler_schema_runs_once(self):
        calls = []
        service = self.service(execute_sql=lambda sql: calls.append(sql))

        service.ensure_scheduler_schema()
        service.ensure_scheduler_schema()

        self.assertEqual(len(calls), 1)
        self.assertIn("create table if not exists hc.scheduler_config", calls[0])
        self.assertIn("create table if not exists hc.climate_schedule_rule", calls[0])

    def test_simulation_payload_validates_domain_action(self):
        service = self.service()

        with self.assertRaises(ValueError):
            service.simulation_payload({"domain": "xiaomi_x10", "action": "water_start"})

    def test_simulate_v2_scheduler_chain_builds_climate_chain(self):
        service = self.service(
            fetch_one=lambda *args, **kwargs: {"mode": "v2_execute_all"},
            climate_state_payload=lambda: {"ok": True, "bridge_online": True, "power": "on", "mode": "heat", "target_temperature": 23},
            climate_command_topic="climate/command",
        )

        result = service.simulate_v2_scheduler_chain(
            {"domain": "climate", "action": "climate_set", "source_ref": "rule-1", "target_temperature": 24}
        )

        self.assertTrue(result["simulated"])
        self.assertEqual(result["chain"]["domain"], "climate")
        self.assertEqual(result["chain"]["command_topic"], "climate/command")
        self.assertEqual(result["chain"]["command_payload"]["target_temperature"], 24)


if __name__ == "__main__":
    unittest.main()
