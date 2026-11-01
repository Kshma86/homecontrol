from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('router_diagnosis', Path(__file__).with_name('diagnose.py'))
diagnose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnose)


class DiagnosisTest(unittest.TestCase):
    def test_decodes_password_in_memory(self):
        # Use rclone's public obscure format without placing any password in argv.
        result = subprocess.run(['/usr/local/bin/rclone', 'obscure', '-'], input='fixture-árvíz',
                                capture_output=True, text=True, check=True)
        self.assertEqual(diagnose.reveal(result.stdout.strip()), 'fixture-árvíz')

    def test_superseded_indexes_do_not_report_deleted_packs_as_missing(self):
        old, new = 'a' * 64, 'b' * 64
        self.assertEqual(diagnose.expected_packs({old: {'packs': [{'id': old}]},
            new: {'packs': [{'id': new}], 'supersedes': [old]}}), {new})

    def test_native_inventory_ignores_paths_outside_pack_directories(self):
        ftp = Mock()
        pack = 'a' * 64
        ftp.nlst.side_effect = [['/repo/data/aa', '../other', '/repo/data/not-a-prefix'],
                               ['/repo/data/aa/' + pack, 'not-a-pack']]
        self.assertEqual(diagnose.native_inventory(ftp, '/repo'), {pack})
        self.assertEqual([call.args for call in ftp.nlst.call_args_list],
                         [('/repo/data',), ('/repo/data/aa',)])

    def test_direct_read_checks_complete_encrypted_pack_hash(self):
        content = b'complete encrypted pack fixture'
        pack = hashlib.sha256(content).hexdigest()
        ftp = Mock()
        ftp.retrbinary.side_effect = lambda command, callback: callback(content)
        result = diagnose.read_pack(ftp, '/repo', pack)
        self.assertTrue(result['sha256_matches_name'])
        ftp.retrbinary.assert_called_once()
        self.assertEqual(ftp.retrbinary.call_args.args[0], 'RETR /repo/data/' + pack[:2] + '/' + pack)

    def test_direct_read_detects_wrong_pack_data(self):
        ftp = Mock()
        ftp.retrbinary.side_effect = lambda command, callback: callback(b'wrong bytes')
        self.assertFalse(diagnose.read_pack(ftp, '/repo', 'a' * 64)['sha256_matches_name'])

    def test_diagnosis_uses_only_read_commands_even_when_listing_misses_a_pack(self):
        content = b'fixture pack'
        pack = hashlib.sha256(content).hexdigest()
        index = 'a' * 64
        repo = Mock()
        repo.settings = {'router_rclone_remote': 'routerbackup', 'router_repository_path': '/repo'}
        repo.env = {}
        repo.call.side_effect = ['[{"id":"' + 'b' * 64 + '"}]', index + '\n',
                                json.dumps({'packs': [{'id': pack}]})]
        repo.run.side_effect = [SimpleNamespace(returncode=0, stdout='[]'),
                               SimpleNamespace(returncode=0, stdout=json.dumps([{'Path':pack[:2] + '/' + pack}]))]
        ftp = Mock()
        ftp.nlst.side_effect = [[pack[:2]], [pack]]
        ftp.retrbinary.side_effect = lambda command, callback: callback(content)
        @contextmanager
        def connect():
            yield ftp
        report = {}
        with tempfile.TemporaryDirectory() as temporary:
            diagnose.inspect(repo, Path(temporary), connect, report)
        self.assertEqual(report['rclone_default']['missing_indexed_pack_count'], 1)
        self.assertEqual(report['rclone_without_mlsd']['missing_indexed_pack_count'], 0)
        self.assertTrue(report['sampled_packs'][0]['sha256_matches_name'])
        self.assertEqual(report['remote_write_commands'], 0)
        self.assertFalse(report['repository_repaired'])
        self.assertTrue(all(call.args[0][0] == '--no-lock' for call in repo.call.call_args_list))
        self.assertTrue(all(call.args[0][:2] == ['rclone', 'lsjson'] for call in repo.run.call_args_list))

    def test_root_is_required_before_reading_private_configuration(self):
        with patch.object(diagnose.os, 'geteuid', return_value=1000):
            with self.assertRaises(PermissionError):
                diagnose.main()


if __name__ == '__main__':
    unittest.main()
