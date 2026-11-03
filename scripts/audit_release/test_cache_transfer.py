import errno
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cache_transfer_tested', Path(__file__).with_name('cache_transfer.py'))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class CacheTransferTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory); source = root / 'source'; target = root / 'target'
        source.write_bytes(os.urandom(1024 * 1024 + 7)); source.chmod(0o600)
        return source, target, c.sha(source)

    def cross_mount(self, source, target):
        original = os.link
        def link(a, b, *args, **kwargs):
            if Path(a) == source: raise OSError(errno.EXDEV, 'Invalid cross-device link')
            return original(a, b, *args, **kwargs)
        return patch.object(c.os, 'link', side_effect=link)

    def test_same_mount_keeps_existing_hardlink_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, expected = self.fixture(directory)
            result = c.transfer_archive(source, target, expected, uid=os.geteuid())
            self.assertEqual(result['method'], 'hardlink'); self.assertTrue(os.path.samefile(source, target))

    def test_only_EXDEV_falls_back_to_independent_verified_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, expected = self.fixture(directory); before = source.stat()
            with self.cross_mount(source, target): result = c.transfer_archive(source, target, expected, uid=os.geteuid())
            self.assertEqual(result['method'], 'verified_copy_after_EXDEV')
            self.assertEqual(c.sha(target), expected); self.assertFalse(os.path.samefile(source, target))
            after = target.stat()
            self.assertEqual((after.st_uid, after.st_gid, after.st_mode & 0o777, after.st_mtime_ns),
                             (before.st_uid, before.st_gid, before.st_mode & 0o777, before.st_mtime_ns))
            self.assertFalse(list(Path(directory).glob('.hc-image-copy-*')))

    def test_extended_attributes_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, expected = self.fixture(directory)
            os.setxattr(source, 'user.hc-test', b'synthetic cache metadata')
            with self.cross_mount(source, target): c.transfer_archive(source, target, expected, uid=os.geteuid())
            self.assertEqual(os.getxattr(target, 'user.hc-test'), b'synthetic cache metadata')

    def test_permission_error_is_not_treated_as_cross_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, expected = self.fixture(directory)
            with patch.object(c.os, 'link', side_effect=PermissionError(errno.EACCES, 'Denied')):
                with self.assertRaises(PermissionError): c.transfer_archive(source, target, expected, uid=os.geteuid())
            self.assertFalse(target.exists())

    def test_existing_target_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, expected = self.fixture(directory); target.write_bytes(b'existing')
            with self.assertRaisesRegex(ValueError, 'Existing'): c.transfer_archive(source, target, expected, uid=os.geteuid())
            self.assertEqual(target.read_bytes(), b'existing')

    def test_wrong_hash_prevents_all_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, expected = self.fixture(directory)
            with self.assertRaisesRegex(ValueError, 'checksum'): c.transfer_archive(source, target, '0' * 64, uid=os.geteuid())
            self.assertFalse(target.exists())

    def test_unsafe_mode_foreign_owner_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, expected = self.fixture(directory)
            source.chmod(0o666)
            with self.assertRaises(ValueError): c.transfer_archive(source, target, expected, uid=os.geteuid())
            source.chmod(0o600)
            with self.assertRaises(ValueError): c.transfer_archive(source, target, expected, uid=os.geteuid() + 1)
            link = Path(directory) / 'symlink'; link.symlink_to(source)
            with self.assertRaisesRegex(ValueError, 'Symlink'): c.transfer_archive(link, target, expected, uid=os.geteuid())

    def test_copy_write_failure_leaves_no_target_or_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, expected = self.fixture(directory)
            with self.cross_mount(source, target), patch.object(c.os, 'fchown', side_effect=OSError(errno.ENOSPC, 'No space left')):
                with self.assertRaises(OSError): c.transfer_archive(source, target, expected, uid=os.geteuid())
            self.assertFalse(target.exists()); self.assertFalse(list(Path(directory).glob('.hc-image-copy-*')))

    def test_concurrent_target_creation_wins_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, expected = self.fixture(directory); original = os.link
            def race(a, b, *args, **kwargs):
                if Path(a) == source: raise OSError(errno.EXDEV, 'Invalid cross-device link')
                target.write_bytes(b'concurrent owner')
                return original(a, b, *args, **kwargs)
            with patch.object(c.os, 'link', side_effect=race):
                with self.assertRaises(FileExistsError): c.transfer_archive(source, target, expected, uid=os.geteuid())
            self.assertEqual(target.read_bytes(), b'concurrent owner')
            self.assertFalse(list(Path(directory).glob('.hc-image-copy-*')))

    def test_source_change_before_publication_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, expected = self.fixture(directory); original = c.sha
            def changed(path):
                digest = original(path)
                if Path(path).name.startswith('.hc-image-copy-'): source.write_bytes(b'changed')
                return digest
            with self.cross_mount(source, target), patch.object(c, 'sha', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'changed'): c.transfer_archive(source, target, expected, uid=os.geteuid())
            self.assertFalse(target.exists())


if __name__ == '__main__': unittest.main(verbosity=2)
