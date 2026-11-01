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
