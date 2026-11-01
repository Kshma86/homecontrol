"""Router backup contracts plus opt-in real restic/rclone/FTP roundtrip."""
import configparser
from contextlib import contextmanager
import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'infra/backend'))
sys.path.insert(0, str(BASE / 'scripts'))
import deployment_policy as policy
from backup_service import BackupService
from backup_protocol import atomic_json, read_json
from backup_export_manifest import allowed_path
from router_backup import DEFAULTS, RouterRepository, private_text, repository, validate
import configure_router_backup as configure

POLICY = {'version': 1, 'profile': 'ai-offline', 'backup_profile': 'router-ftp',
          'blocked_entity_ids': [121], 'blocked_command_topics': ['homecontrol/cmd/ai']}


class RouterContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = {**BackupService.DEFAULT_SETTINGS, 'backup_target': 'router_ftp'}

    def test_repository_and_port(self):
        self.assertEqual(repository(self.settings), 'rclone:routerbackup:/G/hc-backup/restic/homecontrol')
        validate({**self.settings, 'router_ftp_port': 2121})
        for port in (True, 0, 65536):
            with self.assertRaises(ValueError):
                validate({**self.settings, 'router_ftp_port': port})

    def test_paths_cannot_escape_disk(self):
        for value in ('/', '/G', '/G/../elsewhere', '/other/repository', '/G/secret\ncommand'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                repository({**self.settings, 'router_repository_path': value})

    def test_remote_and_host_reject_command_fragments(self):
        for key, value in (('router_rclone_remote', ':ftp:host=other'),
                           ('router_ftp_host', 'ftp://router'), ('router_ftp_user', 'x\r\nPASS y')):
            with self.assertRaises(ValueError):
                validate({**self.settings, key: value})

    def test_credentials_must_be_private_regular_and_not_symlink(self):
        path = self.root / 'private'
        path.write_text('secret')
        path.chmod(0o644)
        with self.assertRaises(ValueError): private_text(path)
        path.chmod(0o600)
        self.assertEqual(private_text(path), 'secret')
        link = self.root / 'link'
        link.symlink_to(path)
        with self.assertRaises(OSError): private_text(link)

    def test_candidate_creation_never_overwrites(self):
        path = self.root / 'candidate'
        configure.create_private(path, 'original')
        with self.assertRaises(FileExistsError): configure.create_private(path, 'replacement')
        self.assertEqual(path.read_text(), 'original')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_policy_allows_only_explicit_router_capability(self):
        file = self.root / 'policy.json'
        atomic_json(file, POLICY)
        with patch.object(policy, 'POLICY_FILE', file):
            self.assertTrue(policy.ai_disabled())
            self.assertTrue(policy.backup_mode_allowed('weekly', self.settings))
            self.assertFalse(policy.backup_mode_allowed('weekly', {'backup_target': 'ai_sftp'}))
            self.assertTrue(policy.backup_mode_allowed('git', self.settings))
            self.assertTrue(policy.public_status()['router_backup_enabled'])
            effective = policy.effective_backup_settings({**self.settings, 'restic_enabled': True,
                                                          'git_offsite_enabled': True})
            self.assertTrue(effective['restic_enabled'])
            self.assertTrue(effective['git_offsite_enabled'])
            for key in ('git_origin_enabled', 'include_gitea', 'ai_weekly_shutdown_after'):
                self.assertFalse(effective[key])
            atomic_json(file, {**POLICY, 'backup_profile': 'unexpected'})
            self.assertFalse(policy.backup_mode_allowed('git', self.settings))
            file.unlink()
            self.assertFalse(policy.backup_mode_allowed('git', self.settings))

    def test_existing_local_only_policy_still_blocks_router_and_git(self):
        local = {k: v for k, v in POLICY.items() if k != 'backup_profile'}
        file = self.root / 'policy.json'
        atomic_json(file, local)
        with patch.object(policy, 'POLICY_FILE', file):
            self.assertFalse(policy.backup_mode_allowed('weekly', self.settings))
            self.assertFalse(policy.backup_mode_allowed('git', self.settings))
            effective = policy.effective_backup_settings({**self.settings, 'restic_enabled': True})
            self.assertFalse(effective['restic_enabled'])

    def test_plan_and_settings_use_router_without_ai(self):
        with patch.dict(os.environ, {'HC_BACKUP_DIR': str(self.root)}), patch.object(policy, 'policy', return_value={**POLICY, 'valid': True, 'restricted': True}):
            service = BackupService(None, None)
            service.timer_file = self.root / 'timer'
            with patch.object(service, 'parse_timer_file', return_value={}):
                submitted = {key: value for key, value in self.settings.items() if key != 'git_paths'}
                settings = service.save_settings({**submitted, 'router_ftp_port': 2121})
            self.assertEqual(settings['router_ftp_port'], 2121)
            plan = service.backup_plan(settings)
            self.assertEqual(plan['restic']['remote']['host'], '192.168.1.1')
            self.assertFalse(plan['restic']['weekly']['wakes_ai_server'])
            self.assertFalse(plan['git']['origin_enabled'])

    def test_export_never_contains_rclone_credentials(self):
        self.assertFalse(allowed_path('scripts/router-rclone.conf'))
        self.assertFalse(allowed_path('docs/router-restic-password'))
        self.assertTrue(allowed_path('scripts/configure_router_backup.py'))

    def test_router_capability_does_not_reopen_ai_http_or_live_restore(self):
        from flask import Flask
        file = self.root / 'policy.json'
        atomic_json(file, POLICY)
        with patch.object(policy, 'POLICY_FILE', file):
            app = Flask(__name__)
            policy.install_routes(app)
            for path in ('/api/ai/node/wake', '/api/backup/full-ai', '/api/backup/gitea/commit',
                         '/api/backup/gitea/status', '/api/backup/restore'):
                app.add_url_rule(path, path, lambda: ('handler', 200), methods=['POST'])
            client = app.test_client()
            for path in ('/api/backup/full-ai', '/api/backup/gitea/commit'):
                self.assertEqual(client.post(path, json={}).status_code, 200)
            for path in ('/api/ai/node/wake', '/api/backup/gitea/status'):
                self.assertEqual(client.post(path, json={}).status_code, 503)
            self.assertEqual(client.post('/api/backup/restore', json={'mode': 'in_place'}).status_code, 503)

    def test_secrets_manifest_includes_private_router_access(self):
        from backup_export import secrets_manifest
        (self.root / 'secrets').mkdir()
        (self.root / 'secrets/manifest.txt').write_text('/etc/homecontrol/legacy-secret\n')
        atomic_json(self.root / 'backups/backup_settings.json', self.settings)
        output = self.root / 'manifest'
        secrets_manifest(self.root, output)
        lines = output.read_text().splitlines()
        self.assertIn(self.settings['router_rclone_config'], lines)
        self.assertIn(self.settings['restic_password_file'], lines)

    def test_ambient_rclone_remote_settings_cannot_override_credentials(self):
        with patch.dict(os.environ, {'RCLONE_CONFIG_ROUTERBACKUP_HOST': 'different-host',
                                     'RESTIC_PASSWORD': 'different-password'}):
            repo = RouterRepository(self.settings)
        self.assertNotIn('RCLONE_CONFIG_ROUTERBACKUP_HOST', repo.env)
        self.assertNotIn('RESTIC_PASSWORD', repo.env)

    def test_old_rclone_is_rejected_before_ftp_connection(self):
        from router_backup import require_rclone
        def run(args, **kwargs): return subprocess.CompletedProcess(args, 0, 'rclone v1.53.3', '')
        with self.assertRaises(ValueError): require_rclone(run)

    def test_old_restic_short_summary_id_is_pinned_to_full_id(self):
        repo = RouterRepository(self.settings)
        source = self.root / 'source'
        source.write_bytes(b'fixture')
        with patch.object(repo, 'prepare'), patch.object(repo, 'call', side_effect=['[]', '{"message_type":"summary","snapshot_id":"aaaaaaaa"}']), \
                patch.object(repo, 'snapshots', return_value=[{'id': 'a' * 64}]):
            self.assertEqual(repo.backup([source]), 'a' * 64)

    def test_backup_failure_never_attempts_init(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1, '', 'not available')
        repo = RouterRepository(self.settings, run=run)
        with patch.object(repo, 'prepare'), self.assertRaises(RuntimeError):
            repo.backup([self.root])
        self.assertFalse(any('init' in command for command in calls))

    def test_retention_groups_dynamic_archive_paths_together(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, '', '')
        repo = RouterRepository(self.settings, run=run)
        with patch.object(repo, 'check'):
            repo.retention()
        self.assertIn('host,tags', calls[0])
        self.assertIn('homecontrol,router-hdd', calls[0])

    def test_router_transport_uses_the_live_verified_parallelism(self):
        repo = RouterRepository(self.settings)
        self.assertIn('rclone.connections=2', repo.command)
        options = next(arg for arg in repo.command if arg.startswith('rclone.args='))
        self.assertIn('--checkers 1 --transfers 1', options)

    def test_retention_requires_full_data_check_before_forgetting(self):
        repo = RouterRepository(self.settings)
        with patch.object(repo, 'check', side_effect=RuntimeError('Missing pack')), \
                patch.object(repo, 'call') as call:
            with self.assertRaises(RuntimeError):
                repo.retention()
            call.assert_not_called()

    def test_retention_checks_before_and_after_prune(self):
        repo = RouterRepository(self.settings)
        order = []
        with patch.object(repo, 'check', side_effect=lambda: order.append('full_check')), \
                patch.object(repo, 'call', side_effect=lambda args: order.append(args[0])):
            repo.retention()
        self.assertEqual(order, ['full_check', 'forget', 'full_check'])

    def test_retention_does_not_hide_failed_post_prune_verification(self):
        repo = RouterRepository(self.settings)
        with patch.object(repo, 'check', side_effect=[None, RuntimeError('Pack unreadable')]), \
                patch.object(repo, 'call') as call:
            with self.assertRaises(RuntimeError):
                repo.retention()
            call.assert_called_once()

    def test_staging_restore_rejects_nonempty_target_and_ambiguous_id(self):
        repo = RouterRepository(self.settings)
        with self.assertRaises(ValueError): repo.restore('latest', self.root)
        (self.root / 'existing').write_text('preserve')
        with self.assertRaises(ValueError): repo.restore('a' * 64, self.root)


class RouterWorkers(unittest.TestCase):
    """Real runner/locks/shell/archive/Git with synthetic external backup binaries."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hc-router-workers-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        (self.project / 'infra/backend').mkdir(parents=True)
        (self.project / 'scripts').mkdir()
        (self.project / 'scripts/access_release').mkdir()
        (self.project / 'scripts/access_release/backup_assets.py').write_text(
            "from pathlib import Path\nimport sys\n"
            "(Path(sys.argv[1])/'offline-image-fixture.bin').write_bytes(b'offline recovery fixture')\n")
        (self.project / 'apps').mkdir()
        (self.project / 'apps/config.txt').write_text('first version')
        for source in (BASE / 'infra/backend').glob('*.py'):
            shutil.copyfile(source, self.project / 'infra/backend' / source.name)
        atomic_json(self.project / 'infra/backend/deployment_policy.json', POLICY)
        names = ('backup_runner_impl.py', 'backup_archive_worker.sh', 'backup_weekly_worker.sh',
                 'backup_check_worker.sh', 'backup_config_sync_worker.sh', 'backup_offsite_worker.sh',
                 'backup_job_state.py', 'deployment_policy_cli.py', 'router_restic.py',
                 'backup_maintenance_worker.sh')
        for name in names:
            shutil.copyfile(BASE / 'scripts' / name, self.project / 'scripts' / name)
        (self.project / 'scripts/export_config_snapshot.py').write_text(
            "import pathlib,sys,shutil\nbase=pathlib.Path(__file__).parents[1]\n"
            "if '--secrets-manifest' in sys.argv: pathlib.Path(sys.argv[-1]).write_text('fixture')\n"
            "else: shutil.copyfile(base/'apps/config.txt',pathlib.Path(sys.argv[1])/'config.txt')\n")
        helper = self.project / 'scripts/create_secrets_bundle.sh'
        helper.write_text('#!/bin/sh\n[ -z "$HC_TEST_FAIL_SECRETS" ]\n'); helper.chmod(0o700)
        self.backups = self.root / 'backups'
        self.backups.mkdir()
        password = self.root / 'password'
        password.write_text('fixture-only'); password.chmod(0o600)
        config = self.root / 'rclone.conf'
        config.write_text('[routerbackup]\ntype=ftp\nhost=192.168.1.1\nuser=kshma\npass=fixture-only\n')
        config.chmod(0o600)
        self.remote = self.root / 'external.git'
        subprocess.run(['git', 'init', '--bare', str(self.remote)], check=True, capture_output=True)
        self.settings = {**BackupService.DEFAULT_SETTINGS, 'backup_target': 'router_ftp',
                         'restic_enabled': True, 'restic_required': True, 'router_rclone_config': str(config),
                         'restic_password_file': str(password), 'git_offsite_enabled': True,
                         'git_offsite_remote': str(self.remote)}
        for key in list(self.settings):
            if key.startswith('include_'): self.settings[key] = False
        self.settings['include_apps'] = True
        atomic_json(self.backups / 'backup_settings.json', self.settings)
        self.trace = self.root / 'trace'
        bin_dir = self.root / 'bin'; bin_dir.mkdir()
        fake = bin_dir / 'fake'
        fake.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name; args=sys.argv[1:]
with open(os.environ['HC_TEST_TRACE'],'a') as stream: stream.write(json.dumps([name]+args)+'\\n')
if name=='ssh': raise SystemExit(99)
if name=='rclone' and args==['version']:
 print('rclone v1.75.2'); raise SystemExit(0)
if name=='restic':
 if 'backup' in args:
  if os.environ.get('HC_TEST_FAIL_RESTIC'): raise SystemExit(1)
  print(json.dumps({'message_type':'summary','snapshot_id':'a'*64}))
 elif 'forget' in args and os.environ.get('HC_TEST_FAIL_RETENTION'): raise SystemExit(1)
 else: print('[]')
else: print('{}')
''')
        fake.chmod(0o700)
        for name in ('restic', 'rclone', 'docker', 'ssh'):
            (bin_dir / name).symlink_to(fake)
        self.env = {**os.environ, 'PATH': str(bin_dir) + ':' + os.environ['PATH'],
                    'HC_TEST_TRACE': str(self.trace), 'HC_PROJECT_ROOT': str(self.project),
                    'BACKUP_ROOT': str(self.backups), 'PYTHONDONTWRITEBYTECODE': '1'}

    def run_job(self, mode='weekly', **env):
        result = subprocess.run([sys.executable, str(self.project / 'scripts/backup_runner_impl.py'),
                                 '--root', str(self.backups), '--mode', mode], env={**self.env, **env},
                                text=True, capture_output=True, timeout=30)
        return result, read_json(self.backups / 'backup-state.json')

    def test_weekly_keeps_external_git_history_and_never_contacts_ai(self):
        result, state = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr + (self.backups / 'backup.log').read_text())
        for name in ('local_archive', 'restic', 'restic_retention', 'git_offsite'):
            self.assertEqual(state['targets'][name]['state'], 'succeeded')
        self.assertNotIn('gitea_dump', state['required_targets'])
        (self.project / 'apps/config.txt').write_text('second version')
        result, state = self.run_job()
        self.assertEqual(result.returncode, 0, (self.backups / 'backup.log').read_text())
        history = subprocess.run(['git', '--git-dir', str(self.remote), 'rev-list', '--count', 'main'],
                                 check=True, capture_output=True, text=True)
        self.assertEqual(history.stdout.strip(), '2')
        commands = [json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertFalse(any(row[0] == 'ssh' or '/api/ai/' in ' '.join(row) for row in commands))
        self.assertFalse((self.backups / 'ai-power-state.json').exists())

    def test_restic_failure_preserves_local_archive_and_previous_success(self):
        result, state = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        previous = read_json(self.backups / 'backup-targets.json')['restic']['last_success']
        result, state = self.run_job(HC_TEST_FAIL_RESTIC='1')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(state['targets']['local_archive']['state'], 'succeeded')
        self.assertEqual(state['targets']['restic']['state'], 'failed')
        self.assertEqual(read_json(self.backups / 'backup-targets.json')['restic']['last_success'], previous)
        self.assertEqual(len(list(self.backups.glob('*.tar.gz'))), 2)

    def test_retention_failure_does_not_erase_successful_snapshot(self):
        result, state = self.run_job(HC_TEST_FAIL_RETENTION='1')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(state['targets']['restic']['state'], 'succeeded')
        self.assertEqual(state['targets']['restic_retention']['state'], 'failed')

    def test_daily_retention_failure_is_reported_even_for_optional_remote(self):
        self.settings['restic_required'] = False
        atomic_json(self.backups / 'backup_settings.json', self.settings)
        result, state = self.run_job('local', HC_TEST_FAIL_RETENTION='1')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(state['targets']['local_archive']['state'], 'succeeded')
        self.assertEqual(state['targets']['restic']['state'], 'succeeded')
        self.assertEqual(state['targets']['restic_retention']['state'], 'failed')

    def test_failed_git_still_runs_local_and_router_backup(self):
        hook = self.remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n'); hook.chmod(0o700)
        result, state = self.run_job()
        self.assertEqual(result.returncode, 1)
        for name in ('local_archive', 'restic'):
            self.assertEqual(state['targets'][name]['state'], 'succeeded')
        self.assertEqual(state['targets']['git_offsite']['state'], 'failed')

    def test_failed_secret_bundle_is_visible_without_skipping_data_backups(self):
        result, state = self.run_job(HC_TEST_FAIL_SECRETS='1')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(state['targets']['secrets_bundle']['state'], 'failed')
        for name in ('local_archive', 'restic', 'git_offsite'):
            self.assertEqual(state['targets'][name]['state'], 'succeeded')

    def test_check_uses_full_data_read_and_common_lock(self):
        result, state = self.run_job('check')
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = [json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertTrue(any(row[0] == 'restic' and '--read-data' in row for row in commands))
        import fcntl
        with (self.backups / 'homecontrol-backup.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            blocked, _ = self.run_job('check')
            self.assertEqual(blocked.returncode, 75)

    def test_local_only_policy_keeps_local_recovery_assets_and_blocks_remotes(self):
        local = {key: value for key, value in POLICY.items() if key != 'backup_profile'}
        atomic_json(self.project / 'infra/backend/deployment_policy.json', local)
        result, state = self.run_job('local')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state['scope'], 'local_only')
        self.assertEqual(state['targets']['restic']['state'], 'skipped')
        import tarfile
        with tarfile.open(next(self.backups.glob('*.tar.gz'))) as archive:
            self.assertTrue(any(name.endswith('/offline-image-fixture.bin') for name in archive.getnames()))
        commands = [json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertFalse(any(row[0] in ('ssh', 'restic', 'rclone') for row in commands))


@unittest.skipUnless(os.environ.get('HC_ROUTER_FTP_TEST') == '1', 'Set HC_ROUTER_FTP_TEST=1 with pyftpdlib, restic and rclone')
class RealFTP(unittest.TestCase):
    @contextmanager
    def environment(self):
        from pyftpdlib.authorizers import DummyAuthorizer
        from pyftpdlib.handlers import FTPHandler
        from pyftpdlib.servers import FTPServer
        logging.getLogger('pyftpdlib').setLevel(logging.ERROR)
        with tempfile.TemporaryDirectory(prefix='hc-router-real-') as temporary:
            root = Path(temporary)
            disk = root / 'ftp/G'
            disk.mkdir(parents=True)
            authorizer = DummyAuthorizer()
            authorizer.add_user('test', 'fixture-password', str(root / 'ftp'), perm='elradfmwMT')
            class Handler(FTPHandler): pass
            Handler.authorizer = authorizer
            server = FTPServer(('127.0.0.1', 0), Handler)
            port = server.socket.getsockname()[1]
            thread = threading.Thread(target=server.serve_forever, kwargs={'timeout': 0.05}, daemon=True)
            thread.start()
            with patch.dict(os.environ, {'XDG_CACHE_HOME': str(root / 'cache')}):
                obscured = subprocess.run(['rclone', 'obscure', '-'], input='fixture-password', text=True,
                                          capture_output=True, check=True).stdout.strip()
                config = root / 'rclone.conf'
                config.write_text('[routerbackup]\ntype = ftp\nhost = 127.0.0.1\nuser = test\nport = {}\npass = {}\n'.format(port, obscured))
                config.chmod(0o600)
                password = root / 'password'
                password.write_text('fixture-restic-secret\n')
                password.chmod(0o600)
                settings = {**BackupService.DEFAULT_SETTINGS, 'backup_target': 'router_ftp',
                            'router_ftp_host': '127.0.0.1', 'router_ftp_user': 'test', 'router_ftp_port': port,
                            'router_rclone_config': str(config), 'restic_password_file': str(password),
                            'router_repository_path': '/G/hc-backup/probes/integration'}
                try:
                    yield root, disk, settings
                finally:
                    server.close_all()
                    thread.join(timeout=5)

    def test_real_encrypted_roundtrip_and_corruption(self):
        with self.environment() as (root, disk, settings):
            repo = RouterRepository(settings, cache=root / 'cache')
            repo.init()
            proof = repo.smoke()
            self.assertTrue(proof['ok'])
            self.assertEqual(len(proof['snapshot_id']), 64)
            # Emergency restore resolves credentials from a decrypted bundle root,
            # pins "latest" once, and writes only into an empty staging directory.
            secrets_root = root / 'decrypted'
            for key in ('router_rclone_config', 'restic_password_file'):
                original = Path(settings[key])
                relocated = secrets_root / original.relative_to('/')
                relocated.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, relocated)
                relocated.chmod(0o600)
            settings_file = root / 'router-settings.json'
            atomic_json(settings_file, settings)
            staging = root / 'emergency-restore'; staging.mkdir()
            restored = subprocess.run([sys.executable, str(BASE / 'scripts/router_restic.py'), 'restore',
                                       '--settings', str(settings_file), '--secrets-root', str(secrets_root),
                                       '--root', str(root / 'locks'), '--snapshot', 'latest', '--staging', str(staging)],
                                      capture_output=True, text=True, timeout=90)
            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertEqual(json.loads(restored.stdout)['snapshot_id'], proof['snapshot_id'])
            from hashlib import sha256
            payloads = list(staging.rglob('random.bin'))
            self.assertEqual(len(payloads), 1)
            self.assertEqual(sha256(payloads[0].read_bytes()).hexdigest(), proof['sha256'])
            repo.retention()
            with self.assertRaises(RuntimeError): repo.init()
            password = Path(settings['restic_password_file'])
            password.write_text('incorrect-password')
            with self.assertRaises(RuntimeError): repo.check()
            password.write_text('fixture-restic-secret\n')
            packs = list((disk / 'hc-backup/probes/integration/data').rglob('*'))
            pack = next(path for path in packs if path.is_file())
            data = pack.read_bytes()
            pack.write_bytes(bytes([data[0] ^ 1]) + data[1:])
            with self.assertRaises(RuntimeError): repo.check()

    def test_two_snapshot_retention_preserves_a_verified_latest_restore(self):
        with self.environment() as (root, disk, settings):
            from hashlib import sha256
            repo = RouterRepository(settings, cache=root / 'cache')
            repo.init()
            source = root / 'payload.bin'
            source.write_bytes(os.urandom(2 * 1024 * 1024))
            first = repo.backup([source])
            source.write_bytes(os.urandom(2 * 1024 * 1024))
            expected = sha256(source.read_bytes()).hexdigest()
            latest = repo.backup([source])
            repo.retention()
            retained = {row['id'] for row in repo.snapshots()}
            self.assertIn(latest, retained)
            self.assertNotIn(first, retained)
            staging = root / 'restore'; staging.mkdir()
            repo.restore(latest, staging)
            self.assertEqual(sha256((staging / source.relative_to('/')).read_bytes()).hexdigest(), expected)

    def test_missing_disk_and_config_mismatch_fail_before_init(self):
        with self.environment() as (root, disk, settings):
            repo = RouterRepository({**settings, 'router_ftp_user': 'other'}, cache=root / 'cache')
            with self.assertRaises(ValueError): repo.init()
            disk.rmdir()
            repo = RouterRepository(settings, cache=root / 'cache')
            with self.assertRaises(RuntimeError): repo.init()
            self.assertFalse(disk.exists())


if __name__ == '__main__':
    unittest.main()
