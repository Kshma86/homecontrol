import importlib.util,json,hashlib,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('audit_live_postcheck',Path(__file__).with_name('postcheck.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class PostcheckTest(unittest.TestCase):
 def fixture(self,base):
  (base/'infra').mkdir();(base/'infra/access-release.json').write_text(json.dumps({'release':p.NAME}))
  runtime=base/'scripts/access_runtime'/p.NAME;runtime.mkdir(parents=True);(runtime/'example.py').write_text('verified')
  row={'Id':'new','Image':'selected','State':{'Running':True,'Health':{'Status':'healthy'}},'RestartCount':0}
  m={'source_sha256':{'example.py':hashlib.sha256(b'verified').hexdigest()},'changed_services':['backend'],
   'baseline':{'homecontrol-backend':{'id':'previous','image':'previous'}},'images':{'backend':'selected'}}
  core=SimpleNamespace(container=lambda n:'homecontrol-'+n,call=lambda args:SimpleNamespace(stdout=json.dumps([row]).encode()),request=lambda path:{'ai_enabled':False,'router_backup_enabled':True})
  return runtime,row,m,core
 def test_runtime_drift_is_rejected_before_success(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);runtime,row,m,core=self.fixture(base);(runtime/'example.py').write_text('changed')
   with patch.object(p,'BASE',base):
    with self.assertRaisesRegex(ValueError,'runtime differs'):p.capture(core,m)
 def test_wrong_image_is_rejected_even_if_healthy(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);runtime,row,m,core=self.fixture(base);row['Image']='wrong'
   with patch.object(p,'BASE',base):
    with self.assertRaisesRegex(ValueError,'Unexpected live image'):p.capture(core,m)
 def test_disabled_ai_and_router_backup_are_acceptance_requirements(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);runtime,row,m,core=self.fixture(base);core.request=lambda path:{'ai_enabled':True,'router_backup_enabled':True}
   with patch.object(p,'BASE',base):
    with self.assertRaisesRegex(ValueError,'AI/router policy'):p.capture(core,m)
if __name__=='__main__':unittest.main(verbosity=2)
