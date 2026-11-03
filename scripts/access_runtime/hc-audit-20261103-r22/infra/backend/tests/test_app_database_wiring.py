"""HC-15 app import/production factories, in a guarded fresh interpreter."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class AppDatabaseWiringTest(unittest.TestCase):
    def test_import_routes_and_actual_lazy_factories_preserve_contract(self):
        fixtures=Path(__file__).with_name('fixtures')
        result=subprocess.run([sys.executable,'-B',str(fixtures/'hc15_import_probe.py')],
            capture_output=True,text=True,timeout=30,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout)
        self.assertEqual(value['routes'],json.loads((fixtures/'hc15_routes.json').read_text()))
        self.assertTrue(value['lazy_import']);self.assertFalse(value['external_work'])
        self.assertEqual(value['calls'],['season','scheduler',['climate',['winter']],['session',['42']]])
