import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

s=importlib.util.spec_from_file_location('r23_owner_resume',Path(__file__).with_name('resume_r23_owner.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def report():
    return {'active_release':m.OLD,'original_worker_active':False,'continuation_worker_active':False,
        'transition_exists':False,'new_runtime_exists':False,'new_private_exists':False,
        'error':{'error_type':'RuntimeError','phase':'prepare_new_private_runtime'},
        'progress':{'phase':'prepare_new_private_runtime'},'original_evidence_preserved':{'ok':True,'files':3},
        'private_log':{'tail_only':False,'conditions':['mosquitto_config_unreadable','private_command_failed'],
            'error_types':['RuntimeError'],'traceback_frames':[{'file':'activate.py','function':'private_mqtt_probe','line':115}]},
        'pre_backup_restore':{'ok':True,'restore':'verified','database':'verified'},
        'broker_stage_directory':{'exists':True,'uid':1883,'gid':1883,'mode':'0o700'},
        'broker_stage_configuration':{'exists':True,'uid':1883,'gid':1883,'mode':'0o600'}}


class PrecisePreflight(unittest.TestCase):
    def test_exact_owner_failure_is_accepted(self):m.validate(report())

    def test_running_worker_new_release_or_cutover_is_rejected(self):
        for key,value in (('active_release',m.NAME),('original_worker_active',True),('continuation_worker_active',True),
                          ('transition_exists',True),('new_runtime_exists',True),('new_private_exists',True)):
            r=report();r[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate(r)

    def test_missing_restore_or_different_failure_is_rejected(self):
        for key in ('ok','restore','database'):
            r=report();r['pre_backup_restore'].pop(key)
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate(r)
        for key,value in (('tail_only',True),('conditions',['private_command_failed']),('error_types',['TimeoutError']),('traceback_frames',[])):
            r=report();r['private_log'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate(r)

    def test_altered_configuration_permissions_are_rejected(self):
        for key in ('broker_stage_directory','broker_stage_configuration'):
            r=report();r[key]['uid']=0
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate(r)

    def test_root_is_required_before_any_guard_or_start(self):
        with patch.object(m.os,'geteuid',return_value=1000),patch.object(m,'verify') as verify,patch.object(m.subprocess,'run') as run:
            with self.assertRaises(PermissionError):m.main()
            verify.assert_not_called();run.assert_not_called()

    def test_original_execution_and_cutover_callbacks_are_preserved(self):
        previous=m.load('owner_wire_previous_test',m.PREVIOUS/'source/resume_r23_inventory.py')
        executor=m.load('owner_wire_executor_test',m.ORIGINAL/'source/scripts/container_update/activate.py')
        owner=m.load('owner_wire_adapter_test',Path(__file__).with_name('mqtt_probe_owner.py'))
        inventory=SimpleNamespace(bridge=Mock());helper=SimpleNamespace();core=SimpleNamespace(phase=Mock())
        before={name:getattr(executor,name) for name in ('execute','Cutover','rollback_once','settle','platform_probes')}
        callbacks={name:getattr(executor.Cutover,name) for name in ('quiesce','stop','install','start','verify','resume','rollback')}
        m.wire(previous,executor,helper,inventory,owner,core)
        self.assertIs(executor.bridge,inventory.bridge)
        for name,value in before.items():self.assertIs(getattr(executor,name),value)
        for name,value in callbacks.items():self.assertIs(getattr(executor.Cutover,name),value)


class ExecutionPreservation(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);base=Path(temp.name)
        private=base/'original';private.mkdir();state=base/'continuation';state.mkdir()
        (private/'activation-attempt.json').write_text('original attempt')
        (private/'pre-proof.json').write_text('verified receipt')
        (private/'runtime').mkdir();(private/'runtime/private-config').write_text('synthetic private data')
        helper=SimpleNamespace(write=lambda path,data:Path(path).write_text(json.dumps(data)))
        return private,state,private/'preserved',helper

    def test_preservation_keeps_bytes_inodes_and_original_attempt(self):
        private,state,history,helper=self.fixture();before=(private/'runtime').stat().st_ino
        with patch.object(m,'PRIV',private),patch.object(m,'STATE',state),patch.object(m,'HISTORY',history):m.preserve(helper)
        self.assertEqual((private/'activation-attempt.json').read_text(),'original attempt')
        self.assertEqual((history/'pre-proof.json').read_text(),'verified receipt')
        self.assertEqual((history/'runtime/private-config').read_text(),'synthetic private data')
        self.assertEqual((history/'runtime').stat().st_ino,before)
        self.assertTrue(json.loads((state/'preservation.json').read_text())['completed'])

    def test_symlink_in_last_entry_prevents_all_moves(self):
        private,state,history,helper=self.fixture();(private/'zzz').symlink_to(state)
        with patch.object(m,'PRIV',private),patch.object(m,'STATE',state),patch.object(m,'HISTORY',history):
            with self.assertRaises(ValueError):m.preserve(helper)
        self.assertFalse(history.exists());self.assertTrue((private/'runtime').exists())

    def test_existing_preservation_is_never_overwritten(self):
        private,state,history,helper=self.fixture();history.mkdir();(history/'keep').write_text('kept')
        with patch.object(m,'PRIV',private),patch.object(m,'STATE',state),patch.object(m,'HISTORY',history):
            with self.assertRaises(ValueError):m.preserve(helper)
        self.assertEqual((history/'keep').read_text(),'kept');self.assertTrue((private/'pre-proof.json').exists())

    def test_partial_move_failure_is_journaled_without_deleting_any_data(self):
        private,state,history,helper=self.fixture();original=m.os.rename
        def rename(source,target):
            if Path(source).name=='runtime':raise OSError('synthetic rename failure')
            return original(source,target)
        with patch.object(m,'PRIV',private),patch.object(m,'STATE',state),patch.object(m,'HISTORY',history),patch.object(m.os,'rename',side_effect=rename):
            with self.assertRaises(OSError):m.preserve(helper)
        self.assertEqual((history/'pre-proof.json').read_text(),'verified receipt')
        self.assertEqual((private/'runtime/private-config').read_text(),'synthetic private data')
        journal=json.loads((state/'preservation.json').read_text());self.assertFalse(journal['completed'])
        self.assertEqual(journal['moved'],['pre-proof.json'])
