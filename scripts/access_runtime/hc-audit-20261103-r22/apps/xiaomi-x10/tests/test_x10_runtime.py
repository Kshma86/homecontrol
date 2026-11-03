"""Synthetic X10 transport/progress tests: never load robot credentials or send packets."""
import ast
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from x10_runtime import MiioTransport, ProgressWatchdog, run_map_refresh, valid_status_sample


def process_call(lock_file, events, gate):
    def runner(*args,**kwargs):
        events.put(('start',time.monotonic()));time.sleep(.08)
        events.put(('end',time.monotonic()))
        return SimpleNamespace(returncode=0,stdout='ok',stderr='')
    gate.wait(5)
    MiioTransport('fake','192.0.2.1','synthetic',lock_file,runner=runner).run(['read'])


def bridge_functions(names,namespace):
    tree=ast.parse((ROOT/'xiaomi_x10_bridge.py').read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<bridge functions>','exec'),namespace)
    return namespace


class MiioTransportTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.lock=Path(self.temp.name)/'miio.lock'

    def transport(self,runner,**kwargs):
        return MiioTransport('fake','192.0.2.1','secret-fixture',self.lock,runner=runner,**kwargs)

    def test_threads_and_separate_instances_never_overlap(self):
        active=0;peak=0;guard=threading.Lock();errors=[]
        def runner(*a,**kw):
            nonlocal active,peak
            with guard:active+=1;peak=max(peak,active)
            time.sleep(.02)
            with guard:active-=1
            return SimpleNamespace(returncode=0,stdout='ok',stderr='')
        first=self.transport(runner);second=self.transport(runner)
        gate=threading.Barrier(8,timeout=5)
        def call(index):
            try:gate.wait();(first if index%2 else second).run(['read'])
            except BaseException as exc:errors.append(exc)
        threads=[threading.Thread(target=call,args=(i,)) for i in range(8)]
        for t in threads:t.start()
        for t in threads:t.join(5);self.assertFalse(t.is_alive())
        self.assertEqual(errors,[]);self.assertEqual(peak,1)

    def test_processes_use_same_file_lock(self):
        ctx=multiprocessing.get_context('fork');events=ctx.Queue();gate=ctx.Event()
        workers=[ctx.Process(target=process_call,args=(str(self.lock),events,gate)) for _ in range(2)]
        try:
            for w in workers:w.start()
            gate.set()
            for w in workers:w.join(5);self.assertEqual(w.exitcode,0)
            records=sorted([events.get(timeout=2) for _ in range(4)],key=lambda item:item[1])
            self.assertEqual([event[0] for event in records],['start','end','start','end'])
        finally:
            for w in workers:
                if w.is_alive():w.kill();w.join()
            events.close();events.join_thread()

    def test_command_guard_runs_inside_transport_lock_and_failure_releases_it(self):
        calls=[]
        transport=self.transport(lambda *a,**kw: calls.append(a) or
            SimpleNamespace(returncode=0,stdout='ok',stderr=''))
        def expired():
            with self.lock.open('a') as contender:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(contender,fcntl.LOCK_EX|fcntl.LOCK_NB)
            raise RuntimeError('fixture-expired')
        with self.assertRaisesRegex(RuntimeError,'fixture-expired'):
            transport.run(['write'],before_send=expired)
        self.assertEqual(calls,[])
        self.assertEqual(transport.run(['poll']),'ok')
        self.assertEqual(len(calls),1)

    def test_contended_file_lock_times_out_without_sending(self):
        calls=[]
        with self.lock.open('w') as held:
            fcntl.flock(held,fcntl.LOCK_EX)
            start=time.monotonic()
            with self.assertRaisesRegex(RuntimeError,'lock wait timed out'):
                self.transport(lambda *a,**kw:calls.append(a),lock_timeout=.08).run(['write'])
            self.assertLess(time.monotonic()-start,.8)
        self.assertEqual(calls,[])

    def test_contended_thread_lock_times_out_without_sending(self):
        t=self.transport(lambda *a,**kw:self.fail('must not send'),lock_timeout=.05)
        t.thread_lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError,'lock wait timed out'):t.run(['write'])
        finally:t.thread_lock.release()

    def test_timeout_redacts_token_and_releases_lock_for_next_call(self):
        calls=[]
        def runner(command,**kw):
            calls.append(command)
            self.assertEqual(kw['timeout'],.1)
            if len(calls)==1:raise subprocess.TimeoutExpired(command,.1)
            return SimpleNamespace(returncode=0,stdout='ok',stderr='')
        t=self.transport(runner,command_timeout=.1)
        with self.assertRaises(RuntimeError) as caught:t.run(['write'])
        self.assertNotIn('secret-fixture',str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertEqual(t.run(['read']),'ok');self.assertEqual(len(calls),2)

    def test_python_miio_typeerror_is_failure_without_automatic_retry(self):
        calls=[]
        def runner(*a,**kw):
            calls.append(a)
            return SimpleNamespace(returncode=1,stdout='',stderr='TypeError: secret-fixture internal miio failure')
        with self.assertRaises(RuntimeError) as caught:self.transport(runner).run(['write'])
        self.assertEqual(len(calls),1);self.assertNotIn('secret-fixture',str(caught.exception))
        self.assertIn('TypeError',str(caught.exception))

    def test_error_output_with_zero_rc_is_not_success(self):
        with self.assertRaises(RuntimeError):
            self.transport(lambda *a,**kw:SimpleNamespace(returncode=0,stdout='ERROR: failed',stderr='')).run(['read'])

    def test_failed_lock_open_releases_thread_lock(self):
        t=self.transport(lambda *a,**kw:None);t.lock_file=str(Path(self.temp.name)/'missing'/'lock')
        with self.assertRaises(OSError):t.run(['read'])
        self.assertTrue(t.thread_lock.acquire(blocking=False));t.thread_lock.release()

    def test_invalid_limits_rejected(self):
        for value in (0,-1,True,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError):self.transport(None,command_timeout=value)

    def test_killed_owner_releases_process_lock(self):
        ctx=multiprocessing.get_context('fork');ready=ctx.Event()
        def hold():
            t=self.transport(None)
            with t.locked():ready.set();time.sleep(30)
        owner=ctx.Process(target=hold);owner.start()
        try:
            self.assertTrue(ready.wait(3));owner.kill();owner.join(3)
            t=self.transport(lambda *a,**kw:SimpleNamespace(returncode=0,stdout='ok',stderr=''),lock_timeout=.1)
            self.assertEqual(t.run(['read']),'ok')
        finally:
            if owner.is_alive():owner.kill();owner.join()

    def test_real_subprocess_timeout_kills_cli_and_unlocks(self):
        pidfile=Path(self.temp.name)/'cli.pid'
        cli=Path(self.temp.name)/'fake-miio'
        cli.write_text('#!'+sys.executable+'\nimport os,time,pathlib\npathlib.Path('+repr(str(pidfile))+').write_text(str(os.getpid()))\ntime.sleep(30)\n')
        cli.chmod(0o700)
        transport=MiioTransport(cli,'192.0.2.1','synthetic',self.lock,command_timeout=.3)
        with self.assertRaisesRegex(RuntimeError,'MIIO command timed out'):transport.run(['read'])
        pid=int(pidfile.read_text())
        self.assertFalse((Path('/proc')/str(pid)).exists())
        self.assertTrue(transport.thread_lock.acquire(blocking=False));transport.thread_lock.release()


class WatchdogTest(unittest.TestCase):
    def setUp(self):
        self.now=0.;self.w=ProgressWatchdog(30,clock=lambda:self.now)

    def test_transient_failure_below_deadline_and_success_recover(self):
        self.now=29.;self.assertEqual(self.w.expired(),{})
        self.w.success('main');self.w.success('status');self.now=40.
        self.assertEqual(self.w.expired(),{})

    def test_busy_main_does_not_mask_status_failure(self):
        self.now=31.;self.w.success('main')
        self.assertEqual(set(self.w.expired()),{'status'})

    def test_healthy_status_does_not_mask_stalled_main(self):
        self.now=31.;self.w.success('status')
        self.assertEqual(set(self.w.expired()),{'main'})

    def test_live_map_only_required_while_tracking(self):
        self.w.require('live_map',False);self.now=40.
        self.w.success('main');self.w.success('status')
        self.assertEqual(self.w.expired(),{})
        self.w.require('live_map',True);self.now=69.
        self.w.success('main');self.w.success('status');self.assertEqual(self.w.expired(),{})
        self.now=71.;self.assertEqual(set(self.w.expired()),{'live_map'})

    def test_healthy_map_does_not_mask_missing_status(self):
        self.w.require('live_map',True);self.now=31.
        self.w.success('main');self.w.success('live_map')
        self.assertEqual(set(self.w.expired()),{'status'})

    def test_live_tracking_reactivation_gets_new_grace_period(self):
        self.w.require('live_map',True);self.now=40.
        self.w.require('live_map',False);self.now=100.
        self.w.require('live_map',True);self.w.success('main');self.w.success('status')
        self.assertEqual(self.w.expired(),{})

    def test_watchdog_exits_without_mqtt_or_robot_operation(self):
        class Exited(BaseException):pass
        exits=[]
        def leave(code):exits.append(code);raise Exited()
        self.now=31.
        ns=bridge_functions(['watchdog_worker'],{'progress_watchdog':self.w,'live_tracking_active':lambda:False,
            'json':json,'os':SimpleNamespace(_exit=leave),'print':lambda *a,**kw:None})
        with self.assertRaises(Exited):ns['watchdog_worker']()
        self.assertEqual(exits,[75])

    def test_logging_failure_still_exits(self):
        class Exited(BaseException):pass
        def fail(*a,**kw):raise BrokenPipeError()
        def leave(code):raise Exited()
        self.now=31.
        ns=bridge_functions(['watchdog_worker'],{'progress_watchdog':self.w,'live_tracking_active':lambda:False,
            'json':json,'os':SimpleNamespace(_exit=leave),'print':fail})
        with self.assertRaises(Exited):ns['watchdog_worker']()

    def test_actual_watchdog_exits_process_with_stalled_worker(self):
        tree=ast.parse((ROOT/'xiaomi_x10_bridge.py').read_text())
        worker=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='watchdog_worker')
        source=("import sys,time,json,os,threading\nfrom types import SimpleNamespace\n"
                "from x10_runtime import ProgressWatchdog\n"
                "progress_watchdog=ProgressWatchdog(.15)\n"
                "live_tracking_active=lambda:False\nconfig=SimpleNamespace(WATCHDOG_CHECK_SEC=.01)\n"
                +ast.unparse(worker)+"\nthreading.Thread(target=watchdog_worker,daemon=True).start()\n"
                "time.sleep(10)\n")
        result=subprocess.run([sys.executable,'-c',source],cwd=ROOT,capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,75,result.stderr)
        self.assertIn('X10 WATCHDOG',result.stdout)


