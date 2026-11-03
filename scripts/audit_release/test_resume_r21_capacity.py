import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('r21_capacity_continuation_tested', Path(__file__).with_name('resume_r21_capacity.py'))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))


class CapacityContinuationTest(unittest.TestCase):
    def test_exact_original_space_threshold_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); size = 2814297607; required = size * 2 + 2 * 1024 ** 3
            write(base / 'backups/homecontrol_fixture.tar.gz.complete.json', {'completed': True, 'size_bytes': size})
            with patch.object(r, 'BASE', base), patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=required)), patch('builtins.print'):
                proof = r.capacity()
            self.assertEqual(proof['required_bytes'], required); self.assertEqual(proof['reserve_bytes'], 2 * 1024 ** 3)

    def test_one_byte_below_capacity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); required = 8 * 1024 ** 3
            with patch.object(r, 'BASE', base), patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=required - 1)), patch('builtins.print'):
                with self.assertRaisesRegex(r.ResumeError, 'INSUFFICIENT_SPACE'): r.capacity()

    def test_incomplete_receipt_is_not_counted_as_completed_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            write(base / 'backups/homecontrol_1.tar.gz.complete.json', {'completed': True, 'size_bytes': 100})
            write(base / 'backups/homecontrol_2.tar.gz.complete.json', {'completed': False, 'size_bytes': 10000000000})
            with patch.object(r, 'BASE', base), patch.object(r.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 ** 12)), patch('builtins.print'):
                self.assertEqual(r.capacity()['required_bytes'], 200 + 2 * 1024 ** 3)

    def test_invalid_completed_archive_size_is_rejected(self):
        for size in (True, 0, -1, '100'):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as directory:
                base = Path(directory); write(base / 'backups/homecontrol_1.tar.gz.complete.json', {'completed': True, 'size_bytes': size})
                with patch.object(r, 'BASE', base), self.assertRaisesRegex(r.ResumeError, 'INVALID_ARCHIVE_SIZE'): r.capacity()

    def test_new_lock_blocks_continuation_without_any_unlock(self):
        adapter = SimpleNamespace(lock_ids=Mock(return_value=['a' * 64])); repo = SimpleNamespace(call=Mock())
        with self.assertRaisesRegex(r.ResumeError, 'NEW_REPOSITORY_LOCK_EXISTS'): r.ensure_unlocked(adapter, repo)
        repo.call.assert_not_called()

    def test_empty_inventory_never_repeats_unlock(self):
        adapter = SimpleNamespace(lock_ids=Mock(return_value=[])); repo = SimpleNamespace(call=Mock())
        proof = r.ensure_unlocked(adapter, repo)
        self.assertFalse(proof['native_unlock_attempted']); repo.call.assert_not_called()

    def fixture(self, directory, error=None):
        root = Path(directory)
        write(root / 'evidence/lock-recovery.json', {'ok': True, 'locks_after': 0, 'force_used': False})
        write(root / 'private/continuation-error.json', r.CAPACITY_ERROR if error is None else error)
        write(root / 'acceptance.json', {'ok': True, 'sha256': {}})
        return root

    def test_only_exact_previous_capacity_error_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            with patch.object(r, 'PRIOR', root), patch.object(r, 'PRIOR_ACCEPTANCE_SHA256', r.digest(root / 'acceptance.json')), patch.object(r, 'PRIOR_LOCK_PROOF_SHA256', r.digest(root / 'evidence/lock-recovery.json')): r.guard_previous()

    def test_other_previous_error_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, {'error_type': 'ValueError', 'detail': 'different failure'})
            with patch.object(r, 'PRIOR', root), patch.object(r, 'PRIOR_ACCEPTANCE_SHA256', r.digest(root / 'acceptance.json')), patch.object(r, 'PRIOR_LOCK_PROOF_SHA256', r.digest(root / 'evidence/lock-recovery.json')):
                with self.assertRaisesRegex(r.ResumeError, 'CAPACITY_ONLY'): r.guard_previous()

    def test_changed_previous_lock_proof_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            with patch.object(r, 'PRIOR', root), patch.object(r, 'PRIOR_ACCEPTANCE_SHA256', r.digest(root / 'acceptance.json')), patch.object(r, 'PRIOR_LOCK_PROOF_SHA256', 'changed'):
                with self.assertRaisesRegex(r.ResumeError, 'LOCK_RECOVERY_PROOF_CHANGED'): r.guard_previous()

    def test_nonroot_never_reads_private_error_or_starts_recovery(self):
        with patch.object(r.os, 'geteuid', return_value=1000), patch.object(r, 'verify_package') as verify:
            with self.assertRaisesRegex(r.ResumeError, 'LOCAL_SUDO'): r.main()
        verify.assert_not_called()


if __name__ == '__main__': unittest.main(verbosity=2)
