"""HC-09 real transactions, no LAN/device access; opt-in disposable HC08 database."""
import copy
import os
import time
import unittest

from scheduler_audit import SchedulerAudit
from scheduler_feedback import weekly_commands
from x10_schedule_delivery import X10ScheduleDelivery
from tests import test_scheduler_audit_postgres as fixtures
from tests.test_scheduler_feedback import SCHEDULE, snapshot


@unittest.skipUnless(os.environ.get('HC08_TEST_POSTGRES') == '1', 'requires isolated HC-08 PostgreSQL')
class FeedbackPostgresTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.SchedulerAuditPostgresTest()
        self.f.setUp()
        self.now=time.time()+1
        self.mono=100.
        self.snap={'mqtt_connected':True,'connection_generation':1,'observation_epoch':'epoch','topics':{}}
        self.s=self.service()
        self.commands=weekly_commands(self.s,[SCHEDULE])
        self.f.admin.execute_sql("update hc.scheduler_config set mode='v2_execute_x10'")

    def service(self,**kwargs):
        return self.f.make_service(v2_allow_x10=True,x10_weekly_schedule_topic='audit/x10/command/schedule_clean_week',
            x10_monitor_snapshot=lambda:self.snap,climate_monitor_snapshot=lambda:self.snap,
            feedback_wall_clock=lambda:self.now,feedback_monotonic_clock=lambda:self.mono,**kwargs)

    def observe(self,topic,payload):
        self.now+=1;self.mono+=1
        self.snap=snapshot(topic,payload,sample=self.now-.2,receipt=self.now-.1,mono=self.mono-.1)

    def tick(self,service=None):
        return X10ScheduleDelivery(service or self.s).tick([SCHEDULE])

    def write(self):
        self.tick()
        self.assertEqual(self.f.published[0][0],'audit/x10/command/read_scheduler')
        self.observe('scheduler/observation',{'entries':[]})
        result=self.tick()
        self.assertEqual(result['status'],'sent')
        self.assertEqual(len(self.f.published),2)
        return result

    def test_read_then_one_write_then_only_fresh_schedule_confirms(self):
        result=self.write()
        self.assertFalse(result['result']['physical_confirmation'])
        self.assertEqual(self.f.counts(),[1,1,1,1])
        self.observe('scheduler/observation',{'entries':self.commands})
        result=self.tick()
        self.assertEqual(result['status'],'confirmed')
        self.assertEqual(result['confirmation']['confirmation_scope'],'robot_weekly_schedule_not_cleaning_completion')
        for _ in range(3):self.tick(self.service())
        self.assertEqual(len(self.f.published),2)

    def test_missing_feedback_and_restart_never_repeat_write(self):
        self.write()
        for _ in range(5):self.tick(self.service())
        self.now+=121;self.mono+=121
        self.assertEqual(self.tick()['status'],'unknown')
        self.observe('scheduler/observation',{'entries':self.commands})
        self.assertEqual(self.tick()['status'],'unknown')
        self.assertEqual(len(self.f.published),2)

    def test_transport_failure_is_unknown_and_not_replayed(self):
        self.tick()
        self.observe('scheduler/observation',{'entries':[]})
        calls=[]
        service=self.service(publish_mqtt=lambda *a:calls.append(a) or (False,'ack timeout'))
        self.assertEqual(self.tick(service)['status'],'unknown')
        for _ in range(3):self.tick(service)
        self.assertEqual(len(calls),1)
        self.observe('scheduler/observation',{'entries':self.commands})
        self.assertEqual(self.tick(service)['status'],'confirmed')

    def test_bridge_acceptance_does_not_confirm_robot_schedule(self):
        result=self.write()
        self.observe('command_result',{'reported_at':self.now+.8,'ok':True,'command':'schedule_clean_week',
                     'extra':{'hc_execution_id':result['execution_id']}})
        self.assertEqual(self.tick()['status'],'accepted')
        self.assertFalse(self.tick()['result']['physical_confirmation'])
        self.assertEqual(len(self.f.published),2)

    def test_old_retained_or_reconnected_matching_snapshot_never_confirms(self):
        self.write()
        for variation in ('retained','old','generation'):
            self.observe('scheduler/observation',{'entries':self.commands})
            if variation=='retained':self.snap['topics']['scheduler/observation']['retain']=True
            if variation=='old':self.snap['topics']['scheduler/observation']['json']['sampled_at']-=100
            if variation=='generation':self.snap['connection_generation']=2
            self.assertNotEqual(self.tick()['status'],'confirmed')
        self.assertEqual(len(self.f.published),2)

    def test_two_independent_workers_read_and_write_once(self):
        self.f.parallel(lambda:self.tick(),lambda:self.tick(self.service()))
        self.assertEqual(len(self.f.published),1)
        self.observe('scheduler/observation',{'entries':[]})
        self.f.parallel(lambda:self.tick(),lambda:self.tick(self.service()))
        self.assertEqual(len(self.f.published),2)
        self.assertEqual(self.f.counts(),[1,1,1,1])

    def test_crash_after_committed_write_claim_does_not_repeat(self):
        self.tick();self.observe('scheduler/observation',{'entries':[]})
        calls=[]
        def crash(*a):
            calls.append(a)
            raise fixtures.ProcessCrash('process died in MQTT')
        with self.assertRaises(fixtures.ProcessCrash):self.tick(self.service(publish_mqtt=crash))
        row=self.f.execution()
        self.assertEqual(row['attempt'],1);self.assertEqual(row['status'],'unknown')
        self.tick(self.service())
        self.assertEqual(len(calls),1);self.assertEqual(len(self.f.published),1)

    def test_lost_result_commit_leaves_claim_and_no_second_write(self):
        self.tick();self.observe('scheduler/observation',{'entries':[]})
        fault=self.service(audit_transaction=lambda:self.f.fault_transaction('set result=result',before=True))
        with self.assertRaises(fixtures.ProcessCrash):self.tick(fault)
        self.assertEqual(self.f.execution()['attempt'],1)
        self.tick(self.service())
        self.assertEqual(len(self.f.published),2)

    def test_each_ledger_insert_failure_rolls_back_without_publish(self):
        for table in ('scheduler_run','event','plan','execution'):
            with self.subTest(table=table):
                self.f.clear();self.f.admin.execute_sql("update hc.scheduler_config set mode='v2_execute_x10'")
                fault=self.service(audit_transaction=lambda:self.f.fault_transaction('insert into hc.'+table))
                with self.assertRaises(fixtures.ProcessCrash):self.tick(fault)
                self.assertEqual(self.f.counts(),[0,0,0,0])
                self.assertEqual(self.f.published,[])

    def test_no_global_flag_no_mqtt_and_no_execution(self):
        result=self.tick(self.service(v2_execution_enabled=False))
        self.assertTrue(result['skipped']);self.assertEqual(self.f.published,[])
        self.assertEqual(self.f.counts(),[0,0,0,0])

    def test_disabled_domain_after_read_blocks_write(self):
        self.tick();self.observe('scheduler/observation',{'entries':[]})
        self.f.admin.execute_sql("update hc.scheduler_config set mode='v2_execute_climate'")
        self.assertEqual(self.tick()['status'],'blocked')
        self.assertEqual(len(self.f.published),1)

    def test_fresh_matching_read_requires_no_schedule_write(self):
        self.tick();self.observe('scheduler/observation',{'entries':self.commands})
        self.assertEqual(self.tick()['status'],'confirmed')
        self.assertEqual(len(self.f.published),1)

    def test_active_robot_blocks_write_but_not_observation(self):
        self.tick();self.observe('scheduler/observation',{'entries':[]})
        self.s.x10_active_cleaning_state=lambda:{'active':True}
        self.tick()
        self.assertEqual(len(self.f.published),1)
        self.s.x10_active_cleaning_state=lambda:{'active':False}
        self.tick()
        self.assertEqual(len(self.f.published),2)

    def climate(self,**overrides):
        self.f.admin.execute_sql("update hc.scheduler_config set mode='v2_execute_climate'")
        service=self.service(**overrides)
        row=SchedulerAudit(service).prepare(self.f.event())['execution']
        SchedulerAudit(service).dispatch(row['id'])
        return service

    def test_climate_publish_only_sent_then_fresh_device_state_confirms(self):
        s=self.climate()
        self.assertEqual(self.f.execution()['status'],'sent')
        command=self.f.execution()['command_payload']
        self.observe('state',{'ok':True,**command})
        SchedulerAudit(s).reconcile_climate()
        self.assertEqual(self.f.execution()['status'],'confirmed')
        self.assertTrue(self.f.execution()['result']['physical_confirmation'])
        s.climate_scheduler_tick()
        self.assertEqual(len(self.f.published),1)

    def test_climate_late_response_after_timeout_stays_unknown(self):
        s=self.climate();self.now+=121;self.mono+=121
        self.observe('state',{'ok':True,**self.f.execution()['command_payload']})
        SchedulerAudit(s).reconcile_climate()
        self.assertEqual(self.f.execution()['status'],'unknown')
        self.assertTrue(self.f.execution()['confirmation']['terminal'])
        self.now+=1;SchedulerAudit(s).reconcile_climate();s.climate_scheduler_tick()
        self.assertEqual(len(self.f.published),1)

    def test_climate_retained_matching_sample_and_ack_only_cannot_confirm(self):
        s=self.climate();command=self.f.execution()['command_payload']
        self.observe('state',{'ok':True,**command})
        self.snap['topics']['state']['retain']=True
        SchedulerAudit(s).reconcile_climate();self.assertEqual(self.f.execution()['status'],'sent')
        self.observe('command_result',{'reported_at':self.now+.8,'ok':True,'command':command})
        SchedulerAudit(s).reconcile_climate()
        self.assertEqual(self.f.execution()['status'],'accepted')
        self.assertFalse(self.f.execution()['result']['physical_confirmation'])

    def test_climate_restart_can_confirm_new_sample_without_republishing(self):
        self.climate();command=self.f.execution()['command_payload']
        self.observe('state',{'ok':True,**command})
        self.snap['observation_epoch']='restarted';self.mono=3.
        self.snap['topics']['state']['received_monotonic']=2.
        SchedulerAudit(self.service()).reconcile_climate()
        self.assertEqual(self.f.execution()['status'],'confirmed')
        self.assertEqual(len(self.f.published),1)

    def test_write_claim_commit_ack_lost_means_no_io_and_no_retry(self):
        self.tick();self.observe('scheduler/observation',{'entries':[]})
        fault=self.service(audit_transaction=lambda:self.f.fault_transaction('never match',after_commit=True))
        with self.assertRaises(fixtures.ProcessCrash):self.tick(fault)
        self.assertEqual(self.f.execution()['attempt'],1)
        self.tick(self.service())
        self.assertEqual(len(self.f.published),1)

    def test_read_claim_commit_ack_lost_means_no_io_and_no_retry(self):
        fault=self.service(audit_transaction=lambda:self.f.fault_transaction('never match',after_commit=True))
        with self.assertRaises(fixtures.ProcessCrash):self.tick(fault)
        self.assertEqual(self.f.counts(),[1,1,1,1])
        self.tick(self.service())
        self.assertEqual(self.f.published,[])

    def test_bound_individual_audit_confirms_only_exact_matching_command(self):
        matching=SchedulerAudit(self.s).prepare(self.f.event('xiaomi_x10',suffix='matching'))['execution']
        mismatch=SchedulerAudit(self.s).prepare(self.f.event('xiaomi_x10',suffix='mismatch'))['execution']
        self.f.admin.execute_one('update hc.execution set command_payload=%s::jsonb where id=%s returning *',
            (self.s.json_dumps(self.commands[0]),matching['id']))
        self.f.admin.execute_one('update hc.execution set command_payload=%s::jsonb where id=%s returning *',
            (self.s.json_dumps({**self.commands[0],'water_level':2}),mismatch['id']))
        self.write()
        row=self.f.admin.fetch_one('select * from hc.execution where id=%s',(matching['id'],))
        self.assertEqual(row['status'],'sent')
        self.observe('scheduler/observation',{'entries':self.commands});self.tick()
        row=self.f.admin.fetch_one('select * from hc.execution where id=%s',(matching['id'],))
        self.assertEqual(row['status'],'confirmed')
        row=self.f.admin.fetch_one('select * from hc.execution where id=%s',(mismatch['id'],))
        self.assertEqual(row['status'],'shadow_ready')

    def test_changed_desired_layout_creates_new_read_intent(self):
        self.write()
        changed={**SCHEDULE,'start_time':'10:00'}
        X10ScheduleDelivery(self.service()).tick([changed])
        self.assertEqual(len(self.f.published),3)
        self.assertTrue(self.f.published[-1][0].endswith('/read_scheduler'))
        self.assertEqual(self.f.counts(),[2,2,2,2])

    def test_republication_after_write_with_pre_write_source_cannot_confirm(self):
        self.write()
        boundary=self.f.execution()['result']['feedback_fence']
        self.observe('scheduler/observation',{'entries':self.commands})
        self.snap['topics']['scheduler/observation']['json']['sampled_at']=boundary['wall']-.1
        self.assertNotEqual(self.tick()['status'],'confirmed')

    def test_service_tick_uses_durable_weekly_delivery(self):
        self.s.x10_desired_weekly_schedules=lambda:[SCHEDULE]
        result=self.s.x10_scheduler_tick()
        self.assertEqual(result['status'],'unknown')
        self.assertEqual(self.f.counts(),[1,1,1,1])
        self.assertTrue(self.f.published[0][0].endswith('/read_scheduler'))
