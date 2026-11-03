import hashlib
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('host_update_plan_tested', Path(__file__).with_name('plan.py'))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


class PlanTests(unittest.TestCase):
    def test_upgrade_new_dependency_and_temporary_dependency_annotations(self):
        rows = p.parse_simulation('Inst docker-ce [5:29.1-1] (5:29.9-1 Docker CE:jammy [amd64])\n'
                                  'Inst new-package (1.0 Ubuntu:22.04/jammy-updates [all]) []\n'
                                  'Inst libkrb5-3 [1.0] (1.1 Ubuntu:22.04/jammy-updates [amd64]) [dependent:amd64 ]\n')
        self.assertEqual(len(rows), 3); self.assertIsNone(rows[1]['installed'])
        self.assertEqual(rows[0]['candidate'], '5:29.9-1')

    def test_removal_duplicate_or_unparsed_transaction_is_rejected(self):
        for text in ('Remv old-package [1.0]\n', 'Inst unexpected-format\n',
                     'Inst foo (1 Ubuntu:22.04 [all])\nInst foo (2 Ubuntu:22.04 [all])\n'):
            with self.subTest(text=text), self.assertRaises(ValueError): p.parse_simulation(text)

    def test_empty_simulation_is_not_a_completed_plan(self):
        with self.assertRaises(ValueError): p.parse_simulation('Reading package lists...\n')

    def fixture(self, data=b'synthetic deb bytes'):
        return 'Package: foo\nVersion: 1:2.0-1\nArchitecture: amd64\nSHA256: '+hashlib.sha256(data).hexdigest()+'\nSize: '+str(len(data))+'\nInstalled-Size: 1024\nFilename: pool/f/foo.deb\nDescription: example\n continuation\n'

    def test_catalog_metadata_requires_exact_version_architecture_and_digest(self):
        record = p.metadata(self.fixture(), 'foo', '1:2.0-1', 'amd64')
        self.assertEqual(record['installed_kib'], 1024)
        for version, arch in (('different', 'amd64'), ('1:2.0-1', 'arm64')):
            with self.assertRaises(ValueError): p.metadata(self.fixture(), 'foo', version, arch)

    def test_conflicting_repository_records_are_rejected(self):
        text = self.fixture() + '\n' + self.fixture().replace('pool/f/foo.deb', 'pool/other.deb')
        with self.assertRaises(ValueError): p.metadata(text, 'foo', '1:2.0-1', 'amd64')

    def test_missing_hash_or_unsafe_repository_path_is_rejected(self):
        for text in (self.fixture().replace('SHA256:', 'Other:'), self.fixture().replace('pool/f/foo.deb', '../foo.deb')):
            with self.assertRaises(ValueError): p.metadata(text, 'foo', '1:2.0-1', 'amd64')

    def test_package_bytes_and_control_identity_must_both_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'foo.deb'; path.write_bytes(b'synthetic deb bytes')
            record = p.metadata(self.fixture(), 'foo', '1:2.0-1', 'amd64')
            good = lambda *args, **kwargs: SimpleNamespace(stdout='Package: foo\nVersion: 1:2.0-1\nArchitecture: amd64\n')
            p.verify_deb(path, record, run=good)
            bad = lambda *args, **kwargs: SimpleNamespace(stdout='Package: wrong\nVersion: 1:2.0-1\nArchitecture: amd64\n')
            with self.assertRaises(ValueError): p.verify_deb(path, record, run=bad)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError): p.verify_deb(path, record, run=good)

    def test_package_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'foo.deb'; path.symlink_to('/dev/null')
            with self.assertRaises(ValueError): p.verify_deb(path, {})

    def test_empty_hook_nodes_are_allowed_but_commands_are_not(self):
        self.assertTrue(p.hooks_are_empty('DPkg::Post-Invoke "";\nDPkg::Pre-Install-Pkgs "";'))
        self.assertFalse(p.hooks_are_empty('APT::Update::Post-Invoke:: "touch /tmp/example";'))


if __name__ == '__main__': unittest.main()
