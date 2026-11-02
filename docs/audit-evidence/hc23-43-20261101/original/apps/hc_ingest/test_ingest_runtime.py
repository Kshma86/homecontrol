import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ingest_runtime import DatabaseWorker, InboundMessage, MessageInbox
import mqtt_ingest_multi as ingest


def wait_for(predicate, timeout=2):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate(): return
        time.sleep(.005)
    raise AssertionError('condition did not become true')


def message(value=b'x', at=None):
    return InboundMessage('fixture/state', value, False, time.time(), time.monotonic() if at is None else at)


class InboxTest(unittest.TestCase):
    def test_limits_and_drop_counters(self):
        q=MessageInbox(2,40)
        self.assertTrue(q.offer(message(),ready=True))
        self.assertTrue(q.offer(message(),ready=True))
        self.assertFalse(q.offer(message(),ready=True))
        self.assertFalse(q.offer(message(b'x'*100),ready=True))
        self.assertFalse(q.offer(message(),ready=False))
        self.assertEqual(q.status()['dropped'],{'overflow':1,'oversize':1,'db_unavailable':1})
        self.assertEqual(q.status()['queued_messages'],2)
        self.assertLessEqual(q.status()['queued_bytes'],40)
    def test_expired_message_never_reaches_consumer(self):
        clock=[10.0];q=MessageInbox(clock=lambda:clock[0],max_age=2)
        q.offer(message(at=9),ready=True);clock[0]=12
        self.assertIsNone(q.take(0));self.assertEqual(q.status()['dropped']['expired'],1)
    def test_fifo_preserves_payload_retain_and_original_receipt(self):
        q=MessageInbox();items=[InboundMessage('fixture',bytes([i]),True,123+i,time.monotonic()) for i in range(4)]
        for m in items:self.assertTrue(q.offer(m,ready=True))
        self.assertEqual([q.take(0) for _ in items],items)
    def test_overflow_never_exceeds_bound_during_burst(self):
        q=MessageInbox(3,100)
        for _ in range(10000):q.offer(message(),ready=True)
        self.assertEqual(q.status()['queued_messages'],3)
        self.assertEqual(q.status()['dropped']['overflow'],9997)
    def test_close_discards_and_rejects_future_items(self):
        q=MessageInbox();q.offer(message(),ready=True);q.close()
        self.assertIsNone(q.take(0));self.assertFalse(q.offer(message(),ready=True))
        self.assertEqual(q.status()['dropped']['shutdown'],2)
    def test_invalid_configuration_is_rejected(self):
        for kwargs in ({'max_messages':0},{'max_bytes':0},{'max_age':float('nan')},{'max_age':0}):
            with self.assertRaises(ValueError):MessageInbox(**kwargs)
    def test_invalidation_rejects_admission_with_stale_ready_snapshot(self):
        q=MessageInbox();q.offer(message(),ready=True)
        q.set_available(False)
        self.assertFalse(q.offer(message(),ready=True))
        self.assertEqual(q.status()['dropped'],{'db_failure':1,'db_unavailable':1})
        q.set_available(True)
        self.assertTrue(q.offer(message(),ready=True))


