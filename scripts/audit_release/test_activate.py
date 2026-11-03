"""Test authorization and failure behavior of the three-component activation wrapper."""
import importlib.util,json,unittest,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('audit_completion_activation',Path(__file__).with_name('activate.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class AuditActivationTest(unittest.TestCase):
 def test_local_root_required_before_any_runtime_probe_or_cutover(self):
  with patch.object(a.os,'geteuid',return_value=1000),patch.object(a.router,'main') as run,patch.object(a.router.core,'verify') as verify:
   with self.assertRaises(PermissionError):a.main()
   run.assert_not_called();verify.assert_not_called()
 def test_existing_platform_is_checked_before_transaction_and_new_platform_inside_verify(self):
  events=[];core=a.router.core
  def transaction(action):
   events.append(action);core.Cutover.verify(object());return 'done'
  with patch.object(a.os,'geteuid',return_value=0),patch.object(core,'verify',return_value={'fixture':True}),patch.object(core,'guard_runtime',side_effect=lambda m:events.append('guard')),patch.object(core.Cutover,'verify',side_effect=lambda c:events.append('application_verify')),patch.object(a,'platform_checks',side_effect=lambda m,previous=False:events.append('before' if previous else 'after')),patch.object(a,'schedule_checks',side_effect=lambda core:events.append('schedules')),patch.object(a,'backup_checks',side_effect=lambda core,m:events.append('backup_preflight')),patch.object(a.router,'main',side_effect=transaction),patch.object(a,'complete',side_effect=lambda core:events.append('complete')):
   self.assertEqual(a.main(),'done')
  self.assertEqual(events,['guard','before','schedules','backup_preflight','activate','application_verify','after','complete'])
 def test_platform_verification_failure_reaches_existing_transaction_rollback(self):
  core=a.router.core;events=[]
  class Context:
   quiesce=lambda self:None
   stop=lambda self:None
   install=lambda self:None
   start=lambda self:None
   verify=lambda self:core.Cutover.verify(self)
   resume=lambda self:events.append('resume')
   rollback=lambda self:events.append('rollback')
  def checks(m,previous=False):
   if not previous:raise RuntimeError('fixture HA failure')
  with patch.object(a.os,'geteuid',return_value=0),patch.object(core,'verify',return_value={}),patch.object(core,'guard_runtime'),patch.object(core.Cutover,'verify',return_value=None),patch.object(a,'platform_checks',side_effect=checks),patch.object(a,'schedule_checks'),patch.object(a,'backup_checks'),patch.object(a.router,'main',side_effect=lambda action:core.switch(Context())):
   with self.assertRaises(RuntimeError):a.main()
  self.assertEqual(events,['rollback'])
 def test_schedule_mismatch_is_rejected_before_any_cutover(self):
  core=a.router.core
  with patch.object(a.os,'geteuid',return_value=0),patch.object(core,'verify',return_value={}),patch.object(core,'guard_runtime'),patch.object(a,'platform_checks'),patch.object(a,'schedule_checks',side_effect=ValueError('timer drift')),patch.object(a.router,'main') as run:
   with self.assertRaisesRegex(ValueError,'timer drift'):a.main()
  run.assert_not_called()
 def test_backup_preflight_failure_prevents_any_cutover(self):
  core=a.router.core
  with patch.object(a.os,'geteuid',return_value=0),patch.object(core,'verify',return_value={}),patch.object(core,'guard_runtime'),patch.object(a,'platform_checks'),patch.object(a,'schedule_checks'),patch.object(a,'backup_checks',side_effect=ValueError('backup preflight failed')),patch.object(a.router,'main') as run:
   with self.assertRaisesRegex(ValueError,'backup preflight failed'):a.main()
  run.assert_not_called()
 def test_replaced_unchanged_component_is_rejected_without_any_stop(self):
  core=a.router.core;manifest={'changed_services':['backend'],'baseline':{'homecontrol-backend':{},'homeassistant':{'id':'old','image':'expected'}}}
  check=SimpleNamespace(ha_ready=Mock(return_value={}),postgres_ready=Mock(return_value={}))
  response=SimpleNamespace(stdout=json.dumps([{'Id':'unexpected','Image':'expected'}]).encode())
  with patch.object(a,'probes',return_value=check),patch.object(core,'call',return_value=response) as call:
   with self.assertRaises(ValueError):a.platform_checks(manifest)
  self.assertEqual(call.call_args.args[0],['docker','inspect','homeassistant'])
 def test_rollback_uses_recorded_router_transaction_without_new_preflight(self):
  with patch.object(a.os,'geteuid',return_value=0),patch.object(a.router,'main',return_value='restored') as run,patch.object(a,'platform_checks') as checks:
   self.assertEqual(a.main('rollback'),'restored')
  run.assert_called_once_with('rollback');checks.assert_not_called()
 def test_failed_final_acceptance_rolls_back_without_writing_handover(self):
  core=SimpleNamespace(load=Mock(return_value={'fixture':True}),rollback=Mock())
  check=SimpleNamespace(capture=Mock(side_effect=ValueError('timer missing')),finish=Mock())
  with patch.dict(sys.modules,{'postcheck':check}):
   with self.assertRaises(ValueError):a.complete(core)
  core.rollback.assert_called_once_with({'fixture':True});check.finish.assert_not_called()
 def test_handover_runs_only_with_verified_final_receipt(self):
  core=SimpleNamespace(load=Mock(return_value={'fixture':True}),rollback=Mock())
  check=SimpleNamespace(capture=Mock(return_value={'ok':True}),finish=Mock())
  with patch.dict(sys.modules,{'postcheck':check}):a.complete(core)
  check.finish.assert_called_once_with(core,live={'ok':True});core.rollback.assert_not_called()
 def test_release_scope_and_rollback_cache_exclude_unrelated_old_candidates(self):
  m=json.loads((a.KIT/'release.json').read_text())
  self.assertEqual(set(m['changed_services']),{'backend','mdns','homecontrol-ha-growatt-poller'})
  self.assertEqual(set(m['recovery_images']),{v['image'] for v in m['baseline'].values()}|set(m['images'].values()))
  self.assertFalse((a.KIT/'source/infra/backend/repository_service.py').exists())
  self.assertTrue((a.KIT/'source/infra/backend/mower_v3_protocol.py').is_file())
if __name__=='__main__':unittest.main(verbosity=2)
