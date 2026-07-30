import json
import unittest
from pathlib import Path
import sys
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_proxy_service import AiKnowledgeLoader, AiProxyService


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class AiProxyServiceTest(unittest.TestCase):
    def service(self, responses=None, error=None, context=None, audit_rows=None, db_count=None):
        calls = []

        def fake_urlopen(req, timeout):
            calls.append((req, timeout))
            if error:
                raise error
            return FakeResponse((responses or [{"ok": True}]).pop(0))

        service = AiProxyService(
            "http://ai.local/",
            12,
            context_summary=lambda: context or {"schema_version": "context.ai.v1", "generated_at": "now", "ok": True},
            json_ready=lambda value: value,
            urlopen_func=fake_urlopen,
            knowledge_loader=AiKnowledgeLoader(max_chars=8000),
            audit_logger=(lambda row: audit_rows.append(row)) if audit_rows is not None else None,
            db_query_count=(lambda: db_count) if db_count is not None else None,
        )
        service.calls = calls
        return service

    def test_chat_rejects_empty_message(self):
        payload, status = self.service().chat({"message": " "})

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "message is required")

    def test_chat_sends_latest_history_and_context(self):
        service = self.service(responses=[{"ok": True, "reply": "szia"}])

        payload, status = service.chat({"message": "hello", "history": list(range(25))})

        self.assertEqual(status, 200)
        self.assertEqual(payload["context"]["schema_version"], "context.ai.v1")
        body = json.loads(service.calls[0][0].data.decode("utf-8"))
        self.assertEqual(body["history"], list(range(5, 25)))
        self.assertEqual(body["context"]["ok"], True)
        self.assertIn("knowledge_docs", body["context"])
        self.assertTrue(body["context"]["knowledge_docs"]["enabled"])

    def test_chat_routes_relevant_knowledge_docs(self):
        service = self.service(responses=[{"ok": True, "reply": "ok"}])

        service.chat({"message": "Mit csinál az X10 scheduler és a klíma?"})

        body = json.loads(service.calls[0][0].data.decode("utf-8"))
        knowledge = body["context"]["knowledge_docs"]
        self.assertIn("x10", knowledge["selected_modules"])
        self.assertIn("climate", knowledge["selected_modules"])
        self.assertIn("x10-domain.md", knowledge["files"])
        self.assertIn("climate-domain.md", knowledge["files"])
        self.assertIn("HomeControl AI Context Pack", knowledge["content"])

    def test_chat_records_audit_trace(self):
        audit_rows = []
        service = self.service(responses=[{"ok": True, "reply": "ok"}], audit_rows=audit_rows, db_count=7)

        payload, status = service.chat({"message": "Mit tudsz az X10 porszívóról?"})

        self.assertEqual(status, 200)
        self.assertEqual(payload["reply"], "ok")
        self.assertEqual(len(audit_rows), 1)
        row = audit_rows[0]
        self.assertEqual(row["question"], "Mit tudsz az X10 porszívóról?")
        self.assertEqual(row["db_query_count"], 7)
        self.assertIn("x10", row["skills"])
        self.assertGreaterEqual(row["total_ms"], 0)
        self.assertGreaterEqual(row["knowledge_ms"], 0)
        self.assertTrue(any(item.get("type") == "knowledge_doc" for item in row["data_sources"]))
        self.assertTrue(any(item.get("skill") == "x10" for item in row["skill_timings"]))

    def test_chat_strips_thinking_from_upstream_reply(self):
        service = self.service(responses=[{"ok": True, "reply": "Okay, let me reason.\n</think>\nA mai locsolás rendben volt."}])

        payload, status = service.chat({"message": "mesélj a mai locsolásról"})

        self.assertEqual(status, 200)
        self.assertEqual(payload["reply"], "A mai locsolás rendben volt.")

    def test_chat_answers_climate_power_from_context_without_model(self):
        service = self.service(
            responses=[{"ok": True, "reply": "wrong source"}],
            context={
                "schema_version": "context.ai.v1",
                "generated_at": "now",
                "ok": True,
                "climate_power": {
                    "ok": True,
                    "meter": {"entity_name": "Klíma fogyasztásmérő"},
                    "month_energy_kwh": 29.74,
                    "month_days": 26,
                    "today_energy_kwh": 0.0,
                    "current_power_w": 0.0,
                },
                "server_power": {"ok": True, "month_energy_kwh": 2.37},
            },
        )

        payload, status = service.chat({"message": "mennyi volt a fogyasztása a klímának a hónapban?"})

        self.assertEqual(status, 200)
        self.assertEqual(service.calls, [])
        self.assertIn("29.74 kWh", payload["reply"])
        self.assertIn("nem a HC szerver", payload["reply"])

    def test_chat_answers_ai_audit_analysis_from_context_without_model(self):
        service = self.service(
            responses=[{"ok": True, "reply": "wrong source"}],
            context={
                "schema_version": "context.ai.v1",
                "generated_at": "now",
                "ok": True,
                "ai_chat_audit": {
                    "ok": True,
                    "sample_size": 12,
                    "success": {"ok_rate_percent": 91.7, "error_count": 1},
                    "latency": {"avg_total_ms": 1234.5, "max_total_ms": 3000.0, "avg_db_query_count": 42.1},
                    "top_skills": [{"name": "ai", "count": 8}],
                    "top_data_sources": [{"name": "context_section:ai_chat_audit", "count": 8}],
                    "slow_context_sections": [{"name": "home_statistics", "avg_ms": 210.5}],
                    "slow_skills": [{"name": "ai", "avg_ms": 1.4}],
                    "recent_questions": [{"question": "elemezd az AI kéréseket"}],
                },
            },
        )

        payload, status = service.chat({"message": "Elemezd az AI kéréseket context layer fejlesztéshez"})

        self.assertEqual(status, 200)
        self.assertEqual(service.calls, [])
        self.assertIn("audit alapján elemzek", payload["reply"])
        self.assertIn("Minta: 12", payload["reply"])
        self.assertIn("home_statistics", payload["reply"])

    def test_chat_answers_climate_settings_followup_from_context_without_model(self):
        service = self.service(
            responses=[{"ok": True, "reply": "hallucinated"}],
            context={
                "schema_version": "context.ai.v1",
                "generated_at": "now",
                "ok": True,
                "climate": {"power": "off", "mode": "cool", "target_temperature": 20, "fan_speed": "auto", "light": "off", "current_temperature": 24},
                "climate_history": {
                    "ok": True,
                    "distributions_7d": {
                        "climate_mode": [{"value": "cool", "sample_count": 8}],
                        "climate_fan_speed": [{"value": "auto", "sample_count": 7}],
                    },
                    "numeric_7d": {
                        "climate_target_temperature": {"avg": 22.5, "min": 20, "max": 24, "sample_count": 6},
                    },
                    "recent_setting_changes_7d": [{"key": "climate_mode", "value": "cool"}],
                },
                "climate_schedules": {
                    "ok": True,
                    "enabled_schedules": [
                        {"label": "Night cool", "day_of_week": 0, "start_time": "22:00", "power": "on", "mode": "cool", "target_temperature": 23, "fan_speed": "auto", "light": "off", "schedule_status": "armed"},
                    ],
                },
                "home_statistics": {"sensors": [{"display_name": "Nappali", "latest_temperature_c": 24.4}]},
            },
        )

        payload, status = service.chat({
            "message": "azt is meg tudod mondani hogy milyen beállításokkal van használva általában?",
            "history": [{"role": "user", "content": "mennyi volt a fogyasztása a klímának a hónapban?"}],
        })

        self.assertEqual(status, 200)
        self.assertEqual(service.calls, [])
        self.assertIn("climate_history", payload["reply"])
        self.assertIn("cool (8)", payload["reply"])
        self.assertIn("átlag 22.5", payload["reply"])
        self.assertIn("Night cool", payload["reply"])
        self.assertNotIn("light=", payload["reply"])
        self.assertNotIn("páratartalom", payload["reply"])
        self.assertNotIn("Nappali", payload["reply"])

    def test_chat_asks_clarification_for_ambiguous_settings_without_model(self):
        service = self.service(responses=[{"ok": True, "reply": "slow answer"}])

        payload, status = service.chat({"message": "milyen beállításokkal van használva általában?", "history": []})

        self.assertEqual(status, 200)
        self.assertEqual(service.calls, [])
        self.assertIn("Pontosan melyik modul", payload["reply"])

    def test_unavailable_server_returns_proxy_error(self):
        payload, status = self.service(error=URLError("offline")).models()

        self.assertEqual(status, 502)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["local_models"], [])


if __name__ == "__main__":
    unittest.main()
