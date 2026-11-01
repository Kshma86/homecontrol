import unittest

from mqtt_flood_detector import MqttFloodDetector


class MqttFloodDetectorTest(unittest.TestCase):
    def test_ignores_bridge_and_subtopics(self):
        detector = MqttFloodDetector()
        self.assertEqual(detector.observe("zigbee/bridge/health", 1), [])
        self.assertEqual(detector.observe("zigbee/device/set", 1), [])

    def test_raises_critical_after_sustained_rate_and_resolves(self):
        detector = MqttFloodDetector(
            warning_per_minute=3,
            critical_per_minute=5,
            sustain_seconds=10,
            recovery_seconds=10,
            window_seconds=60,
        )
        transitions = []
        for timestamp in range(13):
            for offset in range(5):
                transitions.extend(detector.observe("zigbee/0xabc", timestamp + offset / 10))

        self.assertEqual([item.severity for item in transitions], ["warning", "critical"])
        self.assertTrue(all(item.active for item in transitions))

        self.assertEqual(detector.sweep(73), [])
        resolved = detector.sweep(83)
        self.assertEqual(len(resolved), 1)
        self.assertFalse(resolved[0].active)
        self.assertEqual(resolved[0].severity, "resolved")

    def test_warning_does_not_fire_for_short_burst(self):
        detector = MqttFloodDetector(
            warning_per_minute=3,
            critical_per_minute=5,
            sustain_seconds=10,
            recovery_seconds=10,
        )
        for timestamp in (0, 1, 2, 3):
            self.assertEqual(detector.observe("zigbee/0xabc", timestamp), [])
        self.assertFalse(detector.snapshot("zigbee/0xabc", 3).active)
        self.assertEqual(detector.sweep(61), [])


if __name__ == "__main__":
    unittest.main()
