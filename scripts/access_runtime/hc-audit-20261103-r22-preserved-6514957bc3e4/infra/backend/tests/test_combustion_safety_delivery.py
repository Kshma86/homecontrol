import unittest
from unittest.mock import patch

from tests import test_combustion_safety_service as fixtures


class CombustionSafetyDeliveryTest(unittest.TestCase):
    def setUp(self):
        fixtures.CombustionSafetyServiceTest.setUp(self)
        self.wall = 1000.0
        self.mono = 100.0
        self.addCleanup(patch.stopall)
        patch('combustion_safety_service.time.time', side_effect=lambda: self.wall).start()
        patch('combustion_safety_service.time.monotonic', side_effect=lambda: self.mono).start()
        self.snapshot = fixtures.CombustionSafetyServiceTest.start_fan(self)
        self.snapshot.update(danger=True, level='danger')

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds

    def sample(self, entity, key, value, *, ts=None, retained=False):
        self.states.setdefault(entity, {})[key] = value
        self.sample_ts[entity, key] = self.wall if ts is None else ts
        self.sample_meta[entity, key] = {'retained': retained}

    def publisher(self, *outcomes):
        results = iter(outcomes)
        def send(topic, payload):
            self.published.append((topic, payload))
            result = next(results)
            if isinstance(result, Exception):
                raise result
            return result, 'accepted' if result else 'failed'
        self.service.publish_mqtt = send

    def test_failed_shutdown_is_not_sent_and_retries_after_interval(self):
        self.publisher(False, True)
        self.service._shutdown(self.snapshot)
        self.assertFalse(self.service.shutdown_sent)
        self.service._shutdown(self.snapshot)
        self.assertEqual(len(self.published), 1)
        self.advance(10)
        self.service._shutdown(self.snapshot)
        self.assertTrue(self.service.shutdown_sent)
        self.assertFalse(self.service.shutdown_command.status()['observed'])

    def test_accepted_but_unobserved_shutdown_retries_and_exhausts(self):
        self.publisher(True, True, False)
        for _ in range(3):
            self.service._shutdown(self.snapshot)
            self.advance(10)
        for _ in range(10):
            self.service._shutdown(self.snapshot)
            self.advance(100)
        self.assertEqual(len(self.published), 3)
        status = self.service.shutdown_command.status()
        self.assertTrue(status['published'])
        self.assertFalse(status['last_publish_ok'])
        self.assertTrue(status['requires_attention'])
        self.assertFalse(status['observed'])

    def test_publisher_exception_is_failed_attempt_and_can_recover(self):
        self.publisher(TimeoutError('broker unavailable'), True)
        self.service._shutdown(self.snapshot)
        self.assertFalse(self.service.shutdown_sent)
        self.assertIn('broker unavailable', self.service.shutdown_command.message)
        self.advance(10)
        self.service._shutdown(self.snapshot)
        self.assertTrue(self.service.shutdown_sent)

    def test_fresh_off_observation_stops_retries_and_later_running_rearms(self):
        self.service._shutdown(self.snapshot)
        self.advance(1)
        self.sample(1, 'power', 0)
        self.service._shutdown(self.snapshot)
        self.assertTrue(self.service.shutdown_command.status()['observed'])
        self.advance(30)
        self.service._shutdown(self.snapshot)
        self.assertEqual(len(self.published), 1)
        self.sample(1, 'power', 113)
        self.service._shutdown(self.snapshot)
        self.assertEqual(len(self.published), 2)
        self.assertEqual(self.service.shutdown_command.attempts, 1)

    def test_retained_stale_missing_and_future_samples_cannot_confirm_shutdown(self):
        self.service._shutdown(self.snapshot)
        self.advance(1)
        for stamp, retained in ((self.wall, True), (999, False), (self.wall+1, False), (1000, False), (None, False)):
            with self.subTest(stamp=stamp, retained=retained):
                self.sample(1, 'power', 0, ts=stamp, retained=retained)
                if stamp is None:
                    self.sample_ts[1, 'power'] = None
                self.service._shutdown(self.snapshot)
                self.assertFalse(self.service.shutdown_command.status()['observed'])
        self.sample(1, 'power', 0)
        self.sample_meta[1, 'power'] = None
        self.service._shutdown(self.snapshot)
        self.assertFalse(self.service.shutdown_command.status()['observed'])

    def test_sample_age_limit_and_power_w_fallback(self):
        self.service._shutdown(self.snapshot)
        self.advance(62)
        self.sample(1, 'power_w', 0, ts=1001)
        self.service._shutdown(self.snapshot)
        self.assertFalse(self.service.shutdown_command.status()['observed'])
        self.sample(1, 'power_w', 0)
        self.service._shutdown(self.snapshot)
        self.assertTrue(self.service.shutdown_command.status()['observed'])

    def test_fan_off_without_proof_does_not_reset_exhausted_budget(self):
        self.publisher(False, False, False)
        for _ in range(3):
            self.service._shutdown(self.snapshot)
            self.advance(10)
        self.snapshot['fan_active'] = False
        self.service._shutdown(self.snapshot)
        self.snapshot['fan_active'] = True
        self.service._shutdown(self.snapshot)
        self.assertEqual(len(self.published), 3)

    def test_already_inactive_fan_and_disabled_policy_do_not_publish(self):
        self.snapshot['fan_active'] = False
        self.service._shutdown(self.snapshot)
        self.snapshot['fan_active'] = True
        for key in ('enabled', 'auto_shutdown'):
            self.snapshot['config'][key] = False
            self.service._shutdown(self.snapshot)
            self.snapshot['config'][key] = True
        self.snapshot['danger'] = False
        self.service._shutdown(self.snapshot)
        self.assertEqual(self.published, [])

    def test_indicator_failure_does_not_mark_on_or_restart_red_budget_on_level_change(self):
        self.publisher(False, False, False)
        for level in ('danger', 'latched', 'co_warning'):
            self.snapshot['level'] = level
            self.service._indicator(self.snapshot, self.wall)
            self.advance(10)
        self.service._indicator(self.snapshot, self.wall)
        self.assertFalse(self.service.indicator_on)
        self.assertEqual(len(self.published), 3)
        self.assertTrue(self.service.indicator_command.status()['requires_attention'])

    def test_indicator_needs_matching_state_brightness_color_then_fresh_off_rearms(self):
        self.service._indicator(self.snapshot, self.wall)
        self.advance(1)
        self.sample(2, 'switch_state', True)
        self.service._indicator(self.snapshot, self.wall)
        self.assertFalse(self.service.indicator_command.status()['observed'])
        payload = self.service.indicator_command.payload
        self.sample(2, 'brightness', payload['brightness'])
        self.sample(2, 'color', payload['color'])
        self.service._indicator(self.snapshot, self.wall)
        self.assertTrue(self.service.indicator_command.status()['observed'])
        self.advance(1)
        self.sample(2, 'switch_state', False)
        self.service._indicator(self.snapshot, self.wall)
        self.assertEqual(len(self.published), 2)

    def test_off_failure_preserves_last_accepted_on_and_retries(self):
        self.service.indicator_on = True
        self.snapshot['level'] = 'idle'
        self.publisher(False, True)
        self.service._indicator(self.snapshot, self.wall)
        self.assertTrue(self.service.indicator_on)
        self.advance(10)
        self.service._indicator(self.snapshot, self.wall)
        self.assertFalse(self.service.indicator_on)
        self.assertFalse(self.service.indicator_command.status()['observed'])

    def test_offline_indicator_cannot_confirm_even_matching_feedback(self):
        self.service._indicator(self.snapshot, self.wall)
        self.advance(1)
        payload = self.service.indicator_command.payload
        for key, value in {'switch_state': True, 'brightness': payload['brightness'], 'color': payload['color']}.items():
            self.sample(2, key, value)
        self.snapshot['indicator']['radio_online'] = False
        self.service._indicator(self.snapshot, self.wall)
        self.assertFalse(self.service.indicator_command.status()['observed'])

    def test_late_observed_off_can_settle_exhausted_failed_shutdown(self):
        self.publisher(False, False, False)
        for _ in range(3):
            self.service._shutdown(self.snapshot)
            self.advance(10)
        self.sample(1, 'power', 0)
        self.service._shutdown(self.snapshot)
        status = self.service.shutdown_command.status()
        self.assertTrue(status['observed'])
        self.assertFalse(status['published'])
        self.assertFalse(status['requires_attention'])
        self.assertFalse(self.service.shutdown_sent)
        self.assertEqual(len(self.published), 3)

    def test_failed_pulse_does_not_claim_signal_and_still_requests_cleanup_off(self):
        self.snapshot['level'] = 'green'
        self.publisher(False, True)
        self.service._indicator(self.snapshot, self.wall)
        self.assertEqual(self.service.last_signal_at, 0)
        self.assertFalse(self.service.indicator_on)
        self.advance(1)
        self.service._indicator(self.snapshot, self.wall)
        self.assertEqual([p['state'] for _, p in self.published], ['ON', 'OFF'])

    def test_next_pulse_has_its_own_deadline_after_observed_off(self):
        self.snapshot['level'] = 'green'
        self.service._indicator(self.snapshot, self.wall)
        self.advance(1)
        self.service._indicator(self.snapshot, self.wall)
        self.advance(1)
        self.sample(2, 'switch_state', False)
        self.service._indicator(self.snapshot, self.wall)
        self.advance(60)
        self.service._indicator(self.snapshot, self.wall)
        self.assertTrue(self.service.indicator_on)
        self.assertEqual(self.service.pulse_off_at, self.wall+1)
        self.assertEqual([p['state'] for _, p in self.published], ['ON', 'OFF', 'ON'])

    def test_off_preview_failure_does_not_clear_indicator(self):
        self.service.indicator_on = True
        self.publisher(False)
        self.assertFalse(self.service.preview_indicator('off')['ok'])
        self.assertTrue(self.service.indicator_on)

    def test_lamp_error_cannot_prevent_shutdown_and_result_is_current(self):
        self.states[3]['carbon_monoxide'] = True
        original = self.service.fetch_one
        def fetch(sql, params=None):
            if 'topic_base' in sql and params == (2,):
                raise RuntimeError('indicator DB failure')
            return original(sql, params)
        self.service.fetch_one = fetch
        result = self.service.tick()
        self.assertEqual(self.published, [('zigbee/extractor/set', {'state': 'OFF'})])
        self.assertTrue(result['actuation']['shutdown']['published'])
        self.assertFalse(result['actuation']['shutdown']['observed'])

    def test_shutdown_error_does_not_prevent_indicator_attempt(self):
        self.states[3]['carbon_monoxide'] = True
        original = self.service.fetch_one
        self.service.fetch_one = lambda sql, params=None: (_ for _ in ()).throw(RuntimeError('extractor DB failure')) if 'topic_base' in sql and params == (1,) else original(sql, params)
        self.service.tick()
        self.assertEqual(len(self.published), 1)
        self.assertEqual(self.published[0][0], 'zigbee/light/set')

    def test_retry_uses_monotonic_time_when_wall_clock_changes(self):
        self.service._shutdown(self.snapshot)
        self.wall += 10000
        self.service._shutdown(self.snapshot)
        self.assertEqual(len(self.published), 1)
        self.mono += 10
        self.service._shutdown(self.snapshot)
        self.assertEqual(len(self.published), 2)

    def test_inactive_or_retargeted_extractor_does_not_reuse_old_topic(self):
        self.service._shutdown(self.snapshot)
        self.advance(10)
        self.service.fetch_one = lambda *a: None
        self.service._shutdown(self.snapshot)
        self.assertEqual(len(self.published), 1)
        self.service.fetch_one = lambda *a: {'topic_base': 'zigbee/replacement'}
        self.service._shutdown(self.snapshot)
        self.assertEqual(self.published[-1][0], 'zigbee/replacement/set')
        self.assertEqual(self.service.shutdown_command.attempts, 1)

    def test_invalid_limits_are_rejected(self):
        deps = (lambda *a: [], lambda *a: {}, lambda *a: None, lambda *a: (True, ''), lambda *a: None)
        for options in ({'command_retry_seconds': 0}, {'observation_max_age_seconds': float('nan')}, {'command_max_attempts': True}, {'command_max_attempts': 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                fixtures.CombustionSafetyService(*deps, **options)


if __name__ == '__main__':
    unittest.main()
