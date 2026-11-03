import json
import unittest
from unittest.mock import Mock, patch
from climate_window_guard import ClimateWindowGuard


class WindowGuardTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(open_delay_seconds=60, close_delay_seconds=60, desired={}, suspended=False)
        self.rows = [dict(id=1, label='Konyha', ext_id='k', contact=False, extractor_air_role='primary')]
        self.fan = False
        self.live = dict(power='on', mode='heat', target_temperature=22)
        self.publish = Mock(return_value=(True, 'ok'))
        self.sync = Mock()
        def execute(sql, params=()):
            if 'set desired=' in sql:
                self.cfg['desired'] = json.loads(params[0])
                self.cfg['suspended'] = params[1] if len(params) > 1 else True
            elif 'set suspended=false' in sql:
                self.cfg['suspended'] = False
        self.guard = ClimateWindowGuard(lambda sql: self.rows, lambda sql: dict(self.cfg), execute,
            self.publish, lambda: self.live, lambda: {'fan_active': self.fan}, lambda ext: {}, self.sync)
        self.guard.ready = True

    def test_extractor_exempts_only_primary(self):
        self.fan = True
        self.assertFalse(self.guard.status()['blocked'])
        self.rows.append(dict(id=2, label='Szoba', ext_id='s', contact=False, extractor_air_role='secondary'))
        self.assertTrue(self.guard.status()['blocked'])

    def test_start_blocked_immediately_and_off_cancels_resume(self):
        self.assertFalse(self.guard.command('ac', {'power':'on', 'mode':'heat'})[0])
        self.publish.assert_not_called()
        self.assertTrue(self.cfg['suspended'])
        self.guard.command('ac', {'power':'off'})
        self.assertFalse(self.cfg['suspended'])

    def test_stop_delay_and_close_resume(self):
        with patch('climate_window_guard.time.monotonic', return_value=100):
            self.guard.tick('ac')
        self.publish.assert_not_called()
        with patch('climate_window_guard.time.monotonic', return_value=161):
            self.guard.tick('ac')
        self.publish.assert_called_with('ac', {'power':'off'})
        self.rows[0]['contact'] = True
        self.live['power'] = 'off'
        self.publish.reset_mock()
        with patch('climate_window_guard.time.monotonic', return_value=170):
            self.guard.tick('ac')
        self.publish.assert_not_called()
        with patch('climate_window_guard.time.monotonic', return_value=231):
            self.guard.tick('ac')
        self.assertEqual(self.publish.call_args.args[1]['power'], 'on')
        self.assertFalse(self.cfg['suspended'])

    def test_unknown_blocks_even_extractor_exception(self):
        self.fan = True
        self.rows[0]['contact'] = None
        self.assertTrue(self.guard.status()['blocked'])

    def test_new_schedule_overrides_deferred_settings(self):
        self.guard.command('ac', {'power':'on', 'target_temperature':22})
        self.guard.command('ac', {'target_temperature':24})
        self.assertEqual(self.cfg['desired']['target_temperature'], 24)
        self.assertTrue(self.cfg['suspended'])

    def test_invalid_delay(self):
        for value in (-1, 3601, 1.5, True):
            with self.assertRaises(ValueError):
                self.guard.save_config({'open_delay_seconds':value})
