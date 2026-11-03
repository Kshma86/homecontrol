import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

s=importlib.util.spec_from_file_location('r23_broker_owner',Path(__file__).with_name('mqtt_probe_owner.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class BrokerOwner(unittest.TestCase):
    def command(self):
        return ['docker','run','--network','none','--read-only','--user','0:0','--cap-drop','ALL',
            '--cap-add','SETUID','--cap-add','SETGID','--security-opt','no-new-privileges',
            '--mount','type=bind,src=/stage/mqtt/broker,dst=/mosquitto/config,readonly',
            '--entrypoint','mosquitto','candidate','-c','/mosquitto/config/mosquitto.conf','--test-config']

    def test_only_uid_and_root_capabilities_change(self):
        original=self.command();result=m.broker_command(original,Path('/stage'),'candidate')
        self.assertEqual(result[result.index('--user')+1],'1883:1883');self.assertNotIn('--cap-add',result)
        expected=original.copy();expected[expected.index('--user')+1]='1883:1883'
        for value in ('SETUID','SETGID'):
            index=expected.index('--cap-add');self.assertEqual(expected[index+1],value);del expected[index:index+2]
        self.assertEqual(result,expected);self.assertEqual(original,self.command())

    def test_authentication_client_keeps_its_original_user_and_mounts(self):
        args=['docker','run','--network','container:synthetic','--user','0:0','--entrypoint','python','backend','-c','auth']
        self.assertEqual(m.broker_command(args,Path('/stage'),'candidate'),args)

    def test_wrong_image_network_or_private_copy_is_rejected(self):
        for key,value in (('--network','host'),('--user','1000:1000'),('--cap-drop','NET_ADMIN'),
                          ('--mount','type=bind,src=/production,dst=/mosquitto/config,readonly')):
            args=self.command();args[args.index(key)+1]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.broker_command(args,Path('/stage'),'candidate')
        with self.assertRaises(ValueError):m.broker_command(self.command(),Path('/stage'),'different-image')

    def test_added_or_duplicate_capability_is_rejected(self):
        for flags in (['--cap-add','DAC_OVERRIDE'],['--cap-add','SETUID']):
            with self.subTest(flags=flags),self.assertRaises(ValueError):m.broker_command(self.command()+flags,Path('/stage'),'candidate')

    def test_helper_call_is_restored_after_broker_failure(self):
        helper=SimpleNamespace(call=Mock(side_effect=RuntimeError('synthetic failure')));before=helper.call
        def original(core,e,stage,source):e.call(self.command())
        executor=SimpleNamespace(private_mqtt_probe=original);core=SimpleNamespace(load=lambda:{'images':{'mqtt':'candidate'}})
        m.install(executor)
        with self.assertRaises(RuntimeError):executor.private_mqtt_probe(core,helper,Path('/stage'),Path('/source'))
        self.assertIs(helper.call,before)
