"""Root-entrypoint transaction extensions in isolated fixture paths; no devices/network."""
import importlib.util
import json
import subprocess
import tarfile
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('router_activation', Path(__file__).with_name('activate.py'))
activate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activate)
core = activate.core


class Platform:
    @staticmethod
    def no_symlinks(path):
        if Path(path).is_symlink():
            raise ValueError('Unexpected symlink')

    @staticmethod
    def write_json(path, value, mode=0o600):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value)); path.chmod(mode)


class RouterActivationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / 'base'; self.base.mkdir()
        self.kit = Path(self.temp.name) / 'kit'; (self.kit / 'private').mkdir(parents=True)
        self.settings = {**activate.DEFAULTS, 'backup_target': 'router_ftp',
                         'restic_password_file': '/etc/homecontrol/router-restic-password',
                         'git_enabled': True, 'git_offsite_enabled': True,
                         'git_offsite_remote': 'git@example.test:config.git', 'git_offsite_branch': 'main',
                         'git_offsite_ssh_key': '/private/git-key', 'git_offsite_token_file': '/private/token',
                         'restic_required': False, 'schedule_time': '02:15', 'schedule_enabled': True}
        (self.base / 'backups').mkdir(); (self.base / 'secrets').mkdir(); (self.base / 'docs').mkdir()
        (self.base / 'backups/backup_settings.json').write_text(json.dumps(self.settings))
        (self.base / 'secrets/manifest.txt').write_text('/existing/secret\n')

    def test_requires_real_sudo_before_any_operation(self):
        with patch.object(activate.os, 'geteuid', return_value=1000), patch.object(core, 'verify') as verify:
            with self.assertRaises(PermissionError): activate.main()
            verify.assert_not_called()

    def test_candidate_preserves_git_schedule_and_daily_preference(self):
        probe = {**self.settings, 'git_enabled': False, 'git_offsite_enabled': False,
                 'router_repository_path': '/G/hc-backup/probes/router-r14'}
        with patch.object(activate, 'BASE', self.base), patch.object(activate, 'KIT', self.kit), \
                patch.object(core, 'platform', return_value=Platform):
            candidate = activate.candidate_settings(probe)
        for key in ('git_enabled', 'git_offsite_enabled', 'git_offsite_remote', 'git_offsite_branch',
                    'git_offsite_ssh_key', 'schedule_time', 'schedule_enabled', 'restic_required'):
            self.assertEqual(candidate[key], self.settings[key])
        self.assertFalse(candidate['git_origin_enabled'])
        self.assertFalse(candidate['ai_weekly_shutdown_after'])
        self.assertEqual(candidate['router_repository_path'], '/G/hc-backup/restic/homecontrol')

    def test_hooks_snapshot_settings_timer_files_and_enablement_links(self):
        with patch.object(activate, 'BASE', self.base), patch.object(activate, 'KIT', self.kit), \
                patch.object(core, 'UNIT_ROOT', self.base / 'units'), \
                patch.object(core, 'target_files', return_value=[]), patch.object(core, 'install_files'), \
                patch.object(core.Cutover, 'verify'), patch.object(core.Cutover, 'resume'):
            activate.install_hooks(self.settings)
            files = core.target_files()
        self.assertIn(self.base / 'backups/backup_settings.json', files)
        self.assertIn(self.base / 'docs/router-backup-settings.json', files)
        for name in activate.TIMER_NAMES:
            self.assertIn(self.base / 'units' / name, files)
            self.assertIn(self.base / 'units/timers.target.wants' / name, files)

    def test_install_keeps_credentials_private_and_exports_only_public_recovery_settings(self):
        candidate_file = self.kit / 'private/router-settings.json'
        candidate_file.write_text(json.dumps(self.settings))
        with patch.object(activate, 'BASE', self.base), patch.object(activate, 'KIT', self.kit), \
                patch.object(core, 'platform', return_value=Platform), \
                patch.object(core, 'target_files', return_value=[]), patch.object(core, 'install_files') as original, \
                patch.object(core.Cutover, 'verify'), patch.object(core.Cutover, 'resume'):
            activate.install_hooks(self.settings)
            core.install_files({})
            original.assert_called_once_with({})
        self.assertEqual((self.base / 'backups/backup_settings.json').stat().st_mode & 0o777, 0o600)
        public = json.loads((self.base / 'docs/router-backup-settings.json').read_text())
        self.assertNotIn('pass', public)
        self.assertNotIn('git_offsite_remote', public)
        self.assertIn('/etc/homecontrol/router-rclone.conf', (self.base / 'secrets/manifest.txt').read_text())

    def test_watchers_wait_until_backup_and_restore_proofs_complete(self):
        with patch.object(activate, 'KIT', self.kit), patch.object(core, 'platform', return_value=Platform), \
                patch.object(core, 'target_files', return_value=[]), patch.object(core, 'install_files'), \
                patch.object(core.Cutover, 'verify') as verified, patch.object(core.Cutover, 'resume') as resumed:
            pending = activate.install_hooks(self.settings)
            context = object()
            core.Cutover.verify(context)
            verified.assert_called_once_with(context)
            self.assertTrue(pending.exists())
            core.Cutover.resume(context)
            resumed.assert_not_called()
            pending.unlink()
            core.Cutover.resume(context)
            resumed.assert_called_once_with(context)

    def test_post_cutover_backup_failure_automatically_rolls_back(self):
        with patch.object(activate, 'KIT', self.kit), patch.object(core, 'STATE', self.kit / 'private/no-transition'), \
                patch.object(activate.os, 'geteuid', return_value=0), patch.object(core, 'platform', return_value=Platform), \
                patch.object(core, 'verify', return_value={}), patch.object(core, 'guard_runtime'), \
                patch.object(activate, 'prepare_tools'), patch.object(activate, 'probe_settings', return_value={}), \
                patch.object(activate, 'ensure_repository', return_value=SimpleNamespace(smoke=lambda: {'ok': True})), \
                patch.object(activate, 'candidate_settings', return_value={}), \
                patch.object(activate, 'install_hooks', return_value=self.kit / 'private/pending'), \
                patch.object(core, 'deploy'), patch.object(activate, 'full_proof', side_effect=RuntimeError('fixture failure')), \
                patch.object(core, 'rollback') as rollback:
            with self.assertRaises(RuntimeError): activate.main()
            rollback.assert_called_once_with({})

    def test_core_call_can_pass_a_pinned_restore_image_without_duplicate_env(self):
        result = core.call([sys.executable, '-c', 'import os;print(os.environ["HC_RESTORE_POSTGRES_IMAGE"])'],
                           extra_env={'HC_RESTORE_POSTGRES_IMAGE': 'fixture-pinned-image'})
        self.assertEqual(result.stdout.strip(), b'fixture-pinned-image')

    def test_encrypted_recovery_bundle_contains_router_credentials_and_candidate_settings(self):
        sys.path.insert(0, str(activate.SOURCE / 'scripts'))
        from restore_archive import secrets as extract
        common = core.platform()
        identity = self.base / 'infra/ssh/age-key.txt'; identity.parent.mkdir(parents=True)
        subprocess.run(['age-keygen', '-o', str(identity)], check=True, capture_output=True)
        recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
        (self.base / 'secrets/age-recipient.txt').write_text(recipient)
        # The production key name is fixed; keep only synthetic fixture bytes here.
        identity.rename(self.base / 'infra/ssh/homecontrol-secrets-age-key.txt')
        identity = self.base / 'infra/ssh/homecontrol-secrets-age-key.txt'
        empty = self.kit / 'empty'; empty.mkdir()
        (empty / 'SECRETS_BUNDLE_CONTENTS.txt').write_text('fixture\n')
        packed = self.kit / 'old.tar.gz'
        with tarfile.open(packed, 'w:gz') as archive: archive.add(empty, arcname='.')
        subprocess.run(['age', '-r', recipient, '-o', str(self.base / 'secrets/homecontrol-secrets-latest.tar.gz.age'), str(packed)], check=True, capture_output=True)
        config = self.base / 'infra/ssh/router-rclone.conf'; config.write_text('synthetic-ftp-credential')
        password = self.base / 'infra/ssh/router-restic-password'; password.write_text('synthetic-restic-password')
        settings = {**self.settings, 'router_rclone_config': str(config), 'restic_password_file': str(password)}
        runtime = self.kit / 'private/runtime'; (runtime / 'images').mkdir(parents=True)
        with patch.object(core, 'BASE', self.base), patch.object(core, 'KIT', self.kit), \
                patch.object(core, 'PRIVATE', self.base / 'infra/ssh' / activate.NAME), \
                patch.object(core, 'ROUTER_SETTINGS', settings, create=True), patch.object(core, 'platform', return_value=common):
            core.encrypted_bundle(runtime)
        output = self.kit / 'private/homecontrol-secrets-r13.tar.gz.age'
        decoded = self.kit / 'decoded.tar.gz'
        decoded.write_bytes(subprocess.check_output(['age', '-d', '-i', str(identity), str(output)]))
        restored = self.kit / 'decoded'; extract(decoded, restored)
        canonical = restored / 'srv/docker/homecontrol'
        self.assertEqual((canonical / 'infra/ssh/router-rclone.conf').read_text(), 'synthetic-ftp-credential')
        self.assertEqual((canonical / 'infra/ssh/router-restic-password').read_text(), 'synthetic-restic-password')
        self.assertEqual(json.loads((canonical / 'backups/backup_settings.json').read_text()), settings)

    def test_timers_are_enabled_only_after_proof_and_use_same_units(self):
        units_root = self.base / 'units'; units_root.mkdir()
        state = self.kit / 'private/transition'; state.mkdir()
        previous = {name: name == 'homecontrol-backup.timer' for name in activate.TIMER_NAMES}
        (state / 'transition.json').write_text(json.dumps({'active_timers': previous}))
        pending = self.kit / 'private/pending'; pending.write_text('{}')
        units = {name: '[Timer]\nOnCalendar=Sun 03:30:00\n' for name in activate.TIMER_NAMES}
        module = SimpleNamespace(schedule_units=lambda *_: (units, {name: True for name in units}), unit_sources=lambda: units)
        with patch.dict(sys.modules, {'install_backup_f6': module}), patch.object(core, 'STATE', state), \
                patch.object(core, 'UNIT_ROOT', units_root), patch.object(core, 'platform', return_value=Platform), \
                patch.object(core, 'active', return_value=True), patch.object(core, 'call') as call:
            activate.resume_timers(self.settings, pending)
        self.assertFalse(pending.exists())
        for name in activate.TIMER_NAMES:
            self.assertIn(unittest.mock.call(['systemctl', 'enable', name]), call.call_args_list)
            self.assertIn(unittest.mock.call(['systemctl', 'start', name]), call.call_args_list)


if __name__ == '__main__':
    unittest.main(verbosity=2)
