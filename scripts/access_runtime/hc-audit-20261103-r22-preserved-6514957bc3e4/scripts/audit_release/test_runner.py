"""A failed test profile must also fail the invoking shell, never just its JSON."""
import runpy,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
class RunnerExitTest(unittest.TestCase):
 def test_failed_profile_is_nonzero_to_caller(self):
  fake=SimpleNamespace(main=lambda:1)
  with patch.dict(sys.modules,{'check_hc_tests':fake}):
   with self.assertRaises(SystemExit) as result:runpy.run_path(str(Path(__file__).with_name('run_checks.py')),run_name='__main__')
  self.assertEqual(result.exception.code,1)
 def test_successful_profile_is_zero_to_caller(self):
  fake=SimpleNamespace(main=lambda:0)
  with patch.dict(sys.modules,{'check_hc_tests':fake}):
   with self.assertRaises(SystemExit) as result:runpy.run_path(str(Path(__file__).with_name('run_checks.py')),run_name='__main__')
  self.assertEqual(result.exception.code,0)
if __name__=='__main__':unittest.main(verbosity=2)