class MapProcessAndWiringTest(unittest.TestCase):
    def test_map_timeout_kills_child_process_group(self):
        with tempfile.TemporaryDirectory() as temp:
            pidfile=Path(temp)/'child.pid'
            source=('import subprocess,sys,time,pathlib;'
                    'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]);'
                    'pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(30)')
            with self.assertRaisesRegex(RuntimeError,'map refresh timed out'):
                run_map_refresh([sys.executable,'-c',source,str(pidfile)],timeout=.5)
            pid=int(pidfile.read_text())
            for _ in range(30):
                status=Path('/proc')/str(pid)/'stat'
                if not status.exists() or status.read_text().split()[2]=='Z':break
                time.sleep(.01)
            else:self.fail('map MIIO child survived timeout')

    def test_invalid_timeout_never_starts_map_process(self):
        with patch('x10_runtime.subprocess.Popen') as popen:
            with self.assertRaises(ValueError):run_map_refresh(['fake'],timeout=0)
            popen.assert_not_called()

    def test_map_failure_exit_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError,'exit code 7'):
            run_map_refresh([sys.executable,'-c','raise SystemExit(7)'],timeout=2)

    def test_bridge_and_map_use_same_transport_entrypoint(self):
        calls=[]
        ns=bridge_functions(['miio_cmd'],{'run_miio':lambda a:calls.append(a) or 'shared'})
        self.assertEqual(ns['miio_cmd'](['get_property_by','2','1']),'shared')
        tree=ast.parse((ROOT/'xiaomi_x10_map.py').read_text())
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='get_robot_property')
        space={'run_miio':lambda a:calls.append(a) or "[{'code': 0, 'value': 42}]",'ast':ast}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<map property>','exec'),space)
        self.assertEqual(space['get_robot_property'](None,6,8),42)
        self.assertEqual(calls,[['get_property_by','2','1'],['get_property_by','6','8']])

    def test_status_missing_required_fields_does_not_feed_watchdog(self):
        for state,battery,expected in ((12,80,['status']),(None,None,[]),(12,None,[]),('bad',80,[]),(True,80,[]),(12,101,[]),(12,float('nan'),[])):
            progress=[]
            ns=bridge_functions(['read_status'],{'get_property':lambda s,p:state if (s,p)==(2,1) else battery,
                'STATE_TEXT':{},'time':SimpleNamespace(time=lambda:1.),'publish':lambda *a,**kw:None,
                'valid_status_sample':valid_status_sample,'mark_progress':progress.append,'get_map_object':lambda:None,'publish_robot_at_dock':lambda:None})
            ns['read_status']();self.assertEqual(progress,expected)

    def test_invalid_property_reply_is_not_usable_telemetry(self):
        for output in ("[{'code': -1, 'value': 12}]", '[]', 'None', '[123]'):
            ns=bridge_functions(['get_property'],{'miio_cmd':lambda a:output,'ast':ast,'json':json})
            with self.subTest(output=output),self.assertRaises(RuntimeError):ns['get_property'](2,1)

    def test_single_live_error_does_not_feed_watchdog_and_backs_off(self):
        class EndLoop(BaseException):pass
        successes=[];sleeps=[]
        def read():raise RuntimeError('MIIO TypeError fixture')
        def sleep(seconds):sleeps.append(seconds);raise EndLoop()
        ns=bridge_functions(['live_map_worker'],{'live_tracking_active':lambda:True,
            'request_live_robot_position':read,'mark_progress':successes.append,'last_state':{},
            'time':SimpleNamespace(time=lambda:100.,sleep=sleep),'LIVE_MAP_ACTIVE_POLL_SEC':.3,
            'publish':lambda *a,**kw:None})
        with self.assertRaises(EndLoop):ns['live_map_worker']()
        self.assertEqual(successes,[]);self.assertEqual(sleeps,[5])

    def test_successful_live_frame_feeds_only_live_watchdog(self):
        class EndLoop(BaseException):pass
        successes=[]
        def sleep(seconds):raise EndLoop()
        ns=bridge_functions(['live_map_worker'],{'live_tracking_active':lambda:True,
            'request_live_robot_position':lambda:{'map_id':1},'mark_progress':successes.append,
            'time':SimpleNamespace(time=lambda:100.,sleep=sleep),'LIVE_MAP_ACTIVE_POLL_SEC':.3,
            'LIVE_MAP_POLL_SEC':1.5})
        with self.assertRaises(EndLoop):ns['live_map_worker']()
        self.assertEqual(successes,['live_map'])

    def test_failed_map_refresh_keeps_old_md5_and_next_check_retries(self):
        calls=[];errors=[]
        def refresh():
            calls.append('refresh')
            if len(calls)==1:raise RuntimeError('transient download failure')
            return {'maps':[]}
        ns=bridge_functions(['check_map_update'],{'last_map_md5':'old',
            'get_map_object':lambda:{'md5':'new'},'refresh_maps':refresh,
            'publish':lambda *a,**kw:errors.append(a),'print':lambda *a:None})
        ns['check_map_update']();self.assertEqual(ns['last_map_md5'],'old')
        ns['check_map_update']();self.assertEqual(ns['last_map_md5'],'new')
        ns['check_map_update']();self.assertEqual(calls,['refresh','refresh']);self.assertEqual(len(errors),1)

    def test_missing_map_export_does_not_advance_md5(self):
        ns=bridge_functions(['check_map_update'],{'last_map_md5':'old',
            'get_map_object':lambda:{'md5':'new'},'refresh_maps':lambda:None,'print':lambda *a:None})
        ns['check_map_update']();self.assertEqual(ns['last_map_md5'],'old')

    def test_invalid_watchdog_config_rejected_before_start(self):
        for changes in ({'X10_MIIO_TIMEOUT_SEC':'0'},{'X10_WATCHDOG_CHECK_SEC':'300'},
                        {'X10_WATCHDOG_TIMEOUT_SEC':'60'}):
            environment={name:os.environ[name] for name in ('PATH','HOME','PYTHONDONTWRITEBYTECODE') if name in os.environ}
            environment.update(changes)
            result=subprocess.run([sys.executable,'-c','import config'],cwd=ROOT,env=environment,
                                  capture_output=True,text=True,timeout=3)
            self.assertNotEqual(result.returncode,0);self.assertIn('ValueError',result.stderr)


if __name__=='__main__':unittest.main()
