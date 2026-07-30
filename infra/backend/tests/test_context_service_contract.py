import unittest
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from context_service import AI_CONTEXT_SCHEMA_VERSION, CONTEXT_SCHEMA_VERSION, ContextService


class ContextServiceContractTest(unittest.TestCase):
    def test_snapshot_includes_contract_metadata(self):
        service = ContextService({"weather": lambda: {"temperature_c": 21}})

        payload = service.snapshot()

        self.assertEqual(payload["schema_version"], CONTEXT_SCHEMA_VERSION)
        self.assertEqual(payload["contract"]["name"], "hc_context")
        self.assertEqual(payload["contract"]["available_sections"], ["weather"])

    def test_ai_summary_includes_source_contract_metadata(self):
        service = ContextService({
            "weather": lambda: {},
            "irrigation": lambda: {},
            "climate": lambda: {},
            "robot": lambda: {},
            "power_wall": lambda: {},
            "solar": lambda: {},
            "tuya": lambda: {},
            "scheduler_ai": lambda: {},
            "backup": lambda: {},
            "notes": lambda: {},
        })

        payload = service.ai_summary()

        self.assertEqual(payload["schema_version"], AI_CONTEXT_SCHEMA_VERSION)
        self.assertEqual(payload["contract"]["source_version"], CONTEXT_SCHEMA_VERSION)

    def test_expensive_realtime_sections_use_statistics_ttl(self):
        service = ContextService({"scheduler": lambda: {}}, realtime_ttl=5, statistics_ttl=60)

        payload = service.section("scheduler")

        self.assertEqual(payload["_context"]["ttl_sec"], 60)

    def test_ai_summary_uses_lightweight_scheduler_section(self):
        calls = []
        service = ContextService({
            "weather": lambda: {},
            "irrigation": lambda: {},
            "climate": lambda: {},
            "robot": lambda: {},
            "power_wall": lambda: {},
            "solar": lambda: {},
            "tuya": lambda: {},
            "scheduler_ai": lambda: calls.append("scheduler_ai") or {},
            "backup": lambda: {},
            "notes": lambda: {},
        })

        payload = service.ai_summary()

        self.assertTrue(payload["ok"])
        self.assertEqual(calls, ["scheduler_ai"])

    def test_ai_summary_includes_compact_irrigation_pilot_when_available(self):
        service = ContextService({
            "weather": lambda: {},
            "irrigation": lambda: {},
            "climate": lambda: {},
            "robot": lambda: {},
            "power_wall": lambda: {},
            "solar": lambda: {},
            "tuya": lambda: {},
            "scheduler_ai": lambda: {},
            "backup": lambda: {},
            "notes": lambda: {},
            "irrigation_pilot": lambda: {
                "config": {"mode": "pilot", "base_duration_minutes": 90},
                "recommendation": {
                    "mode": "pilot",
                    "final_duration": 0,
                    "triggered_rules": ["rain_skip"],
                    "reason": "rain",
                },
                "today_decision": {
                    "execution_status": "skipped",
                    "triggered_rules": ["rain_skip"],
                },
            },
        })

        payload = service.ai_summary()

        self.assertEqual(payload["irrigation_pilot"]["config"]["mode"], "pilot")
        self.assertEqual(payload["irrigation_pilot"]["recommendation"]["triggered_rules"], ["rain_skip"])
        self.assertEqual(payload["irrigation_pilot"]["today_decision"]["execution_status"], "skipped")

    def test_ai_summary_includes_compact_server_power_when_available(self):
        service = ContextService({
            "weather": lambda: {},
            "irrigation": lambda: {},
            "climate": lambda: {},
            "robot": lambda: {},
            "power_wall": lambda: {},
            "solar": lambda: {},
            "tuya": lambda: {},
            "scheduler_ai": lambda: {},
            "backup": lambda: {},
            "notes": lambda: {},
            "server_power": lambda: {
                "ok": True,
                "device": {"display_name": "HC szerver", "entity_name": "plug"},
                "power_24h": [{"power_w": 20}, {"power_w": 30}],
                "daily_30d": [{"energy_kwh": 0.4}, {"energy_kwh": 0.6}],
                "summary": {"current_power_w": 25, "today_energy_kwh": 0.5, "power_samples": 2},
            },
        })

        payload = service.ai_summary()

        self.assertEqual(payload["server_power"]["device"]["display_name"], "HC szerver")
        self.assertEqual(payload["server_power"]["avg_power_w_24h"], 25)
        self.assertEqual(payload["server_power"]["avg_daily_energy_kwh_7d"], 0.5)

    def test_ai_summary_includes_compact_climate_power_when_available(self):
        today = date.today()
        service = ContextService({
            "weather": lambda: {},
            "irrigation": lambda: {},
            "climate": lambda: {},
            "robot": lambda: {},
            "power_wall": lambda: {},
            "solar": lambda: {},
            "tuya": lambda: {},
            "scheduler_ai": lambda: {},
            "backup": lambda: {},
            "notes": lambda: {},
            "climate_power_history": lambda: {
                "ok": True,
                "meter": {"entity_name": "Gree klíma", "device_name": "Climate plug"},
                "power_24h": [{"power_w": 100}, {"power_w": 200}],
                "daily_30d": [{"day": today.isoformat(), "energy_kwh": 1.2}, {"day": today.isoformat(), "energy_kwh": 0.8}],
                "summary": {"today_energy_kwh": 0.8, "power_samples": 2, "daily_days": 2},
            },
        })

        payload = service.ai_summary()

        self.assertEqual(payload["climate_power"]["meter"]["entity_name"], "Gree klíma")
        self.assertEqual(payload["climate_power"]["avg_power_w_24h"], 150)
        self.assertEqual(payload["climate_power"]["energy_kwh_30d"], 2.0)
        self.assertEqual(payload["climate_power"]["month_energy_kwh"], 2.0)

    def test_ai_summary_includes_compact_climate_schedules_when_available(self):
        service = ContextService({
            "weather": lambda: {},
            "irrigation": lambda: {},
            "climate": lambda: {"power": "on", "mode": "cool", "target_temperature": 23, "fan_speed": "auto", "light": "off"},
            "robot": lambda: {},
            "power_wall": lambda: {},
            "solar": lambda: {},
            "tuya": lambda: {},
            "scheduler_ai": lambda: {},
            "backup": lambda: {},
            "notes": lambda: {},
            "climate_schedules": lambda: {
                "ok": True,
                "schedules": [
                    {"id": 1, "label": "Evening cool", "day_of_week": 0, "start_time": "18:00", "is_enabled": True, "power": "on", "mode": "cool", "target_temperature": 23, "fan_speed": "auto", "light": "off", "schedule_status": "armed"},
                    {"id": 2, "label": "Disabled", "day_of_week": 1, "start_time": "08:00", "is_enabled": False, "power": "off", "mode": "cool", "target_temperature": 24, "fan_speed": "low", "light": "off", "schedule_status": "disabled"},
                ],
            },
        })

        payload = service.ai_summary()

        self.assertEqual(payload["climate"]["fan_speed"], "auto")
        self.assertEqual(payload["climate_schedules"]["count"], 2)
        self.assertEqual(payload["climate_schedules"]["enabled_count"], 1)
        self.assertEqual(payload["climate_schedules"]["enabled_schedules"][0]["target_temperature"], 23)

    def test_ai_summary_includes_compact_climate_history_when_available(self):
        service = ContextService({
            "weather": lambda: {},
            "irrigation": lambda: {},
            "climate": lambda: {},
            "robot": lambda: {},
            "power_wall": lambda: {},
            "solar": lambda: {},
            "tuya": lambda: {},
            "scheduler_ai": lambda: {},
            "backup": lambda: {},
            "notes": lambda: {},
            "climate_history": lambda: {
                "ok": True,
                "latest": {"climate_mode": "cool"},
                "numeric_7d": {"climate_target_temperature": {"avg": 22}},
                "distributions_7d": {"climate_mode": [{"value": "cool", "sample_count": 4}]},
                "recent_setting_changes_7d": [{"key": "climate_mode", "value": "cool"}],
                "samples_24h": [{"key": "climate_current_temperature", "value": 24}],
                "summary": {"samples_24h": 1},
            },
        })

        payload = service.ai_summary()

        self.assertEqual(payload["climate_history"]["latest"]["climate_mode"], "cool")
        self.assertEqual(payload["climate_history"]["numeric_7d"]["climate_target_temperature"]["avg"], 22)
        self.assertIn("setting questions", payload["climate_history"]["analysis_goal"])
        self.assertNotIn("humidity", payload["climate_history"]["analysis_goal"])

    def test_ai_summary_includes_compact_ai_chat_audit_when_available(self):
        service = ContextService({
            "weather": lambda: {},
            "irrigation": lambda: {},
            "climate": lambda: {},
            "robot": lambda: {},
            "power_wall": lambda: {},
            "solar": lambda: {},
            "tuya": lambda: {},
            "scheduler_ai": lambda: {},
            "backup": lambda: {},
            "notes": lambda: {},
            "ai_chat_audit": lambda: {
                "ok": True,
                "sample_size": 3,
                "success": {"ok_rate_percent": 100},
                "latency": {"avg_total_ms": 200},
                "top_skills": [{"name": "ai", "count": 2}],
                "top_data_sources": [{"name": "context_section:ai_chat_audit", "count": 2}],
                "slow_context_sections": [{"name": "home_statistics", "avg_ms": 120}],
                "slow_skills": [{"name": "base", "avg_ms": 1}],
                "recent_questions": [{"question": "elemezd az AI kéréseket"}],
            },
        })

        payload = service.ai_summary()

        self.assertEqual(payload["ai_chat_audit"]["sample_size"], 3)
        self.assertEqual(payload["ai_chat_audit"]["top_skills"][0]["name"], "ai")
        self.assertIn("context layer", payload["ai_chat_audit"]["analysis_goal"])

    def test_warmup_builds_requested_sections(self):
        calls = []
        service = ContextService({"weather": lambda: calls.append("weather") or {}}, realtime_ttl=5, statistics_ttl=60)

        payload = service.warmup(["weather"])

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["warmed"], ["weather"])
        self.assertEqual(calls, ["weather"])


if __name__ == "__main__":
    unittest.main()
