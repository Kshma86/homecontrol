"""A sleeping contact sensor must not lose its opening state after five minutes."""
from unittest.mock import patch
import unittest

from tests import test_combustion_safety_service as fixtures


class OpeningEventTest(unittest.TestCase):
    def setUp(self):
        fixtures.CombustionSafetyServiceTest.setUp(self)
        self.wall, self.mono = 1000., 500.
        wall = patch('combustion_safety_service.time.time', side_effect=lambda: self.wall)
        mono = patch('combustion_safety_service.time.monotonic', side_effect=lambda: self.mono)
        wall.start()
        mono.start()
        self.addCleanup(wall.stop)
        self.addCleanup(mono.stop)
        self.states[1]['power'] = 180
        self.openings[0].update(ext_id='kitchen', ts=self.wall-660)

    def tick_running(self):
        self.service.tick()
        self.wall += 1
        self.mono += 1
        return self.service.tick()

    def test_kitchen_open_eleven_minutes_ago_is_green_without_timestamp_rewrite(self):
        result = self.tick_running()
        self.assertTrue(result['primary_open'])
        self.assertEqual(result['level'], 'green')
        self.assertEqual(result['openings'][0]['ts'], 340.)
        for _ in range(20):
            self.wall += 60
            self.mono += 60
            self.assertEqual(self.service.tick()['level'], 'green')
        self.assertEqual(self.openings[0]['ts'], 340.)

    def test_old_secondary_open_is_secondary_without_primary_open(self):
        self.openings[0]['contact'] = True
        self.openings[1].update(contact=False, ts=10.)
        result = self.tick_running()
        self.assertFalse(result['primary_open'])
        self.assertTrue(result['secondary_open'])
        self.assertEqual(result['level'], 'secondary')

    def test_offline_unknown_or_missing_radio_never_proves_open(self):
        for status in (False, None, 'true', 1):
            with self.subTest(status=status):
                original = self.service.zigbee_radio_status
                self.service.zigbee_radio_status = lambda ext: {'radio_online': status} if ext == 'kitchen' else original(ext)
                result = self.tick_running()
                self.assertFalse(result['primary_open'])
                self.assertEqual(result['level'], 'closed')
                self.service.zigbee_radio_status = original

    def test_untrusted_missing_future_or_invalid_event_never_proves_open(self):
        cases = [(None, {'retained': False}), (self.wall+100, {'retained': False}),
                 (float('nan'), {'retained': False}), (float('inf'), {'retained': False}),
                 (340., {'retained': True}), (340., {}), (340., None)]
        for stamp, meta in cases:
            with self.subTest(stamp=stamp, meta=meta):
                self.openings[0].update(ts=stamp, meta=meta)
                self.assertFalse(self.tick_running()['primary_open'])

    def test_close_event_immediately_removes_green_then_reopen_restores_it(self):
        self.assertEqual(self.tick_running()['level'], 'green')
        self.openings[0].update(contact=True, ts=self.wall)
        self.assertEqual(self.service.tick()['level'], 'closed')
        self.openings[0].update(contact=False, ts=self.wall)
        self.assertEqual(self.service.tick()['level'], 'green')

    def test_unknown_or_non_boolean_contact_cannot_prove_open(self):
        for value in (None, 'false', 0, ''):
            with self.subTest(value=value):
                self.openings[0]['contact'] = value
                self.assertFalse(self.tick_running()['primary_open'])

    def test_old_contact_does_not_relax_power_freshness_or_danger_latch(self):
        self.assertEqual(self.tick_running()['level'], 'green')
        self.sample_ts[1, 'power'] = self.wall-301
        result = self.service.tick()
        self.assertIsNone(result['fan_active'])
        self.assertEqual(result['level'], 'unknown')
        self.states[3]['carbon_monoxide'] = True
        result = self.service.tick()
        self.assertTrue(result['latched'])
        self.assertEqual(result['level'], 'danger')


if __name__ == '__main__':
    unittest.main()
