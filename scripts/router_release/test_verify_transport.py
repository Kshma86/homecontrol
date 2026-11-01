import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location('router_transport', Path(__file__).with_name('verify_transport.py'))
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


class TransportTest(unittest.TestCase):
    def repo(self):
        repo = Mock()
        repo.command = ['restic', '-o', 'rclone.args=serve restic --stdio']
        return repo

    def test_command_keeps_remote_read_only_and_limits_parallelism(self):
        original = self.repo().command
        result = transport.command(original, True)
        self.assertIn('--no-lock', result)
        self.assertIn('rclone.connections=2', result)
        self.assertTrue(any('--checkers 1 --transfers 1' in value for value in result))
        self.assertNotIn('--no-lock', original)

    def test_deployed_missing_list_continues_to_serialized_full_check(self):
        repo = self.repo()
        pack = 'a' * 64
        repo.call.side_effect = ['', pack + '\n', 'all data read']
        report = {}
        transport.compare(repo, {pack}, report)
        self.assertEqual(report['deployed']['missing_pack_count'], 1)
        self.assertEqual(report['serialized']['check'], 'full_data_verified')
        self.assertEqual([call.args[0] for call in repo.call.call_args_list],
                         [['list', 'packs'], ['list', 'packs'], ['check', '--read-data']])

    def test_deployed_metadata_failure_does_not_prevent_independent_read_proof(self):
        repo = self.repo()
        pack = 'a' * 64
        repo.call.side_effect = [pack, RuntimeError('original check failed'), pack, 'full data read']
        report = {}
        transport.compare(repo, {pack}, report)
        self.assertEqual(report['deployed']['error_type'], 'RuntimeError')
        self.assertTrue(report['serialized_verified'])

    def test_serialized_inventory_mismatch_prevents_full_check(self):
        repo = self.repo()
        repo.call.side_effect = ['', '']
        report = {}
        with self.assertRaises(ValueError):
            transport.compare(repo, {'a' * 64}, report)
        self.assertEqual(repo.call.call_count, 2)
        self.assertNotIn('serialized_verified', report)

    def test_serialized_read_error_is_never_reported_as_verified(self):
        repo = self.repo()
        pack = 'a' * 64
        repo.call.side_effect = ['', pack, RuntimeError('pack unreadable')]
        report = {}
        with self.assertRaises(RuntimeError):
            transport.compare(repo, {pack}, report)
        self.assertNotIn('serialized_verified', report)

    def test_root_required_before_accessing_live_credentials(self):
        with patch.object(transport.os, 'geteuid', return_value=1000):
            with self.assertRaises(PermissionError):
                transport.main()


if __name__ == '__main__':
    unittest.main()
