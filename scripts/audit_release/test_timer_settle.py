import hashlib
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

t = load('timer_settle_tested', Path(__file__).with_name('timer_settle.py'))
f = load('sealed_r22_schedules_tested', Path('/srv/docker/homecontrol/backups/releases/hc-audit-20261103-r22/source/scripts/audit_release/schedules.py'))


class TimerTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory); names = ['homecontrol-' + n + '.timer' for n in
            ('backup', 'ai-weekly-backup', 'restic-check', 'log-maintenance', 'post-boot-health')]
        units = {}
        for name in names:
            (root / name).write_text('sealed unit\n')
            units[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        state = {'now': 0, 'finish': 2, 'fail': False, 'missing': False, 'unit': t.SERVICE,
                 'timer_active': 'active', 'exit': '0', 'calls': 0, 'mutate': lambda: None}
        def call(args, **kwargs):
            state['calls'] += 1
            if args[1] == 'is-enabled': return SimpleNamespace(stdout=b'enabled\n')
            busy = state['now'] < state['finish']
            if 'LoadState' in args[3] and args[2] == t.TIMER:
                data = {'LoadState': 'loaded', 'ActiveState': state['timer_active'],
                        'SubState': 'running' if busy else 'waiting', 'Unit': state['unit']}
            elif 'LoadState' in args[3]:
                data = {'LoadState': 'loaded', 'Type': 'oneshot', 'ActiveState': 'activating' if busy else 'inactive',
                        'SubState': 'start' if busy else 'dead', 'Result': 'exit-code' if state['fail'] else 'success',
                        'ExecMainStatus': state['exit']}
            else:
                no_next = args[2] == t.TIMER and (busy or state['missing'])
                data = {'NextElapseUSecRealtime': '', 'NextElapseUSecMonotonic': 'infinity' if no_next else '10min'}
            return SimpleNamespace(stdout=('\n'.join(k + '=' + v for k, v in data.items()) + '\n').encode())
        def sleep(seconds): state['now'] += seconds; state['mutate']()
        core = SimpleNamespace(UNIT_ROOT=root, KIT=root, platform=lambda: SimpleNamespace(no_symlinks=lambda p: None, units=lambda p: {}),
                               digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest(), active=lambda n: True, call=call)
        plan = {'scope': 'system', 'applied': False, 'units': units, 'enabled': dict.fromkeys(names, True)}
        return core, plan, state, lambda: state['now'], sleep

    def test_real_frozen_check_rejects_running_then_passes_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            core, plan, state, clock, sleep = self.fixture(directory)
            with self.assertRaisesRegex(ValueError, t.MISSING): f.check_schedules(core, plan)
            result = t.check(core, f.check_schedules, plan, clock=clock, sleep=sleep)
            self.assertEqual(state['now'], 2)
            self.assertEqual(len(result['timers']), 5)
            self.assertTrue(result['health_service_acceptance']['waited_for_completion'])
            self.assertEqual(result['timers'][t.TIMER]['next_trigger']['NextElapseUSecMonotonic'], '10min')

    def test_idle_health_with_future_trigger_does_not_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            core, plan, state, clock, sleep = self.fixture(directory); state['finish'] = 0
            result = t.check(core, f.check_schedules, plan, clock=clock, sleep=sleep)
            self.assertFalse(result['health_service_acceptance']['waited_for_completion'])

    def test_failed_health_is_rejected_even_with_future_trigger(self):
        with tempfile.TemporaryDirectory() as directory:
            core, plan, state, clock, sleep = self.fixture(directory); state.update(finish=0, fail=True)
            with self.assertRaisesRegex(ValueError, 'Health service failed'): t.check(core, f.check_schedules, plan, clock=clock, sleep=sleep)

    def test_health_failure_while_waiting_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            core, plan, state, clock, sleep = self.fixture(directory)
            state['mutate'] = lambda: state.update(fail=True)
            with self.assertRaisesRegex(ValueError, 'Health service failed'): t.check(core, f.check_schedules, plan, clock=clock, sleep=sleep)

    def test_stalled_service_has_bounded_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            core, plan, state, clock, sleep = self.fixture(directory); state['finish'] = 1000
            with self.assertRaisesRegex(ValueError, 'deadline'): t.check(core, f.check_schedules, plan, timeout=3, clock=clock, sleep=sleep)
            self.assertEqual(state['now'], 3)

    def test_inactive_timer_without_trigger_still_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            core, plan, state, clock, sleep = self.fixture(directory); state.update(finish=0, missing=True)
            with self.assertRaisesRegex(ValueError, t.MISSING): t.check(core, f.check_schedules, plan, clock=clock, sleep=sleep)
            self.assertEqual(state['now'], 5)

    def test_hash_drift_while_waiting_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            core, plan, state, clock, sleep = self.fixture(directory)
            state['mutate'] = lambda: (core.UNIT_ROOT / t.TIMER).write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'Backup unit changed'): t.check(core, f.check_schedules, plan, clock=clock, sleep=sleep)

    def test_other_timer_missing_trigger_is_never_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            core, plan, state, clock, sleep = self.fixture(directory)
            def failed(*args, **kwargs): raise ValueError('Scheduled timer has no next trigger: homecontrol-backup.timer')
            with self.assertRaisesRegex(ValueError, 'homecontrol-backup.timer'): t.check(core, failed, plan, clock=clock, sleep=sleep)
            self.assertEqual(state['now'], 0)

    def test_wrong_target_service_or_inactive_timer_is_rejected(self):
        for change in ({'unit': 'different.service'}, {'timer_active': 'inactive'}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                core, plan, state, clock, sleep = self.fixture(directory); state.update(change)
                with self.assertRaisesRegex(ValueError, 'Health timer is not ready'): t.check(core, f.check_schedules, plan, clock=clock, sleep=sleep)

    def test_nonzero_exit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            core, plan, state, clock, sleep = self.fixture(directory); state.update(finish=0, exit='1')
            with self.assertRaisesRegex(ValueError, 'did not finish successfully'): t.check(core, f.check_schedules, plan, clock=clock, sleep=sleep)

    def test_disabled_or_drifted_unit_is_never_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            core, plan, state, clock, sleep = self.fixture(directory); plan['enabled'][t.TIMER] = False
            with self.assertRaisesRegex(ValueError, 'five configured'): t.check(core, f.check_schedules, plan, clock=clock, sleep=sleep)
            self.assertEqual(state['now'], 0)


if __name__ == '__main__': unittest.main()
