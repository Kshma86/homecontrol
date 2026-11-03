import errno
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('resume_r22_install_tested', Path(__file__).with_name('resume_r22_install.py'))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
spec = importlib.util.spec_from_file_location('install_cache_transfer_tested', Path(__file__).with_name('cache_transfer.py'))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))


class ResumeInstallTests(unittest.TestCase):
    def fixture(self, directory):
        base = Path(directory); kit = base / 'kit'
        core = SimpleNamespace(OLD='r18', RUNTIME=base / 'runtime', PRIVATE=base / 'private-runtime',
                               STATE=kit / 'private/transition', active=Mock(return_value=False), guard_runtime=Mock(),
                               platform=lambda: SimpleNamespace(no_symlinks=lambda path: None))
        for path in (core.RUNTIME, core.PRIVATE, kit / 'private/baseline-runner'): path.mkdir(parents=True)
        (core.RUNTIME / 'public.py').write_text('sealed runtime')
        manifest = {'source_sha256': {'public.py': r.digest(core.RUNTIME / 'public.py')}}
        stage = kit / 'private/runtime'
        for root in (stage, core.PRIVATE):
            (root / 'images').mkdir(parents=True)
            (root / 'images/manifest.json').write_text('same image metadata')
            (root / 'config').write_text('synthetic private fixture')
        (stage / 'images/access-images.tar.gz').write_bytes(b'synthetic image archive')
        write(core.STATE / 'result.json', {'state': 'rolled_back', 'success': True})
        write(core.STATE / 'transition.json', {'release': r.NAME})
        write(kit / 'deployment-status.json', {'phase': 'previous_release_restored'})
        error = {'error_type': 'Error', 'detail': repr([(str(stage / 'images/access-images.tar.gz'),
                str(core.PRIVATE / 'images/access-images.tar.gz'), '[Errno 18] Invalid cross-device link')])}
        write(kit / 'private/entry-error.json', error)
        proof = {'ok': True, 'release': core.OLD, 'run_id': r.RUN, 'archive_sha256': r.ARCHIVE_SHA256,
                 'restore': 'verified', 'database': 'verified', 'git': 'pushed'}
        write(kit / 'evidence/baseline-backup-restore.json', proof)
        job = {'run_id': r.RUN, 'state': 'completed', 'returncode': 0, 'archive': {'sha256': r.ARCHIVE_SHA256},
               'targets': {n: {'state': 'succeeded'} for n in ('local_archive', 'restic', 'git_offsite', 'secrets_bundle', 'restic_retention')}}
        write(base / 'backups/backup-state.json', job); write(base / 'backups/runs' / (r.RUN + '.json'), job)
        return base, kit, core, manifest, error, job

    def test_exact_single_cache_EXDEV_after_verified_rollback_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory)
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit): self.assertEqual(r.guard(core, manifest), error)
            core.guard_runtime.assert_called_once_with(manifest)

    def test_other_errno_target_or_error_type_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory)
            for change in ({'error_type': 'ValueError'}, {'detail': error['detail'].replace('[Errno 18]', '[Errno 13]')},
                           {'detail': error['detail'].replace('access-images.tar.gz', 'other-file')}, {'detail': '__import__("os").system("false")'}):
                with self.subTest(change=change), patch.object(r, 'KIT', kit), self.assertRaises(r.ResumeError):
                    r.guard_error({**error, **change}, core)

    def test_multiple_copy_failures_are_not_hidden_by_cache_workaround(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory)
            error['detail'] = repr([('a', 'b', '[Errno 18]'), ('c', 'd', '[Errno 13]')])
            with patch.object(r, 'KIT', kit), self.assertRaisesRegex(r.ResumeError, 'NOT_SINGLE_CACHE'):
                r.guard_error(error, core)

    def test_failed_or_missing_rollback_blocks_continuation(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory)
            write(core.STATE / 'result.json', {'state': 'failed', 'success': False})
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), self.assertRaisesRegex(r.ResumeError, 'ROLLBACK_RESULT'):
                r.guard(core, manifest)

    def test_newer_backup_run_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory)
            write(base / 'backups/backup-state.json', {**job, 'run_id': 'newer'})
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), self.assertRaisesRegex(r.ResumeError, 'BASELINE_RUN_CHANGED'):
                r.guard(core, manifest)

    def test_missing_restore_proof_or_failed_target_is_rejected(self):
        for what in ('restore', 'restic'):
            with self.subTest(what=what), tempfile.TemporaryDirectory() as directory:
                base, kit, core, manifest, error, job = self.fixture(directory)
                if what == 'restore':
                    proof = r.read(kit / 'evidence/baseline-backup-restore.json'); proof['database'] = 'not_run'
                    write(kit / 'evidence/baseline-backup-restore.json', proof)
                else:
                    job['targets']['restic']['state'] = 'failed'; write(base / 'backups/backup-state.json', job)
                with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), self.assertRaises(r.ResumeError): r.guard(core, manifest)

    def test_changed_runtime_or_unexpected_private_file_blocks_preservation(self):
        for what in ('runtime', 'private'):
            with self.subTest(what=what), tempfile.TemporaryDirectory() as directory:
                base, kit, core, manifest, error, job = self.fixture(directory)
                if what == 'runtime': (core.RUNTIME / 'public.py').write_text('changed')
                else: (core.PRIVATE / 'unexpected').write_text('unknown')
                with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), self.assertRaises(r.ResumeError): r.guard(core, manifest)

    def test_already_present_cache_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory)
            (core.PRIVATE / 'images/access-images.tar.gz').write_bytes(b'existing')
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), self.assertRaises(r.ResumeError): r.guard(core, manifest)

    def test_busy_supervisor_blocks_all_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory); core.active.return_value = True
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), self.assertRaisesRegex(r.ResumeError, 'SUPERVISOR_STILL_ACTIVE'):
                r.guard(core, manifest)

    def test_preservation_renames_every_tree_without_deleting_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory)
            with patch.object(r, 'KIT', kit): moves = r.preserve_failed_install(core, 'fixture')
            self.assertEqual(len(moves), 4)
            for row in moves:
                self.assertFalse(Path(row['original']).exists()); self.assertTrue(Path(row['preserved']).is_dir())
            self.assertEqual((Path(moves[0]['preserved']) / 'public.py').read_text(), 'sealed runtime')

    def test_existing_preservation_destination_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory)
            other = core.RUNTIME.with_name(core.RUNTIME.name + '-preserved-fixture'); other.mkdir()
            with patch.object(r, 'KIT', kit), self.assertRaisesRegex(r.ResumeError, 'PRESERVATION_DESTINATION'):
                r.preserve_failed_install(core, 'fixture')
            self.assertTrue((core.RUNTIME / 'public.py').is_file())

    def test_partial_preservation_error_restores_original_names(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory); original = r.exclusive_rename; count = 0
            def fail_second(before, after):
                nonlocal count
                count += 1
                if count == 2: raise PermissionError(errno.EACCES, 'Synthetic error')
                original(before, after)
            with patch.object(r, 'KIT', kit), patch.object(r, 'exclusive_rename', side_effect=fail_second), self.assertRaises(PermissionError):
                r.preserve_failed_install(core, 'fixture')
            self.assertTrue(core.RUNTIME.is_dir()); self.assertTrue(core.PRIVATE.is_dir()); self.assertTrue(core.STATE.is_dir())

    def test_atomic_rename_refuses_a_racing_existing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            before, after = Path(directory) / 'before', Path(directory) / 'after'; before.mkdir(); after.mkdir()
            with self.assertRaises(FileExistsError): r.exclusive_rename(before, after)
            self.assertTrue(before.is_dir()); self.assertTrue(after.is_dir())

    def test_nonroot_never_loads_any_release(self):
        with patch.object(r.os, 'geteuid', return_value=1000), patch.object(r, 'verify_sidecar') as verify:
            with self.assertRaisesRegex(r.ResumeError, 'LOCAL_SUDO_REQUIRED'): r.main()
        verify.assert_not_called()

    def test_real_copytree_error_shape_and_verified_copy_continuation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); kit = root / 'kit'; stage = kit / 'private/runtime'; private = root / 'private'
            (stage / 'images').mkdir(parents=True)
            source = stage / 'images/access-images.tar.gz'; source.write_bytes(b'synthetic cache'); source.chmod(0o600)
            (stage / 'config').write_text('synthetic secret')
            original = os.link
            def cross(a, b, *args, **kwargs):
                if Path(a) == source: raise OSError(errno.EXDEV, 'Invalid cross-device link', str(source))
                return original(a, b, *args, **kwargs)
            def original_copy(a, b):
                if Path(a) == source: os.link(a, b); return b
                return shutil.copy2(a, b)
            with patch.object(c.os, 'link', side_effect=cross):
                with self.assertRaises(shutil.Error) as raised: shutil.copytree(stage, private, copy_function=original_copy)
                with patch.object(r, 'KIT', kit):
                    r.guard_error({'error_type': 'Error', 'detail': str(raised.exception)}, SimpleNamespace(PRIVATE=private))
                private.rename(root / 'preserved-failed-private')
                def corrected_copy(a, b):
                    if Path(a) == source:
                        c.transfer_archive(a, b, c.sha(source), uid=os.geteuid()); return b
                    return shutil.copy2(a, b)
                shutil.copytree(stage, private, copy_function=corrected_copy)
            self.assertEqual(c.sha(private / 'images/access-images.tar.gz'), c.sha(source))
            self.assertEqual((private / 'config').read_text(), 'synthetic secret')
            self.assertFalse((root / 'preserved-failed-private/images/access-images.tar.gz').exists())

    def test_special_runtime_entry_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core, manifest, error, job = self.fixture(directory)
            os.mkfifo(core.RUNTIME / 'unexpected-fifo')
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), self.assertRaisesRegex(r.ResumeError, 'SPECIAL_FAILED_RUNTIME'):
                r.guard(core, manifest)


if __name__ == '__main__': unittest.main(verbosity=2)