class WorkerTest(unittest.TestCase):
    def worker(self, **overrides):
        defaults=dict(connect=lambda:None,process=lambda m:None,tick=lambda:None,
                      finish=lambda:None,close=lambda:None,retry_seconds=.03)
        defaults.update(overrides);w=DatabaseWorker(MessageInbox(),**defaults)
        self.addCleanup(lambda:w.stop(2));return w
    def test_only_one_thread_owns_connect_process_ticks_and_close(self):
        owners=[];processed=threading.Event()
        def record(*args):owners.append(threading.get_ident())
        w=self.worker(connect=record,process=lambda m:(record(),processed.set()),tick=record,finish=record,close=record)
        t=w.start();self.assertIs(w.start(),t);wait_for(lambda:w.ready)
        w.inbox.offer(message(),ready=w.ready);self.assertTrue(processed.wait(1));self.assertTrue(w.stop(1))
        self.assertEqual(set(owners),{t.ident});self.assertNotEqual(t.ident,threading.get_ident())
    def test_connection_failure_is_throttled_and_shutdown_interrupts_retry(self):
        attempts=[]
        def connect():attempts.append(time.monotonic());raise OSError('fixture unavailable')
        w=self.worker(connect=connect,retry_seconds=1);w.start();wait_for(lambda:attempts)
        for _ in range(100):self.assertFalse(w.inbox.offer(message(),ready=w.ready))
        started=time.monotonic();self.assertTrue(w.stop(.2));self.assertLess(time.monotonic()-started,.3)
        self.assertEqual(len(attempts),1);self.assertEqual(w.inbox.status()['dropped']['db_unavailable'],100)
    def test_write_failure_discards_backlog_and_is_not_replayed(self):
        calls=[];entered=threading.Event();release=threading.Event()
        def process(m):
            calls.append(m.payload)
            if m.payload==b'bad':entered.set();release.wait(1);raise OSError('lost response')
        w=self.worker(process=process);w.start();wait_for(lambda:w.ready)
        w.inbox.offer(message(b'bad'),ready=True);self.assertTrue(entered.wait(1))
        w.inbox.offer(message(b'old'),ready=True);release.set()
        wait_for(lambda:w.status()['connect_attempts']>=2 and w.ready)
        w.inbox.offer(message(b'fresh'),ready=True);wait_for(lambda:b'fresh' in calls)
        self.assertEqual(calls,[b'bad',b'fresh']);self.assertEqual(w.inbox.status()['dropped']['db_failure'],1)
    def test_blocked_flush_cannot_make_shutdown_wait_forever(self):
        entered=threading.Event();release=threading.Event()
        def finish():entered.set();release.wait(2)
        w=self.worker(finish=finish);w.start();wait_for(lambda:w.ready)
        started=time.monotonic();self.assertFalse(w.stop(.02));self.assertLess(time.monotonic()-started,.2)
        self.assertTrue(entered.wait(1));release.set();self.assertTrue(w.stop(1))
    def test_stop_during_connect_closes_without_processing_or_flush(self):
        entered=threading.Event();release=threading.Event();closed=[];processed=[];flushed=[]
        def connect():entered.set();release.wait(2)
        w=self.worker(connect=connect,close=lambda:closed.append(True),process=processed.append,finish=lambda:flushed.append(True))
        w.start();self.assertTrue(entered.wait(1));self.assertFalse(w.stop(.01));release.set();self.assertTrue(w.stop(1))
        self.assertTrue(closed);self.assertFalse(processed);self.assertFalse(flushed)
    def test_stalled_db_job_stops_admission_but_keeps_memory_bound(self):
        entered=threading.Event();release=threading.Event()
        def process(m):entered.set();release.wait(2)
        w=self.worker(process=process,stall_seconds=.01);w.start();wait_for(lambda:w.ready)
        w.inbox.offer(message(),ready=True);self.assertTrue(entered.wait(1));time.sleep(.03)
        self.assertTrue(w.status()['stalled']);self.assertFalse(w.ready)
        self.assertFalse(w.inbox.offer(message(),ready=w.ready));release.set()
    def test_resource_closes_before_a_second_connection_is_created(self):
        events=[];failed=[False]
        def connect():events.append('connect')
        def process(m):
            if not failed[0]:failed[0]=True;raise OSError()
        w=self.worker(connect=connect,process=process,close=lambda:events.append('close'));w.start();wait_for(lambda:w.ready)
        w.inbox.offer(message(),ready=True);wait_for(lambda:events.count('connect')==2)
        self.assertEqual(events[:3],['connect','close','connect'])


class ProductionMainTest(unittest.TestCase):
    def test_network_loop_continues_during_db_startup_and_recovers_with_fresh_data(self):
        network=threading.get_ident();owners=[];values=[];closed=[];loops=[0];warm_release=threading.Event()
        class Cursor:
            def close(self):closed.append(('cursor',threading.get_ident()))
        class Connection:
            closed=False
            def cursor(self):return Cursor()
            def close(self):closed.append(('connection',threading.get_ident()))
        class Client:
            def reconnect_delay_set(self,**kwargs):pass
            def connect(self,*args):self.on_connect(self,None,None,0)
            def subscribe(self,*args):pass
            def disconnect(self):pass
            def loop(self,timeout):
                loops[0]+=1
                if loops[0]==12:warm_release.set()
                self.on_message(self,None,SimpleNamespace(topic='zigbee/fixture',payload=json.dumps({'temperature':loops[0]}).encode(),retain=False))
                time.sleep(.004)
                if loops[0]>=40:ingest.running=False
                return 0
        def connect(*a,**kw):owners.append(threading.get_ident());self.assertEqual(kw['connect_timeout'],3);return Connection()
        def warm(cur):self.assertTrue(warm_release.wait(1))
        def persist(cur,eid,key,vt,v,rule,tnow,meta,**kwargs):owners.append(threading.get_ident());values.append(v);return True
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(ingest,'running',True),patch.object(ingest,'mqtt_connected',False),patch.object(ingest,'mqtt_started_once',False),patch.object(ingest,'INGEST_STATUS_FILE',folder+'/status.json'),patch.object(ingest,'HEARTBEAT_FILE',folder+'/heartbeat'),patch.object(ingest.mqtt,'Client',return_value=Client()),patch.object(ingest.psycopg2,'connect',side_effect=connect),patch.object(ingest,'verify_runtime_role'),patch.object(ingest,'warm_last_saved_from_entity_state',side_effect=warm),patch.object(ingest,'cached_entity_id',return_value=1),patch.object(ingest,'cached_rules',return_value={'temperature':ingest.Rule('state',None,None,None,True)}),patch.object(ingest,'cached_metric_meta',return_value=ingest.MetricMeta('num',None,None,False)),patch.object(ingest,'upsert_presence'),patch.object(ingest,'persist_metric',side_effect=persist):
                self.assertEqual(ingest.main(),0)
        self.assertEqual(loops[0],40);self.assertTrue(values);self.assertGreaterEqual(min(values),12)
        self.assertNotIn(network,owners);self.assertEqual(len(set(owners)),1)
        self.assertEqual([kind for kind,ident in closed],['cursor','connection'])
        self.assertTrue(all(ident==owners[0] for kind,ident in closed))

