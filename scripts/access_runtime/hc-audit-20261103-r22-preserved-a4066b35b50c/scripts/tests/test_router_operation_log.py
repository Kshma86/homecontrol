import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('router_operation_log_tested', Path(__file__).resolve().parents[1] / 'router_operation_log.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PrivateDiagnosticTest(unittest.TestCase):
    def test_failed_snapshot_exit_code_and_private_output_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            response = subprocess.CompletedProcess([], 3, stdout='{"message_type":"error"}', stderr='private-detail')
            execute = Mock(return_value=response)
            logger = m.OperationLog(folder, 'a' * 32, run=execute)
            result = logger(['restic', 'backup', '--json'], env={'RESTIC_PASSWORD': 'not-recorded'})
            self.assertIs(result, response)
            self.assertEqual(result.returncode, 3)
            files = list((Path(folder) / 'router-diagnostics').glob('*.json'))
            self.assertEqual(len(files), 1)
            self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(files[0].parent.stat().st_mode), 0o700)
            payload = json.loads(files[0].read_text())
            self.assertEqual(payload['stderr'], 'private-detail')
            self.assertEqual(payload['exit_code'], 3)
            self.assertNotIn('not-recorded', files[0].read_text())
            self.assertNotIn('env', payload)
            self.assertNotIn('args', payload)

    def test_success_does_not_create_diagnostic_files(self):
        with tempfile.TemporaryDirectory() as folder:
            execute = Mock(return_value=subprocess.CompletedProcess([], 0, stdout='success', stderr=''))
            logger = m.OperationLog(folder, 'b' * 32, run=execute)
            logger(['restic', 'backup'])
            self.assertFalse((Path(folder) / 'router-diagnostics').exists())
            self.assertIsNone(logger.last_failure)

    def test_symlinked_directory_is_not_used_and_original_failure_is_not_masked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'outside').mkdir()
            (root / 'router-diagnostics').symlink_to(root / 'outside', target_is_directory=True)
            response = subprocess.CompletedProcess([], 1, stdout='', stderr='original failure')
            logger = m.OperationLog(root, 'c' * 32, run=Mock(return_value=response))
            self.assertIs(logger(['rclone', 'lsf']), response)
            self.assertTrue(logger.record_failed)
            self.assertEqual(list((root / 'outside').iterdir()), [])

    def test_output_is_bounded_and_marked_when_truncated(self):
        with tempfile.TemporaryDirectory() as folder:
            response = subprocess.CompletedProcess([], 1, stdout='x' * (m.LIMIT + 1), stderr='tail')
            logger = m.OperationLog(folder, 'd' * 32, run=Mock(return_value=response))
            logger(['restic', 'check'])
            payload = json.loads(next((Path(folder) / 'router-diagnostics').glob('*.json')).read_text())
            self.assertEqual(len(payload['stdout']), m.LIMIT)
            self.assertTrue(payload['stdout_truncated'])
            self.assertFalse(payload['stderr_truncated'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
