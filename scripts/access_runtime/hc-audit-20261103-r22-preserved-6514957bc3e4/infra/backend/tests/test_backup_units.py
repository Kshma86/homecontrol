"""F6 unit transition contract with fake managers and temporary installed units."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('f6_install',PROJECT/'scripts/install_backup_f6.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class Manager:
    def __init__(self):
        self.calls=[];self.fail_enable=None;self.bus_error=False
        self.enabled={('system','homecontrol-backup.timer'):True,('user','homecontrol-backup.timer'):True,('user','homecontrol-log-maintenance.timer'):True}
        self.active_services=set()
    def __call__(self,args,**kwargs):
        self.calls.append(args)
        scope='user' if args[0]=='runuser' else 'system'
        params=args[args.index('systemctl')+1:];params=[p for p in params if p!='--user'];command=params[0]
        if self.bus_error and scope=='user':return subprocess.CompletedProcess(args,1,'','bus unavailable')
        if command=='is-active':
            unit=params[-1]
            active=(scope,unit) in self.active_services if unit.endswith('.service') else self.enabled.get((scope,unit),False)
            return subprocess.CompletedProcess(args,0 if active else 3,'active' if active else 'inactive','')
        if command=='is-enabled':
            wanted=self.enabled.get((scope,params[-1]),False)
            return subprocess.CompletedProcess(args,0 if wanted else 1,'enabled' if wanted else 'disabled','')
        if command=='show' and any('NextElapse' in arg for arg in args):
            return subprocess.CompletedProcess(args,0,'NextElapseUSecRealtime=Tue 2026-10-27 02:15:00 CET\nNextElapseUSecMonotonic=0\n','')
        if command in ('enable','disable'):
            if self.fail_enable and command=='enable' and self.fail_enable in params:
                self.fail_enable=None;return subprocess.CompletedProcess(args,1,'','injected failure')
            for unit in params[1:]:
                if not unit.startswith('--'):self.enabled[(scope,unit)]=command=='enable'
        return subprocess.CompletedProcess(args,0,'','')


class BackupUnitTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'backups';self.units=Path(self.temp.name)/'system';self.units.mkdir()
        self.manager=Manager()
        self.patch_user=patch.object(module.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000));self.patch_user.start();self.addCleanup(self.patch_user.stop)
        self.patch_uid=patch.object(module.os,'geteuid',return_value=0);self.patch_uid.start();self.addCleanup(self.patch_uid.stop)

    def apply(self,**kwargs):return module.install(root=self.root,unit_dir=self.units,run=self.manager,**kwargs)

    def test_plan_is_read_only_and_chooses_only_system_scope(self):
        result=self.apply();self.assertFalse(result['applied']);self.assertFalse(self.manager.calls);self.assertFalse(self.root.exists())
        self.assertEqual(result['scope'],'system');self.assertEqual(set(result['retire_user_timers']),set(module.USER_TIMERS))

    def test_apply_disables_both_user_timers_and_installs_single_runner(self):
        result=self.apply(apply=True);self.assertTrue(result['applied'])
        self.assertTrue(self.manager.enabled[('system','homecontrol-backup.timer')])
        for name in module.USER_TIMERS:self.assertFalse(self.manager.enabled[('user',name)])
        for file in self.units.glob('*.service'):
            if 'apply' not in file.name:self.assertIn('backup_runner.py',file.read_text())
        self.assertTrue((self.root/'f6-installed.json').exists())

    def test_user_manager_error_refuses_before_any_unit_change(self):
        self.manager.bus_error=True
        with self.assertRaises(RuntimeError):self.apply(apply=True)
        self.assertFalse(list(self.units.iterdir()))
        self.assertFalse(any('disable' in c for c in self.manager.calls))

    def test_running_legacy_service_refuses_transition(self):
        for active in [('user','homecontrol-backup.service'),('system','homecontrol-backup-apply.service')]:
            with self.subTest(active=active):
                self.manager.active_services={active}
                with self.assertRaisesRegex(RuntimeError,'active'):self.apply(apply=True)
                self.assertFalse(list(self.units.iterdir()))

    def test_failure_restores_previous_units_and_enabled_states(self):
        old=self.units/'homecontrol-backup.service';old.write_text('old installed unit\n')
        self.manager.fail_enable='homecontrol-backup.timer'
        with self.assertRaises(RuntimeError):self.apply(apply=True)
        self.assertEqual(old.read_text(),'old installed unit\n')
        self.assertEqual([p.name for p in self.units.iterdir()],['homecontrol-backup.service'])
        for name in module.USER_TIMERS:self.assertTrue(self.manager.enabled[('user',name)])
        self.assertFalse((self.root/'f6-installed.json').exists())

    def test_operator_calendar_and_disabled_timer_are_preserved(self):
        self.root.mkdir();(self.root/'backup_settings.json').write_text(json.dumps({'schedule_time':'04:27','schedule_enabled':False,'ai_weekly_backup_schedule':'Sat 06:15','ai_weekly_backup_enabled':False}))
        self.apply(apply=True)
        self.assertIn('04:27:00',(self.units/'homecontrol-backup.timer').read_text())
        self.assertIn('Sat 06:15:00',(self.units/'homecontrol-ai-weekly-backup.timer').read_text())
        self.assertFalse(self.manager.enabled[('system','homecontrol-backup.timer')]);self.assertFalse(self.manager.enabled[('system','homecontrol-ai-weekly-backup.timer')])

    def test_invalid_settings_never_replace_schedules(self):
        self.root.mkdir();(self.root/'backup_settings.json').write_text('invalid')
        with self.assertRaises(ValueError):self.apply(apply=True)
        self.assertFalse(self.manager.calls)

    def test_apply_is_repeatable_without_changing_worker_paths(self):
        self.apply(apply=True);before={p.name:p.read_text() for p in self.units.iterdir()}
        self.apply(apply=True);self.assertEqual(before,{p.name:p.read_text() for p in self.units.iterdir()})

    def test_fresh_host_without_legacy_account_installs_full_manifest_twice(self):
        with patch.object(module.pwd,'getpwnam',side_effect=KeyError('no legacy user')), patch.object(module,'assert_no_user_units') as inventory:
            a=self.apply(apply=True,fresh_host=True,restore_host=True)
            before={p.name:p.read_text() for p in self.units.iterdir()}
            b=self.apply(apply=True,fresh_host=True,restore_host=True)
        self.assertEqual(inventory.call_count,2);self.assertEqual(len(a['units']),14)
        self.assertTrue(self.manager.enabled[('system','homecontrol-post-boot-health.timer')])
        self.assertIn('homecontrol-backup.timer',b['next_triggers'])
        self.assertIn('--restore-host',before['homecontrol-backup-apply.service'])
        self.assertEqual(before,{p.name:p.read_text() for p in self.units.iterdir()})
        self.assertFalse(any(c[0]=='runuser' for c in self.manager.calls))

    def test_fresh_host_dead_bus_with_existing_user_units_is_refused(self):
        self.manager.bus_error=True
        with patch.object(module,'assert_no_user_units',side_effect=RuntimeError('existing user units')):
            with self.assertRaisesRegex(RuntimeError,'existing user'):self.apply(apply=True,fresh_host=True,restore_host=True)
        self.assertFalse(list(self.units.iterdir()))

    def test_full_restore_missing_next_trigger_rolls_back_units(self):
        def missing(args,**kwargs):
            result=self.manager(args,**kwargs)
            if 'show' in args and any('NextElapse' in arg for arg in args):
                return subprocess.CompletedProcess(args,0,'NextElapseUSecRealtime=\nNextElapseUSecMonotonic=0\n','')
            return result
        with self.assertRaisesRegex(RuntimeError,'next trigger'):
            module.install(apply=True,root=self.root,unit_dir=self.units,run=missing,restore_host=True)
        self.assertFalse(list(self.units.iterdir()))


if __name__=='__main__':unittest.main()
