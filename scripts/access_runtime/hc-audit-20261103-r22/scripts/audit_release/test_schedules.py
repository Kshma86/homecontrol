"""Exercise current schedules, stale receipts, tampering and systemd failures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('audit_schedules_tested', Path(__file__).with_name('schedules.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class ScheduleTest(unittest.TestCase):
    def fixture(self, folder):
        base = Path(folder)
        names = ['homecontrol-' + n + '.timer' for n in ('backup', 'ai-weekly-backup', 'restic-check', 'log-maintenance', 'post-boot-health')]
        unit_root = base / 'units'
        unit_root.mkdir()
        enabled = {name: True for name in names}
        hashes = {}
        for name in names:
            (unit_root / name).write_text('[Timer]\nOnCalendar=daily\n')
            hashes[name] = hashlib.sha256((unit_root / name).read_bytes()).hexdigest()
        (base / 'backups').mkdir()
        # Deliberately stale, as in the real r19 incident. Never authoritative.
        (base / 'backups/f6-installed.json').write_text(json.dumps({'enabled': dict(zip(names, [True, False, False, True, True])), 'units': hashes}))
        def call(args, **kwargs):
            return SimpleNamespace(stdout=b'enabled\n' if args[1] == 'is-enabled' else b'NextElapseUSecRealtime=Tue 2026-11-03 02:15:00 CET\nNextElapseUSecMonotonic=0\n')
        platform = SimpleNamespace(no_symlinks=Mock(), units=lambda path: {})
        core = SimpleNamespace(BASE=base, KIT=base / 'kit', UNIT_ROOT=unit_root,
                               platform=lambda: platform,
                               digest=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
                               active=lambda name: True, call=Mock(side_effect=call))
        return core, {'scope': 'system', 'applied': False, 'units': hashes, 'enabled': enabled}

    def test_current_plan_accepts_five_active_timers_despite_three_in_old_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            core, plan = self.fixture(folder)
            result = s.check_schedules(core, plan)
            self.assertEqual(len(result['timers']), 5)
            self.assertTrue(result['read_only'])
            self.assertEqual({call.args[0][1] for call in core.call.call_args_list}, {'is-enabled', 'show'})

    def test_tampered_timer_bytes_fail_even_when_all_timers_are_active(self):
        with tempfile.TemporaryDirectory() as folder:
            core, plan = self.fixture(folder)
            (core.UNIT_ROOT / next(iter(plan['units']))).write_text('changed')
            with self.assertRaisesRegex(ValueError, 'Backup unit changed'): s.check_schedules(core, plan)

    def test_missing_active_timer_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            core, plan = self.fixture(folder)
            core.active = lambda name: not name.endswith('restic-check.timer')
            with self.assertRaisesRegex(ValueError, 'active state differs'): s.check_schedules(core, plan)

    def test_disabled_timer_is_rejected_even_if_still_active(self):
        with tempfile.TemporaryDirectory() as folder:
            core, plan = self.fixture(folder)
            core.call = lambda args, **kwargs: SimpleNamespace(stdout=b'disabled\n')
            with self.assertRaisesRegex(ValueError, 'enablement differs'): s.check_schedules(core, plan)

    def test_no_future_trigger_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            core, plan = self.fixture(folder)
            core.call = lambda args, **kwargs: SimpleNamespace(stdout=b'enabled\n' if args[1] == 'is-enabled' else b'NextElapseUSecRealtime=\nNextElapseUSecMonotonic=0\n')
            with self.assertRaisesRegex(ValueError, 'no next trigger'): s.check_schedules(core, plan)

    def test_configuration_requires_all_five_router_timers(self):
        with tempfile.TemporaryDirectory() as folder:
            core, plan = self.fixture(folder)
            plan['enabled']['homecontrol-ai-weekly-backup.timer'] = False
            with self.assertRaisesRegex(ValueError, 'five configured'): s.check_schedules(core, plan)

    def test_new_release_dropin_is_checked_against_frozen_source(self):
        with tempfile.TemporaryDirectory() as folder:
            core, plan = self.fixture(folder)
            core.platform().units = lambda path: {'homecontrol-backup.service.d/hc44.conf': 'expected'}
            path = core.UNIT_ROOT / 'homecontrol-backup.service.d/hc44.conf'
            path.parent.mkdir()
            path.write_text('wrong-runtime')
            with self.assertRaisesRegex(ValueError, 'Backup unit changed'): s.check_schedules(core, plan)

    def test_conflicting_unit_definitions_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            core, plan = self.fixture(folder)
            core.platform().units = lambda path: {'homecontrol-backup.timer': 'different'}
            with self.assertRaisesRegex(ValueError, 'Conflicting expected unit'): s.check_schedules(core, plan)

    def test_generator_is_called_only_in_read_only_restore_host_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            core, plan = self.fixture(folder)
            module = SimpleNamespace(install=Mock(return_value=plan))
            fake_spec = SimpleNamespace(loader=SimpleNamespace(exec_module=Mock()))
            with patch.object(s.importlib.util, 'spec_from_file_location', return_value=fake_spec), patch.object(s.importlib.util, 'module_from_spec', return_value=module):
                self.assertIs(s.schedule_plan(core), plan)
            module.install.assert_called_once_with(apply=False, root=core.BASE / 'backups', restore_host=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
