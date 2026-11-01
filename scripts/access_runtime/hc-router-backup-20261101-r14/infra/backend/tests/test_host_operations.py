"""HC-44: real Unix RPC/peer identity, synthetic roots, no live Docker."""
import fcntl,importlib.util,json,os,socket,sys,tarfile,tempfile,threading,time,unittest,uuid
from pathlib import Path
from unittest.mock import Mock,patch

PROJECT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(PROJECT/'scripts/hostops'))
from server import CapabilityServer,OperationJournal
from executor import DockerCapabilities,Executor,bounded_command
from host_operations_client import HostOperationsClient,HostBackupService,docker_capability_request,HostOperationsUnavailable
from scoped_ai_power_coordination import ScopedAiPowerCoordinator
from backup_protocol import atomic_json,seal,verify_archive
from backup_service import BackupService


class HostOperationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        with patch.dict(os.environ,{'HC_BACKUP_DIR':str(self.root/'backups'),'HC_RESTORE_STAGING_DIR':str(self.root/'stage')}):
            self.backup=BackupService(Mock(),Mock())
        self.backup.backup_root.mkdir()
        self.backup.timer_file=self.root/'timer';self.backup.service_file=self.root/'service'
        self.target=self.root/'target';self.target.mkdir()
        self.backup.restore_targets={'scripts':self.target}
        self.restart_calls=[]
        def run(args,**kw):
            if args[:2]==['docker','ps']:
                self.assertIn('label=com.docker.compose.project=homecontrol',args)
                return json.dumps(dict(ID='abcdef123456',Names='homecontrol-backend',Image='pinned',State='running',Status='Up')).encode()
            if args[:2]==['docker','restart']:
                self.restart_calls.append(args);return b'abcdef123456'
            return b'{}'
        self.docker=DockerCapabilities(run=run,stats=lambda target:{'cpu_percent':1,'memory_usage_bytes':123})
        self.executor=Executor(self.docker,self.backup)
        self.journal=OperationJournal(self.root/'jobs')
        self.socket=self.root/'operations.sock'
        self.server=CapabilityServer(self.socket,self.executor,self.journal,allowed_uid=os.getuid())
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01});self.thread.start()
        def finish():self.server.shutdown();self.server.server_close();self.thread.join(2)
        self.addCleanup(finish)
        self.client=HostOperationsClient(self.socket);self.proxy=HostBackupService(self.client)

    def call_backup(self,method,*values):
        return self.client.call('backup',method=method,values=list(values))

    def archive(self):
        source=self.root/'archive-source';(source/'scripts').mkdir(parents=True)
        (source/'scripts/file.txt').write_text('restored')
        seal(source,'local',{})
        path=self.backup.backup_root/'homecontrol_hostops_fixture.tar.gz'
        with tarfile.open(path,'w:gz') as tar:tar.add(source,arcname='backup')
        checked=verify_archive(path)
        atomic_json(str(path)+'.complete.json',dict(version=1,completed=True,name=path.name,
            timestamp='2026-10-29T12:00:00+00:00',mtime_ns=path.stat().st_mtime_ns,**checked))
        return path

    def test_inventory_and_stats_are_fixed_capabilities(self):
        self.assertEqual(self.client.call('containers')[0]['Names'],['/homecontrol-backend'])
        self.assertEqual(self.client.call('stats',container='backend')['memory_usage_bytes'],123)

    def test_foreign_target_and_command_fields_are_rejected(self):
        for args in ({'container':'other-container'},{'container':'backend','command':['sh']},
                     {'container':'backend;id'},{'container':'/var/run/docker.sock'}):
            with self.subTest(args=args),self.assertRaises(ValueError):self.client.call('restart',**args)
        self.assertEqual(self.restart_calls,[])

    def test_raw_docker_api_and_exec_have_no_compatibility_route(self):
        with patch.dict(os.environ,{'HC_HOST_OPS_SOCKET':str(self.socket)}):
            for method,path in [('POST','/containers/create'),('POST','/containers/backend/exec'),('GET','/containers/backend/json'),('GET','/'),('POST','/exec/id/start')]:
                with self.subTest(path=path),self.assertRaises(ValueError):docker_capability_request(method,path)
            with self.assertRaises(ValueError):docker_capability_request('POST','/containers/backend/restart?t=10',b'{}')

    def test_restart_is_durable_accepted_and_idempotent(self):
        identity=uuid.uuid4().hex
        receipt=self.client.call('restart',container='backend',request_id=identity)
        self.assertEqual(receipt['state'],'queued')
        self.assertEqual(receipt['host_job_id'],identity)
        self.client.call('restart',container='backend',request_id=identity)
        for _ in range(100):
            row=self.client.call('job',job_id=identity)
            if row['state']=='completed':break
            time.sleep(.01)
        self.assertEqual(row['state'],'completed')
        self.assertEqual(len(self.restart_calls),1)
        with self.assertRaises(ValueError):self.client.call('restart',container='homecontrol-backend',request_id=identity)

    def test_interrupted_job_is_not_replayed(self):
        identity=uuid.uuid4().hex
        atomic_json(self.journal.root/(identity+'.json'),dict(state='running',digest='same'))
        self.assertEqual(self.journal.recover_abandoned(),1)
        self.assertEqual(self.journal.lookup(identity)['state'],'uncertain')
        callback=Mock()
        with self.assertRaises(RuntimeError):self.journal.perform(identity,'same','backup',callback)
        callback.assert_not_called()

    def test_restart_cannot_follow_a_replaced_container_identity(self):
        receipt=self.client.call('restart',container='backend')
        original=self.docker.run
        self.docker.run=lambda args,**kw:original(args,**kw).replace(b'abcdef123456',b'fedcba654321')
        for _ in range(100):
            job=self.client.call('job',job_id=receipt['host_job_id'])
            if job['state']=='failed':break
            time.sleep(.01)
        self.assertEqual(job['state'],'failed')
        self.assertEqual(self.restart_calls,[])

    def test_wrong_peer_uid_cannot_execute(self):
        self.server.allowed_uid=os.getuid()+1
        with self.assertRaises(HostOperationsUnavailable):self.client.call('containers')

    def test_missing_executor_does_not_try_local_docker(self):
        with patch('subprocess.run',side_effect=AssertionError('local fallback')):
            with self.assertRaises(HostOperationsUnavailable):HostOperationsClient(self.root/'missing').call('containers')

    def test_backup_queue_is_the_existing_f6_queue(self):
        payload,status=self.proxy.create_payload(lambda *a:{'changed':'backup'})
        self.assertEqual(status,202)
        request=json.loads((self.backup.backup_root/'requests'/(payload['run_id']+'.json')).read_text())
        self.assertEqual(request['mode'],'local')
        self.assertEqual(payload['context'],{'changed':'backup'})

    def test_proxy_cannot_invoke_arbitrary_backup_method(self):
        with self.assertRaises(AttributeError):self.proxy.run_gitea_script('evil')
        with self.assertRaises(ValueError):self.call_backup('run_gitea_script','evil')

    def test_settings_cannot_change_host_paths_commands_or_ssh_destinations(self):
        for data in ({'restic_password_file':'/etc/shadow'},{'ai_backup_host':'evil;id'},
                     {'git_offsite_remote':'--upload-pack=evil'},{'schedule_time':'02:15\nExecStart=evil'},
                     {'retention_days':True},{'include_apps':'true'},{'command':'id'}):
            with self.subTest(data=data),self.assertRaises(ValueError):self.call_backup('update_settings_payload',data)
        self.assertFalse(self.backup.settings_file.exists())

    def test_safe_schedule_update_keeps_protected_destinations(self):
        before=self.backup.settings()
        payload,status=self.proxy.update_settings_payload({'schedule_time':'04:20','retention_days':21},lambda *a:{})
        self.assertEqual(status,200)
        self.assertEqual(payload['settings']['ai_backup_host'],before['ai_backup_host'])
        self.assertIn('04:20',self.backup.timer_file.read_text())

    def test_verified_restore_runs_in_host_targets_and_compare_works(self):
        path=self.archive();(self.target/'file.txt').write_text('before')
        with patch('backup_service.ai_disabled',return_value=False):
            result,status=self.proxy.compare_payload(path.name,'scripts/file.txt')
            self.assertEqual(status,200);self.assertFalse(result['same'])
            result,status=self.proxy.restore_payload(dict(backup=path.name,paths=['scripts/file.txt'],mode='in_place',confirm='RESTORE'),lambda *a:{})
        self.assertEqual(status,200);self.assertTrue(result['ok'])
        self.assertEqual((self.target/'file.txt').read_text(),'restored')

    def test_unverified_restore_and_arbitrary_destination_rejected(self):
        path=self.archive();Path(str(path)+'.complete.json').unlink()
        with self.assertRaises(ValueError):self.call_backup('restore_payload',dict(backup=path.name,paths=['scripts'],mode='in_place',confirm='RESTORE'))
        with self.assertRaises(ValueError):self.call_backup('restore_payload',dict(backup=path.name,paths=['scripts'],destination='/etc',mode='staging'))
        self.assertEqual(list(self.target.iterdir()),[])

    def test_restore_path_escape_is_rejected_by_the_existing_contract(self):
        path=self.archive()
        with patch('backup_service.ai_disabled',return_value=False),self.assertRaises(ValueError):
            self.call_backup('restore_payload',dict(backup=path.name,paths=['scripts/../../etc'],mode='in_place',confirm='RESTORE'))
        self.assertEqual(list(self.target.iterdir()),[])

    def test_total_rpc_timeout_contains_a_reconcilable_job_identity(self):
        original=self.executor.dispatch
        self.executor.dispatch=lambda *a:time.sleep(.15)
        identity=uuid.uuid4().hex
        with self.assertRaisesRegex(TimeoutError,identity):self.client.call('containers',timeout=.02,request_id=identity)
        self.executor.dispatch=original

    def test_command_timeout_and_output_are_bounded(self):
        with self.assertRaises(TimeoutError):bounded_command([sys.executable,'-c','import time;time.sleep(3)'],timeout=.05)
        with self.assertRaises(RuntimeError):bounded_command([sys.executable,'-c','print("x"*2000)'],limit=100)

    def test_scoped_ai_state_preserves_common_backup_lock_and_cancels_old_owner(self):
        root=self.backup.backup_root
        atomic_json(root/'ai-power-state.json',dict(version=1,generation='old',intent={'owner':'old'}))
        coordinator=ScopedAiPowerCoordinator(root)
        self.assertIsNone(coordinator.read()['intent'])
        with coordinator.locked() as state:coordinator.invalidate(state,'new session')
        self.assertEqual(coordinator.path,root/'ai-control/ai-power-state.json')
        with (root/'homecontrol-backup.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertTrue(coordinator.guard()['backup_running'])
            with self.assertRaises(BlockingIOError):
                with coordinator.reserve_power():pass

    def test_f6_adapter_creates_a_verified_synthetic_archive_with_scoped_state(self):
        import subprocess
        from tests.test_backup_runner import BackupRunnerTest
        fixture=BackupRunnerTest();fixture.setUp()
        try:
            launcher=self.root/'canonical_runner.py'
            launcher.write_text((PROJECT/'scripts/hostops/canonical_backup_runner.py.in').read_text().replace('@RELEASE_ROOT_JSON@',json.dumps(str(PROJECT))))
            result=subprocess.run([sys.executable,str(launcher),
                '--root',str(fixture.root),'--mode','local'],env=fixture.env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            state=json.loads((fixture.root/'backup-state.json').read_text())
            self.assertEqual(state['state'],'completed')
            self.assertTrue((fixture.root/'ai-control/ai-power-state.json').is_file())
            self.assertFalse((fixture.root/'ai-power-state.json').exists())
        finally:fixture.doCleanups()


class HostOperationRouteTest(unittest.TestCase):
    def test_backend_restart_returns_the_persisted_host_receipt(self):
        from flask import Flask
        from api_route_modules import register_admin_routes
        app=Flask(__name__)
        register_admin_routes(app,get_context_service=lambda:None,get_admin_service=lambda:None,
            get_process_binding_service=lambda:None,get_season_profile_service=lambda:None,json_ready=lambda x:x)
        receipt={'restart_requested':True,'host_job_id':'1'*32,'state':'queued'}
        with patch('api_route_modules.docker_socket_request',return_value=(json.dumps(receipt).encode(),'')) as call:
            response=app.test_client().post('/api/admin/containers/backend/restart')
            self.assertEqual(response.status_code,202)
            self.assertEqual(response.get_json()['host_job_id'],'1'*32)
            call.assert_called_once()
            self.assertEqual(app.test_client().post('/api/admin/containers/foreign/restart').status_code,404)
            call.assert_called_once()

    def test_backend_identity_and_mount_gate_rejects_raw_socket_even_read_only(self):
        from installation_plan import validate_backend
        good={'Config':{'User':'10001:10001'},'HostConfig':{'ReadonlyRootfs':True,'CapDrop':['ALL'],
            'SecurityOpt':['no-new-privileges:true']},'Mounts':[]}
        self.assertEqual(validate_backend(good),[])
        bad={**good,'Mounts':[{'Type':'bind','Source':'/var/run/docker.sock','Destination':'/var/run/docker.sock','RW':False}]}
        self.assertIn('raw_host_socket_or_root_mount_forbidden',validate_backend(bad))

    def test_mqtt_plan_is_non_mutating_and_keeps_finding_open(self):
        spec=importlib.util.spec_from_file_location('hc41_plan',PROJECT/'scripts/plan_mqtt_access.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result=module.plan({'1883/tcp':[{'HostIp':'0.0.0.0','HostPort':'1883'}]})
        self.assertFalse(result['full_finding_fixed'])
        self.assertFalse(result['network_plan_ready'])
        self.assertFalse(result['passwords_changed'])
        with self.assertRaises(ValueError):module.plan({},allowed_clients=['192.168.1.2;id'])


if __name__=='__main__':unittest.main()
