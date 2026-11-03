import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import os
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('audit_prepare', Path(__file__).with_name('prepare_audit_restore.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class AuditPreparationTest(unittest.TestCase):
    def test_operator_identity_is_accepted_by_root_export(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'identity'
            path.write_text('private-test-identity')
            path.chmod(0o600)
            with patch.object(prepare.os, 'geteuid', return_value=0):
                self.assertEqual(prepare.recovery_key(path, os.getuid()), 'private-test-identity')

    def test_public_or_foreign_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'identity'
            path.write_text('private-test-identity')
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                prepare.recovery_key(path, os.getuid())
            path.chmod(0o600)
            with patch.object(prepare.os, 'fstat', return_value=SimpleNamespace(st_mode=0o100600, st_uid=123456)):
                with self.assertRaises(ValueError):
                    prepare.recovery_key(path, os.getuid())

    def test_identity_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'identity'
            path.write_text('private-test-identity')
            path.chmod(0o600)
            link = Path(root) / 'link'
            link.symlink_to(path)
            with self.assertRaises(OSError):
                prepare.recovery_key(link, os.getuid())

    def test_requires_operator_sudo_before_private_reads(self):
        with patch.object(prepare.os, 'geteuid', return_value=1000):
            with self.assertRaises(PermissionError):
                prepare.main()

    def test_binary_bundle_is_not_logged_and_does_not_break_export(self):
        log = io.StringIO()
        prepare.log_result(log, SimpleNamespace(stdout=b'encrypted-bundle-bytes', stderr=b''))
        self.assertIn('22 bytes', log.getvalue())
        self.assertNotIn('encrypted-bundle-bytes', log.getvalue())

    def test_text_diagnostics_are_preserved_in_private_log(self):
        log = io.StringIO()
        prepare.log_result(log, SimpleNamespace(stdout='phase done\n', stderr='diagnostic\n'))
        self.assertEqual(log.getvalue(), 'phase done\ndiagnostic\n')


if __name__ == '__main__':
    unittest.main()
