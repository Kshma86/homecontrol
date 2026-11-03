import importlib.util
from pathlib import Path
import unittest

s=importlib.util.spec_from_file_location('r23_diagnosis',Path(__file__).with_name('diagnose_start.py'))
d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


class Redaction(unittest.TestCase):
    def test_unrecognized_messages_and_argv_are_withheld(self):
        secret='private-token-do-not-publish'
        text='ValueError: '+secret+'\nCOMMAND '+repr(['curl','https://'+secret])
        result=d.summarize(text)
        self.assertNotIn(secret,str(result));self.assertEqual(result['conditions'],[])

    def test_dynamic_path_is_replaced_by_fixed_label(self):
        result=d.summarize('ValueError: Sealed source changed: confidential-file-name')
        self.assertEqual(result['conditions'],['sealed_source_changed'])
        self.assertNotIn('confidential-file-name',str(result))

    def test_host_postcheck_condition_and_stage_are_recognized(self):
        command=['/usr/bin/python3',str(d.BASE/'maintenance/host-update-20261103/source/check.py'),'postcheck']
        result=d.summarize('COMMAND '+repr(command)+'\n{"ok":false,"condition":"Other running containers require maintenance review"}\nRuntimeError: Command failed: /usr/bin/python3')
        self.assertEqual(result['last_command_kind'],'r22_host_postcheck')
        self.assertIn('other_container_running',result['conditions'])
        self.assertIn('private_command_failed',result['conditions'])

    def test_traceback_does_not_emit_private_directories_or_unknown_function(self):
        result=d.summarize('  File "/secret-token/activate.py", line 42, in secret_function')
        self.assertEqual(result['traceback_frames'],[{'file':'activate.py','line':42,'function':'withheld'}])
        self.assertNotIn('secret',str(result))


if __name__=='__main__':unittest.main()
