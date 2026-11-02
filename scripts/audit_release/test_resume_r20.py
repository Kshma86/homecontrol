"""Fault injection for resuming the exact pre-cutover timeout, no live access."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('resume_r20_tested', Path(__file__).with_name('resume_r20.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def write(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class ResumeTest(unittest.TestCase):
    def fixture(self, directory):
        base = Path(directory)
        kit = base / 'release'
        side = base / 'continuation'
        (side / 'private').mkdir(parents=True)
        (kit / 'private').mkdir(parents=True)
        core = SimpleNamespace(BASE=base, KIT=kit, OLD_RUNTIME=base / 'old-runtime', OLD_PRIVATE=base / 'old-private',
                               RUNTIME=base / 'new-runtime', PRIVATE=Path('/srv/docker/homecontrol/infra/ssh/' + r.NAME),
                               STATE=kit / 'private/transition', guard_runtime=Mock(), idle=Mock())
        core.platform = lambda: SimpleNamespace(write_json=write, no_symlinks=lambda p: None)
        (base / 'backups').mkdir()
        for name in ('ai-backup.lock', 'homecontrol-backup.lock'):
            (base / 'backups' / name).touch()
        def locked(stack):
            for name in ('ai-backup.lock', 'homecontrol-backup.lock'):
                handle = stack.enter_context((base / 'backups' / name).open('a'))
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        core.locked = locked
        receipt = {'completed': True, 'run_id': r.RUN, 'name': r.ARCHIVE, 'mode': 'local',
                   'sha256': r.ARCHIVE_SHA256, 'timestamp': datetime.now(timezone.utc).isoformat(),
                   'size_bytes': 123, 'verified_files': 7,
                   'coverage': {'include_' + n: True for n in ('postgres', 'apps', 'infra', 'zigbee2mqtt', 'homeassistant', 'scripts', 'docker_meta')}}
        write(base / 'backups' / (r.ARCHIVE + '.complete.json'), receipt)
        job = {'state': 'running', 'run_id': r.RUN, 'mode': 'local', 'scope': 'router', 'pid': 99999999, 'archive': receipt,
               'targets': {'local_archive': {'state': 'succeeded'}, 'restic': {'state': 'succeeded'}}}
        write(base / 'backups/runs' / (r.RUN + '.json'), job)
        write(base / 'backups/backup-state.json', job)
        write(kit / 'deployment-status.json', {'phase': 'fresh_backup'})
        command = ['python3', str(core.OLD_RUNTIME / 'scripts/hostops/backup_runner.py'), '--mode', 'local']
        write(kit / 'private/audit-error.json', {'error_type': 'TimeoutExpired', 'detail': str(subprocess.TimeoutExpired(command, 900))})
        write(kit / 'private/progress.json', {'phase': 'fresh_backup'})
        return base, kit, side, core, receipt, job

    def test_nonroot_is_rejected_before_loading_any_release(self):
        with patch.object(r.os, 'geteuid', return_value=1000), patch.object(r, 'verify_sidecar') as verify:
            with self.assertRaisesRegex(r.ResumeError, 'LOCAL_SUDO'): r.main()
        verify.assert_not_called()

    def test_sidecar_source_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            source = side / 'source/resume_r20.py'
            source.parent.mkdir()
            source.write_text('original')
            write(side / 'acceptance.json', {'ok': True, 'sha256': {'source/resume_r20.py': r.digest(source)}})
            source.write_text('changed')
            with patch.object(r, 'SIDECAR', side):
                with self.assertRaisesRegex(r.ResumeError, 'CONTINUATION_CHANGED'): r.verify_sidecar()

    def test_only_exact_pre_cutover_timeout_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit): r.guard(core, {})
            core.guard_runtime.assert_called_once_with({})

    def test_different_failure_cannot_be_resumed(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            write(kit / 'private/audit-error.json', {'error_type': 'ValueError', 'detail': 'unrelated'})
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit):
                with self.assertRaisesRegex(r.ResumeError, 'UNEXPECTED_ORIGINAL'): r.guard(core, {})

    def test_existing_transition_blocks_continuation(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            core.STATE.mkdir()
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit):
                with self.assertRaisesRegex(r.ResumeError, 'TRANSITION_ALREADY'): r.guard(core, {})

    def test_existing_runtime_blocks_continuation(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            core.RUNTIME.mkdir()
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit):
                with self.assertRaisesRegex(r.ResumeError, 'CUTOVER_ALREADY'): r.guard(core, {})

    def test_old_or_incomplete_backup_is_never_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            with patch.object(r, 'BASE', base):
                for change, code in (({'timestamp': (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()}, 'OLDER_THAN'),
                                     ({'completed': False}, 'RECEIPT_MISMATCH'),
                                     ({'sha256': 'changed'}, 'RECEIPT_MISMATCH'),
                                     ({'coverage': {}}, 'COVERAGE_INCOMPLETE')):
                    with self.subTest(change=change):
                        write(base / 'backups' / (r.ARCHIVE + '.complete.json'), {**receipt, **change})
                        with self.assertRaisesRegex(r.ResumeError, code): r.archive_receipt()

    def test_dead_runner_is_marked_failed_and_original_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            with patch.object(r, 'BASE', base), patch.object(r, 'SIDECAR', side), patch.object(r.os, 'kill', side_effect=ProcessLookupError):
                r.recover_job(core)
            changed = r.read(base / 'backups/backup-state.json')
            self.assertEqual(changed['state'], 'failed')
            self.assertEqual(changed['returncode'], 124)
            self.assertEqual(changed['archive'], receipt)
            self.assertEqual(r.read(side / 'private/interrupted-run-original.json'), job)

    def test_live_runner_is_never_reclassified(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            with patch.object(r, 'BASE', base), patch.object(r, 'SIDECAR', side), patch.object(r.os, 'kill'):
                with self.assertRaisesRegex(r.ResumeError, 'PID_STILL_EXISTS'): r.recover_job(core)
            self.assertEqual(r.read(base / 'backups/backup-state.json'), job)

    def test_a_held_real_backup_lock_prevents_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            with (base / 'backups/homecontrol-backup.lock').open('rb') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(r, 'BASE', base), patch.object(r, 'SIDECAR', side):
                    with self.assertRaises(BlockingIOError): r.recover_job(core)
            self.assertEqual(r.read(base / 'backups/backup-state.json'), job)

    def test_a_newer_job_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            write(base / 'backups/backup-state.json', {'run_id': 'newer'})
            with patch.object(r, 'BASE', base), patch.object(r, 'SIDECAR', side):
                with self.assertRaisesRegex(r.ResumeError, 'BACKUP_STATE_CHANGED'): r.recover_job(core)

    def test_archive_is_fully_reverified_before_receipt_is_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            fake = SimpleNamespace(verify_archive=Mock(return_value={k: receipt[k] for k in ('sha256', 'size_bytes', 'verified_files')}))
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), patch.dict(sys.modules, {'backup_protocol': fake}), patch('builtins.print'):
                r.reuse_pre_backup(core)
            saved = r.read(kit / 'private/pre-backup.json')
            self.assertEqual(saved['sha256'], r.ARCHIVE_SHA256)
            self.assertIn('interrupted', saved['original_job_state'])
            fake.verify_archive.assert_called_once_with(base / 'backups' / r.ARCHIVE)

    def test_corrupt_archive_does_not_publish_pre_backup_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            fake = SimpleNamespace(verify_archive=Mock(side_effect=ValueError('corrupt')))
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), patch.dict(sys.modules, {'backup_protocol': fake}), patch('builtins.print'):
                with self.assertRaisesRegex(ValueError, 'corrupt'): r.reuse_pre_backup(core)
            self.assertFalse((kit / 'private/pre-backup.json').exists())

    def staging_fixture(self, directory):
        base, kit, side, core, receipt, job = self.fixture(directory)
        old = core.OLD_PRIVATE
        (old / 'compose-env').mkdir(parents=True)
        (old / 'mqtt').mkdir()
        (old / 'compose-env/backend.env').write_text('RUNTIME=' + str(core.OLD_RUNTIME) + '\nPRIVATE=' + str(old) + '\n')
        (old / 'mqtt/password').write_text('synthetic-password')
        write(old / 'network-policy.json', {'esp_ip': '192.168.1.179', 'esp_confirmed': True})
        root = kit / 'private/runtime'
        import shutil
        shutil.copytree(old, root)
        env = root / 'compose-env/backend.env'
        env.write_text(env.read_text().replace(str(core.OLD_RUNTIME), str(core.RUNTIME)).replace(str(old), str(core.PRIVATE)))
        (root / 'images').mkdir()
        (root / 'images/access-images.tar.gz').write_bytes(b'synthetic-images')
        manifest = {'offline_image_archive_sha256': r.digest(root / 'images/access-images.tar.gz'), 'recovery_images': ['sha256:fixture']}
        write(root / 'images/manifest.json', {'archive': 'access-images.tar.gz', 'sha256': manifest['offline_image_archive_sha256'], 'images': manifest['recovery_images']})
        encrypted = kit / 'private/homecontrol-secrets-r13.tar.gz.age'
        encrypted.write_bytes(b'synthetic-encrypted-bundle')
        write(kit / 'private/secret-receipt.json', {'roundtrip_verified': True, 'sha256': r.digest(encrypted), 'files': 3})
        def decoded(packed, target):
            for path in root.rglob('*'):
                if path.is_file() and not path.is_relative_to(root / 'images'):
                    dest = target / str(core.PRIVATE).lstrip('/') / path.relative_to(root)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(path.read_bytes())
            (target / 'SECRETS_BUNDLE_METADATA.txt').write_text('release=' + r.NAME + '\n')
        module = SimpleNamespace(secrets=decoded)
        core.call = Mock(return_value=SimpleNamespace(stdout=b'synthetic-packed-bundle'))
        return base, kit, side, core, manifest, root, module

    def test_staging_and_encrypted_bundle_must_match_current_private_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, manifest, root, module = self.staging_fixture(directory)
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), patch.object(r, 'SIDECAR', side), patch.dict(sys.modules, {'restore_archive': module}):
                r.staged_private(core, manifest)
            proof = r.read(side / 'private/staging-reverified.json')
            self.assertTrue(proof['encrypted_roundtrip'])
            self.assertEqual(core.call.call_args.args[0][-1], str(kit / 'private/homecontrol-secrets-r13.tar.gz.age'))

    def test_changed_staged_credential_is_rejected_before_decrypting(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, manifest, root, module = self.staging_fixture(directory)
            (root / 'mqtt/password').write_text('changed')
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), patch.object(r, 'SIDECAR', side):
                with self.assertRaisesRegex(r.ResumeError, 'PRIVATE_INPUTS_CHANGED'): r.staged_private(core, manifest)
            core.call.assert_not_called()

    def test_changed_staged_image_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, manifest, root, module = self.staging_fixture(directory)
            (root / 'images/access-images.tar.gz').write_bytes(b'changed')
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), patch.object(r, 'SIDECAR', side):
                with self.assertRaisesRegex(r.ResumeError, 'STAGED_IMAGES_CHANGED'): r.staged_private(core, manifest)

    def test_encrypted_bundle_cannot_claim_a_different_release(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, manifest, root, module = self.staging_fixture(directory)
            decode = module.secrets
            def wrong(packed, target):
                decode(packed, target)
                (target / 'SECRETS_BUNDLE_METADATA.txt').write_text('release=other\n')
            module.secrets = wrong
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), patch.object(r, 'SIDECAR', side), patch.dict(sys.modules, {'restore_archive': module}):
                with self.assertRaisesRegex(r.ResumeError, 'ENCRYPTED_RELEASE_CHANGED'): r.staged_private(core, manifest)

    def test_authenticated_bundle_must_contain_the_exact_staged_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, manifest, root, module = self.staging_fixture(directory)
            decode = module.secrets
            def wrong(packed, target):
                decode(packed, target)
                (target / str(core.PRIVATE).lstrip('/') / 'mqtt/password').write_text('different')
            module.secrets = wrong
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), patch.object(r, 'SIDECAR', side), patch.dict(sys.modules, {'restore_archive': module}):
                with self.assertRaisesRegex(r.ResumeError, 'ENCRYPTED_STAGING_MISMATCH'): r.staged_private(core, manifest)

    def test_a_later_phase_blocks_resume_even_with_the_original_timeout_error(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, side, core, receipt, job = self.fixture(directory)
            write(kit / 'deployment-status.json', {'phase': 'router_restore_proof'})
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit):
                with self.assertRaisesRegex(r.ResumeError, 'NOT_PRE_CUTOVER'): r.guard(core, {})
            core.guard_runtime.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
