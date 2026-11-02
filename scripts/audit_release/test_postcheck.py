import importlib.util,json,hashlib,tempfile,unittest,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
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
 def test_final_capture_uses_current_generated_schedule_not_historical_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);runtime,row,m,core=self.fixture(base)
   proof={'timers':{'timer'+str(n):{'active':True} for n in range(5)},'unit_sha256':{},'read_only':True}
   module=SimpleNamespace(schedule_plan=Mock(return_value={'current':True}),check_schedules=Mock(return_value=proof))
   with patch.object(p,'BASE',base),patch.dict(sys.modules,{'schedules':module}):result=p.capture(core,m,final=True)
   self.assertEqual(result['scheduled_units'],proof);self.assertEqual(len(result['active_timers']),5)
   module.check_schedules.assert_called_once_with(core,{'current':True})
 def test_final_capture_does_not_ignore_schedule_failure(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);runtime,row,m,core=self.fixture(base)
   module=SimpleNamespace(schedule_plan=Mock(return_value={}),check_schedules=Mock(side_effect=ValueError('timer missing')))
   with patch.object(p,'BASE',base),patch.dict(sys.modules,{'schedules':module}):
    with self.assertRaisesRegex(ValueError,'timer missing'):p.capture(core,m,final=True)
 def test_successful_handover_records_final_status_after_writing_documents(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);kit=base/'release';(kit/'evidence').mkdir(parents=True);(base/'docs').mkdir()
   accepted={'ok':True,'release':p.NAME,'run_id':'verified-run','snapshot_id':'verified-snapshot'}
   (kit/'evidence/router-live-acceptance.json').write_text(json.dumps(accepted))
   for name in ('AUDIT_REPAIR.md','DEPLOYMENT_PREP.md'):(base/name).write_text('# Record\nHistoric evidence\n')
   def write(path,value,mode):path.write_text(json.dumps(value))
   core=SimpleNamespace(load=lambda:{},platform=lambda:SimpleNamespace(write_json=write))
   with patch.object(p,'BASE',base),patch.object(p,'KIT',kit),patch('builtins.print'):p.finish(core,live={'ok':True,'runtime_source_count':789})
   result=json.loads((kit/'deployment-status.json').read_text())
   self.assertEqual(result['state'],'deployed_and_audit_handover_complete')
   self.assertEqual(result['audit_in_progress'],['HC-41','HC-43'])
   self.assertIn('verified-snapshot',(base/'docs/audit-final-20261102.md').read_text())
if __name__=='__main__':unittest.main(verbosity=2)
