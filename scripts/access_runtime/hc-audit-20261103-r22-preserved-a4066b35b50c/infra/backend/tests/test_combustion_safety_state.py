import threading
import unittest
from unittest.mock import patch

from tests import test_combustion_safety_service as fixtures


class CombustionSafetyStateTest(unittest.TestCase):
    def setUp(self):
        fixtures.CombustionSafetyServiceTest.setUp(self)
        self.wall, self.mono = 1000.0, 500.0
        self.addCleanup(patch.stopall)
        patch('combustion_safety_service.time.time', side_effect=lambda: self.wall).start()
        patch('combustion_safety_service.time.monotonic', side_effect=lambda: self.mono).start()

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds

    def restarted(self):
        fixture = fixtures.CombustionSafetyServiceTest()
        fixture.setUp()
        fixture.service.runtime_store = self.runtime_store
        return fixture

    def latch(self):
        self.states[3]['carbon_monoxide'] = True
        self.service.tick()
        self.states[3]['carbon_monoxide'] = False
        self.advance(1)
        return self.service.tick()

    def test_get_before_worker_has_no_db_or_publish_and_is_unknown_latched(self):
        def forbidden(*args):
            self.fail('GET performed I/O')
        self.service.fetch_all = self.service.fetch_one = self.service.execute_one = self.service.publish_mqtt = forbidden
        state = self.service.state_payload()
        self.assertTrue(state['stale'])
        self.assertTrue(state['latched'])
        self.assertIsNone(state['evaluation_age_seconds'])
        self.assertEqual(state, self.service.evaluate(123))
        self.assertEqual(self.runtime_store.saves, 0)

    def test_get_load_does_not_advance_fan_co_or_latch(self):
        self.config['fan_on_seconds'] = 5
        self.states[1]['power'] = 100
        self.service.tick()
        before = (self.service.fan_active, self.service.fan_candidate_since, self.service.last_co,
                  self.service.co_warning_active, self.service.latched, self.runtime_store.saves)
        self.advance(4)
        for _ in range(300):
            self.service.state_payload()
            self.service.evaluate()
        after = (self.service.fan_active, self.service.fan_candidate_since, self.service.last_co,
                 self.service.co_warning_active, self.service.latched, self.runtime_store.saves)
        self.assertEqual(after, before)
        self.assertFalse(self.service.fan_active)
        self.advance(1)
        self.assertTrue(self.service.tick()['fan_active'])

    def test_get_returns_independent_complete_snapshot(self):
        self.service.tick()
        result = self.service.state_payload()
        result['config']['enabled'] = False
        result['co']['state'].clear()
        result['latched'] = True
        self.assertTrue(self.service.state_payload()['config']['enabled'])
        self.assertFalse(self.service.state_payload()['latched'])
        copy = self.service.last_snapshot
        copy['latched'] = True
        self.assertFalse(self.service.last_snapshot['latched'])

    def test_get_does_not_wait_for_blocked_actuation(self):
        entered, release, read_done = threading.Event(), threading.Event(), threading.Event()
        def blocked(*args):
            entered.set()
            if not release.wait(3):
                raise AssertionError('actuation not released')
        self.service._shutdown = blocked
        worker = threading.Thread(target=self.service.tick)
        worker.start()
        reader = None
        try:
            self.assertTrue(entered.wait(2))
            reader = threading.Thread(target=lambda: (self.service.state_payload(), read_done.set()))
            reader.start()
            self.assertTrue(read_done.wait(1), 'GET blocked on decision/command I/O')
        finally:
            release.set()
            worker.join(3)
            if reader:
                reader.join(3)
        self.assertFalse(worker.is_alive())

    def test_overlapping_ticks_have_one_decision_owner(self):
        entered, release = threading.Event(), threading.Event()
        evaluate = self.service._evaluate
        calls = []
        def blocked(now):
            calls.append(now)
            entered.set()
            if not release.wait(3):
                raise AssertionError('evaluation not released')
            return evaluate(now)
        self.service._evaluate = blocked
        worker = threading.Thread(target=self.service.tick)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.service.tick()
            self.assertEqual(len(calls), 1)
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())

    def test_short_alarm_survives_restart_with_clear_current_input(self):
        self.states[3]['carbon_monoxide'] = True
        self.service.tick()
        restarted = self.restarted()
        result = restarted.service.tick()
        self.assertTrue(result['latched'])
        self.assertFalse(result['danger'])
        self.assertEqual(result['level'], 'latched')

    def test_fresh_ack_is_durable_and_does_not_re_evaluate(self):
        self.latch()
        before = (self.service.fan_candidate_since, self.service.last_co, self.service.last_co_sample_at)
        result = self.service.acknowledge()
        self.assertFalse(result['latched'])
        self.assertFalse(self.runtime_store.row['latched'])
        self.assertEqual(before, (self.service.fan_candidate_since, self.service.last_co, self.service.last_co_sample_at))
        self.assertFalse(self.restarted().service.tick()['latched'])

    def test_active_or_newly_arriving_alarm_cannot_be_acknowledged(self):
        for smoke in (False, True):
            with self.subTest(smoke=smoke):
                self.states[3]['carbon_monoxide'] = not smoke
                self.states[4]['smoke'] = smoke
                self.service.tick()
                with self.assertRaises(ValueError):
                    self.service.acknowledge()
        self.states[3]['carbon_monoxide'] = self.states[4]['smoke'] = False
        self.advance(1)
        self.service.tick()
        self.states[3]['carbon_monoxide'] = True
        with self.assertRaises(ValueError):
            self.service.acknowledge()
        self.assertTrue(self.runtime_store.row['latched'])

    def test_ack_and_tick_are_serialized_under_active_danger(self):
        self.service.tick()
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        evaluate = self.service._evaluate
        def blocked(now):
            entered.set()
            if not release.wait(3):
                raise AssertionError('tick not released')
            return evaluate(now)
        self.service._evaluate = blocked
        self.states[3]['carbon_monoxide'] = True
        worker = threading.Thread(target=self.service.tick)
        worker.start()
        errors = []
        def ack():
            try:
                self.service.acknowledge()
            except ValueError:
                errors.append('rejected')
            finally:
                done.set()
        command = None
        try:
            self.assertTrue(entered.wait(2))
            command = threading.Thread(target=ack)
            command.start()
            self.assertFalse(done.wait(.05))
        finally:
            release.set()
            worker.join(3)
            if command:
                command.join(3)
        self.assertEqual(errors, ['rejected'])
        self.assertTrue(self.runtime_store.row['latched'])

    def test_stale_snapshot_cannot_clear_latch_or_grant_fan_exemption(self):
        self.latch()
        self.advance(6)
        result = self.service.state_payload()
        self.assertTrue(result['stale'])
        self.assertTrue(result['latched'])
        self.assertIsNone(result['fan_active'])
        with self.assertRaises(ValueError):
            self.service.acknowledge()

    def test_retained_missing_future_and_fault_inputs_block_ack(self):
        self.latch()
        for stamp, meta in ((None, {'retained': False}),
                            (self.wall+1, {'retained': False}), (self.wall, {'retained': True}), (self.wall, None)):
            with self.subTest(stamp=stamp, meta=meta):
                self.sample_ts[3, 'carbon_monoxide'] = stamp
                self.sample_meta[3, 'carbon_monoxide'] = meta
                with self.assertRaises(ValueError):
                    self.service.acknowledge()
        self.sample_ts.clear()
        self.sample_meta.clear()
        self.states[3]['fault'] = True
        with self.assertRaises(ValueError):
            self.service.acknowledge()
        self.states[3]['fault'] = 'unknown'
        with self.assertRaises(ValueError):
            self.service.acknowledge()

    def test_offline_co_or_smoke_blocks_ack(self):
        self.latch()
        self.service.zigbee_radio_status = lambda ext_id: {'radio_online': False}
        with self.assertRaises(ValueError):
            self.service.acknowledge()

    def test_unbound_smoke_is_optional_but_co_is_required(self):
        original = self.service.binding_entity_id
        self.service.binding_entity_id = lambda key: None if key == 'combustion_smoke_sensor' else original(key)
        self.latch()
        self.assertFalse(self.service.acknowledge()['latched'])
        self.service.binding_entity_id = lambda key: None if key == 'combustion_co_sensor' else original(key)
        self.service.tick()
        with self.assertRaises(ValueError):
            self.service.acknowledge()

    def test_missing_store_stays_unknown_and_can_recover_without_get_writes(self):
        self.runtime_store.fail_load = True
        result = self.service.tick()
        self.assertFalse(result['persistence']['restored'])
        self.assertTrue(result['latched'])
        for _ in range(10):
            self.service.state_payload()
        self.assertEqual(self.runtime_store.saves, 0)
        with self.assertRaises(ValueError):
            self.service.acknowledge()
        self.runtime_store.fail_load = False
        self.assertTrue(self.service.tick()['persistence']['restored'])

    def test_transient_alarm_during_db_outage_is_persisted_on_return(self):
        self.runtime_store.fail_load = True
        self.states[3]['carbon_monoxide'] = True
        self.service.tick()
        self.states[3]['carbon_monoxide'] = False
        self.runtime_store.fail_load = False
        self.advance(1)
        self.service.tick()
        self.assertTrue(self.runtime_store.row['latched'])
        self.assertTrue(self.restarted().service.tick()['latched'])

    def test_failed_latch_write_remains_pending_and_is_retried(self):
        self.runtime_store.fail_save = True
        self.states[3]['carbon_monoxide'] = True
        result = self.service.tick()
        self.assertFalse(result['persistence']['restored'])
        self.assertTrue(result['latched'])
        self.states[3]['carbon_monoxide'] = False
        self.runtime_store.fail_save = False
        self.advance(1)
        self.service.tick()
        self.assertTrue(self.runtime_store.row['latched'])

    def test_failed_ack_commit_never_reports_clear(self):
        self.latch()
        self.runtime_store.fail_save = True
        with self.assertRaises(RuntimeError):
            self.service.acknowledge()
        self.assertTrue(self.service.state_payload()['latched'])
        self.assertTrue(self.runtime_store.row['latched'])
        self.assertFalse(self.service._runtime_loaded)
        self.assertFalse(self.service.state_payload()['persistence']['restored'])
        self.assertIn('uncertain', self.service.state_payload()['evaluation_error'])

    def test_revision_conflict_prevents_stale_ack(self):
        self.latch()
        self.runtime_store.row['revision'] += 1
        with self.assertRaises(RuntimeError):
            self.service.acknowledge()
        self.assertTrue(self.runtime_store.row['latched'])

    def test_old_alarm_remains_latched_while_radio_is_present(self):
        self.states[3]['carbon_monoxide'] = True
        self.sample_ts[3, 'carbon_monoxide'] = self.wall-1000
        result = self.service.tick()
        self.assertTrue(result['danger'])
        self.assertTrue(result['latched'])
        self.assertTrue(result['input_health']['co'])
        with self.assertRaises(ValueError):
            self.service.acknowledge()

    def test_sleeping_sensors_keep_known_clear_state_for_six_months(self):
        self.latch()
        self.states[3]['fault'] = False
        for entity in (3, 4):
            for key in self.states[entity]:
                self.sample_ts[entity, key] = self.wall
        self.advance(180 * 86400)
        before = dict(self.sample_ts)
        result = self.service.tick()
        self.assertTrue(result['input_health']['co'])
        self.assertTrue(result['input_health']['smoke'])
        self.assertTrue(result['latched'])  # Radio presence never clears the latch.
        self.assertFalse(self.service.acknowledge()['latched'])
        self.assertEqual(self.sample_ts, before)  # No fabricated fresh samples.

    def test_sleeping_sensors_offline_or_unknown_block_ack_individually(self):
        for sensor in ('co', 'unknown'):  # Fixture maps smoke entity to 'unknown'.
            for online in (False, None):
                with self.subTest(sensor=sensor, online=online):
                    self.service.zigbee_radio_status = lambda ext, sensor=sensor, online=online: {'radio_online': online if ext == sensor else True}
                    self.service.tick()
                    with self.assertRaises(ValueError):
                        self.service.acknowledge()

    def test_radio_presence_does_not_invent_missing_or_invalid_sensor_state(self):
        for entity, key in ((3,'carbon_monoxide'), (4,'smoke')):
            for stamp, meta in ((None, {'retained': False}), (self.wall+1, {'retained': False}),
                                (float('nan'), {'retained': False}), (self.wall, {'retained': True}),
                                (self.wall, None)):
                with self.subTest(entity=entity, stamp=stamp, meta=meta):
                    self.sample_ts[entity,key] = stamp
                    self.sample_meta[entity,key] = meta
                    self.service.tick()
                    with self.assertRaises(ValueError):
                        self.service.acknowledge()
                    self.sample_ts.clear()
                    self.sample_meta.clear()
        for entity in (3,4):
            saved = self.states[entity]
            self.states[entity] = {}
            self.service.tick()
            with self.assertRaises(ValueError):
                self.service.acknowledge()
            self.states[entity] = saved

    def test_alarm_after_long_sleep_latches_until_clear_event_and_manual_ack(self):
        self.service.tick()
        self.advance(180 * 86400)
        for entity, key in ((3,'carbon_monoxide'), (4,'smoke')):
            with self.subTest(entity=entity):
                self.states[entity][key] = True
                self.sample_ts[entity,key] = self.wall
                self.assertTrue(self.service.tick()['danger'])
                with self.assertRaises(ValueError): self.service.acknowledge()
                self.states[entity][key] = False
                self.advance(1)
                self.sample_ts[entity,key] = self.wall
                self.assertTrue(self.service.tick()['latched'])
                self.assertFalse(self.service.acknowledge()['latched'])

    def test_new_co_value_after_long_sleep_is_compared_once(self):
        self.sample_ts[3,'carbon_monoxide_value'] = self.wall
        self.service.tick()
        self.advance(180 * 86400)
        self.states[3]['carbon_monoxide_value'] = 3
        self.sample_ts[3,'carbon_monoxide_value'] = self.wall
        self.assertTrue(self.service.tick()['co']['rising'])
        self.assertFalse(self.service.tick()['co']['rising'])

    def test_event_driven_policy_does_not_relax_continuous_feedback(self):
        self.latch()
        for entity in (3,4):
            for key in self.states[entity]: self.sample_ts[entity,key] = self.wall
        self.sample_ts[1,'power'] = self.wall
        for opening in self.openings: opening['ts'] = self.wall
        self.advance(301)
        result = self.service.tick()
        self.assertTrue(result['input_health']['co'])
        self.assertTrue(result['input_health']['smoke'])
        self.assertFalse(result['input_health']['fan'])
        self.assertIsNone(result['fan_active'])
        self.assertTrue(result['primary_open'])  # Contact events do not expire with power.
        self.assertFalse(self.service.acknowledge()['latched'])

    def test_co_history_survives_restart_and_duplicate_sample_is_not_new_rise(self):
        self.states[3]['carbon_monoxide_value'] = 2
        self.sample_ts[3, 'carbon_monoxide_value'] = self.wall
        self.service.tick()
        self.advance(1)
        self.states[3]['carbon_monoxide_value'] = 4
        self.sample_ts[3, 'carbon_monoxide_value'] = self.wall
        self.assertTrue(self.service.tick()['co']['rising'])
        self.assertFalse(self.service.tick()['co']['rising'])
        restarted = self.restarted()
        restarted.states[3]['carbon_monoxide_value'] = 7
        self.advance(1)
        self.assertTrue(restarted.service.tick()['co']['rising'])
        self.assertTrue(restarted.service.co_warning_active)

    def test_fan_debounce_uses_monotonic_clock_and_unknown_sample_breaks_candidate(self):
        self.config['fan_on_seconds'] = 5
        self.states[1]['power'] = 100
        self.service.tick()
        self.wall += 10000
        self.assertFalse(self.service.tick()['fan_active'])
        self.mono += 4
        self.sample_ts[1, 'power'] = self.wall-301
        self.assertIsNone(self.service.tick()['fan_active'])
        self.sample_ts.clear()
        self.advance(1)
        self.assertFalse(self.service.tick()['fan_active'])
        self.advance(5)
        self.assertTrue(self.service.tick()['fan_active'])
        self.config['fan_off_seconds'] = 3
        self.states[1]['power'] = 0
        self.service.tick()
        self.advance(2)
        self.assertTrue(self.service.tick()['fan_active'])
        self.advance(1)
        self.assertFalse(self.service.tick()['fan_active'])

    def test_old_open_contact_with_present_radio_still_proves_air_supply(self):
        self.states[1]['power'] = 100
        self.service.tick()
        self.openings[0]['ts'] = self.wall-301
        self.advance(1)
        result = self.service.tick()
        self.assertTrue(result['primary_open'])
        self.assertEqual(result['level'], 'green')

    def test_event_db_failure_does_not_hide_published_decision(self):
        self.states[3]['carbon_monoxide'] = True
        self.service.execute_one = lambda *a: (_ for _ in ()).throw(RuntimeError('event DB failure'))
        result = self.service.tick()
        self.assertTrue(result['latched'])
        self.assertIn('event DB failure', result['event_error'])
        self.assertTrue(self.service.state_payload()['latched'])

    def test_new_input_and_snapshot_limits_are_validated(self):
        deps = (lambda *a: [], lambda *a: {}, lambda *a: None, lambda *a: (True, ''), lambda *a: None)
        for options in ({'input_max_age_seconds': 0}, {'snapshot_max_age_seconds': float('nan')}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                fixtures.CombustionSafetyService(*deps, **options)

    def test_sample_arriving_during_evaluation_is_not_mistaken_for_future_data(self):
        original = self.service.fetch_all
        def fetch(sql, params=None):
            if 'entity_state' in sql:
                self.wall += .01
            return original(sql, params)
        self.service.fetch_all = fetch
        self.states[3]['carbon_monoxide_value'] = 12
        result = self.service.tick()
        self.assertTrue(result['input_health']['co'])
        self.assertTrue(result['input_health']['fan'])
        self.assertTrue(result['input_health']['smoke'])
        self.assertEqual(self.runtime_store.row['last_co'], 12)

    def test_unknown_fan_does_not_clear_restored_co_warning(self):
        self.runtime_store.row['co_warning_active'] = True
        self.sample_ts[1, 'power'] = None
        result = self.service.tick()
        self.assertTrue(result['co_warning_active'])
        self.assertFalse(result['input_health']['fan'])


if __name__ == '__main__':
    unittest.main()
