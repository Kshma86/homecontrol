import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('r21_precheck_diagnosis_tested', Path(__file__).with_name('diagnose_r21_precheck.py'))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class PrecheckDiagnosisTest(unittest.TestCase):
    def test_raw_exception_is_never_echoed_in_summary(self):
        result = d.safe_error({'error_type': 'RuntimeError', 'detail': 'private-credential-value; connection reset'})
        self.assertNotIn('private-credential-value', json.dumps(result))
        self.assertEqual(result['error_classes'], ['transport'])
        self.assertIsNone(result['restic_exit_code'])

    def test_known_original_restic_exit_code_is_preserved_without_detail(self):
        result = d.safe_error({'error_type': 'RuntimeError', 'detail': 'Restic operation failed (exit 1); repository was not reinitialized'})
        self.assertEqual(result['restic_exit_code'], 1)
        self.assertNotIn('detail', result)

    def test_destructive_operations_never_reach_process_runner(self):
        run = Mock()
        for args in (['unlock'], ['repair', 'index'], ['forget', '--prune'], ['init'], ['backup', '/source']):
            with self.subTest(args=args), self.assertRaises(ValueError):
                d.read_operation(None, args, None, 'unused', run=run)
        run.assert_not_called()

    def test_check_uses_no_lock_and_retains_raw_error_only_in_private_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = SimpleNamespace(command=['restic', '-o', 'rclone.args=fixture'], env={'FIXTURE': 'not-public'})
            error = 'pack abcdef1234567890: does not exist\nprivate-credential-value\nconnection reset'
            run = Mock(return_value=subprocess.CompletedProcess([], 1, 'private stdout', error))
            result = d.read_operation(repo, ['check', '--read-data'], root, 'check', run=run)
            args = run.call_args.args[0]
            self.assertEqual(args, ['restic', '--no-lock', '-o', 'rclone.args=fixture', 'check', '--read-data'])
            self.assertEqual(result['missing_pack_count'], 1)
            self.assertNotIn('private', json.dumps(result))
            self.assertEqual((root / 'check.stderr').read_text(), error)
            for field in ('stdout', 'stderr'):
                self.assertEqual((root / ('check.' + field)).stat().st_mode & 0o777, 0o600)

    def test_timeout_keeps_partial_byte_output_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = SimpleNamespace(command=['restic'], env={})
            run = Mock(side_effect=subprocess.TimeoutExpired(['restic'], 10800, output=b'partial', stderr=b'timed out'))
            result = d.read_operation(repo, ['check', '--read-data'], root, 'check', run=run)
            self.assertEqual(result['exit_code'], 124)
            self.assertTrue(result['timed_out'])
            self.assertEqual((root / 'check.stdout').read_text(), 'partial')

    def test_lock_inventory_reports_only_count(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = SimpleNamespace(command=['restic'], env={})
            run = Mock(return_value=subprocess.CompletedProcess([], 0, 'a' * 64 + '\n' + 'b' * 64 + '\n', ''))
            result = d.read_operation(repo, ['list', 'locks'], Path(directory), 'locks', run=run)
            self.assertEqual(result['lock_count'], 2)
            self.assertNotIn('a' * 64, json.dumps(result))

    def test_existing_cutover_state_prevents_diagnosis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('STATE', 'RUNTIME', 'PRIVATE'):
                paths = {key: root / key for key in ('STATE', 'RUNTIME', 'PRIVATE')}
                paths[name].mkdir()
                core = SimpleNamespace(**paths, guard_runtime=Mock())
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unexpected r21 cutover'):
                    d.validate_state(core, {})
                paths[name].rmdir()

    def test_foreign_runtime_guard_failure_is_not_ignored(self):
        core = SimpleNamespace(guard_runtime=Mock(side_effect=ValueError('runtime changed')))
        with self.assertRaisesRegex(ValueError, 'runtime changed'):
            d.validate_state(core, {})

    def test_non_root_never_starts_diagnostic_or_supervisor(self):
        with patch.object(d.os, 'geteuid', return_value=1000), patch.object(d, 'load_module') as load:
            with self.assertRaises(PermissionError): d.main()
            with self.assertRaises(PermissionError): d.worker()
        load.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
