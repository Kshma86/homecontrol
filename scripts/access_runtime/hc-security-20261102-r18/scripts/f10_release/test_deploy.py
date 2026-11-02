"""Transaction fault injection and release boundary regression tests."""
import importlib.util,json,sys,tempfile,unittest,subprocess,tarfile,shutil
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('r13',Path(__file__).with_name('deploy.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class Fault(Exception):pass
class Fixture:
 def __init__(self,fail=None):self.events=[];self.fail=fail
 def event(self,name):
  self.events.append(name)
  if self.fail==name:raise Fault(name)
 def quiesce(self):self.event('quiesce')
 def stop(self):self.event('stop')
 def install(self):self.event('install')
 def start(self):self.event('start')
 def verify(self):self.event('verify')
 def resume(self):self.event('resume')
 def rollback(self):self.event('rollback')
class CutoverTests(unittest.TestCase):
 def test_success(self):
  c=Fixture();r.switch(c);self.assertEqual(c.events,['quiesce','stop','install','start','verify','resume'])
 def test_pre_stop_failure_only_resumes_watchers(self):
  c=Fixture('quiesce')
  with self.assertRaises(Fault):r.switch(c)
  self.assertEqual(c.events,['quiesce','resume'])
 def test_every_mutating_phase_rolls_back(self):
  for phase in ('stop','install','start','verify','resume'):
   with self.subTest(phase=phase):
    c=Fixture(phase)
    with self.assertRaises(Fault):r.switch(c)
    self.assertEqual(c.events[-1],'rollback')
 def test_keyboard_interrupt_after_partial_stop_rolls_back(self):
  c=Fixture()
  def interrupted():c.events.append('stop');raise KeyboardInterrupt()
  c.stop=interrupted
  with self.assertRaises(KeyboardInterrupt):r.switch(c)
  self.assertEqual(c.events,['quiesce','stop','rollback'])
 def test_later_release_blocks_rollback_before_any_stop(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);(base/'infra').mkdir();(base/'infra/access-release.json').write_text('{"release":"later"}')
   with patch.object(r,'BASE',base),patch.object(r,'platform',return_value=None),patch.object(r,'call') as call:
    with self.assertRaises(ValueError):r.rollback({})
    call.assert_not_called()
 def test_scope_and_persistent_volumes(self):
  k=r.KIT;m=json.loads((k/'release.json').read_text());before=json.loads((r.BASE/'infra/docker-compose.yml').read_text());after=json.loads((k/'source/runtime.compose.json').read_text())
  expected={'zigbee2mqtt', 'homecontrol-ha-growatt-poller', 'backend', 'pgbouncer', 'mdns', 'proxy', 'hc_ingest', 'homecontrol-gree-climate', 'frontend', 'homecontrol-xiaomi-x10', 'mqtt', 'ai-server', 'homecontrol-tuya-poller', 'postgres'}
  self.assertEqual(set(m['changed_services']),expected)
  for name,old in before['services'].items():
   new=after['services'][name]
   if name not in expected:self.assertEqual(old,new,name);continue
   edited=dict(new);edited['image']=old['image']
   edited.pop('pull_policy',None)
   if 'pull_policy' in old:edited['pull_policy']=old['pull_policy']
   edited['volumes']=[{k:v.replace('/'+r.NAME+'/', '/'+r.OLD+'/') if k=='source' else v for k,v in row.items()} for row in edited.get('volumes',[])]
   if not edited['volumes'] and 'volumes' not in old:edited.pop('volumes')
   edited['env_file']=[{k:v.replace('/'+r.NAME+'/', '/'+r.OLD+'/') if k=='path' else v for k,v in row.items()} for row in edited.get('env_file',[])]
   if not edited['env_file'] and 'env_file' not in old:edited.pop('env_file')
   self.assertEqual(old,edited,name)
 def test_platform_paths_and_cache_exclusion(self):
  s=r.KIT/'source'
  for name in ('canonical_backup_runner.py','scripts/install_restore_host.py','scripts/restore_runtime.py','scripts/bootstrap_restore_v0_1.sh','scripts/access_release/common.py'):
   data=(s/name).read_text();self.assertNotIn(r.OLD,data,name)
   original=(r.OLD_RUNTIME/name).read_text()
   if r.OLD in original:self.assertIn(r.NAME,data,name)
  self.assertIn("--exclude 'ssh/*/images'",(s/'scripts/backup_archive_worker.sh').read_text())
  self.assertIn("TABLE='hc41_r10'",(s/'scripts/access_release/network.py').read_text())
 def test_robot_guard_never_accepts_active_remote_state(self):
  m=json.loads((r.KIT/'release.json').read_text())
  fake=m['baseline'];result=type('Result',(),{})
  def command(args,**kw):
   row=fake[args[-1]];return type('R',(),{'stdout':json.dumps([{'Id':row['id'],'Image':row['image']}]).encode()})()
  with patch.object(r,'call',side_effect=command),patch.object(r,'active',return_value=True),patch.object(r,'request',side_effect=[{'ok':True},{'robot_state':2}]):
   with self.assertRaisesRegex(ValueError,'Robot'):r.guard_runtime(m)
 def test_encrypted_bundle_roundtrip_without_host_secrets(self):
  common=r.platform()
  sys.path.insert(0,str(r.KIT/'source/scripts'))
  from restore_archive import secrets as extract
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);base=root/'project';kit=root/'kit';private=kit/'private';private.mkdir(parents=True)
   identity=base/'infra/ssh/homecontrol-secrets-age-key.txt';identity.parent.mkdir(parents=True)
   subprocess.run(['age-keygen','-o',str(identity)],check=True,capture_output=True)
   recipient=subprocess.check_output(['age-keygen','-y',str(identity)],text=True).strip()
   (base/'secrets').mkdir();(base/'secrets/age-recipient.txt').write_text(recipient)
   existing=root/'existing';existing.mkdir();(existing/'SECRETS_BUNDLE_CONTENTS.txt').write_text('fixture\n')
   old=root/'old.tar.gz'
   with tarfile.open(old,'w:gz') as tar:tar.add(existing,arcname='.')
   subprocess.run(['age','-r',recipient,'-o',str(base/'secrets/homecontrol-secrets-latest.tar.gz.age'),str(old)],check=True,capture_output=True)
   (base/'infra/ssh/test-key').write_text('fake-key-only')
   (base/'secrets/manifest.txt').write_text('infra/ssh/test-key\ninfra/ssh/homecontrol-secrets-age-key.txt\n')
   runtime=private/'runtime';(runtime/'compose-env').mkdir(parents=True);(runtime/'images').mkdir()
   (runtime/'compose-env/backend.env').write_text('FIXTURE=yes\n');(runtime/'images/archive').write_text('omit')
   with patch.object(r,'BASE',base),patch.object(r,'KIT',kit),patch.object(r,'PRIVATE',base/'infra/ssh'/r.NAME),patch.object(r,'platform',return_value=common):
    r.encrypted_bundle(runtime)
   decoded=root/'decoded.tar.gz';decoded.write_bytes(subprocess.check_output(['age','-d','-i',str(identity),str(private/'homecontrol-secrets-r13.tar.gz.age')]))
   checked=root/'checked';extract(decoded,checked)
   files={str(f.relative_to(checked)) for f in checked.rglob('*') if f.is_file()}
   self.assertIn('srv/docker/homecontrol/infra/ssh/test-key',files)
   self.assertIn('srv/docker/homecontrol/infra/ssh/'+r.NAME+'/compose-env/backend.env',files)
   self.assertFalse(any('images' in name or 'age-key' in name for name in files))
   self.assertTrue(json.loads((private/'secret-receipt.json').read_text())['roundtrip_verified'])
 def test_secret_allowlist(self):
  self.assertEqual(r.secret_archive_name(Path('/etc/homecontrol/restic-password')),Path('/etc/homecontrol/restic-password'))
  for name in ('/home/a/key','/etc/shadow'):
   with self.assertRaises(ValueError):r.secret_archive_name(Path(name))
 def test_cloud_credential_copy_preserves_original_and_readonly_copy(self):
  spec=importlib.util.spec_from_file_location('smoke',Path(__file__).with_name('cloud_smoke.py'))
  smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source';target=Path(tmp)/'copy';source.write_text('fake-session');source.chmod(0o600)
   smoke.prepare_auth(source,target)
   self.assertEqual(target.read_text(),'fake-session')
   self.assertEqual(target.stat().st_mode&0o777,0o400)
   self.assertEqual(source.stat().st_mode&0o777,0o600)
 def test_cloud_acceptance_requires_verified_result_and_pins_receipt(self):
  import sys
  sys.path.insert(0,str(Path(__file__).parent))
  import activate
  common=activate.release.platform()
  with tempfile.TemporaryDirectory() as tmp:
   kit=Path(tmp);(kit/'evidence').mkdir()
   (kit/'evidence/xiaomi-approval.json').write_text('{"saved_xiaomi_session_use":true,"robot_commands":false}')
   (kit/'evidence/x10-cloud.json').write_text('{"ok":false}')
   with patch.object(activate.release,'KIT',kit),patch.object(activate.release,'load',return_value={}),patch.object(activate.release,'platform'):
    with self.assertRaises(ValueError):activate.accept_cloud()
   self.assertFalse((kit/'release.json').exists())
   (kit/'evidence/x10-cloud.json').write_text(json.dumps({'ok':True,'robot_commands_sent':False,'cloud_tls_and_saved_session':True,'map_downloaded_and_json_decoded':True}))
   (kit/'evidence/acceptance.json').write_text('{"ok":false,"pending":["cloud"],"evidence_sha256":{}}')
   with patch.object(activate.release,'KIT',kit),patch.object(activate.release,'load',return_value={'source_sha256':{'source':'pinned'}}),patch.object(activate.release,'platform',return_value=common):
    activate.accept_cloud()
   final=json.loads((kit/'release.json').read_text());report=json.loads((kit/'evidence/acceptance.json').read_text())
   self.assertTrue(final['ready_for_root_deploy']);self.assertTrue(report['ok']);self.assertEqual(report['pending'],[])
   self.assertEqual(final['source_sha256'],{'source':'pinned'})
   self.assertEqual(final['acceptance_sha256'],r.digest(kit/'evidence/acceptance.json'))
   self.assertEqual(report['evidence_sha256']['x10-cloud.json'],r.digest(kit/'evidence/x10-cloud.json'))
 def test_actual_install_holds_both_real_locks_with_common_without_locked(self):
  common=r.platform()
  import install
  self.assertFalse(hasattr(common,'locked'))
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);(base/'backups').mkdir()
   for name in ('ai-backup.lock','homecontrol-backup.lock'):(base/'backups'/name).touch()
   before={p.name:p.stat().st_ino for p in (base/'backups').iterdir()}
   def held(*args):
    for file in (base/'backups').iterdir():
     with file.open('a') as handle:
      with self.assertRaises(BlockingIOError):r.fcntl.flock(handle,r.fcntl.LOCK_EX|r.fcntl.LOCK_NB)
   with patch.object(install,'BASE',base),patch.object(r,'phase'),patch.object(r,'reconcile',side_effect=held) as reconcile,patch.object(r,'install_files',side_effect=held) as install_files:
    r.Cutover({},{}).install()
    reconcile.assert_called_once_with('deploy');install_files.assert_called_once_with({})
   self.assertEqual(before,{p.name:p.stat().st_ino for p in (base/'backups').iterdir()})
   with r.ExitStack() as stack:
    with patch.object(install,'BASE',base):r.locked(stack)
 def test_actual_rollback_uses_real_lock_adapter(self):
  common=r.platform()
  import install
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);(base/'backups').mkdir();(base/'infra').mkdir();state=base/'state';state.mkdir()
   (base/'infra/access-release.json').write_text(json.dumps({'release':r.OLD}))
   (state/'transition.json').write_text(json.dumps({'release':r.NAME,'active_timers':{'fixture.timer':True}}))
   for name in ('ai-backup.lock','homecontrol-backup.lock'):(base/'backups'/name).touch()
   def held(*args):
    for file in (base/'backups').iterdir():
     with file.open('a') as handle:
      with self.assertRaises(BlockingIOError):r.fcntl.flock(handle,r.fcntl.LOCK_EX|r.fcntl.LOCK_NB)
   with patch.object(r,'BASE',base),patch.object(install,'BASE',base),patch.object(r,'STATE',state),patch.object(r,'phase'),patch.object(r,'active',return_value=False),patch.object(r,'idle'),patch.object(r,'call') as call,patch.object(r,'reconcile',side_effect=held),patch.object(common,'restore_snapshot',side_effect=held),patch.object(r,'wait_ready') as ready:
    r.rollback({'changed_services':['backend']})
    ready.assert_called_once_with({'changed_services':['backend']},previous=True)
    self.assertEqual(json.loads((state/'result.json').read_text())['state'],'rolled_back')
    self.assertIn(unittest.mock.call(['systemctl','start','fixture.timer']),call.call_args_list)
 def test_real_file_install_and_snapshot_rollback_in_fixture_root(self):
  common=r.platform()
  import install
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp)/'project';kit=Path(tmp)/'kit';source=kit/'source';state=kit/'private/transition'
   shutil.copytree(r.KIT/'source',source,ignore=shutil.ignore_patterns('__pycache__'))
   runtime=base/'scripts/access_runtime'/r.NAME;private=base/'infra/ssh'/r.NAME;units=base/'etc-systemd'
   stage=kit/'private/runtime';(stage/'mqtt/broker').mkdir(parents=True);(stage/'mqtt/credentials').mkdir()
   (stage/'mqtt/broker/mosquitto.conf').write_text('fixture')
   (stage/'mqtt/credentials/backend.password').write_text('fake-password')
   (base/'backups/ai-control').mkdir(parents=True);(base/'infra/private').mkdir(parents=True);(base/'secrets').mkdir()
   for name in ('ai-backup.lock','homecontrol-backup.lock'):(base/'backups'/name).touch()
   before={base/'infra/docker-compose.yml':b'{"fixture":"old"}\n',base/'infra/access-release.json':json.dumps({'release':r.OLD}).encode(),base/'secrets/manifest.txt':b'# fixture\n',base/'secrets/homecontrol-secrets-latest.tar.gz.age':b'old-encrypted-fixture'}
   for file,data in before.items():file.write_bytes(data)
   (kit/'private/homecontrol-secrets-r13.tar.gz.age').write_bytes(b'new-encrypted-fixture')
   def map_path(value):return units if str(value)=='/etc/systemd/system' else Path(value)
   real_units=common.units
   with patch.object(r,'BASE',base),patch.object(r,'KIT',kit),patch.object(r,'RUNTIME',runtime),patch.object(r,'PRIVATE',private),patch.object(r,'STATE',state),patch.object(r,'UNIT_ROOT',units),patch.object(install,'BASE',base),patch.object(install,'RUNTIME',runtime),patch.object(install,'PRIVATE',private),patch.object(install,'Path',side_effect=map_path),patch.object(install,'units',side_effect=lambda src:real_units(src,runtime=runtime)),patch.object(install.os,'chown') as chown,patch.object(install,'call') as unit_call:
    common.snapshot(r.target_files(),state)
    common.write_json(state/'transition.json',{'release':r.NAME,'active_timers':{'fixture.timer':True}})
    r.install_files({'offline_image_archive_sha256':'fixture-sha'})
    self.assertEqual(json.loads((base/'infra/access-release.json').read_text())['release'],r.NAME)
    self.assertEqual((base/'infra/docker-compose.yml').read_bytes(),(source/'runtime.compose.json').read_bytes())
    self.assertEqual((private/'mqtt/credentials/backend.password').stat().st_mode&0o777,0o400)
    self.assertTrue((units/'homecontrol-hostops.service').exists())
    unit_call.assert_called_once_with(['systemctl','daemon-reload'])
    self.assertIn(unittest.mock.call(private/'mqtt/credentials/backend.password',10001,10001),chown.call_args_list)
    def ready(*args,**kwargs):
     for file,data in before.items():self.assertEqual(file.read_bytes(),data)
    with patch.object(r,'phase'),patch.object(r,'active',return_value=False),patch.object(r,'idle'),patch.object(r,'call') as call,patch.object(r,'reconcile') as reconcile,patch.object(r,'wait_ready',side_effect=ready):
     r.rollback({'changed_services':['backend']})
     reconcile.assert_called_once_with('rollback')
     self.assertIn(unittest.mock.call(['systemctl','start','homecontrol-hostops.service']),call.call_args_list)
    self.assertFalse((units/'homecontrol-hostops.service').exists())
    self.assertEqual(json.loads((state/'result.json').read_text())['state'],'rolled_back')
 def test_phase_receipts_have_public_metadata_and_private_copy(self):
  with tempfile.TemporaryDirectory() as tmp:
   kit=Path(tmp)
   with patch.object(r,'KIT',kit):r.phase('preflight_common_locks')
   public=kit/'deployment-status.json';private=kit/'private/progress.json'
   self.assertEqual(json.loads(public.read_text()),json.loads(private.read_text()))
   self.assertEqual(set(json.loads(public.read_text())),{'phase','timestamp'})
   self.assertEqual(public.stat().st_mode&0o777,0o644)
   self.assertEqual(private.stat().st_mode&0o777,0o600)
if __name__=='__main__':unittest.main(verbosity=2)
