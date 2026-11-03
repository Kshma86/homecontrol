import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch

s=importlib.util.spec_from_file_location('container_activate',Path(__file__).with_name('activate.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
switch=m.load('reviewed_container_switch',m.BASE/'scripts/access_runtime/hc-audit-20261103-r22/scripts/f10_release/deploy.py').switch


class TransactionBoundaries(unittest.TestCase):
    def test_ordered_stop_and_start_cover_every_candidate_exactly_once(self):
        manifest=json.loads((m.KIT/'release.json').read_text());expected=set(manifest['changed_services'])
        started=[name for group in m.START_GROUPS for name in group]
        self.assertEqual(set(started),expected);self.assertEqual(len(started),len(expected))
        self.assertEqual(set(m.STOP_PEERS)|{'backend'},expected)
        self.assertEqual(len(m.STOP_PEERS)+1,len(expected))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.core=Mock();self.core.STATE=Path(self.temp.name);self.core.OLD_PRIVATE=Path('/old-private')
        self.core.container.side_effect=lambda name:'zigbee2mqtt' if name=='zigbee2mqtt' else 'homecontrol-'+name.removeprefix('homecontrol-')
        self.core.compose.return_value=['docker','compose','-f','reviewed.json']
        self.e=Mock();self.data=Mock();self.identities={'identities':['one','two']};self.firewall={'hash':'same'}
        self.manifest={'changed_services':['backend','frontend','proxy','homecontrol-gree-climate','homecontrol-xiaomi-x10','mqtt','zigbee2mqtt']}
        self.context=m.Cutover(self.core,self.e,self.manifest,{'x.timer':True},self.firewall,self.identities,self.data)
        self.patches=[patch.object(m,'read',return_value={'release':m.OLD}),
                      patch.object(m,'bridge',return_value=self.identities),
                      patch.object(m,'firewall',return_value=self.firewall),patch.object(m,'settle'),
                      patch.object(m,'platform_probes',return_value={}),
                      patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'[]',''))]
        for item in self.patches:item.start();self.addCleanup(item.stop)

    def test_failed_idle_guard_never_stops_apps(self):
        self.core.guard_runtime.side_effect=ValueError('busy')
        with self.assertRaises(ValueError):
            try:switch(self.context)
            except BaseException:m.rollback_once(self.context);raise
        self.e.call.assert_not_called();self.e.resume.assert_called_once_with({'x.timer':True})
        self.data.restore.assert_not_called()

    def test_physical_guard_failure_after_hostops_stop_leaves_apps_running(self):
        self.e.physical_guard.side_effect=ValueError('active irrigation')
        with self.assertRaises(ValueError):self.context.stop()
        m.rollback_once(self.context)
        commands=[c.args[0] for c in self.e.call.call_args_list]
        self.assertFalse(any(c[:2]==['docker','stop'] for c in commands))
        self.assertIn(['systemctl','start','homecontrol-hostops.service'],commands)

    def test_backend_stops_before_intent_handover_and_mqtt_stops_before_snapshot(self):
        timeline=[]
        self.e.call.side_effect=lambda args,**kw:timeline.append(args)
        self.core.reconcile.side_effect=lambda reason:timeline.append(['handover',reason])
        self.data.capture.side_effect=lambda path:timeline.append(['snapshot']) or {'captured':True}
        self.context.stop()
        self.assertLess(timeline.index(['docker','stop','--time','60','homecontrol-backend']),timeline.index(['handover','deploy']))
        self.assertLess(timeline.index(['docker','stop','--time','60','homecontrol-mqtt']),timeline.index(['snapshot']))

    def test_partial_stop_failure_rolls_back_only_once(self):
        self.core.reconcile.side_effect=[ValueError('handover failed'),None]
        with self.assertRaises(ValueError):
            try:switch(self.context)
            except BaseException:m.rollback_once(self.context);raise
        self.assertTrue(self.context.rollback_attempted)
        self.core.platform.return_value.restore_snapshot.assert_called_once()

    def test_mutable_data_restored_before_any_old_service_starts(self):
        saved=self.core.STATE/'application-data';saved.mkdir();(saved/'metadata.json').write_text('{}')
        self.context.app_stop_attempted=True;restored=[]
        self.data.restore.side_effect=lambda path:restored.append(True)
        def call(args,**kw):
            if args[:2]==['docker','compose']:self.assertTrue(restored)
        self.e.call.side_effect=call
        m.rollback_once(self.context);m.rollback_once(self.context)
        self.data.restore.assert_called_once_with(saved)

    def test_inaccessible_container_inspection_stops_rollback_before_data_replacement(self):
        self.context.app_stop_attempted=True
        saved=self.core.STATE/'application-data';saved.mkdir();(saved/'metadata.json').write_text('{}')
        with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','permission denied')):
            with self.assertRaises(RuntimeError):m.rollback_once(self.context)
        self.data.restore.assert_not_called()

    def test_unchanged_zigbee_identities_are_required(self):
        with patch.object(m,'bridge',return_value={'identities':['changed']}):
            with self.assertRaises(ValueError):self.context.verify()

    def test_successful_verify_does_not_resume_timers_before_post_backup(self):
        self.context.resume();self.e.resume.assert_not_called()

    def test_changed_firewall_prevents_any_candidate_service_start(self):
        with patch.object(m,'firewall',return_value={'hash':'changed'}):
            with self.assertRaises(ValueError):self.context.start()
        commands=[c.args[0] for c in self.e.call.call_args_list]
        self.assertFalse(any(c[:2]==['docker','compose'] for c in commands))

    def test_broker_and_zigbee_start_before_application_peers(self):
        self.context.start()
        commands=[c.args[0] for c in self.e.call.call_args_list]
        starts=[c for c in commands if c[:2]==['docker','compose']]
        self.assertEqual(starts[0][-1],'mqtt');self.assertEqual(starts[1][-1],'zigbee2mqtt')
        self.assertEqual(starts[-1][-3:],['backend','frontend','proxy'])


class CommandAdapter(unittest.TestCase):
    def test_expected_nonzero_status_is_returned_without_running_twice(self):
        e=Mock();e.LOG=io.StringIO();result=subprocess.CompletedProcess([],3,b'inactive\n',b'')
        with patch.object(m.subprocess,'run',return_value=result) as run:
            self.assertIs(m.adapter_call(e,['systemctl','is-active','a'],allowed=(0,3)),result)
        run.assert_called_once()

    def test_decrypted_secret_bundle_is_not_copied_into_command_log(self):
        e=Mock();e.LOG=io.StringIO();result=subprocess.CompletedProcess([],0,b'private-bundle-content',b'')
        with patch.object(m.subprocess,'run',return_value=result):
            self.assertEqual(m.adapter_call(e,['age','-d','-i','key','bundle']).stdout,b'private-bundle-content')
        self.assertNotIn('private-bundle-content',e.LOG.getvalue())


if __name__=='__main__':unittest.main()
