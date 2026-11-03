import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('baseline_summary', Path(__file__).with_name('summarize_r21_baseline_failure.py'))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class BaselineSummaryTests(unittest.TestCase):
    def test_raw_credentials_paths_and_messages_are_withheld(self):
        row = {'message_type': 'error', 'during': 'archival',
               'item': str(d.BASE / 'infra/private-credential'),
               'error': {'message': 'private-password permission denied'}}
        result = d.summary({'tool': 'restic', 'operation': 'backup', 'exit_code': 1,
                            'stdout': json.dumps(row),
                            'stderr': 'ftp://private-user:private-password@private-host: 550 Requested action not taken; failed to save'})
        text = json.dumps(result)
        self.assertNotIn('private-', text)
        self.assertEqual(result['ftp_reply_codes'], ['550'])
        self.assertEqual(result['source_errors'][0]['source_group'], 'infrastructure')
        self.assertIn('permission', result['error_classes'])
        self.assertIn('backend_write', result['error_classes'])

    def test_multiple_failure_classes_and_snapshot_summary(self):
        result = d.summary({'stdout': json.dumps({'message_type': 'summary', 'snapshot_id': 'a' * 64}),
                            'stderr': 'connection reset; no space left on device'})
        self.assertEqual(result['snapshot_summaries'], 1)
        self.assertEqual(set(result['error_classes']), {'transport', 'disk_full'})

    def test_unclassified_error_does_not_leak(self):
        result = d.summary({'stderr': 'private-unrecognized-error', 'tool': 'private-tool',
                            'operation': 'private-operation', 'exit_code': 'private-code'})
        self.assertNotIn('private-', json.dumps(result))
        self.assertIsNone(result['exit_code'])
        self.assertEqual(result['error_classes'], ['unclassified_private_detail_retained'])

    def test_non_dictionary_json_and_invalid_lines_are_ignored(self):
        result = d.summary({'stdout': 'not json\n[]\nnull\n4\n"secret"'})
        self.assertEqual(result['source_errors'], [])

    def test_source_error_output_is_bounded(self):
        row = json.dumps({'message_type': 'error', 'item': '/secret', 'error': 'file changed'})
        result = d.summary({'stdout': '\n'.join([row] * 45), 'stderr_truncated': True})
        self.assertEqual(result['source_error_count'], 45)
        self.assertEqual(len(result['source_errors']), 40)
        self.assertTrue(result['stderr_truncated'])

    def test_unprivileged_execution_reads_nothing(self):
        with patch.object(d.os, 'geteuid', return_value=1000), patch.object(d.Path, 'read_text') as read:
            with self.assertRaises(PermissionError):
                d.main()
        read.assert_not_called()

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'target').write_text('{}')
            (root / 'link').symlink_to(root / 'target')
            with self.assertRaisesRegex(ValueError, 'SYMLINK'):
                d.read_private(root / 'link')

    def test_public_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'log.json'
            path.write_text('{}')
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError, 'PERMISSIONS'):
                d.read_private(path)

    def test_non_regular_file_is_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fifo'
            os.mkfifo(path, 0o600)
            with self.assertRaisesRegex(ValueError, 'PERMISSIONS'):
                d.read_private(path)

    def test_only_documented_source_groups_are_exposed(self):
        self.assertEqual(d.group(d.BASE / 'infra/ssh/release/key'), 'release_credentials_or_image_cache')
        self.assertEqual(d.group('/unrecognized/private'), 'other')

    def fixture(self, root):
        kit = root / 'backups/releases/r21'
        sidecar = root / 'backups/releases/continuation'
        for rel, value in (('infra/access-release.json', {'release': 'hc-security-20261102-r18'}),
                           ('backups/backup-state.json', {'run_id': d.RUN, 'state': 'failed'})):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value))
        kit.mkdir(parents=True)
        (kit / 'deployment-status.json').write_text(json.dumps({'phase': 'baseline_full_backup'}))
        work = root / 'backups/router-diagnostics'
        work.mkdir()
        (work / (d.RUN + '-' + 'a' * 32 + '.json')).touch()
        (work / ('b' * 32 + '-' + 'a' * 32 + '.json')).touch()
        return kit, sidecar

    def test_full_summary_selects_only_failed_run_and_emits_no_raw_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kit, sidecar = self.fixture(root)
            payload = {'run_id': d.RUN, 'tool': 'restic', 'operation': 'backup', 'exit_code': 1,
                       'stderr': 'private-password connection reset'}
            output = io.StringIO()
            with patch.object(d, 'BASE', root), patch.object(d, 'KIT', kit), patch.object(d, 'SIDECAR', sidecar), \
                 patch.object(d.os, 'geteuid', return_value=0), \
                 patch.object(d, 'read_private', side_effect=[payload, {'error_type': 'RuntimeError', 'detail': 'private-exception'}]) as read, \
                 patch('sys.stdout', output):
                d.main()
            result = json.loads(output.getvalue())
            self.assertEqual(result['private_log_count'], 1)
            self.assertEqual(read.call_count, 2)
            self.assertNotIn('private-password', output.getvalue())
            self.assertNotIn('private-exception', output.getvalue())
            self.assertEqual(result['remote_commands'], 0)

    def test_changed_run_stops_before_reading_private_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kit, sidecar = self.fixture(root)
            (root / 'backups/backup-state.json').write_text(json.dumps({'run_id': 'changed', 'state': 'failed'}))
            with patch.object(d, 'BASE', root), patch.object(d, 'KIT', kit), patch.object(d.os, 'geteuid', return_value=0), \
                 patch.object(d, 'read_private') as read:
                with self.assertRaisesRegex(ValueError, 'BACKUP_RUN_CHANGED'):
                    d.main()
            read.assert_not_called()

    def test_http_bridge_500_is_not_reported_as_an_ftp_reply(self):
        result = d.summary({'stderr': 'Save(<data/private>): unexpected HTTP response (500): 500 Internal Server Error'})
        self.assertEqual(result['http_status_codes'], ['500'])
        self.assertEqual(result['ftp_reply_codes'], [])
        self.assertEqual(result['unattributed_reply_codes'], [])

    def test_bare_numeric_token_does_not_prove_protocol(self):
        result = d.summary({'stderr': 'unclassified message with 500'})
        self.assertEqual(result['reply_code_candidates'], ['500'])
        self.assertEqual(result['unattributed_reply_codes'], ['500'])
        self.assertEqual(result['ftp_reply_codes'], [])
        self.assertEqual(result['http_status_codes'], [])

    def test_explicit_ftp_command_error_is_distinguished(self):
        result = d.summary({'stderr': 'update stor: 500 Unknown command'})
        self.assertEqual(result['ftp_reply_codes'], ['500'])
        self.assertEqual(result['http_status_codes'], [])
        self.assertIn('unknown_command', result['transport_conditions'])
        self.assertIn('ftp_upload_stor', result['failure_stages'])

    def test_upload_control_connection_timeout_retains_only_fixed_labels(self):
        log = 'rclone: private-path Post request rcat error: update stor: read tcp 192.0.2.2:12345->192.0.2.1:21: i/o timeout'
        result = d.summary({'stderr': log})
        text = json.dumps(result)
        self.assertNotIn('192.0.2', text)
        self.assertNotIn('private-path', text)
        self.assertIn('tcp_read_timeout', result['transport_conditions'])
        self.assertIn('restic_bridge_upload', result['failure_stages'])
        self.assertIn('ftp_upload_stor', result['failure_stages'])
        self.assertEqual(result['stderr_groups'][0]['tcp_peer_roles'], ['ftp_control_port_21'])

    def test_repeated_failures_are_counted_and_unknown_lines_withheld(self):
        result = d.summary({'stderr': '\n'.join(['private unknown line', 'broken pipe', 'broken pipe'])})
        self.assertEqual(result['stderr_groups'][0]['count'], 2)
        self.assertEqual(result['unclassified_stderr_line_count'], 1)
        self.assertNotIn('private unknown line', json.dumps(result))

    def test_truncated_log_does_not_claim_complete_source_error_inventory(self):
        result = d.summary({'stdout_truncated': True})
        self.assertFalse(result['source_error_inventory_complete'])
        self.assertEqual(result['source_error_count'], 0)

    def test_object_ids_and_names_are_withheld_but_object_kind_is_preserved(self):
        object_id = 'a' * 64
        result = d.summary({'stderr': 'data/aa/' + object_id + ': failed to save: connection reset by peer'})
        self.assertNotIn(object_id, json.dumps(result))
        self.assertEqual(result['stderr_groups'][0]['repository_object_kinds'], ['data_pack'])

    def test_mixed_http_and_ftp_errors_keep_both_evidence_types(self):
        result = d.summary({'stderr': '500 Unknown command\nHTTP/2.0 500 Internal Server Error'})
        self.assertEqual(result['ftp_reply_codes'], ['500'])
        self.assertEqual(result['http_status_codes'], ['500'])
        self.assertEqual(len(result['stderr_groups']), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
