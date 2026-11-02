"""Actuator observations must stay fresh even when history samples are thinned."""
import unittest
from unittest.mock import patch

import mqtt_ingest_multi as ingest


class LiveFeedbackTest(unittest.TestCase):
    def setUp(self):
        ingest.last_saved.clear()
        ingest.last_saved_retained.clear()
        ingest.pending_measurements.clear()
        self.addCleanup(ingest.last_saved.clear)
        self.addCleanup(ingest.last_saved_retained.clear)
        self.addCleanup(ingest.pending_measurements.clear)
        self.history = []
        def insert(cur, rows, page_size):
            self.history.extend(rows)
            return {m.sample_id for m in rows}
        insert_mock = patch.object(ingest.MeasurementQueue, '_insert', side_effect=insert)
        insert_mock.start()
        self.addCleanup(insert_mock.stop)
        class Cursor:
            def execute(self, sql): pass
        self.cursor = Cursor()
        mock = patch.object(ingest, 'upsert_entity_state')
        self.upsert = mock.start()
        self.addCleanup(mock.stop)

    def emit(self, key, value, at, rule, *, retained=False):
        return ingest.persist_metric(self.cursor, 1, key, 'bool' if isinstance(value, bool) else 'num',
                                     value, rule, at, {'retained': retained, 'recv_ts': at})

    def test_unchanged_power_stays_fresh_but_history_keeps_its_interval(self):
        rule = ingest.Rule('both', 1, 5, 300, True, True)
        for at in range(1000, 1601, 10):
            self.assertTrue(self.emit('power', 0, at, rule))
        self.assertEqual(self.upsert.call_count, 61)
        self.assertEqual(len(self.history), 3)
        self.assertEqual(ingest.last_saved[1, 'power'], (0, 1600))

    def test_power_threshold_crossing_is_visible_during_history_min_interval(self):
        rule = ingest.Rule('both', 100, 60, 300, True, True)
        self.emit('power', 19, 1000, rule)
        self.emit('power', 51, 1001, rule)
        self.assertEqual(self.upsert.call_args.args[4], 51)
        self.assertEqual(len(self.history), 1)

    def test_same_off_and_color_feedback_refresh_after_first_observation(self):
        for key, value in (('switch_state', False), ('brightness', 50), ('color', {'x': .17, 'y': .7})):
            with self.subTest(key=key):
                rule = ingest.Rule('state', None, None, None, True, True)
                self.emit(key, value, 1000, rule)
                self.emit(key, value, 2000, rule)
                self.assertEqual(self.upsert.call_args.args[5]['recv_ts'], 2000)
        self.assertEqual(self.upsert.call_count, 6)

    def test_retained_or_unknown_provenance_cannot_replace_live_feedback(self):
        rule = ingest.Rule('both', 1, 5, 300, True, True)
        self.emit('power', 100, 1000, rule)
        for retained in (True, None):
            self.assertFalse(self.emit('power', 0, 2000, rule, retained=retained))
        self.assertEqual(self.upsert.call_count, 1)
        self.assertEqual(ingest.last_saved[1, 'power'], (100, 1000))

    def test_disabled_and_history_only_rules_do_not_refresh_state(self):
        self.assertFalse(self.emit('power', 0, 1000, ingest.Rule('both', 1, 5, 300, False, True)))
        rule = ingest.Rule('history', 1, 5, 300, True, True)
        self.assertTrue(self.emit('power', 0, 1000, rule))
        self.assertFalse(self.emit('power', 0, 1001, rule))
        self.upsert.assert_not_called()

    def test_unbound_metrics_and_sleeping_events_keep_existing_throttling(self):
        for key, value in (('power', 0), ('temperature', 20), ('smoke', False)):
            rule = ingest.Rule('both', None, 60, 300, True)
            self.assertTrue(self.emit(key, value, 1000, rule))
            self.assertFalse(self.emit(key, value, 1001, rule))
        self.assertEqual(self.upsert.call_count, 3)

    def test_requests_cannot_become_observations_or_presence(self):
        for suffix in ('set', 'get', 'set/state', 'get/brightness'):
            self.assertIsNone(ingest.topic_base_of('zigbee/light/' + suffix))
        self.assertEqual(ingest.topic_base_of('zigbee/light'), 'zigbee/light')
        self.assertEqual(ingest.topic_base_of('zigbee/light/availability'), 'zigbee/light')


if __name__ == '__main__':
    unittest.main()
