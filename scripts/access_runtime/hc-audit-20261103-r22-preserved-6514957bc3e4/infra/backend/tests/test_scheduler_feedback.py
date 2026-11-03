"""HC-09: source samples, transport completion and device evidence are distinct."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mqtt_monitor_service import MqttClientService
from scheduler_feedback import (climate_observation, entry_matches, fence, fresh_frame,
                                weekly_commands, weekly_observation)
from tests import test_scheduler_service as fixtures


def snapshot(topic, payload, sample=101., receipt=102., mono=12.):
    return {'mqtt_connected': True, 'connection_generation': 1, 'observation_epoch': 'epoch',
            'topics': {topic: {'json': {'sampled_at': sample, **payload}, 'timestamp': receipt,
                              'received_monotonic': mono, 'retain': False, 'connection_generation': 1}}}


BOUNDARY = {'wall': 100., 'monotonic': 10., 'monitor_epoch': 'epoch'}
SCHEDULE = dict(day_index=0, start_time='09:00', enabled=1, map_id=3, mode=0, suction=0,
                water_level=0, segments=[1, 2])


class TransportCompletionTest(unittest.TestCase):
    def run_publish(self, published=True, rc=0, wait_error=None, cleanup_error=False):
        info = Mock(rc=rc)
        info.is_published.return_value = published
        info.wait_for_publish.side_effect = wait_error
        client = Mock()
        client.publish.return_value = info
        if cleanup_error: client.loop_stop.side_effect = RuntimeError('cleanup')
        with patch('mqtt_monitor_service.mqtt.Client', return_value=client), \
                patch('mqtt_monitor_service.command_blocked', return_value=False):
            result = MqttClientService('unused.invalid', 1883, json.dumps).publish('audit/hc09', {})
        self.assertTrue(client.disconnect.called)
        self.assertTrue(client.loop_stop.called)
        return result

    def test_rc_success_without_completion_is_uncertain(self):
        ok, message = self.run_publish(False)
        self.assertFalse(ok)
        self.assertIn('uncertain', message)

    def test_completed_transport_only_reports_published(self):
        self.assertEqual(self.run_publish(), (True, 'published'))

    def test_rc_error_wait_exception_and_cleanup_failure(self):
        self.assertFalse(self.run_publish(rc=4)[0])
        self.assertFalse(self.run_publish(wait_error=RuntimeError('wait failed'))[0])
        self.assertTrue(self.run_publish(cleanup_error=True)[0])

    def test_policy_and_empty_topic_never_connect(self):
        client = Mock()
        with patch('mqtt_monitor_service.mqtt.Client', client), \
                patch('mqtt_monitor_service.command_blocked', return_value=True):
            self.assertFalse(MqttClientService('unused',1883,json.dumps).publish('audit/hc09',{})[0])
        client.assert_not_called()

    def test_real_paho_timeout_has_success_rc_without_completion(self):
        import paho.mqtt.client as mqtt
        info = mqtt.MQTTMessageInfo(1)
        info.wait_for_publish(timeout=0.001)
        self.assertEqual(info.rc, mqtt.MQTT_ERR_SUCCESS)
        self.assertFalse(info.is_published())


class FreshObservationTest(unittest.TestCase):
    def check(self, snap, boundary=BOUNDARY):
        return fresh_frame(snap, 'state', boundary, 90, 105., 15.)

    def test_fresh_post_intent_sample(self):
        self.assertTrue(self.check(snapshot('state', {}))[1]['fresh'])

    def test_retained_disconnect_old_generation_missing_epoch(self):
        original = snapshot('state', {})
        variants = []
        for key, value in [('mqtt_connected',False),('connection_generation',2),('observation_epoch',None)]:
            s=copy.deepcopy(original);s[key]=value;variants.append(s)
        s=copy.deepcopy(original);s['topics']['state']['retain']=True;variants.append(s)
        for s in variants:
            with self.subTest(snapshot=s):self.assertIsNone(self.check(s)[0])

    def test_republication_cannot_refresh_old_device_sample(self):
        self.assertIsNone(self.check(snapshot('state', {}, sample=1.))[0])
        self.assertIsNone(self.check(snapshot('state', {}, sample=99.))[0])

    def test_invalid_future_source_or_receipt_clocks(self):
        for sample in (None, True, float('nan'), float('inf'), 0., 106., '101'):
            with self.subTest(sample=sample):self.assertIsNone(self.check(snapshot('state', {},sample=sample))[0])
        self.assertIsNone(self.check(snapshot('state', {},receipt=106.))[0])
        self.assertIsNone(self.check(snapshot('state', {},mono=16.))[0])
        self.assertIsNone(self.check(snapshot('state', {},mono=9.))[0])

    def test_restart_uses_source_time_not_old_monotonic_clock(self):
        s=snapshot('state', {},mono=1.);s['observation_epoch']='new-process'
        self.assertTrue(self.check(s)[1]['fresh'])
        s['topics']['state']['json']['sampled_at']=99.
        self.assertIsNone(self.check(s)[0])

    def test_bridge_acceptance_is_not_device_confirmation(self):
        command={'power':'on','hc_execution_id':'one'}
        s=snapshot('command_result', {'reported_at':101.,'command':command,'ok':True})
        result=climate_observation(s,command,BOUNDARY,90,105.,15.)
        self.assertTrue(result['accepted']);self.assertFalse(result['confirmed'])

    def test_nested_state_requires_post_intent_source_sample(self):
        command={'power':'on','hc_execution_id':'one'}
        for sample, expected in [(99.,False),(101.,True)]:
            s=snapshot('command_result',{'reported_at':101.,'command':command,'ok':True,
                       'state':{'sampled_at':sample,'ok':True,'power':'on'}})
            result=climate_observation(s,command,BOUNDARY,90,105.,15.)
            self.assertEqual(result['confirmed'],expected)

    def test_climate_requires_all_requested_fields_and_actual_numeric_value(self):
        command={'power':'on','target_temperature':23}
        for temp, expected in [(23,True),(23.9,False),(None,False),(True,False),('23',False)]:
            s=snapshot('state',{'ok':True,'power':'on','target_temperature':temp})
            self.assertEqual(climate_observation(s,command,BOUNDARY,90,105.,15.)['confirmed'],expected)

    def test_diagnostics_need_persisted_boundary(self):
        s=fixtures.SchedulerServiceTest().service(climate_monitor_snapshot=lambda:snapshot('state',{'ok':True,'power':'on'}),
             feedback_wall_clock=lambda:105.,feedback_monotonic_clock=lambda:15.)
        self.assertFalse(s.climate_confirmation_diagnostics({'power':'on'})['confirmed'])
        self.assertTrue(s.confirmation_diagnostics({'domain':'climate','command_payload':{'power':'on'},
            'execution_result':{'feedback_fence':BOUNDARY}})['confirmed'])

    def test_x10_zero_fields_missing_fields_and_other_task(self):
        s=fixtures.SchedulerServiceTest().service()
        commands=weekly_commands(s,[SCHEDULE]);entry=commands[0]
        self.assertTrue(entry_matches(entry,entry))
        for field in ('mode','water_level','enabled','map_id','suction','segments'):
            changed={**entry};changed.pop(field)
            with self.subTest(field=field):self.assertFalse(entry_matches(entry,changed))
        obs=snapshot('scheduler/observation',{'entries':[entry,{'task_id':'quick-clean','enabled':0}]})
        self.assertTrue(weekly_observation(obs,commands,BOUNDARY,90,105.,15.)['confirmed'])
        obs['topics']['scheduler/observation']['json']['entries'].append({**entry,'task_id':'13','days':'0010000'})
        self.assertFalse(weekly_observation(obs,commands,BOUNDARY,90,105.,15.)['confirmed'])

    def test_x10_retained_matching_schedule_cannot_confirm(self):
        commands=weekly_commands(fixtures.SchedulerServiceTest().service(),[SCHEDULE])
        obs=snapshot('scheduler/observation',{'entries':commands})
        obs['topics']['scheduler/observation']['retain']=True
        self.assertFalse(weekly_observation(obs,commands,BOUNDARY,90,105.,15.)['confirmed'])

    def test_duplicate_owned_slot_cannot_confirm(self):
        commands=weekly_commands(fixtures.SchedulerServiceTest().service(),[SCHEDULE])
        entries=[commands[0],{**commands[0],'suction':2}]
        self.assertFalse(weekly_observation(snapshot('scheduler/observation',{'entries':entries}),
            commands,BOUNDARY,90,105.,15.)['confirmed'])

    def test_diagnostics_cannot_reconfirm_timed_out_intent(self):
        s=fixtures.SchedulerServiceTest().service(climate_monitor_snapshot=lambda:snapshot('state',{'ok':True,'power':'on'},sample=230.,receipt=231.),
             feedback_wall_clock=lambda:232.,feedback_monotonic_clock=lambda:15.)
        result=s.climate_confirmation_diagnostics({'power':'on'},BOUNDARY)
        self.assertFalse(result['confirmed']);self.assertFalse(result['observed']['confirmed'])

    def test_sample_age_includes_mqtt_delay_even_after_wall_clock_adjustment(self):
        snap=snapshot('state',{},sample=20.,receipt=100.,mono=1.)
        # Wall age is 85s; source age at receipt plus monotonic delay is 94s.
        self.assertIsNone(self.check(snap,boundary=None)[0])
