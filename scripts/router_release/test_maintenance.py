import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('router_maintenance', Path(__file__).with_name('maintenance.py'))
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


class MaintenanceTest(unittest.TestCase):
    def test_full_check_failure_prevents_retention(self):
        repo = Mock()
        repo.check.side_effect = RuntimeError('damaged')
        report = {'ok': False}
        with self.assertRaises(RuntimeError):
            maintenance.maintain(repo, report)
        repo.retention.assert_not_called()
        self.assertFalse(report['ok'])
        self.assertEqual(report['phase'], 'check_before_retention')

    def test_retention_failure_preserves_diagnostic_phase(self):
        repo = Mock()
        repo.retention.side_effect = RuntimeError('FTP failure')
        report = {'ok': False}
        with self.assertRaises(RuntimeError):
            maintenance.maintain(repo, report)
        self.assertEqual(repo.check.call_count, 1)
        self.assertEqual(report['check_before'], 'verified')
        self.assertEqual(report['phase'], 'retention')
        self.assertFalse(report['ok'])

    def test_rechecks_data_after_retention(self):
        repo = Mock()
        report = {'ok': False}
        maintenance.maintain(repo, report)
        self.assertEqual([call[0] for call in repo.mock_calls], ['check', 'retention', 'check'])
        self.assertTrue(report['ok'])

    def test_recheck_failure_is_not_success(self):
        repo = Mock()
        repo.check.side_effect = [None, RuntimeError('unreadable')]
        report = {'ok': False}
        with self.assertRaises(RuntimeError):
            maintenance.maintain(repo, report)
        self.assertEqual(report['retention'], 'verified')
        self.assertFalse(report['ok'])

    def test_redacts_real_and_obscured_passwords_and_urls(self):
        text = 'error ftp://user:unknown@router; secret obscured long-secret'
        safe = maintenance.redact(text, ['secret', 'long-secret', 'obscured', ''])
        self.assertNotIn('secret', safe)
        self.assertNotIn('obscured', safe)
        self.assertNotIn('unknown', safe)
        self.assertIn('router', safe)

    def test_requires_real_sudo(self):
        with patch.object(maintenance.os, 'geteuid', return_value=1000):
            with self.assertRaises(PermissionError):
                maintenance.main()


if __name__ == '__main__':
    unittest.main()
