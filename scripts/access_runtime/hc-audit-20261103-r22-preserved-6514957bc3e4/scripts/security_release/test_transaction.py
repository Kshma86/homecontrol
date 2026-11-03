"""HA transaction fault injection: synthetic files, no Docker/systemd/network."""
import importlib.util,json,os,io
from pathlib import Path
import shutil,sqlite3,sys,tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import ha_state
spec=importlib.util.spec_from_file_location('security_activation',HERE/'activate.py')
activate=importlib.util.module_from_spec(spec);spec.loader.exec_module(activate)


class StateTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.source=self.root/'original';self.source.mkdir(mode=0o750)
  (self.source/'configuration.yaml').write_text('default_config:\n')
  (self.source/'.storage').mkdir();(self.source/'.storage/auth').write_text('synthetic auth only')
  (self.source/'.storage/auth').chmod(0o600)
  with sqlite3.connect(self.source/'home-assistant_v2.db') as db:
   db.execute('create table events(value text)');db.execute("insert into events values('original')")
  self.backup=self.root/'backup';ha_state.capture(self.source,self.backup)
  self.live=self.root/'live';shutil.copytree(self.source,self.live)

 def test_verified_snapshot_restores_original_database_auth_and_directory_modes(self):
  (self.live/'.storage/auth').write_text('candidate')
  with sqlite3.connect(self.live/'home-assistant_v2.db') as db:db.execute("insert into events values('candidate')")
  quarantine=ha_state.replace(self.backup,self.live)
  self.assertTrue(quarantine.is_dir());self.assertEqual((self.live/'.storage/auth').read_text(),'synthetic auth only')
  with sqlite3.connect(self.live/'home-assistant_v2.db') as db:self.assertEqual(db.execute('select value from events').fetchall(),[('original',)])
  self.assertEqual(self.live.stat().st_mode&0o777,0o750)

 def test_second_rename_failure_preserves_current_config(self):
  real=os.replace;calls=[]
  def fail(source,target):
   calls.append((source,target))
   if len(calls)==2:raise OSError('synthetic second rename failure')
   return real(source,target)
  with patch.object(ha_state.os,'replace',side_effect=fail),self.assertRaises(OSError):ha_state.replace(self.backup,self.live)
  self.assertTrue((self.live/'.storage/auth').is_file());self.assertEqual(len(calls),3)

 def test_corrupt_backup_fails_before_moving_live_config(self):
  (self.backup/'.storage/auth').write_text('corrupt')
  with patch.object(ha_state.os,'replace') as rename,self.assertRaises(ValueError):ha_state.replace(self.backup,self.live)
  rename.assert_not_called()

 def test_receipt_path_escape_fails_before_any_rename(self):
  p=self.backup/'.hc-snapshot.json';m=json.loads(p.read_text());m['files']['../outside']=m['files'].pop('configuration.yaml');p.write_text(json.dumps(m))
  with patch.object(ha_state.os,'replace') as rename,self.assertRaises(ValueError):ha_state.replace(self.backup,self.live)
  rename.assert_not_called()

 def test_snapshot_symlink_fails_before_external_file_is_read(self):
  (self.source/'link').symlink_to(self.root/'outside')
  with self.assertRaises(ValueError):ha_state.capture(self.source,self.root/'another')


class HookTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.base=Path(self.temp.name);self.kit=self.base/'kit';(self.kit/'private').mkdir(parents=True)
  (self.base/'infra').mkdir();(self.base/'infra/access-release.json').write_text('{"release":"new"}')
  self.state=self.kit/'private/transition';self.state.mkdir();(self.state/'transition.json').write_text('{"release":"new"}')
  self.events=[]
  class Cutover:
   def stop(inner):self.events.append('stop_core')
   def start(inner):self.events.append('start_core')
   def verify(inner):self.events.append('verify_core')
  def write(path,value,*args):
   path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
  self.platform=SimpleNamespace(write_json=write)
  self.core=SimpleNamespace(NAME='new',OLD='old',STATE=self.state,Cutover=Cutover,
   target_files=lambda:[],install_files=lambda m:self.events.append('install_core'),
   rollback=lambda m:self.events.append('rollback_core'),platform=lambda:self.platform,
   phase=lambda n:None,call=Mock(),idle=Mock())
  self.router=SimpleNamespace(core=self.core,install_hooks=lambda c:self.kit/'pending')
  self.manifest={'homeassistant_image':'sha256:'+'2'*64,'baseline':{'homeassistant':{'image':'sha256:'+'1'*64}}}
  for name,value in (('BASE',self.base),('KIT',self.kit),('SOURCE',self.kit/'source')):
   p=patch.object(activate,name,value);p.start();self.addCleanup(p.stop)
  self.capture=patch.object(activate,'capture',return_value={'sqlite':{'consistent_online_copy':True}}).start();self.addCleanup(patch.stopall)
  self.rollback=activate.install_hooks(self.router,self.manifest);self.router.install_hooks({})
  self.context=Cutover()

 def test_stop_is_journaled_before_docker_stop_is_attempted(self):
  def stop(args,**kwargs):
   self.assertTrue(json.loads((self.kit/'private/ha-state.json').read_text())['stopped'])
   raise InterruptedError('after Docker accepted stop')
  self.core.call.side_effect=stop
  with self.assertRaises(InterruptedError):self.context.stop()
  self.assertNotIn('stop_core',self.events)

 def test_partial_stop_rollback_restarts_previous_ha_without_replacing_database(self):
  self.context.stop()
  with patch.object(activate,'ha_command') as start,patch.object(activate,'ha_ready'),patch.object(activate,'replace') as restore:
   self.core.rollback(self.manifest)
  restore.assert_not_called();start.assert_called_once_with(self.core,self.manifest,previous=True)
  self.assertIn('rollback_core',self.events)

 def test_new_ha_start_is_marked_before_it_can_migrate_data(self):
  self.context.stop()
  def start(core,m):self.assertTrue(json.loads((self.kit/'private/ha-state.json').read_text())['data_may_be_upgraded'])
  with patch.object(activate,'ha_command',side_effect=start):self.context.start()

 def test_upgraded_database_is_restored_before_core_rollback(self):
  self.context.stop()
  with patch.object(activate,'ha_command'):self.context.start()
  with patch.object(activate,'replace',side_effect=lambda *a:self.events.append('restore_db')),patch.object(activate,'ha_command'),patch.object(activate,'ha_ready'):
   self.rollback(self.manifest)
  self.assertLess(self.events.index('restore_db'),self.events.index('rollback_core'))

 def test_later_release_blocks_rollback_before_any_stop(self):
  (self.base/'infra/access-release.json').write_text('{"release":"later"}')
  with self.assertRaises(ValueError):self.core.rollback(self.manifest)
  self.core.call.assert_not_called()

 def test_busy_backup_blocks_rollback_before_any_ha_change(self):
  self.context.stop();self.core.call.reset_mock();self.core.idle.side_effect=ValueError('busy')
  with self.assertRaises(ValueError):self.core.rollback(self.manifest)
  self.core.call.assert_not_called()

 def test_missing_transition_blocks_rollback_before_any_ha_change(self):
  (self.state/'transition.json').unlink()
  with self.assertRaises(FileNotFoundError):self.core.rollback(self.manifest)
  self.core.call.assert_not_called()

 def test_nonroot_entrypoint_cannot_read_private_state_or_load_core(self):
  with patch.object(activate.os,'geteuid',return_value=1000),patch.object(activate,'load_router') as load:
   with self.assertRaises(PermissionError):activate.main()
  load.assert_not_called()


class PostgreSQLReadinessTests(unittest.TestCase):
 def test_existing_collation_mismatch_blocks_acceptance_without_database_mutation(self):
  core=SimpleNamespace(call=Mock(return_value=SimpleNamespace(stdout=b'{"major":16,"recorded":"2.41","actual":"2.42"}')))
  with self.assertRaises(ValueError):activate.postgres_ready(core)
  sql=core.call.call_args.kwargs['input'].decode()
  self.assertTrue(sql.startswith('SELECT '));self.assertNotIn('ALTER',sql);self.assertNotIn('REINDEX',sql)

 def test_matching_postgres_16_collation_is_accepted(self):
  core=SimpleNamespace(call=Mock(return_value=SimpleNamespace(stdout=b'{"major":16,"recorded":"2.41","actual":"2.41"}')))
  self.assertTrue(activate.postgres_ready(core)['ok'])


class AuthenticatedReadinessTests(unittest.TestCase):
 def test_existing_token_is_used_only_on_loopback_and_not_in_public_receipt(self):
  with tempfile.TemporaryDirectory() as directory:
   base=Path(directory);kit=base/'kit';(kit/'private').mkdir(parents=True)
   credential=base/'infra/ssh/old/compose-env/growatt.env';credential.parent.mkdir(parents=True)
   credential.write_text('HA_TOKEN=synthetic-private-token\n');credential.chmod(0o600)
   (base/'infra/docker-compose.yml').write_text(json.dumps({'services':{'homecontrol-ha-growatt-poller':{'env_file':[{'path':str(credential)}]}}}))
   storage=base/'homeassistant/config/.storage';storage.mkdir(parents=True)
   (storage/'core.entity_registry').write_text(json.dumps({'data':{'entities':[{'platform':'growatt_server','entity_id':'sensor.fixture'}]}}))
   def write(path,value,*args):Path(path).write_text(json.dumps(value))
   core=SimpleNamespace(call=lambda *a,**k:SimpleNamespace(stdout=json.dumps([{'Image':'old','State':{'Running':True}}])),
        platform=lambda:SimpleNamespace(no_symlinks=lambda p:None,write_json=write))
   manifest={'baseline':{'homeassistant':{'image':'old'}},'homeassistant_image':'new'}
   response=io.BytesIO(json.dumps([{'entity_id':'sensor.fixture','state':'42'}]).encode());response.status=200
   with patch.object(activate,'BASE',base),patch.object(activate,'KIT',kit),patch.object(activate.urllib.request,'urlopen',return_value=response) as request:
    report=activate.ha_ready(core,manifest,previous=True)
   req=request.call_args.args[0]
   self.assertEqual(req.full_url,'http://127.0.0.1:8123/api/states')
   self.assertEqual(req.get_header('Authorization'),'Bearer synthetic-private-token')
   self.assertEqual(report['previously_available_growatt_entities_preserved'],1)
   self.assertNotIn('synthetic-private-token',json.dumps(report))


if __name__=='__main__':unittest.main()
