import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from power_wall_service import PowerWallService


def noop(*args, **kwargs):
    return None


class PowerWallServiceTest(unittest.TestCase):
    def service(self):
        return PowerWallService(
            fetch_all=noop,
            fetch_one=noop,
            execute_one=noop,
            publish_mqtt=noop,
            ensure_schema=noop,
            api_cache_get=lambda key: None,
            api_cache_set=lambda key, data, ttl: data,
            api_cache_delete_prefix=noop,
            normalize_text=lambda value, default="": str(value or "").strip() or default,
            guard_repeat_seconds=30,
        )

    def test_bool_from_request_value(self):
        service = self.service()

        self.assertTrue(service.bool_from_request_value("on"))
        self.assertTrue(service.bool_from_request_value(1))
        self.assertFalse(service.bool_from_request_value("off"))
        self.assertFalse(service.bool_from_request_value(0))
        self.assertIsNone(service.bool_from_request_value("maybe"))

    def test_parse_hhmm(self):
        service = self.service()

        self.assertEqual(service.parse_hhmm("06:30").strftime("%H:%M"), "06:30")
        with self.assertRaises(ValueError):
            service.parse_hhmm("6:xx")

    def test_random_minutes_clamps_inverted_ranges(self):
        service = self.service()

        value = service.random_minutes({"min": 10, "max": 3, "scheduler_jitter_minutes": 0}, "min", "max")

        self.assertEqual(value, 10)


if __name__ == "__main__":
    unittest.main()
