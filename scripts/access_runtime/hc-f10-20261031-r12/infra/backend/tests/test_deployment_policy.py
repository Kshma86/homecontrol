"""Restricted release contracts: no real LAN/device I/O; real HTTP/process admission."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from flask import Flask
import deployment_policy as policy
from ai_node_service import AiNodeService
from ai_proxy_service import AiProxyService
from api_route_modules import register_ai_routes, register_backup_routes
from backup_service import BackupService
from mqtt_monitor_service import MqttClientService
from power_wall_service import PowerWallService
from process_binding_service import ProcessBindingService
from tests import test_backup_runner as runner_fixture
from tests.test_backup_units import Manager

PROJECT = Path(__file__).resolve().parents[3]
POLICY = {'version': 1, 'profile': 'ai-offline', 'blocked_entity_ids': [121],
          'blocked_command_topics': ['homecontrol/cmd/tuya/Mosógép/switch'],
          'blocked_tuya_device_ids': ['synthetic-ai-device']}


class RestrictedPolicyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root/'policy.json'; self.path.write_text(json.dumps(POLICY))
        for name, value in (('POLICY_FILE', self.path), ('POLICY_REQUIRED', True)):
            p = patch.object(policy, name, value); p.start(); self.addCleanup(p.stop)

    def forbidden(self, *args, **kwargs):
        self.fail('Restricted operation reached an external callback')

    def node(self):
        with patch.dict(os.environ, {'HC_BACKUP_DIR': str(self.root/'backup')}):
            service = AiNodeService(self.forbidden, self.forbidden, self.forbidden, self.forbidden,
                                    process_binding_entity_id=lambda key: '121', start_worker=False)
        self.addCleanup(service.close)
        service.host = '192.0.2.2'; service.mac = '001122334455'; service.ssh_user = 'synthetic'
        return service

    def test_missing_optional_policy_keeps_standard_profile(self):
        self.assertFalse(policy.load_policy(self.root/'missing', required=False)['restricted'])

    def test_mandatory_missing_corrupt_and_invalid_policy_fail_closed(self):
        for content in (None, 'bad JSON', '{}', json.dumps({**POLICY, 'blocked_entity_ids': [True]})):
            with self.subTest(content=content):
                if content is None: self.path.unlink(missing_ok=True)
                else: self.path.write_text(content)
                self.assertTrue(policy.ai_disabled())
                self.assertFalse(policy.public_status()['policy_valid'])
                self.assertTrue(policy.command_blocked('any/actuator', {}))
                self.assertFalse(policy.backup_mode_allowed('weekly'))

    def test_environment_cannot_disable_baked_policy(self):
        with patch.dict(os.environ, {'HC_DEPLOYMENT_PROFILE': 'standard', 'HC_DEPLOYMENT_POLICY': '/missing',
                                     'AI_NODE_HOST': '192.0.2.2'}):
            self.assertTrue(policy.ai_disabled())

    def test_invalid_mandatory_policy_refuses_application_startup(self):
        self.path.write_text('broken')
        with self.assertRaisesRegex(RuntimeError, 'startup refused'):
            policy.install_routes(Flask(__name__))

    def test_status_and_settings_explain_local_only_without_mutating_stored_settings(self):
        stored = {key: True for key in policy.REMOTE_SETTINGS}; before = dict(stored)
        effective = policy.effective_backup_settings(stored)
        self.assertEqual(stored, before)
        self.assertTrue(all(effective[key] is False for key in policy.REMOTE_SETTINGS))
        self.assertTrue(policy.public_status()['local_backup_only'])

    def test_all_ai_node_actions_block_before_network_or_publisher(self):
        node = self.node()
        with patch('ai_node_service.socket.socket', side_effect=self.forbidden), patch('ai_node_service.subprocess.run', side_effect=self.forbidden):
            self.assertTrue(node.start_power_guard())
            self.assertEqual(node.health()['state'], 'disabled')
            self.assertEqual(node.wake()[1], 503)
            self.assertEqual(node.shutdown_request(0, True)[1], 503)
            self.assertFalse(node.schedule_power_off(0)['scheduled'])
            self.assertFalse(node.set_power_plug(False, 'test')['ok'])
            self.assertFalse(node._publish_power(True, 'test')['ok'])
            for action in ('shutdown', 'start_stack', 'restart_stack', 'pull_images'):
                with self.assertRaises(ValueError): node.remote_command(action)
            with self.assertRaises(ValueError): node.send_wake_on_lan()
            node._pending = {'phase': 'off'}
            self.assertIsNone(node.run_pending_power()); self.assertIsNone(node._pending)
        self.assertFalse((self.root/'backup').exists())

    def test_ai_proxy_never_contacts_gateway_even_for_context_status(self):
        service = AiProxyService('http://192.0.2.2', 1, context_summary=self.forbidden,
                                 json_ready=lambda x: x, urlopen_func=self.forbidden)
        self.assertEqual(service.status()[1], 503)
        with self.assertRaises(OSError): service.request('/chat', {})
        self.assertFalse(service._proxy('/models')[0]['ok'])

    def test_generic_mqtt_and_renamed_tuya_payload_cannot_switch_ai(self):
        mqtt = MqttClientService('192.0.2.1', 1883, json.dumps)
        with patch('mqtt_monitor_service.mqtt.Client', side_effect=self.forbidden):
            for topic,payload in ((POLICY['blocked_command_topics'][0], {'value': False}),
                                  ('homecontrol/cmd/tuya/renamed/switch', {'entity_id': 121, 'value': True})):
                self.assertFalse(mqtt.publish(topic, payload)[0])
        self.assertFalse(policy.command_blocked('homecontrol/cmd/tuya/other/switch', {'entity_id': 122}))

    def test_consumer_blocks_ai_device_id_alias_even_after_a_name_change(self):
        self.assertTrue(policy.tuya_device_blocked('renamed', 'synthetic-ai-device'))
        self.assertTrue(policy.tuya_device_blocked('Mosógép', 'different-id'))
        self.assertFalse(policy.tuya_device_blocked('other', 'other-id'))

    def test_power_wall_scheduler_and_name_only_tuya_use_the_same_guard(self):
        service = PowerWallService(*(self.forbidden for _ in range(9)), guard_repeat_seconds=30)
        row = {'entity_id': 121, 'entity_name': 'renamed', 'platform': 'tuya'}
        for value in (True, False): self.assertFalse(service.publish_switch(row, value)[0])
        service.tuya_command_entity = lambda **kwargs: row
        self.assertFalse(service.tuya_switch_command(None, 'renamed', True)[1]['ok'])
        service.publish_mqtt = Mock(return_value=(True, 'published'))
        self.assertTrue(service.publish_switch({**row, 'entity_id': 122}, True)[0])
        service.publish_mqtt.assert_called_once()

    def test_ai_binding_change_rejected_before_database_or_coordination(self):
        binding = object.__new__(ProcessBindingService)
        with self.assertRaises(ValueError): binding.set_binding('ai_node_power_plug', 122)

    def test_http_ai_remote_backup_and_power_backdoors_rejected_before_handlers(self):
        app = Flask(__name__); policy.install_routes(app)
        register_ai_routes(app, get_ai_node_service=self.forbidden, get_ai_proxy_service=self.forbidden)
        register_backup_routes(app, get_context_service=self.forbidden, get_backup_service=self.forbidden,
                               context_command_meta=self.forbidden, invalidate_context_sections=self.forbidden,
                               json_ready=lambda x: x)
        for path in ('/api/power-wall/command', '/api/tuya/command', '/api/process-bindings/ai_node_power_plug'):
            app.add_url_rule(path, path, self.forbidden, methods=['POST','PUT'])
        client = app.test_client()
        for path in ('/api/ai/node/wake','/api/ai/node/command','/api/ai/chat','/api/ai/restart','/api/admin/containers/ai/restart',
                     '/api/backup/full-ai','/api/backup/gitea/commit','/api/backup/gitea/status','/api/backup/gitea/restore',
                     '/api/power-wall/command','/api/tuya/command'):
            with self.subTest(path=path):
                result = client.post(path, json={'entity_id': 121, 'action': 'shutdown', 'value': False})
                self.assertEqual(result.status_code, 503)
                self.assertEqual(result.json['code'], 'deployment_restricted')
        self.assertEqual(client.put('/api/process-bindings/ai_node_power_plug', json={'entity_id':122}).status_code,503)
        self.assertTrue(client.get('/api/deployment/status').json['restricted'])

    def test_old_code_cannot_be_restored_over_host_guards_but_staging_is_allowed(self):
        with patch.dict(os.environ, {'HC_BACKUP_DIR': str(self.root/'backup')}):
            service = BackupService(self.forbidden, self.forbidden)
        service.safe_path = self.forbidden
        with self.assertRaises(ValueError): service.restore_paths('old.tar.gz',['scripts'],'in_place','RESTORE')
        self.assertEqual(service.recover_restore_payload({'run_id':'old','confirm':'ROLLBACK'})[1],503)
        app=Flask(__name__);policy.install_routes(app)
        app.add_url_rule('/api/backup/restore','restore',lambda:{'staging':True},methods=['POST'])
        client=app.test_client()
        self.assertEqual(client.post('/api/backup/restore',json={'mode':'in_place','confirm':'RESTORE'}).status_code,503)
        self.assertEqual(client.post('/api/backup/restore/recover',json={'confirm':'ROLLBACK'}).status_code,503)
        self.assertEqual(client.post('/api/backup/restore',json={'mode':'staging'}).status_code,200)

    def test_backup_service_rejects_remote_requests_before_queue_or_subprocess(self):
        with patch.dict(os.environ, {'HC_BACKUP_DIR': str(self.root/'backup')}):
            service = BackupService(self.forbidden,self.forbidden)
        with patch('backup_service.subprocess.run', side_effect=self.forbidden):
            self.assertEqual(service.full_ai_backup_payload(self.forbidden)[1],503)
            self.assertEqual(service.gitea_commit_payload({},self.forbidden)[1],503)
            self.assertEqual(service.gitea_status_payload()[1],503)
            self.assertEqual(service.gitea_restore_payload({})[1],503)
        self.assertFalse((self.root/'backup').exists())

    def test_installer_disables_remote_timers_despite_saved_enabled_flags(self):
        spec=importlib.util.spec_from_file_location('restricted_installer',PROJECT/'scripts/install_backup_f6.py')
        installer=importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        root=self.root/'backup';root.mkdir();settings=root/'backup_settings.json'
        settings.write_text(json.dumps({'ai_weekly_backup_enabled':True,'restic_enabled':True}))
        before=settings.read_bytes();manager=Manager();units=self.root/'units'
        from types import SimpleNamespace
        with patch.object(installer.os,'geteuid',return_value=0), patch.object(installer.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000)):
            result=installer.install(apply=True,root=root,unit_dir=units,run=manager)
        self.assertTrue(result['enabled']['homecontrol-backup.timer'])
        self.assertFalse(result['enabled']['homecontrol-ai-weekly-backup.timer'])
        self.assertFalse(result['enabled']['homecontrol-restic-check.timer'])
        self.assertTrue(result['enabled']['homecontrol-full-ai-backup-request.path'])
        self.assertEqual(settings.read_bytes(),before)


class RestrictedRunnerTest(unittest.TestCase):
    setUp = runner_fixture.BackupRunnerTest.setUp
    save_settings = runner_fixture.BackupRunnerTest.save_settings
    commands = runner_fixture.BackupRunnerTest.commands

    def prepare_code(self):
        if hasattr(self, 'code'):return
        self.code=Path(self.temp.name)/'code';backend=self.code/'infra/backend'
        backend.mkdir(parents=True)
        for path in (PROJECT/'infra/backend').glob('*.py'):shutil.copy2(path,backend/path.name)
        (backend/'deployment_policy.json').write_text(json.dumps(POLICY))
        module=backend/'deployment_policy.py';module.write_text(module.read_text().replace('POLICY_REQUIRED = False','POLICY_REQUIRED = True'))
        scripts=self.code/'scripts';scripts.mkdir()
        for path in (PROJECT/'scripts').glob('*'):
            if path.is_file() and path.suffix in ('.py','.sh'):shutil.copy2(path,scripts/path.name)
        if (PROJECT/'scripts/access_release').exists():
            shutil.copytree(PROJECT/'scripts/access_release',scripts/'access_release',ignore=shutil.ignore_patterns('__pycache__'))

    def run_job(self,mode):
        self.prepare_code()
        return subprocess.run([sys.executable,str(self.code/'scripts/backup_runner.py'),'--root',str(self.root),'--mode',mode],
                              env={**self.env,'RESTIC_REQUIRED':'true'},capture_output=True,text=True,timeout=30)

    def test_local_backup_ignores_remote_settings_and_environment_without_losing_them(self):
        self.settings['restic_required']=True;self.save_settings();before=(self.root/'backup_settings.json').read_bytes()
        result=self.run_job('local');self.assertEqual(result.returncode,0,result.stderr+'\n'+(self.root/'backup.log').read_text())
        calls=self.commands();self.assertFalse(any(x[0] in ('ssh','git','restic') for x in calls))
        job=json.loads((self.root/'backup-state.json').read_text())
        self.assertEqual(job['scope'],'local_only');self.assertEqual(job['required_targets'],['local_archive'])
        self.assertEqual(job['targets']['restic']['state'],'skipped')
        self.assertEqual((self.root/'backup_settings.json').read_bytes(),before)

    def test_remote_cli_modes_and_stale_requests_cannot_start_workers(self):
        for mode in ('weekly','git','check'):
            result=self.run_job(mode);self.assertEqual(result.returncode,78,result.stderr)
            self.assertFalse(self.trace.exists())
            job=json.loads((self.root/'backup-state.json').read_text())
            self.assertEqual(job['state'],'failed');self.assertEqual(job['code'],'deployment_restricted')

    def test_direct_worker_invocation_is_also_rejected_before_any_remote_io(self):
        self.prepare_code()
        for name in ('backup_weekly_worker.sh','backup_check_worker.sh','backup_config_sync_worker.sh'):
            result=subprocess.run(['bash',str(self.code/'scripts'/name)],env=self.env,capture_output=True,text=True)
            self.assertEqual(result.returncode,78,result.stderr)
            self.assertFalse(self.trace.exists())

    def test_queue_drains_rejected_remote_job_without_replaying_or_busy_loop(self):
        self.prepare_code()
        from backup_protocol import enqueue
        request=enqueue(self.root,'weekly')
        result=subprocess.run([sys.executable,str(self.code/'scripts/backup_runner.py'),'--root',str(self.root),'--drain'],env=self.env,capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        self.assertFalse(list((self.root/'requests').glob('*.json')))
        job=json.loads((self.root/'runs'/(request['run_id']+'.json')).read_text())
        self.assertEqual(job['code'],'deployment_restricted');self.assertFalse(self.trace.exists())
