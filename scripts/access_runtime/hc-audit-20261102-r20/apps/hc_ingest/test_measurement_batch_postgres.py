"""Real PostgreSQL HC-33 fault injection; only the disposable loopback lab."""
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import psycopg2
import mqtt_ingest_multi as ingest
from measurement_batch import MeasurementQueue


@unittest.skipUnless(os.getenv('HC33_RECOVERY_LAB')=='1','requires isolated HC-33 lab')
class BatchPostgresTest(unittest.TestCase):
    def setUp(self):
        self.dsn='host=127.0.0.1 dbname=hc11_recovery_test user=postgres'
        self.conn=self.connect();self.addCleanup(lambda:self.conn.close())
        with self.conn.cursor() as c:
            c.execute('select current_database()');self.assertEqual(c.fetchone()[0],'hc11_recovery_test')
            c.execute('drop schema if exists hc cascade')
            c.execute((Path(__file__).resolve().parents[2]/'infra/db/baselines/hc_r1_058_v1.sql').read_text())
            c.execute((Path(__file__).resolve().parents[2]/'infra/db/062_hc33_ingest_sample_identity.sql').read_text())
            c.execute("insert into hc.device(platform,name) values('system','fixture') returning id");device=c.fetchone()[0]
            c.execute("insert into hc.entity(device_id,name) values(%s,'fixture') returning id",(device,));self.eid=c.fetchone()[0]
            c.execute("insert into hc.metric(key,value_type) values('temperature','num')")
            c.execute("insert into hc.entity_metric(entity_id,metric_key,store_mode,deadband_num,min_interval_sec,max_interval_sec) values(%s,'temperature','both',1,5,300)",(self.eid,))
        self.queue=MeasurementQueue()
        p=patch.object(ingest,'pending_measurements',self.queue);p.start();self.addCleanup(p.stop)
        ingest.last_saved.clear();ingest.last_saved_retained.clear()
        self.addCleanup(ingest.last_saved.clear);self.addCleanup(ingest.last_saved_retained.clear)
        self.rule=ingest.Rule('both',0,0,300,True)
    def connect(self):
        c=psycopg2.connect(self.dsn);c.autocommit=True;return c
    def scalar(self,sql):
        with self.conn.cursor() as cur:cur.execute(sql);return cur.fetchone()[0]
    def stage(self,value,**kw):
        return ingest.persist_metric(None,self.eid,'temperature','num',value,self.rule,time.time(),{'retained':False,'recv_ts':time.time()},defer_flush=True,**kw)
    def flush(self,cur=None):
        if cur is not None:return ingest.flush_measurements(cur)
        with self.conn.cursor() as c:return ingest.flush_measurements(c)
    def test_closed_connection_before_batch_keeps_pending_sample(self):
        self.stage(5);identity=self.queue.items[0].sample_id
        cur=self.conn.cursor();self.conn.close()
        with self.assertRaises(psycopg2.InterfaceError):self.flush(cur)
        self.assertEqual(self.queue.items[0].sample_id,identity);self.assertFalse(ingest.last_saved)
        self.conn=self.connect();self.assertEqual(self.flush(),1)
        self.assertEqual(self.scalar('select count(*) from hc.measurement'),1)
    def test_missing_or_wrong_identity_index_fails_readiness_check(self):
        with self.conn.cursor() as c:
            c.execute('grant usage on schema hc to hc_app')
            c.execute('grant select,insert,update,delete on all tables in schema hc to hc_app')
            c.execute('grant usage,select on all sequences in schema hc to hc_app')
            c.execute('drop index hc.ux_measurement_ingest_sample_id')
        app=psycopg2.connect(self.dsn.replace('user=postgres','user=hc_app'));app.autocommit=True
        self.addCleanup(app.close)
        with self.assertRaisesRegex(RuntimeError,'migration 062'):ingest.verify_runtime_role(app)
        with self.conn.cursor() as c:c.execute('create unique index ux_measurement_ingest_sample_id on hc.measurement(entity_id)')
        with self.assertRaisesRegex(RuntimeError,'migration 062'):ingest.verify_runtime_role(app)

    def test_multiple_pages_roll_back_on_connection_failure_then_reconnect_without_duplicate(self):
        for i in range(7):self.stage(i)
        ids=[m.sample_id for m in self.queue.items]
        class Cursor:
            def __init__(self,inner):self.inner=inner;self.pages=0
            def __getattr__(self,name):return getattr(self.inner,name)
            def execute(self,sql,*args):
                if (sql.decode() if isinstance(sql,bytes) else sql).lstrip().lower().startswith('insert into hc.measurement'):
                    self.pages+=1
                    if self.pages==2:raise psycopg2.OperationalError('fixture disconnected before second page')
                return self.inner.execute(sql,*args)
        with self.conn.cursor() as cur,patch.object(ingest,'MEASUREMENT_BATCH_SIZE',2):
            with self.assertRaises(psycopg2.OperationalError):self.flush(Cursor(cur))
        self.assertEqual(self.scalar('select count(*) from hc.measurement'),0)
        self.assertEqual(self.scalar('select count(*) from hc.entity_state'),0)
        self.assertFalse(ingest.last_saved);self.assertEqual([m.sample_id for m in self.queue.items],ids)
        self.conn.close();self.conn=self.connect();self.assertEqual(self.flush(),7)
        self.assertEqual(self.scalar('select count(distinct ingest_sample_id) from hc.measurement'),7)
        self.assertEqual(self.scalar("select v_num from hc.entity_state where key='temperature'"),6)
        self.assertEqual(ingest.last_saved[self.eid,'temperature'][0],6)
    def test_commit_response_loss_retries_same_id_without_state_side_effect_or_duplicates(self):
        self.stage(12);identity=self.queue.items[0].sample_id
        outer=self
        class Cursor:
            def __init__(self,inner):self.inner=inner
            def __getattr__(self,name):return getattr(self.inner,name)
            def execute(self,sql,*args):
                result=self.inner.execute(sql,*args)
                if sql=='COMMIT':outer.conn.close();raise psycopg2.OperationalError('fixture response lost AFTER real commit')
                return result
        cur=self.conn.cursor()
        with self.assertRaises(psycopg2.OperationalError):self.flush(Cursor(cur))
        self.assertEqual(self.queue.items[0].sample_id,identity);self.assertFalse(ingest.last_saved)
        self.conn=self.connect()
        self.assertEqual(self.scalar('select count(*) from hc.measurement'),1)
        with self.conn.cursor() as c:c.execute("update hc.entity_state set v_num=999 where key='temperature'")
        self.assertEqual(self.flush(),1)
        self.assertEqual(self.scalar('select count(*) from hc.measurement'),1)
        self.assertEqual(self.scalar("select v_num from hc.entity_state where key='temperature'"),999)
        self.assertEqual(self.queue.status()['duplicate_confirmations'],1)
    def test_one_invalid_history_row_does_not_lose_valid_rows(self):
        self.stage(1);self.stage(2)
        ingest.queue_measurement(999999,'temperature','num',2,{'retained':False})
        self.stage(3)
        with patch.object(ingest,'MEASUREMENT_BATCH_SIZE',2):self.assertEqual(self.flush(),3)
        self.assertEqual(self.scalar('select count(*) from hc.measurement'),3)
        self.assertEqual(self.scalar("select v_num from hc.entity_state where key='temperature'"),3)
        self.assertEqual(self.queue.status()['dropped']['invalid_data'],1)
        self.assertEqual(ingest.last_saved[self.eid,'temperature'][0],3)
    def test_invalid_state_rolls_back_paired_history_too(self):
        with self.conn.cursor() as c:c.execute('alter table hc.entity_state add constraint lab_nonnegative check(v_num>=0)')
        self.stage(1);self.stage(-1);self.stage(2)
        self.assertEqual(self.flush(),2)
        self.assertEqual(self.scalar('select count(*) from hc.measurement where v_num<0'),0)
        self.assertEqual(self.scalar('select count(*) from hc.measurement'),2)
        self.assertEqual(self.queue.status()['dropped']['invalid_data'],1)
    def test_overflow_does_not_advance_state_or_committed_cache(self):
        self.queue.max_messages=1
        self.assertTrue(self.stage(1));self.assertFalse(self.stage(2))
        self.assertFalse(ingest.last_saved);self.assertEqual(self.scalar('select count(*) from hc.entity_state'),0)
        self.assertEqual(self.flush(),1);self.assertEqual(ingest.last_saved[self.eid,'temperature'][0],1)
        self.assertTrue(self.stage(2));self.assertEqual(self.flush(),1)
        self.assertEqual(self.scalar("select v_num from hc.entity_state where key='temperature'"),2)
    def test_restart_warms_history_cache_instead_of_newer_feedback_state(self):
        self.stage(10);self.flush()
        with self.conn.cursor() as c:
            c.execute("update hc.measurement set ts=now()-interval '400 seconds'")
            c.execute("update hc.entity_state set ts=now(),v_num=11")
            ingest.warm_last_saved_from_entity_state(c)
        self.assertEqual(ingest.last_saved[self.eid,'temperature'][0],10)
        self.assertGreater(time.time()-ingest.last_saved[self.eid,'temperature'][1],399)
        self.assertTrue(ingest.should_write(self.eid,'temperature',10,ingest.Rule('both',100,5,300,True),time.time())[0])
    def test_confirmed_state_and_history_use_original_receipt_timestamp(self):
        old=time.time()-12
        ingest.persist_metric(None,self.eid,'temperature','num',10,self.rule,old,{'retained':False,'recv_ts':old},defer_flush=True)
        self.flush()
        with self.conn.cursor() as c:
            c.execute("select s.ts=m.ts and s.ts < now()-interval '11 seconds' from hc.entity_state s join hc.measurement m on m.entity_id=s.entity_id and m.key=s.key")
            self.assertTrue(c.fetchone()[0])
    def test_newer_feedback_in_same_message_cannot_be_overwritten_by_earlier_batch(self):
        rule=ingest.Rule('both',100,60,300,True,True)
        with self.conn.cursor() as c:
            ingest.persist_metric(c,self.eid,'temperature','num',19,rule,time.time(),{'retained':False},defer_flush=True)
            ingest.persist_metric(c,self.eid,'temperature','num',51,rule,time.time(),{'retained':False},defer_flush=True)
        self.assertEqual(self.scalar("select v_num from hc.entity_state where key='temperature'"),51)
        self.assertEqual(self.scalar('select v_num from hc.measurement'),19)
        self.assertEqual(ingest.last_saved[self.eid,'temperature'][0],19)
    def test_history_only_manual_valve_preserves_session_tracking(self):
        with self.conn.cursor() as c:
            c.execute("insert into hc.metric(key,value_type) values('manual_valve_state','text')")
            ingest.persist_metric(c,self.eid,'manual_valve_state','text','OPEN',
                ingest.Rule('history',None,0,300,True),time.time(),{'retained':False})
        self.assertEqual(self.scalar("select count(*) from hc.measurement where key='manual_valve_state'"),1)
        self.assertEqual(self.scalar('select count(*) from hc.entity_state'),0)
        self.assertEqual(self.scalar("select count(*) from hc.irrigation_manual_session where started_by='physical_manual' and status='running'"),1)
    def test_existing_timestamp_key_conflicts_are_counted_without_corrupting_state(self):
        at=time.time()
        for value in (1,2,3):
            ingest.persist_metric(None,self.eid,'temperature','num',value,self.rule,at,{'retained':False},defer_flush=True)
        self.assertEqual(self.flush(),1)
        self.assertEqual(self.queue.status()['dropped']['invalid_data'],2)
        self.assertEqual(self.scalar("select v_num from hc.entity_state where key='temperature'"),1)
        with self.conn.cursor() as c:ingest.warm_last_saved_from_entity_state(c)
        self.assertEqual(ingest.last_saved[self.eid,'temperature'][0],1)

    def test_additive_migration_keeps_legacy_writes_and_idempotent_reapply(self):
        with self.conn.cursor() as c:
            c.execute((Path(__file__).resolve().parents[2]/'infra/db/062_hc33_ingest_sample_identity.sql').read_text())
            for i in range(2):c.execute('insert into hc.measurement(ts,entity_id,key,v_num) values(now(),%s,\'temperature\',1)',(self.eid,))
        self.assertEqual(self.scalar('select count(*) from hc.measurement where ingest_sample_id is null'),2)

if __name__=='__main__':unittest.main()
