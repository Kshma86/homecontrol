import unittest
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from robot_service import RobotService


class FakeMonitor:
    def __init__(self, values):
        self.values = values

    def snapshot(self):
        return {
            "mqtt_connected": True,
            "last_error": "",
            "broker": "mqtt:1883",
            "base_topic": "homecontrol/xiaomi_x10",
            "topics": {},
            "raw": [],
        }

    def value(self, key):
        return self.values.get(key)


class RobotServiceTest(unittest.TestCase):
    def service(self, values):
        return self.service_with_map_dir(values, None)

    def service_with_map_dir(self, values, map_dir):
        return RobotService(
            fetch_all=lambda *args, **kwargs: [],
            normalize_text=lambda value, default="": str(value or "").strip() or default,
            publish_mqtt=lambda *args, **kwargs: (True, "published"),
            invalidate_context=lambda *args, **kwargs: None,
            context_meta=lambda *sections: {"invalidated": list(sections)},
            monitor=FakeMonitor(values),
            base_topic="homecontrol/xiaomi_x10",
            map_dir=map_dir,
        )

    def test_state_payload_treats_none_strings_as_missing_telemetry(self):
        payload = self.service({
            "bridge/online": "1",
            "bridge/status": "online",
            "state": {"state": None, "state_text": "unknown_None", "battery": None},
            "robot_state": "None",
            "robot_state_text": "unknown_None",
            "battery": "None",
            "charge_status": "None",
            "task_state": "None",
            "clean_mode": "None",
            "suction": "None",
            "water_level": "None",
        }).state_payload()

        self.assertIsNone(payload["robot_state_text"])
        self.assertIsNone(payload["battery"])
        self.assertFalse(payload["telemetry_available"])
        self.assertIn("robot_state_text", payload["missing_telemetry_fields"])

    def test_state_payload_uses_state_topic_as_fallback(self):
        payload = self.service({
            "state": {"state": 8, "state_text": "charging", "battery": 82},
            "robot_state": "None",
            "robot_state_text": "None",
            "battery": "None",
        }).state_payload()

        self.assertEqual(payload["robot_state"], 8)
        self.assertEqual(payload["robot_state_text"], "charging")
        self.assertEqual(payload["battery"], 82)

    def test_state_payload_uses_latest_capture_status_when_mqtt_telemetry_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture_dir = Path(tmp) / "captures"
            capture_dir.mkdir()
            (capture_dir / "latest.jsonl").write_text(
                '{"kind":"status","ts":1784308125,"iso":"2026-07-17T19:08:45","label":"1. Szint","map_id":197,'
                '"data":{"battery":93,"charge_status":1,"clean_mode":0,"mop_attached":0,"state":6,'
                '"state_text":"idle_docked","suction":3,"task_state":6,"water_level":2}}\n',
                encoding="utf-8",
            )

            payload = self.service_with_map_dir({
                "state": {"state": None, "state_text": "unknown_None", "battery": None},
                "robot_state": "None",
                "robot_state_text": "unknown_None",
                "battery": "None",
                "charge_status": "None",
                "task_state": "None",
                "clean_mode": "None",
                "suction": "None",
                "water_level": "None",
            }, Path(tmp)).state_payload()

        self.assertTrue(payload["telemetry_available"])
        self.assertEqual(payload["telemetry_source"], "capture")
        self.assertEqual(payload["robot_state_text"], "idle_docked")
        self.assertEqual(payload["battery"], 93)
        self.assertEqual(payload["clean_mode"], 0)
        self.assertEqual(payload["suction"], 3)
        self.assertEqual(payload["water_level"], 2)


if __name__ == "__main__":
    unittest.main()
