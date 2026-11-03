import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('host_postcheck_tested', Path(__file__).with_name('check.py'))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class RebootTests(unittest.TestCase):
    def fixture(self):
        before = {'boot_id':'old','next_kernel':'5.15.0-202-generic','root_uuid':'root',
                  'mounts':{'backups':{'uuid':'var','fsroot':'/data'}}}
        after = {'boot_id':'new','kernel':'5.15.0-202-generic','root_uuid':'root',
                 'mounts':copy.deepcopy(before['mounts']),'dpkg_audit':''}
        return before, after

    def test_expected_reboot_kernel_and_mounts_pass(self):
        before, after = self.fixture(); c.validate_reboot(after, before)

    def test_same_boot_is_rejected(self):
        before, after = self.fixture(); after['boot_id']='old'
        with self.assertRaisesRegex(ValueError,'reboot has not'): c.validate_reboot(after,before)

    def test_old_running_kernel_is_rejected(self):
        before, after = self.fixture(); after['kernel']='5.15.0-187-generic'
        with self.assertRaisesRegex(ValueError,'kernel'): c.validate_reboot(after,before)

    def test_wrong_backup_partition_or_bind_root_is_rejected(self):
        for field, value in (('uuid','srv'),('fsroot','/old-data')):
            with self.subTest(field=field):
                before, after = self.fixture(); after['mounts']['backups'][field]=value
                with self.assertRaisesRegex(ValueError,'filesystem'): c.validate_reboot(after,before)

    def test_incomplete_package_configuration_is_rejected(self):
        before, after = self.fixture(); after['dpkg_audit']='pending configuration'
        with self.assertRaisesRegex(ValueError,'dpkg'): c.validate_reboot(after,before)

    def test_before_reboot_gate_keeps_mount_and_dpkg_checks(self):
        before, after = self.fixture(); after.update(boot_id='old',kernel='5.15.0-187-generic')
        c.validate_reboot(after,before,require_reboot=False)
        after['mounts']['backups']['uuid']='wrong'
        with self.assertRaisesRegex(ValueError,'filesystem'): c.validate_reboot(after,before,require_reboot=False)


if __name__ == '__main__': unittest.main()
