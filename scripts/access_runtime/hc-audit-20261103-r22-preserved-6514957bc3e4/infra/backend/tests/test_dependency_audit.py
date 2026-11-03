import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SOURCE=Path(__file__).resolve().parents[3]/'scripts/dependency_audit.py'
spec=importlib.util.spec_from_file_location('offline_dependency_audit',SOURCE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DependencyAuditTest(unittest.TestCase):
    def test_semver_prerelease_precedence_and_ignored_build_metadata(self):
        order = ['1.0.0-alpha', '1.0.0-alpha.1', '1.0.0-alpha.beta',
                 '1.0.0-beta', '1.0.0-beta.2', '1.0.0-beta.11', '1.0.0-rc.1', '1.0.0']
        self.assertEqual(sorted(order, key=module.SemVer), order)
        self.assertEqual(module.SemVer('1.0.0+build.1'), module.SemVer('1.0.0+build.2'))
        for invalid in ('1.0', '01.0.0', '1.0.0-01', '1.0.0-'):
            with self.assertRaises(ValueError): module.SemVer(invalid)

    def test_npm_fixed_release_does_not_hide_affected_prerelease(self):
        entry = {'ranges': [{'type': 'SEMVER', 'events': [{'introduced': '0'}, {'fixed': '2.0.0'}]}]}
        self.assertTrue(module.affected(entry, '2.0.0-rc.1', ecosystem='npm'))
        self.assertFalse(module.affected(entry, '2.0.0+release', ecosystem='npm'))

    def test_npm_lock_keeps_scoped_and_nested_names_without_duplicate_pairs(self):
        lock = {'lockfileVersion': 3, 'packages': {'': {'name': 'root'},
                'node_modules/@demo/pkg': {'version': '1.0.0'},
                'node_modules/outer/node_modules/@demo/pkg': {'version': '1.0.0'},
                'node_modules/other': {'version': '2.0.0'}}}
        self.assertEqual(module.npm_inventory(lock), {'frontend_build': [('@demo/pkg', '1.0.0'), ('other', '2.0.0')]})

    def test_alias_groups_merge_transitive_records_without_double_counting(self):
        rows = [{'id': 'one', 'aliases': ['CVE-1']}, {'id': 'two', 'aliases': ['CVE-2']},
                {'id': 'three', 'aliases': ['CVE-1', 'CVE-2']}]
        self.assertEqual(len(module.advisory_groups(rows)), 1)

    def test_missing_version_evidence_is_unknown(self):
        self.assertIsNone(module.affected({}, '1.0'))

    def test_fixed_boundary_and_reintroduced_branch(self):
        entry={'ranges':[{'type':'ECOSYSTEM','events':[{'introduced':'0'},{'fixed':'1.2'},
            {'introduced':'2.0'},{'fixed':'2.1'}]}]}
        for version,expected in [('1.1',True),('1.2',False),('2.0',True),('2.1',False)]:
            self.assertIs(module.affected(entry,version),expected)

    def test_last_affected_is_inclusive_and_limit_exclusive(self):
        for key,expected in [('fixed',False),('limit',False),('last_affected',True)]:
            entry={'ranges':[{'type':'ECOSYSTEM','events':[{'introduced':'0'},{key:'2.0'}]}]}
            self.assertIs(module.affected(entry,'2.0'),expected)

    def test_git_range_is_unknown_not_a_false_clean_bill(self):
        entry={'ranges':[{'type':'GIT','events':[{'introduced':'hash'}]}]}
        self.assertIsNone(module.affected(entry,'3.0'))
        self.assertIs(module.affected({**entry,'versions':['3.0']},'3.0'),True)

    def test_scan_filters_future_withdrawn_and_unrelated_packages_locally(self):
        base={'id':'fixture','published':'2026-10-30','affected':[{'package':{'ecosystem':'PyPI','name':'demo_pkg'},
            'ranges':[{'type':'ECOSYSTEM','events':[{'introduced':'0'},{'fixed':'2'}]}]}]}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'catalog.zip'
            with zipfile.ZipFile(path,'w') as archive:
                for name,row in [('good',base),('future',{**base,'published':'2026-11-01'}),
                    ('withdrawn',{**base,'withdrawn':'2026-10-31'})]:
                    archive.writestr(name+'.json',json.dumps(row))
            result=module.scan({'fixture':[['demo-pkg','1']]},path,cutoff='2026-10-31')
            self.assertEqual(len(result['matches']),1)
            self.assertFalse(result['private_inventory_uploaded'])
