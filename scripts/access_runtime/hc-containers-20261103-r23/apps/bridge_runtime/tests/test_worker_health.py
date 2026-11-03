import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'worker_health.py'
spec = importlib.util.spec_from_file_location('canonical_worker_health', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WorkerHealthTest(unittest.TestCase):
    def test_missing_initial_cycle_is_only_live_during_startup_grace(self):
        now = [0]
        health = module.WorkerHealth(maximum=30, clock=lambda: now[0])
        self.assertTrue(health.snapshot(connected=True)['live'])
        self.assertFalse(health.snapshot(connected=True)['ready'])
        now[0] = 31
        self.assertFalse(health.snapshot(connected=True)['live'])

    def test_failed_device_attempt_is_live_but_not_ready(self):
        health = module.WorkerHealth()
        health.progress(success=False)
        state = health.snapshot(connected=True)
        self.assertTrue(state['live'])
        self.assertFalse(state['ready'])

    def test_broker_outage_does_not_kill_liveness(self):
        health = module.WorkerHealth()
        health.progress(success=True)
        state = health.snapshot(connected=False)
        self.assertTrue(state['live'])
        self.assertFalse(state['ready'])
        self.assertTrue(health.snapshot(connected=True)['ready'])

    def test_stuck_command_owner_cannot_be_hidden_by_reporter_thread(self):
        health = module.WorkerHealth(maximum=30)
        health.progress(success=True)
        for commands in ({'worker_alive': False},
                         {'worker_alive': True, 'closed': False, 'last_loop_age_sec': 31}):
            self.assertFalse(health.snapshot(connected=True, commands=commands)['live'])

    def test_stuck_poll_is_unhealthy_despite_fresh_json(self):
        now = [0]
        health = module.WorkerHealth(maximum=30, clock=lambda: now[0])
        health.progress(success=True)
        now[0] = 31
        self.assertFalse(health.snapshot(connected=True)['live'])

    def test_read_probe_rejects_recycled_pid_stale_future_and_bad_state(self):
        good = {'written_at': 100, 'process_ticks': 'ticks', 'live': True, 'ready': True}
        self.assertTrue(module.assess(good, now=101, ticks='ticks', mode='ready'))
        for changes in ({'process_ticks': 'other'}, {'written_at': 0},
                        {'written_at': 110}, {'written_at': float('nan')},
                        {'written_at': True}, {'live': False}):
            self.assertFalse(module.assess({**good, **changes}, now=101, ticks='ticks'))

    def test_shutdown_removes_health_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'status.json'
            health = module.WorkerHealth(path=path)
            health.start(lambda: {'connected': False})
            self.assertTrue(health.thread.is_alive())
            health.close()
            self.assertFalse(health.thread.is_alive())
            self.assertFalse(path.exists())

    def test_health_build_context_copies_identical(self):
        for name in ('tuya-poller', 'gree-climate', 'xiaomi-x10', 'ha-growatt-poller'):
            self.assertEqual(SOURCE.read_bytes(), (SOURCE.parents[1] / name / SOURCE.name).read_bytes())


if __name__ == '__main__':
    unittest.main()
