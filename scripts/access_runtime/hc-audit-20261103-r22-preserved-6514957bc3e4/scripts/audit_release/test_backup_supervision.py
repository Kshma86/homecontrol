import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('backup_supervision_tested', Path(__file__).with_name('backup_supervision.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class SupervisionTest(unittest.TestCase):
    def test_cgroup_budget_exceeds_runner_budget_and_includes_stop_grace(self):
        command = b.command(['/usr/bin/python3', '/safe/runner.py', '--mode', 'weekly'])
        self.assertIn('--property=KillMode=mixed', command)
        self.assertIn('--wait', command)
        self.assertIn('--collect', command)
        self.assertGreater(b.RUNTIME_SECONDS, 10800)
        self.assertGreater(b.CLIENT_SECONDS, b.RUNTIME_SECONDS + 90)

    def test_a_client_failure_stops_supervisor_before_propagating(self):
        failure = subprocess.TimeoutExpired(['systemd-run'], b.CLIENT_SECONDS)
        original = Mock(side_effect=[SimpleNamespace(stdout=b'not-found\n'), failure, SimpleNamespace(returncode=0)])
        with self.assertRaises(subprocess.TimeoutExpired): b.supervised_call(original, ['python3', '/safe/runner.py'])
        self.assertEqual(original.call_args_list[-1].args[0], ['systemctl', 'stop', b.UNIT])
        self.assertEqual(original.call_args_list[-1].kwargs['allowed'], (0, 5))

    def test_existing_supervisor_is_never_stopped_or_reused(self):
        original = Mock(return_value=SimpleNamespace(stdout=b'loaded\n'))
        with self.assertRaisesRegex(ValueError, 'already exists'): b.supervised_call(original, ['python3', '/safe/runner.py'])
        self.assertEqual(original.call_count, 1)

    def test_only_approved_backup_entrypoints_receive_new_supervision(self):
        original = Mock(return_value=SimpleNamespace(stdout=b'not-found\n'))
        core = SimpleNamespace(call=original, OLD_RUNTIME=Path('/old'), RUNTIME=Path('/new'), BUSY_UNITS=('original.service',))
        b.install(core)
        with patch('builtins.print'):
            core.call(['python3', '/new/scripts/hostops/backup_runner.py', '--mode', 'weekly'], timeout=7200)
        self.assertTrue(any(c.args[0][0] == 'systemd-run' for c in original.call_args_list))
        self.assertIn(b.UNIT, core.BUSY_UNITS)
        original.reset_mock()
        core.call(['docker', 'inspect', 'homecontrol-backend'], timeout=10)
        original.assert_called_once_with(['docker', 'inspect', 'homecontrol-backend'], timeout=10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
