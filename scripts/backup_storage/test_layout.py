from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout
import migrate


class TreeCopyTest(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source'; target = root / 'target'; source.mkdir(); target.mkdir()
        (source / 'settings').mkdir(); (source / 'settings/private').write_bytes(b'fixture bytes')
        (source / 'settings/private').chmod(0o600)
        os.setxattr(source / 'settings/private', 'user.fixture', b'preserved')
        os.link(source / 'settings/private', source / 'settings/second')
        (source / 'link').symlink_to('settings/private')
        for name in layout.PINNED:
            if name in ('releases', 'ai-control'):
                (source / name).mkdir(); (source / name / 'not-copied').write_bytes(b'pinned')
            else: (source / name).touch()
        return source, target

    def test_real_rsync_preserves_content_modes_xattrs_links_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = self.fixture(Path(directory)); expected = layout.inventory(source)
            layout.copy_tree(source, target)
            self.assertTrue(layout.verify_copy(expected, target)['ok'])
            self.assertTrue(all(not (target / name).exists() for name in layout.PINNED))
            self.assertEqual((target / 'settings/private').stat().st_ino, (target / 'settings/second').stat().st_ino)
            self.assertEqual((target / 'settings/private').stat().st_mode & 0o777, 0o600)
            self.assertEqual(os.getxattr(target / 'settings/private', 'user.fixture'), b'preserved')

    def test_copy_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = self.fixture(Path(directory)); expected = layout.inventory(source)
            layout.copy_tree(source, target); (target / 'settings/private').write_bytes(b'corrupt')
            with self.assertRaises(layout.StorageError): layout.verify_copy(expected, target)

    def test_copied_permission_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = self.fixture(Path(directory)); expected = layout.inventory(source)
            layout.copy_tree(source, target); (target / 'settings/private').chmod(0o644)
            with self.assertRaises(layout.StorageError): layout.verify_copy(expected, target)

    def test_cleanup_preserves_pins_and_changed_target_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = self.fixture(Path(directory)); expected = layout.inventory(source)
            layout.copy_tree(source, target); (target / 'settings/private').write_bytes(b'new setting')
            result = layout.cleanup_verified_duplicates(source, target, expected)
            self.assertEqual(result['retained_changed_entries'], 2)
            self.assertTrue((source / 'settings/private').exists())
            self.assertFalse((source / 'link').exists())
            self.assertTrue(all((source / name).exists() for name in layout.PINNED))

    def test_changed_source_prevents_any_duplicate_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = self.fixture(Path(directory)); expected = layout.inventory(source)
            layout.copy_tree(source, target); (source / 'new').write_bytes(b'new')
            with self.assertRaises(layout.StorageError): layout.cleanup_verified_duplicates(source, target, expected)
            self.assertTrue((source / 'settings/private').exists())

    def test_special_file_is_not_silently_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory); os.mkfifo(source / 'fifo')
            with self.assertRaisesRegex(layout.StorageError, 'Special file'): layout.inventory(source)

    def test_held_common_lock_prevents_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'backups'; source.mkdir()
            for name in ('ai-backup.lock', 'homecontrol-backup.lock'): (source / name).touch()
            p = migrate.Paths(base=root)
            with ExitStack() as first:
                migrate.common_locks(p, first)
                with ExitStack() as second, self.assertRaises(BlockingIOError): migrate.common_locks(p, second)

    def test_missing_lock_is_never_recreated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'backups').mkdir()
            with ExitStack() as stack, self.assertRaises(layout.StorageError): migrate.common_locks(migrate.Paths(base=root), stack)
            self.assertFalse((root / 'backups/ai-backup.lock').exists())

    def test_units_order_mounts_before_docker_and_keep_existing_release_dropins(self):
        p = migrate.Paths(); units = migrate.unit_files(p)
        mounts = {name: text for name, text in units.items() if name.endswith('.mount')}
        self.assertEqual(len(mounts), 5)
        self.assertIn('srv-docker-homecontrol-backups-ai\\x2dcontrol.mount', mounts)
        for text in mounts.values(): self.assertIn('Before=docker.service homecontrol-hostops.service', text)
        self.assertNotIn('docker.service.d/hc-access.conf', units)
        self.assertIn('check --mounts-only', units['docker.service.d/hc-backup-storage.conf'])
        self.assertNotIn('--mounts-only', units['homecontrol-backup.service.d/hc-backup-storage.conf'])

    def test_symlinked_storage_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'link').symlink_to(root / 'missing')
            with self.assertRaises(layout.StorageError): layout.no_symlinks(root / 'link')


if __name__ == '__main__': unittest.main(verbosity=2)
