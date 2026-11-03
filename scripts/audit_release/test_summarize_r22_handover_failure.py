import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('summary', Path(__file__).with_name('summarize_r22_handover_failure.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SummaryTests(unittest.TestCase):
    def test_known_final_conditions(self):
        for message in s.EXACT:
            self.assertEqual(s.classify({'error_type': 'ValueError', 'detail': message}, set())['condition'], message)

    def test_unit_and_container_names_must_be_sealed(self):
        for prefix in s.PREFIXES:
            with self.subTest(prefix=prefix):
                result = s.classify({'error_type': 'ValueError', 'detail': prefix + 'homecontrol-backup.timer'}, {'homecontrol-backup.timer'})
                self.assertTrue(result['recognized'])
                self.assertEqual(result['component'], 'homecontrol-backup.timer')

    def test_sensitive_and_multiline_text_is_never_echoed(self):
        for detail in ('ftp://user:SECRET@host/path',
                       'Backup unit changed: homecontrol-backup.timer\nSECRET',
                       'Unhealthy component: SECRET', {'secret': 'SECRET'}, None):
            result = s.classify({'error_type': 'SECRET', 'detail': detail}, {'homecontrol-backup.timer'})
            self.assertFalse(result['recognized'])
            self.assertNotIn('SECRET', str(result))

    def test_read_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); (p / 'real').write_text('{}'); (p / 'link').symlink_to(p / 'real')
            with self.assertRaises(ValueError): s.read(p / 'link')

    def test_read_rejects_large_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'large'
            with p.open('wb') as stream: stream.truncate(4 * 1024 ** 2 + 1)
            with self.assertRaises(ValueError): s.read(p)


if __name__ == '__main__': unittest.main()
