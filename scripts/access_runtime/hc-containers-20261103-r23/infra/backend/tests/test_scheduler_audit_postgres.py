"""HC-08 faults/races on a dedicated, opt-in, disposable PostgreSQL only."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import threading
import unittest
from urllib.parse import urlparse, urlunparse

from scheduler_audit import SchedulerAudit, scheduler_audit_transaction
from tests import test_scheduler_service as fixtures


class ProcessCrash(BaseException):
    pass


@unittest.skipUnless(os.environ.get('HC08_TEST_POSTGRES') == '1', 'requires isolated HC-08 PostgreSQL')
class SchedulerAuditPostgresTest(unittest.TestCase):
    def setUp(self):
        from database_service import DatabaseService
        from psycopg.rows import dict_row
        url = os.environ['HC08_TEST_DATABASE_URL']
        parsed = urlparse(url)
        if parsed.hostname != '127.0.0.1' or parsed.path != '/hc08_audit_test':
            raise AssertionError('HC-08 tests require the dedicated isolated database')
        self.admin = DatabaseService(url)
        source = (Path(__file__).resolve().parents[2] / 'db/003_hc_v2_core.sql').read_text()
        scheduler = (Path(__file__).resolve().parents[2] / 'db/059_hc07_startup_schema.sql').read_text()
        ddl = '\n'.join(re.search(r'create table if not exists hc\.' + table + r' \(.*?\n\);', scheduler, re.S).group()
                        for table in ('scheduler_config', 'scheduler_job', 'scheduler_run'))
        self.admin.execute_sql('create schema if not exists hc; create table if not exists hc.entity(id bigint primary key);')
        self.admin.execute_sql(source)
        self.admin.execute_sql(ddl + '''
            alter table hc.scheduler_run add column if not exists idempotency_key text;
            create unique index if not exists ux_scheduler_run_idempotency on hc.scheduler_run(idempotency_key) where idempotency_key is not null;
            DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='hc_app') THEN
                CREATE ROLE hc_app LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
            END IF; END $$;
            grant connect on database hc08_audit_test to hc_app;
            grant usage on schema hc to hc_app;
            grant select,insert,update,delete on all tables in schema hc to hc_app;
            grant usage on all sequences in schema hc to hc_app;
        ''')
        self.clear()
        app_url = urlunparse(parsed._replace(netloc='hc_app@127.0.0.1' + (':' + str(parsed.port) if parsed.port else '')))
        self.db = DatabaseService(app_url, expected_role='hc_app')
        self.connect = lambda: self.db.conn(dict_row)
        self.published = []
        self.fans = []
        self.service = self.make_service()
        self.audit = SchedulerAudit(self.service)

    def clear(self):
        self.admin.execute_sql('truncate hc.event,hc.plan,hc.execution,hc.scheduler_run,hc.scheduler_config restart identity cascade; insert into hc.scheduler_config(id,mode) values(1,\'v2_execute_climate\');')

    def make_service(self, **overrides):
        values = dict(fetch_one=self.db.fetch_one, fetch_all=self.db.fetch_all,
                      execute_one=self.db.execute_one,
                      audit_transaction=lambda: scheduler_audit_transaction(self.connect),
                      climate_command_topic='test/climate/command',
                      climate_state_payload=lambda: {'power': 'off'},
                      publish_mqtt=lambda topic, command: self.published.append((topic, command)) or (True, 'fake publisher'),
                      sync_auto_climate_power_wall=lambda value: self.fans.append(value) or [{'power': value}])
        values.update(overrides)
        return fixtures.SchedulerServiceTest().service(**values)

    def event(self, domain='climate', action=None, suffix='one'):
        action = action or {'climate': 'climate_set', 'irrigation': 'water_start', 'xiaomi_x10': 'clean_start'}[domain]
        return dict(key='shadow:' + domain + ':fixture:' + suffix, domain=domain, action=action,
                    status='shadow_would_set', payload={'source_ref': 'rule-one', 'power': 'on',
                    'climate_mode': 'heat', 'target_temperature': 24, 'duration_minutes': 5, 'extra_fan': 'off'})

    def counts(self):
        return [self.admin.fetch_one('select count(*) as n from hc.' + name)['n'] for name in ['scheduler_run', 'event', 'plan', 'execution']]

    def execution(self):
        return self.admin.fetch_one('select * from hc.execution order by created_at limit 1')

    @contextmanager
    def fault_transaction(self, stage, *, before=False, after_commit=False):
        with scheduler_audit_transaction(self.connect) as real:
            class FaultQueries:
                def invoke(inner, method, query, params=()):
                    matches = stage in query.lower()
                    if matches and before:
                        raise ProcessCrash(stage)
                    result = getattr(real, method)(query, params)
                    if matches and not after_commit:
                        raise ProcessCrash(stage)
                    return result
                def fetch_one(inner, query, params=()): return inner.invoke('fetch_one', query, params)
                def fetch_all(inner, query, params=()): return inner.invoke('fetch_all', query, params)
                def execute_one(inner, query, params=()): return inner.invoke('execute_one', query, params)
            yield FaultQueries()
        if after_commit:
            raise ProcessCrash('commit acknowledgement lost')

    def parallel(self, *callbacks):
        gate = threading.Barrier(len(callbacks), timeout=10)
        results, errors = [], []
        def work(callback):
            try:
                gate.wait()
                results.append(callback())
            except BaseException as exc: errors.append(exc)
        threads = [threading.Thread(target=work, args=(callback,)) for callback in callbacks]
        for t in threads:t.start()
        for t in threads:
            t.join(15)
            self.assertFalse(t.is_alive(), 'scheduler DB worker hung')
        self.assertEqual(errors, [])
        return results

    def test_failure_after_every_insert_rolls_back_whole_chain_all_domains(self):
        for domain, action in [('climate','climate_set'),('irrigation','water_start'),('irrigation','water_stop'),('xiaomi_x10','clean_start')]:
            for stage in ['scheduler_run','event','plan','execution']:
                with self.subTest(domain=domain, action=action, stage=stage):
                    self.clear()
                    service = self.make_service(audit_transaction=lambda: self.fault_transaction('insert into hc.' + stage))
                    with self.assertRaises(ProcessCrash):SchedulerAudit(service).prepare(self.event(domain, action))
                    self.assertEqual(self.counts(), [0,0,0,0])
                    self.assertTrue(self.audit.prepare(self.event(domain, action))['created'])
                    self.assertEqual(self.counts(), [1,1,1,1])
                    self.assertEqual(self.published, [])
                    self.assertEqual(self.fans, [])

    def test_independent_connections_prepare_one_chain(self):
        other = SchedulerAudit(self.make_service())
        result = self.parallel(lambda: self.audit.prepare(self.event()), lambda: other.prepare(self.event()))
        self.assertEqual(sorted(row['created'] for row in result), [False,True])
        self.assertEqual(self.counts(), [1,1,1,1])

    def test_independent_dispatchers_publish_only_once(self):
        row = self.audit.prepare(self.event())['execution']
        other = SchedulerAudit(self.make_service())
        result = self.parallel(lambda: self.audit.dispatch(row['id']), lambda: other.dispatch(row['id']))
        self.assertEqual(sum(x is not None for x in result), 1)
        self.assertEqual(len(self.published), 1)
        self.assertEqual(self.execution()['attempt'], 1)

    def test_legacy_partial_chains_recover_after_due_time_without_replay(self):
        for domain in ['climate','irrigation','xiaomi_x10']:
            for depth in [1,2,3]:
                with self.subTest(domain=domain, depth=depth):
                    self.clear()
                    event = self.event(domain)
                    run = self.service.insert_run_once(event['key'],domain,event['action'],event['status'],event['payload'])
                    self.admin.execute_sql("update hc.scheduler_run set requested_at=now()-interval '2 days'")
                    payload = {**event['payload'], 'scheduler_run_id':run['id']}
                    if depth>=2:
                        fact = self.service.insert_v2_event_once('v2:'+event['key'],domain,event['action'],event['status'],payload)
                    if depth>=3:
                        builder = {'climate':self.service.insert_v2_climate_plan_once,'irrigation':self.service.insert_v2_irrigation_plan_once,'xiaomi_x10':self.service.insert_v2_x10_plan_once}[domain]
                        builder(fact,event['action'],payload)
                    self.service.shadow_audit_events = lambda: []
                    self.assertEqual(self.service.record_shadow_audit(), 0)
                    self.assertEqual(self.counts(), [1,1,1,1])
                    self.service.climate_scheduler_tick()
                    row=self.execution()
                    self.assertEqual(row['status'],'unknown')
                    self.assertTrue(row['result']['delivery_uncertain'])
                    self.assertIsNone(row['result']['publish_attempted'])
                    self.assertEqual(row['created_at'],self.admin.fetch_one('select requested_at from hc.scheduler_run')['requested_at'])
                    self.assertEqual(self.published, [])
                    self.assertEqual(self.fans, [])

    def test_legacy_completed_execution_is_never_overwritten(self):
        row=self.audit.prepare(self.event())['execution']
        self.admin.execute_sql("update hc.scheduler_run set payload=payload-'_audit_protocol'; update hc.execution set status='confirmed',result='{\"old\":true}'")
        self.audit.prepare(self.event())
        self.service.climate_scheduler_tick()
        self.assertEqual(self.execution()['result'], {'old':True})
        self.assertEqual(self.execution()['status'],'confirmed')
        self.assertEqual(self.published, [])

    def test_historical_x10_recovery_cannot_be_marked_as_new_weekly_execution(self):
        event=self.event('xiaomi_x10')
        self.service.insert_run_once(event['key'],event['domain'],event['action'],event['status'],event['payload'])
        self.admin.execute_sql("update hc.scheduler_run set requested_at=now()-interval '4 months'")
        self.audit.recover()
        self.service.mark_v2_x10_executions('confirmed',{'weekly':'current'})
        self.assertEqual(self.execution()['status'],'unknown')
        self.assertTrue(self.execution()['result']['audit_recovered'])
        self.assertEqual(self.published,[])

    def test_repeat_uses_original_payload_and_cannot_change_intent(self):
        self.audit.prepare(self.event())
        changed=self.event();changed['payload']['target_temperature']=16
        self.assertFalse(self.audit.prepare(changed)['created'])
        self.assertEqual(self.execution()['command_payload']['target_temperature'],24)

    def test_pending_committed_chain_survives_restart_and_dispatches_once(self):
        service=self.make_service(audit_transaction=lambda:self.fault_transaction('never match',after_commit=True))
        with self.assertRaises(ProcessCrash):SchedulerAudit(service).prepare(self.event())
        self.assertEqual(self.counts(),[1,1,1,1])
        restarted=self.make_service()
        restarted.shadow_audit_events=lambda:[]
        restarted.record_shadow_audit()
        restarted.climate_scheduler_tick();restarted.climate_scheduler_tick()
        row=self.execution()
        self.assertEqual(row['status'],'sent')
        self.assertFalse(row['result']['physical_confirmation'])
        self.assertFalse(row['confirmation']['confirmed'])
        self.assertFalse(row['confirmation']['fresh'])
        self.assertEqual(len(self.published),1)

    def test_claim_commit_reply_lost_never_authorizes_publish(self):
        row=self.audit.prepare(self.event())['execution']
        service=self.make_service(audit_transaction=lambda:self.fault_transaction('never match',after_commit=True))
        with self.assertRaises(ProcessCrash):SchedulerAudit(service).dispatch(row['id'])
        self.service.climate_scheduler_tick()
        self.assertEqual(self.execution()['status'],'unknown')
        self.assertEqual(self.published,[])

    def test_crash_after_claim_before_publish_is_not_replayed(self):
        row=self.audit.prepare(self.event())['execution']
        claim=self.audit.claim_climate(row['id'])
        self.assertEqual(claim['status'],'unknown')
        self.make_service().climate_scheduler_tick()
        self.assertEqual(self.published,[])

    def test_crash_after_publish_before_result_is_not_replayed(self):
        row=self.audit.prepare(self.event())['execution']
        def publish(topic,payload):
            self.published.append((topic,payload));raise ProcessCrash('reply lost')
        with self.assertRaises(ProcessCrash):SchedulerAudit(self.make_service(publish_mqtt=publish)).dispatch(row['id'])
        self.make_service().climate_scheduler_tick()
        self.assertEqual(len(self.published),1)
        self.assertEqual(self.execution()['status'],'unknown')

    def test_publisher_timeout_and_false_result_remain_unknown(self):
        for kind in ['timeout','false']:
            with self.subTest(kind=kind):
                self.clear();self.published.clear()
                row=self.audit.prepare(self.event())['execution']
                def publish(topic,payload):
                    self.published.append((topic,payload))
                    if kind=='timeout':raise TimeoutError('lost acknowledgement')
                    return False,'transport outcome uncertain'
                SchedulerAudit(self.make_service(publish_mqtt=publish)).dispatch(row['id'])
                self.service.climate_scheduler_tick()
                self.assertEqual(self.execution()['status'],'unknown')
                self.assertEqual(len(self.published),1)

    def test_result_write_failure_cannot_trigger_second_publish(self):
        row=self.audit.prepare(self.event())['execution']
        service=self.make_service(audit_transaction=lambda:self.fault_transaction('error=%s',before=True))
        with self.assertRaises(ProcessCrash):SchedulerAudit(service).dispatch(row['id'])
        self.service.climate_scheduler_tick()
        self.assertEqual(self.execution()['status'],'unknown')
        self.assertEqual(len(self.published),1)

    def test_secondary_power_action_failure_is_uncertain_and_not_replayed(self):
        row=self.audit.prepare(self.event())['execution']
        def fan(value):raise TimeoutError('power wall reply lost')
        SchedulerAudit(self.make_service(sync_auto_climate_power_wall=fan)).dispatch(row['id'])
        self.service.climate_scheduler_tick()
        self.assertTrue(self.execution()['result']['delivery_uncertain'])
        self.assertTrue(self.execution()['result']['published'])
        self.assertEqual(len(self.published),1)

    def test_publisher_observes_committed_claim_outside_any_preparation_transaction(self):
        row=self.audit.prepare(self.event())['execution']
        def publish(topic,payload):
            observed=self.admin.fetch_one('select status,attempt from hc.execution where id=%s',(row['id'],))
            self.assertEqual(observed,{'status':'unknown','attempt':1})
            self.assertEqual(self.counts(),[1,1,1,1])
            self.published.append((topic,payload));return True,'fake'
        SchedulerAudit(self.make_service(publish_mqtt=publish)).dispatch(row['id'])
        self.assertEqual(len(self.published),1)

    def test_expired_intent_is_blocked_instead_of_late_restart_publish(self):
        self.audit.prepare(self.event())
        self.admin.execute_sql("update hc.scheduler_run set requested_at=now()-interval '2 minutes'")
        self.service.climate_scheduler_tick()
        self.assertEqual(self.execution()['status'],'blocked')
        self.assertEqual(self.execution()['attempt'],0)
        self.assertEqual(self.published,[])

    def test_domain_and_global_flags_rechecked_at_dispatch(self):
        for mode,global_flag,domain_flag in [('v2_execute_irrigation',True,True),('v2_execute_climate',False,True),('v2_execute_climate',True,False)]:
            with self.subTest(mode=mode,global_flag=global_flag,domain_flag=domain_flag):
                self.clear();self.audit.prepare(self.event())
                self.admin.execute_sql('update hc.scheduler_config set mode=%s',(mode,))
                self.make_service(v2_execution_enabled=global_flag,v2_allow_climate=domain_flag).climate_scheduler_tick()
                self.assertEqual(self.execution()['status'],'blocked')
                self.assertEqual(self.published,[])

    def test_disabled_engine_prepares_shadow_only(self):
        for flags in [dict(v2_execution_enabled=False),dict(v2_allow_climate=False)]:
            with self.subTest(flags=flags):
                self.clear();SchedulerAudit(self.make_service(**flags)).prepare(self.event())
                self.service.climate_scheduler_tick()
                self.assertEqual(self.execution()['status'],'shadow_ready')
                self.assertEqual(self.published,[])

    def test_duplicate_historical_plan_requires_reconciliation(self):
        self.audit.prepare(self.event())
        self.admin.execute_sql("insert into hc.plan(event_id,domain,type) select event_id,domain,type from hc.plan limit 1")
        with self.assertRaisesRegex(RuntimeError,'Duplicate'):self.audit.prepare(self.event())
        self.assertEqual(self.published,[])

    def test_daily_and_dst_repeated_local_minute_deduplication(self):
        job={'domain':'climate','source':'fixture','source_ref':'rule','is_enabled':True,'day_of_week':6,'start_time':'02:30','payload':{'power':'on'}}
        clock={'today':'2026-10-25','day_of_week':6,'local_minute':'02:30'}
        first=self.service.shadow_audit_events(clock=clock,jobs=[job])[0]
        repeated=self.service.shadow_audit_events(clock=clock,jobs=[job])[0]
        self.assertTrue(self.audit.prepare(first)['created']);self.assertFalse(self.audit.prepare(repeated)['created'])
        next_day=self.service.shadow_audit_events(clock={**clock,'today':'2026-11-01'},jobs=[job])[0]
        self.assertTrue(self.audit.prepare(next_day)['created'])
        self.assertEqual(self.counts(),[2,2,2,2])

    def test_missing_table_rolls_back_run_reservation(self):
        self.admin.execute_sql('alter table hc.execution rename to unavailable_execution')
        try:
            with self.assertRaises(Exception):self.audit.prepare(self.event())
        finally:self.admin.execute_sql('alter table hc.unavailable_execution rename to execution')
        self.assertEqual(self.counts(),[0,0,0,0])

    def test_transaction_adapter_is_required(self):
        with self.assertRaisesRegex(RuntimeError,'transaction adapter'):
            SchedulerAudit(self.make_service(audit_transaction=None)).prepare(self.event())
        self.assertEqual(self.counts(),[0,0,0,0])

    def test_diagnostic_snapshot_does_not_hold_audit_transaction(self):
        reads=[]
        def snapshot():
            count=self.admin.fetch_one("select count(*) as n from pg_stat_activity where datname=current_database() and usename='hc_app' and state='idle in transaction'")['n']
            self.assertEqual(count,0)
            reads.append(True)
            return {'power':'off'}
        audit=SchedulerAudit(self.make_service(climate_state_payload=snapshot))
        audit.prepare(self.event());audit.prepare(self.event())
        self.assertEqual(reads,[True])

    def test_claim_update_failure_rolls_back_without_publishing(self):
        row=self.audit.prepare(self.event())['execution']
        audit=SchedulerAudit(self.make_service(audit_transaction=lambda:self.fault_transaction("status='unknown'")))
        with self.assertRaises(ProcessCrash):audit.dispatch(row['id'])
        self.assertEqual(self.execution()['status'],'pending')
        self.assertEqual(self.published,[])
        self.service.climate_scheduler_tick()
        self.assertEqual(len(self.published),1)

    def test_result_commit_reply_loss_keeps_final_record_without_replay(self):
        row=self.audit.prepare(self.event())['execution']
        counter=[]
        @contextmanager
        def transaction():
            with scheduler_audit_transaction(self.connect) as q:yield q
            counter.append(True)
            if len(counter)==2:raise ProcessCrash('final commit reply lost')
        audit=SchedulerAudit(self.make_service(audit_transaction=transaction))
        with self.assertRaises(ProcessCrash):audit.dispatch(row['id'])
        self.service.climate_scheduler_tick()
        self.assertEqual(self.execution()['status'],'sent')
        self.assertEqual(len(self.published),1)


if __name__=='__main__':unittest.main()
