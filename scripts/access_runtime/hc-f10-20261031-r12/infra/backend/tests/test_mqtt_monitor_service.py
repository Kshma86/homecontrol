import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mqtt_monitor_service import IrrigationMqttMonitorState


class IrrigationMonitorReceiptTest(unittest.TestCase):
    def setUp(self):
        self.monitor = IrrigationMqttMonitorState("unused.invalid", 1883, "fixture", {
            "pump_metrics": "audit/tele", "esp_nano_status": "audit/status",
        })
        self.client = SimpleNamespace(subscribe=lambda *args, **kwargs: None)

    def message(self, retain=False):
        self.monitor._on_message(self.client, None, SimpleNamespace(
            topic="audit/tele", payload=b'{"valve":"CLOSED","last_tele_sec_ago":0}', retain=retain,
        ))

    def test_receipt_metadata_preserves_retained_flag_and_clock(self):
        self.monitor._on_connect(self.client, None, {}, 0)
        with patch("time.monotonic", return_value=123.5), patch("time.time", return_value=456.0):
            self.message(retain=True)
            live = self.monitor.snapshot()
        item = live["topics"]["pump_metrics"]
        self.assertTrue(item["retain"])
        self.assertEqual(item["received_monotonic"], 123.5)
        self.assertEqual(item["timestamp"], 456.0)
        self.assertEqual(item["connection_generation"], live["connection_generation"])

    def test_disconnect_reconnect_does_not_relabel_cached_receipts(self):
        self.monitor._on_connect(self.client, None, {}, 0)
        self.message()
        original = self.monitor.snapshot()
        self.monitor._on_disconnect(self.client, None, 1)
        self.assertFalse(self.monitor.snapshot()["mqtt_connected"])
        self.monitor._on_connect(self.client, None, {}, 0)
        reconnected = self.monitor.snapshot()
        self.assertTrue(reconnected["mqtt_connected"])
        self.assertGreater(reconnected["connection_generation"], original["connection_generation"])
        self.assertEqual(reconnected["topics"]["pump_metrics"], original["topics"]["pump_metrics"])
        self.message()
        refreshed = self.monitor.snapshot()
        self.assertEqual(refreshed["topics"]["pump_metrics"]["connection_generation"], refreshed["connection_generation"])

    def test_failed_connect_does_not_create_a_new_live_connection(self):
        self.monitor._on_connect(self.client, None, {}, 5)
        live = self.monitor.snapshot()
        self.assertFalse(live["mqtt_connected"])
        self.assertEqual(live["connection_generation"], 0)


if __name__ == "__main__":
    unittest.main()
