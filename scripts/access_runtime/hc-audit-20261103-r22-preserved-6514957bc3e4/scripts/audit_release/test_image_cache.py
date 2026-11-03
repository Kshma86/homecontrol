import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('image_cache_tested', Path(__file__).with_name('image_cache.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class ImageCacheTest(unittest.TestCase):
    def fixture(self, root):
        rows = [Path(root) / str(n) for n in range(4)]
        for path in rows:
            path.write_bytes(b'immutable synthetic image archive')
            path.chmod(0o600)
        return rows, hashlib.sha256(rows[0].read_bytes()).hexdigest()

    def test_all_bytes_and_modes_are_preserved_while_duplicate_blocks_are_shared(self):
        with tempfile.TemporaryDirectory() as root:
            rows, digest = self.fixture(root)
            before = [(p.read_bytes(), p.stat().st_mode, p.stat().st_uid, p.stat().st_gid) for p in rows]
            result = c.deduplicate(rows, digest, apply=True, uid=os.geteuid())
            self.assertEqual(result['previous_unique_inodes'], 4)
            self.assertEqual(len({p.stat().st_ino for p in rows}), 1)
            self.assertEqual([(p.read_bytes(), p.stat().st_mode, p.stat().st_uid, p.stat().st_gid) for p in rows], before)

    def test_bad_last_archive_prevents_all_replacements(self):
        with tempfile.TemporaryDirectory() as root:
            rows, digest = self.fixture(root)
            rows[-1].write_bytes(b'changed')
            before = [p.stat().st_ino for p in rows]
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                c.deduplicate(rows, digest, apply=True, uid=os.geteuid())
            self.assertEqual([p.stat().st_ino for p in rows], before)

    def test_read_only_plan_preserves_all_inode_identities(self):
        with tempfile.TemporaryDirectory() as root:
            rows, digest = self.fixture(root)
            before = [p.stat().st_ino for p in rows]
            result = c.deduplicate(rows, digest, uid=os.geteuid())
            self.assertFalse(result['applied'])
            self.assertEqual([p.stat().st_ino for p in rows], before)

    def test_different_modes_are_not_silently_changed(self):
        with tempfile.TemporaryDirectory() as root:
            rows, digest = self.fixture(root)
            rows[-1].chmod(0o400)
            with self.assertRaisesRegex(ValueError, 'different ownership'):
                c.deduplicate(rows, digest, apply=True, uid=os.geteuid())

    def test_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            rows, digest = self.fixture(root)
            link = Path(root) / 'symlink'
            link.symlink_to(rows[0])
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                c.deduplicate([link, rows[1]], digest, apply=True, uid=os.geteuid())

    def test_a_repeated_deduplication_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            rows, digest = self.fixture(root)
            c.deduplicate(rows, digest, apply=True, uid=os.geteuid())
            self.assertEqual(c.deduplicate(rows, digest, apply=True, uid=os.geteuid())['replacements'], 0)

    def test_new_release_link_reuses_immutable_data_without_overwriting(self):
        with tempfile.TemporaryDirectory() as root:
            rows, digest = self.fixture(root)
            target = Path(root) / 'next-cache'
            c.link_archive(rows[0], target, digest, uid=os.geteuid())
            self.assertEqual(target.stat().st_ino, rows[0].stat().st_ino)
            with self.assertRaisesRegex(ValueError, 'Existing cache'):
                c.link_archive(rows[0], target, digest, uid=os.geteuid())


if __name__ == '__main__':
    unittest.main(verbosity=2)
