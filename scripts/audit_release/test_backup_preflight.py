import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import sys

spec = importlib.util.spec_from_file_location('backup_preflight_tested', Path(__file__).with_name('backup_preflight.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def write(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class BackupPreflightTest(unittest.TestCase):
    def core(self, base):
        return SimpleNamespace(BASE=base, KIT=base / 'kit', OLD='old', OLD_RUNTIME=base / 'old-runtime',
            platform=lambda: SimpleNamespace(write_json=write, no_symlinks=lambda path: None),
            locked=Mock(), idle=Mock(), phase=Mock())

    def test_space_failure_prevents_any_new_backup(self):
        with tempfile.TemporaryDirectory() as d:
            core = self.core(Path(d))
            cache = SimpleNamespace(deduplicate=Mock(return_value={'ok': True}), paths=lambda base: [])
            supervision = SimpleNamespace(install=Mock())
            with patch.object(p.os, 'geteuid', return_value=0), patch.dict(sys.modules, {'image_cache': cache, 'backup_supervision': supervision}), patch.object(p.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), patch('builtins.print'):
                with self.assertRaisesRegex(ValueError, 'Insufficient space'): p.prepare(core, {'offline_image_archive_sha256': 'sha'})
            supervision.install.assert_not_called()

    def test_shadow_runner_preserves_the_current_release_recovery_namespace(self):
        with tempfile.TemporaryDirectory() as d:
            core = self.core(Path(d))
            core.OLD_RUNTIME.mkdir(); (core.OLD_RUNTIME / 'identity.py').write_text("NAME='old'\nPRIVATE='old-private'\n")
            (core.OLD_RUNTIME / 'scripts').mkdir()
            for name in ('router_restic.py', 'router_operation_log.py'):
                path = core.KIT / 'source/scripts' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('reviewed logging overlay')
            digest = hashlib.sha256((core.OLD_RUNTIME / 'identity.py').read_bytes()).hexdigest()
            write(core.BASE / 'backups/releases/old/release.json', {'source_sha256': {'identity.py': digest}})
            core.digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            root = p.baseline_runner(core)
            self.assertEqual((root / 'identity.py').read_bytes(), (core.OLD_RUNTIME / 'identity.py').read_bytes())
            self.assertFalse((core.OLD_RUNTIME / 'scripts/router_operation_log.py').exists())
            self.assertEqual((root / 'scripts/router_restic.py').read_text(), 'reviewed logging overlay')

    def proof_fixture(self, directory, git='succeeded', restore_sha='archive-sha'):
        base = Path(directory); core = self.core(base); shadow = base / 'shadow'
        write(base / 'backups/backup-state.json', {'run_id': 'before'})
        receipt = {'completed': True, 'name': 'archive.tar.gz', 'sha256': 'archive-sha'}
        job = {'run_id': 'after', 'state': 'completed', 'mode': 'weekly', 'scope': 'router', 'archive': receipt,
               'targets': {n: {'state': 'succeeded'} for n in ('local_archive', 'restic', 'secrets_bundle', 'git_offsite')}}
        job['targets']['git_offsite']['state'] = git
        def supervised(call, args): write(base / 'backups/backup-state.json', job)
        module = SimpleNamespace(supervised_call=Mock(side_effect=supervised))
        checked = {'sha256': 'archive-sha', 'verified_files': 7, 'size_bytes': 123}
        backup = SimpleNamespace(verify_archive=Mock(return_value=checked))
        def restore(args, **kwargs):
            write(base / 'backups/restore-smoke-result.json', {'ok': True, 'restic': 'sha256_verified',
                'database': 'restore_verified_without_owner_acl', 'restic_archive': {'sha256': restore_sha}, 'snapshot_id': 'snapshot'})
        core.call = Mock(side_effect=restore)
        return core, shadow, module, backup

    def test_full_git_router_and_pg_restore_are_required_before_pre_backup_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            core, shadow, module, backup = self.proof_fixture(d)
            with patch.object(p, 'baseline_runner', return_value=shadow), patch.dict(sys.modules, {'backup_supervision': module, 'backup_protocol': backup}), patch('builtins.print'):
                p.prove_current_backup(core, {'baseline': {'homecontrol-postgres': {'image': 'pinned-postgres'}}})
            proof = json.loads((core.KIT / 'evidence/baseline-backup-restore.json').read_text())
            self.assertEqual(proof['release'], 'old'); self.assertTrue(proof['platform_still_running'])
            self.assertEqual(module.supervised_call.call_args.args[1][1], str(shadow / 'scripts/hostops/backup_runner.py'))
            self.assertTrue((core.KIT / 'private/pre-backup.json').exists())
            self.assertEqual(core.call.call_args.kwargs['extra_env']['HC_RESTORE_POSTGRES_IMAGE'], 'pinned-postgres')

    def test_failed_git_prevents_any_restore_or_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            core, shadow, module, backup = self.proof_fixture(d, git='failed')
            with patch.object(p, 'baseline_runner', return_value=shadow), patch.dict(sys.modules, {'backup_supervision': module, 'backup_protocol': backup}), patch('builtins.print'):
                with self.assertRaisesRegex(ValueError, 'git_offsite'): p.prove_current_backup(core, {})
            core.call.assert_not_called(); self.assertFalse((core.KIT / 'private/pre-backup.json').exists())

    def test_a_different_restored_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            core, shadow, module, backup = self.proof_fixture(d, restore_sha='different-archive')
            with patch.object(p, 'baseline_runner', return_value=shadow), patch.dict(sys.modules, {'backup_supervision': module, 'backup_protocol': backup}), patch('builtins.print'):
                with self.assertRaisesRegex(ValueError, 'restore proof failed'): p.prove_current_backup(core, {'baseline': {'homecontrol-postgres': {'image': 'pinned'}}})
            self.assertFalse((core.KIT / 'evidence/baseline-backup-restore.json').exists())


if __name__ == '__main__': unittest.main(verbosity=2)
