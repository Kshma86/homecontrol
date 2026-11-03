"""Reboot guards against stale receipts and unexpected boot selection."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('host_guarded_reboot', Path(__file__).with_name('reboot.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
KERNEL = '5.15.0-202-generic'
CONFIG = '''header
set default="0"
menuentry 'Ubuntu' {
 linux /boot/vmlinuz-5.15.0-202-generic root=UUID=root-uuid ro
 initrd /boot/initrd.img-5.15.0-202-generic
}
'''


class BootSelection(unittest.TestCase):
    def test_reviewed_entry_and_empty_overrides_pass(self):
        m.validate_boot(CONFIG, 'GRUB_DEFAULT=0\n', {}, KERNEL, 'root-uuid')

    def test_saved_or_nonfirst_default_rejected(self):
        for value in ('saved', '1', '"0"'):
            with self.subTest(default=value), self.assertRaises(ValueError):
                m.validate_boot(CONFIG, 'GRUB_DEFAULT=' + value, {}, KERNEL, 'root-uuid')

    def test_pending_recovery_or_one_boot_override_rejected(self):
        for key in ('next_entry', 'prev_saved_entry', 'initrdfail', 'prev_entry'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_boot(CONFIG, 'GRUB_DEFAULT=0', {key: 'other-entry'}, KERNEL, 'root-uuid')

    def test_wrong_kernel_root_or_initrd_rejected(self):
        for config in (CONFIG.replace('vmlinuz-5.15.0-202', 'vmlinuz-5.15.0-187'),
                       CONFIG.replace('root=UUID=root-uuid', 'root=UUID=other'),
                       CONFIG.replace('initrd.img-5.15.0-202', 'initrd.img-5.15.0-187')):
            with self.subTest(config=config), self.assertRaises(ValueError):
                m.validate_boot(config, 'GRUB_DEFAULT=0', {}, KERNEL, 'root-uuid')


def receipts():
    return ({'ok': True, 'state': 'upgraded_pending_reboot', 'reboot_performed': False, 'boot_id': 'boot'},
            {'boot_id': 'boot'}, {'ok': True, 'run_id': 'run', 'snapshot_id': 'snapshot',
            'archive_sha256': 'sha', 'restore': 'verified', 'database': 'verified'})


class ReceiptGuards(unittest.TestCase):
    def test_matching_pending_upgrade_passes(self): m.validate_receipts(*receipts(), 'boot')

    def test_prior_boot_or_failed_acceptance_rejected(self):
        for field, value in [('ok', False), ('boot_id', 'old'), ('state', 'installing'), ('reboot_performed', True)]:
            accepted, before, proof = receipts(); accepted[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.validate_receipts(accepted, before, proof, 'boot')

    def test_missing_fresh_restore_proof_rejected(self):
        for field in receipts()[2]:
            accepted, before, proof = receipts(); del proof[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.validate_receipts(accepted, before, proof, 'boot')

    def test_failed_preflight_never_dispatches_reboot_or_stops_hostops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'boot-id').write_text('boot')
            accepted, before, proof = receipts()
            executor = Mock(); executor.PHASE = 'reboot_preflight'
            executor.read.side_effect = lambda path: {
                'before.json': before, 'upgrade-success.json': accepted, 'pre-proof.json': proof}[path.name]
            executor.checks.return_value.main.side_effect = ValueError('readiness failed')
            with patch.object(m, 'STATE', root), patch.object(m, 'BOOT_ID', root / 'boot-id'):
                with self.assertRaises(ValueError): m.perform(executor)
            executor.call.assert_not_called(); executor.pause.assert_not_called()


if __name__ == '__main__': unittest.main()
