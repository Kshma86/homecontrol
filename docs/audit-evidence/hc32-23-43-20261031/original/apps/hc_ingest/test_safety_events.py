"""Event-driven alarm transitions must bypass numeric/history throttling."""
import unittest

import mqtt_ingest_multi as ingest


class SafetyEventTest(unittest.TestCase):
    def setUp(self):
        ingest.last_saved.clear()
        ingest.last_saved_retained.clear()
        self.addCleanup(ingest.last_saved.clear)
        self.addCleanup(ingest.last_saved_retained.clear)

    def test_alarm_and_clear_transitions_bypass_min_interval(self):
        rule = ingest.Rule('both', None, 3600, 86400, True)
        for key in ('carbon_monoxide', 'smoke', 'smoke_alarm', 'fire', 'alarm', 'fault'):
            for before, after in ((False,True),(True,False)):
                with self.subTest(key=key, after=after):
                    ingest.last_saved[1,key] = (before,1000.)
                    self.assertTrue(ingest.should_write(1,key,after,rule,1000.01)[0])

    def test_every_co_change_bypasses_deadband_and_min_interval(self):
        rule = ingest.Rule('both', 1, 3600, 86400, True)
        for key in ('carbon_monoxide_value', 'co', 'co_ppm'):
            for before, after in ((19.9,20.1),(20.1,19.9),(1.,1.1)):
                with self.subTest(key=key, before=before):
                    ingest.last_saved[1,key] = (before,1000.)
                    self.assertTrue(ingest.should_write(1,key,after,rule,1000.01)[0])

    def test_unchanged_sleeping_state_is_not_a_new_event(self):
        rule = ingest.Rule('both', None, 1, 86400, True)
        ingest.last_saved[1,'smoke'] = (False,1000.)
        self.assertFalse(ingest.should_write(1,'smoke',False,rule,1060.)[0])
        self.assertTrue(ingest.should_write(1,'smoke',False,rule,87400.)[0])

    def test_disabled_rules_and_non_safety_deadbands_are_preserved(self):
        ingest.last_saved[1,'smoke'] = (False,1000.)
        self.assertFalse(ingest.should_write(1,'smoke',True,ingest.Rule('both',None,1,86400,False),1060.)[0])
        ingest.last_saved[1,'temperature'] = (20.,1000.)
        self.assertFalse(ingest.should_write(1,'temperature',20.1,ingest.Rule('both',1,1,86400,True),1060.)[0])

    def test_unchanged_retained_replay_never_replaces_recorded_safety_event(self):
        rule = ingest.Rule('both', 1, 1, 3600, True)
        for key in (*ingest.COMBUSTION_EVENT_KEYS, 'fault'):
            with self.subTest(key=key):
                ingest.last_saved[1,key] = (0,1000.)
                self.assertFalse(ingest.should_write(1,key,0,rule,100000.,retained=True,co_sensor=True)[0])
        self.assertEqual(ingest.last_saved[1,'carbon_monoxide_value'], (0,1000.))

    def test_retained_alarm_is_accepted_but_retained_clear_cannot_clear_it(self):
        rule = ingest.Rule('both', 1, 3600, 86400, True)
        for key, low, high in [('smoke',False,True),('carbon_monoxide',False,True),('fault',False,True),('carbon_monoxide_value',0,30)]:
            with self.subTest(key=key):
                ingest.last_saved[1,key] = (low,1000.)
                self.assertTrue(ingest.should_write(1,key,high,rule,1000.01,retained=True,co_sensor=True)[0])
                ingest.last_saved[1,key] = (high,1000.)
                self.assertFalse(ingest.should_write(1,key,low,rule,100000.,retained=True,co_sensor=True)[0])

    def test_live_confirmation_of_retained_or_unknown_state_bypasses_throttling(self):
        rule = ingest.Rule('both', None, 3600, 86400, True)
        for provenance in (True,None):
            ingest.last_saved[1,'smoke'] = (False,1000.)
            ingest.last_saved_retained[1,'smoke'] = provenance
            self.assertTrue(ingest.should_write(1,'smoke',False,rule,1000.01)[0])
        ingest.update_last(1,'smoke',False,1000.01,retained=False)
        self.assertFalse(ingest.should_write(1,'smoke',False,rule,1000.02)[0])

    def test_first_retained_value_remains_untrusted_instead_of_being_relabelled(self):
        # Caller keeps meta.retained=true; this never authorizes a clear ACK.
        self.assertTrue(ingest.should_write(1,'smoke',True,ingest.Rule('both',None,1,86400,True),1000.,retained=True)[0])

    def test_replay_protection_does_not_filter_live_alarm_or_other_metric(self):
        rule = ingest.Rule('both', None, 1, 3600, True)
        ingest.last_saved[1,'smoke'] = (False,1000.)
        self.assertTrue(ingest.should_write(1,'smoke',True,rule,1000.01,retained=False)[0])
        ingest.last_saved[1,'temperature'] = (20,1000.)
        self.assertTrue(ingest.should_write(1,'temperature',20,rule,100000.,retained=True)[0])


if __name__ == '__main__':
    unittest.main()
