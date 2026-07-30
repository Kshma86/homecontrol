import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from command_service import CommandService


class FakeContextService:
    def __init__(self):
        self.invalidated = []

    def invalidate(self, section):
        self.invalidated.append(section)
        return {"ok": True, "section": section}


class CommandServiceTest(unittest.TestCase):
    def test_meta_deduplicates_sections_and_builds_read_after_urls(self):
        service = CommandService(lambda: FakeContextService())

        meta = service.meta("irrigation", "irrigation", "weather", "")

        self.assertEqual(meta["invalidated"], ["irrigation", "weather"])
        self.assertEqual(meta["read_after"], ["/api/context/irrigation", "/api/context/weather"])

    def test_invalidate_calls_context_service_once_per_unique_section(self):
        context = FakeContextService()
        service = CommandService(lambda: context)

        invalidated = service.invalidate("tuya", "power_wall", "tuya", source="test")

        self.assertEqual(invalidated, ["tuya", "power_wall"])
        self.assertEqual(context.invalidated, ["tuya", "power_wall"])
        self.assertEqual(service.recent_events(1)[0]["source"], "test")

    def test_mqtt_topic_mapping(self):
        service = CommandService(lambda: FakeContextService())

        self.assertEqual(service.sections_for_mqtt_topic("homecontrol/tele/irrigation/esp-irrigation-1/diag"), ["irrigation", "irrigation_pilot"])
        self.assertEqual(service.sections_for_mqtt_topic("zigbee/0xa4c13844a0908898"), ["irrigation", "irrigation_pilot", "irrigation_statistics"])
        self.assertEqual(service.sections_for_mqtt_topic("homecontrol/xiaomi_x10/status"), ["robot"])
        self.assertEqual(service.sections_for_mqtt_topic("homecontrol/gree_climate/state"), ["climate", "climate_power_history"])
        self.assertEqual(service.sections_for_mqtt_topic("homecontrol/cmd/tuya/kitchen/switch"), ["tuya", "power_wall"])


if __name__ == "__main__":
    unittest.main()