class ConnectionCleanupTest(unittest.TestCase):
    def test_actual_connect_closes_failed_role_or_warmup_resources(self):
        import ast
        from pathlib import Path
        tree=ast.parse(Path(ingest.__file__).read_text())
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        functions=[n for n in main.body if isinstance(n,ast.FunctionDef) and n.name in ('connect_db','close_db')]
        outer=ast.parse('def factory():\n conn=cur=None\n last_flush_at=0\n contact_drops=0\n').body[0]
        outer.body.extend(functions);outer.body.extend(ast.parse('return connect_db,close_db').body)
        module=ast.fix_missing_locations(ast.Module(body=[outer],type_ignores=[]))
        for fail_at in ('role','warmup','none','cursor_close'):
            with self.subTest(fail_at=fail_at):
                closed=[]
                class Cursor:
                    def close(self):
                        closed.append('cursor')
                        if fail_at=='cursor_close':raise OSError()
                class Connection:
                    def cursor(self):return Cursor()
                    def close(self):closed.append('connection')
                def verify(c):
                    if fail_at=='role':raise RuntimeError('fixture denied role')
                def warm(c):
                    if fail_at=='warmup':raise ingest.OperationalError('fixture warmup failure')
                namespace={**vars(ingest),'psycopg2':SimpleNamespace(connect=lambda *a,**kw:Connection()),'verify_runtime_role':verify,'warm_last_saved_from_entity_state':warm,'pending_contacts':{}}
                exec(compile(module,'actual-connect-closures','exec'),namespace)
                connect,close=namespace['factory']()
                if fail_at in ('role','warmup'):
                    with self.assertRaises((RuntimeError,ingest.OperationalError)):connect()
                else:connect();close()
                self.assertEqual(closed,['connection'] if fail_at=='role' else ['cursor','connection'])

    def test_status_file_error_does_not_interrupt_network_or_shutdown_reporting(self):
        import ast
        from pathlib import Path
        from unittest.mock import Mock
        main=next(n for n in ast.parse(Path(ingest.__file__).read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='main')
        report=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='report_status')
        logger=Mock()
        namespace={**vars(ingest),'worker':SimpleNamespace(status=lambda:{}),'contact_drops':0,'process_start_ticks':'fixture','log_limited':logger}
        exec(compile(ast.Module(body=[report],type_ignores=[]),'actual-status-closure','exec'),namespace)
        with patch.object(Path,'write_text',side_effect=OSError('fixture disk full')),patch('builtins.print'):
            namespace['report_status']()
        logger.assert_called_once_with('ingest_status_write','[INGEST_STATUS] write failed: OSError')

    def test_process_exits_nonzero_when_shutdown_flush_is_permanently_blocked(self):
        import subprocess
        import sys
        code='''
import threading,time
from ingest_runtime import DatabaseWorker,MessageInbox
entered=threading.Event()
def finish():entered.set();threading.Event().wait()
w=DatabaseWorker(MessageInbox(),connect=lambda:None,process=lambda m:None,tick=lambda:None,finish=finish,close=lambda:None)
w.start()
while not w.ready:time.sleep(.001)
stopped=w.stop(.05)
assert entered.wait(.5)
raise SystemExit(0 if stopped else 1)
'''
        result=subprocess.run([sys.executable,'-c',code],timeout=2,capture_output=True,text=True)
        self.assertEqual(result.returncode,1,result.stderr)


if __name__=='__main__':unittest.main()
