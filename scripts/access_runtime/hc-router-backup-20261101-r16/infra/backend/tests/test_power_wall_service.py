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
            process_binding_entity_id=lambda key: 1,
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

    def test_climate_on_is_queued_but_off_cancels_and_publishes(self):
        from unittest.mock import Mock
        service = self.service()
        row = {"entity_id": 1, "entity_name": "fan", "auto_climate_delay_minutes": 3}
        service.fetch_all = Mock(return_value=[row])
        service.execute_one = Mock(return_value={"entity_id": 1})
        service.publish_switch = Mock(return_value=(True, "ok", "topic", {}))
        result = service.sync_auto_climate("on")
        self.assertEqual(result[0]["delay_minutes"], 3)
        service.publish_switch.assert_not_called()
        self.assertIn("coalesce(auto_climate_on_at", service.execute_one.call_args.args[0])
        service.sync_auto_climate("off")
        service.publish_switch.assert_called_once_with(row, False, "homecontrol-climate-auto")
        self.assertTrue(any("auto_climate_on_at = null" in call.args[0] for call in service.execute_one.call_args_list))

    def test_zero_delay_is_immediate_and_manual_command_cancels_pending(self):
        from unittest.mock import Mock
        service = self.service()
        row = {"entity_id": 1, "entity_name": "fan", "auto_climate_delay_minutes": 0}
        service.fetch_all = Mock(return_value=[row])
        service.execute_one = Mock(return_value={"entity_id": 1})
        service.publish_switch = Mock(return_value=(True, "ok", "topic", {}))
        service.sync_auto_climate("on")
        service.publish_switch.assert_called_once_with(row, True, "homecontrol-climate-auto")
        service.command_entity = Mock(return_value=row)
        service.cancel_climate_start = Mock()
        service.switch_command(1, False)
        service.cancel_climate_start.assert_called_once_with(1)

    def test_delayed_start_requires_successful_claim(self):
        from unittest.mock import Mock
        service = self.service()
        row = {"entity_id": 1, "auto_climate_on_at": "due"}
        service.fetch_all = Mock(return_value=[row])
        service.execute_one = Mock(return_value=None)
        service.publish_switch = Mock(return_value=(True, "ok", "topic", {}))
        service.climate_delay_tick()
        service.publish_switch.assert_not_called()
        service.execute_one.return_value = {"entity_id": 1}
        service.climate_delay_tick()
        service.publish_switch.assert_called_once_with(row, True, "homecontrol-climate-auto")

    def test_delay_validation(self):
        service = self.service()
        for value in [-1, 121, 1.5, True, "3"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                service.set_policy(1, delay_minutes=value)


if __name__ == "__main__":
    unittest.main()
