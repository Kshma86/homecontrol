import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

spec=importlib.util.spec_from_file_location('r23_inventory_resume',Path(__file__).with_name('resume_r23_inventory.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def diagnosis():
    return {'active_release':m.OLD,'worker_active':False,'new_runtime_exists':False,'new_private_exists':False,
        'recorded_error_type':'RuntimeError','recorded_phase':'starting',
        'private_entries_present':{'activation-attempt.json':True,'activation-error.json':True,
            'activation-private.log':True,'progress.json':False,'paused-units.json':False,'pre-proof.json':False,
            'post-proof.json':False,'runtime':False,'transition':False},
        'private_log':{'tail_only':False,'last_command_kind':'zigbee_bridge_devices_read',
            'conditions':['mqtt_probe_no_message','private_command_failed'],
            'error_types':['RuntimeError','TimeoutError'],
            'traceback_frames':[{'file':'activate.py','function':'bridge','line':68}]}}


class ExactFailureGuard(unittest.TestCase):
    def test_only_proven_pre_transition_failure_is_accepted(self):m.validate_diagnosis(diagnosis())

    def test_active_worker_or_later_release_is_rejected(self):
        for key,value in [('worker_active',True),('active_release',m.NAME),('active_release','later')]:
            row=diagnosis();row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_diagnosis(row)

    def test_any_progress_or_private_stage_is_rejected(self):
        for key in ('progress.json','paused-units.json','pre-proof.json','post-proof.json','runtime','transition'):
            row=diagnosis();row['private_entries_present'][key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_diagnosis(row)
        for key in ('new_runtime_exists','new_private_exists'):
            row=diagnosis();row[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_diagnosis(row)

    def test_missing_original_evidence_is_rejected(self):
        for key in m.PRESERVED:
            row=diagnosis();row['private_entries_present'][key]=False
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_diagnosis(row)

    def test_other_failure_or_truncated_log_is_rejected(self):
        for key,value in [('tail_only',True),('last_command_kind','zigbee_bridge_info_read'),
                          ('conditions',['private_command_failed']),('error_types',['RuntimeError']),
                          ('traceback_frames',[])]:
            row=diagnosis();row['private_log'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_diagnosis(row)

    def test_later_phase_is_rejected(self):
        row=diagnosis();row['recorded_phase']='post_full_backup'
        with self.assertRaises(ValueError):m.validate_diagnosis(row)


class NarrowAdapter(unittest.TestCase):
    def test_frozen_execution_and_all_cutover_callbacks_are_unchanged(self):
        executor=m.load('r23_narrow_adapter_test',m.ORIGINAL/'source/scripts/container_update/activate.py')
        before={name:getattr(executor,name) for name in ('execute','Cutover','rollback_once','private_mqtt_probe','settle','platform_probes')}
        methods={name:getattr(executor.Cutover,name) for name in ('quiesce','stop','install','start','verify','resume','rollback')}
        helper=SimpleNamespace();core=SimpleNamespace(phase=Mock());inventory=SimpleNamespace(bridge=Mock())
        m.wire(executor,helper,inventory,core)
        self.assertIs(executor.bridge,inventory.bridge)
        for name,value in before.items():self.assertIs(getattr(executor,name),value)
        for name,value in methods.items():self.assertIs(getattr(executor.Cutover,name),value)

    def test_root_is_required_before_diagnosis_or_start(self):
        with patch.object(m.os,'geteuid',return_value=1000),patch.object(m,'guard') as guard,patch.object(m.subprocess,'run') as run:
            with self.assertRaises(PermissionError):m.main()
            guard.assert_not_called();run.assert_not_called()


if __name__=='__main__':unittest.main()
