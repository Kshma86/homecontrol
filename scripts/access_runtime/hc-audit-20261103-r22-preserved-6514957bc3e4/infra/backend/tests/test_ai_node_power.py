"""HC-31: fake transport/clock, real temporary flock coordination; no device I/O."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from ai_node_service import AiNodeService
from ai_power_coordination import AiPowerCoordinator
from process_binding_service import ProcessBindingService


class AiPowerFixture:
    def setUp(self):
        # Physical transport is replaced below; exercise the enabled policy in
        # this fixture independently of the host's AI-offline deployment file.
        policy = patch('ai_node_service.ai_disabled', return_value=False)
        policy.start()
        self.addCleanup(policy.stop)
        binding_policy = patch('deployment_policy.ai_disabled', return_value=False)
        binding_policy.start()
        self.addCleanup(binding_policy.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = [100.0]
        self.binding = ['plug-A']
        self.topic = ['zigbee/plug-A']
        self.events = []
        self.coordinator = AiPowerCoordinator(self.root)
        self.service = self.make_service()
        self.service.initialize_power_state()

    def make_service(self, *, worker=False):
        with patch.dict(os.environ, {'HC_BACKUP_DIR': str(self.root)}):
            service = AiNodeService(
                lambda entity: {'entity_id': entity, 'entity_name': entity, 'topic_base': self.topic[0]},
                lambda row, value, source: (self.events.append(('power', row['entity_id'], value)) or (True, 'requested', row['topic_base'], {})),
                lambda *args: None, lambda *args: None,
                process_binding_entity_id=lambda key: self.binding[0],
                coordinator=self.coordinator, clock=lambda: self.now[0],
                wall_clock=lambda: 1700000000 + self.now[0], start_worker=worker)
        service.mac = '001122334455'
        service.send_wake_on_lan = lambda: self.events.append(('wol',))
        service.remote_command = lambda action: (self.events.append(('ssh', action)) or {'ok': True})
        self.addCleanup(service.close)
        return service

    def advance(self, seconds):
        self.now[0] += seconds
        return self.service.run_pending_power()

    def off_events(self):
        return [event for event in self.events if event[0] == 'power' and event[-1] is False]

    @contextmanager
    def backup_lock(self, name='homecontrol-backup.lock'):
        with (self.root / name).open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield


class AiPowerTest(AiPowerFixture, unittest.TestCase):
    def test_shutdown_and_power_off_execute_once_after_delay(self):
        result, status = self.service.shutdown_request(10)
        self.assertEqual(status, 200); self.assertTrue(result['power_off']['scheduled'])
        self.assertEqual(self.events, [('ssh', 'shutdown')])
        self.advance(9); self.assertFalse(self.off_events())
        self.advance(1); self.advance(1)
        self.assertEqual(self.off_events(), [('power', 'plug-A', False)])

    def test_wake_cancels_delayed_cut_and_deferred_shutdown(self):
        self.service.shutdown_request(10)
        self.service.wake(); self.advance(10)
        self.assertFalse(self.off_events())
        self.events.clear()
        with self.backup_lock():
            self.assertTrue(self.service.shutdown_request(10)[0]['deferred'])
            self.service.wake()
        self.advance(10)
        self.assertNotIn(('ssh', 'shutdown'), self.events)
        self.assertFalse(self.off_events())

    def test_new_backup_cancels_old_intent_even_if_finished_before_deadline(self):
        self.service.schedule_power_off(10)
        with self.backup_lock():
            self.coordinator.begin_backup('b' * 32)
            self.coordinator.finish_backup('b' * 32)
        self.advance(10)
        self.assertFalse(self.off_events())

    def test_active_backup_at_deadline_cancels_instead_of_retrying(self):
        for name in ('ai-backup.lock', 'homecontrol-backup.lock'):
            with self.subTest(name=name):
                self.service.schedule_power_off(10)
                with self.backup_lock(name):
                    self.advance(10)
                self.advance(10)
                self.assertFalse(self.off_events())

    def test_binding_change_and_topic_change_cannot_switch_a_different_target(self):
        self.service.schedule_power_off(10)
        self.binding[0] = 'plug-B'; self.advance(10)
        self.assertFalse(self.off_events())
        self.binding[0] = 'plug-A'; self.service.schedule_power_off(10)
        self.topic[0] = 'zigbee/other-device'; self.advance(10)
        self.assertFalse(self.off_events())

    def test_binding_a_b_a_invalidates_generation_and_other_bindings_do_not(self):
        binding = ProcessBindingService(*(lambda *a: None for _ in range(7)), ai_power_coordinator=self.coordinator)
        binding._set_binding = lambda key, entity: self.binding.__setitem__(0, entity)
        self.service.schedule_power_off(10)
        binding.set_binding('ai_node_power_plug', 'plug-B')
        binding.set_binding('ai_node_power_plug', 'plug-A')
        self.advance(10); self.assertFalse(self.off_events())
        self.service.schedule_power_off(10)
        binding._set_binding = lambda *args: None
        binding.set_binding('combustion_indicator', 'other')
        self.advance(10); self.assertEqual(len(self.off_events()), 1)

    def test_latest_shutdown_replaces_earlier_deadline(self):
        self.service.shutdown_request(10)
        self.service.shutdown_request(20)
        self.advance(10); self.assertFalse(self.off_events())
        self.advance(10); self.assertEqual(len(self.off_events()), 1)

    def test_restart_never_replays_intent_or_accepts_old_completion(self):
        self.service.schedule_power_off(10)
        self.coordinator.begin_backup('b' * 32)
        restarted = self.make_service(); restarted.initialize_power_state()
        self.assertEqual(restarted.shutdown_request(1, True, 'b' * 32)[1], 409)
        self.advance(20); restarted.run_pending_power()
        self.assertFalse(self.events)

    def test_no_configured_plug_still_allows_protected_ssh_shutdown(self):
        self.binding[0] = ''
        self.service.fetch_power_wall_command_entity = lambda entity: None
        result, status = self.service.shutdown_request(10)
        self.assertEqual(status, 200); self.assertFalse(result['power_off']['scheduled'])
        self.advance(10); self.assertEqual(self.events, [('ssh', 'shutdown')])

    def test_expired_intent_is_not_executed(self):
        self.service.schedule_power_off(10)
        self.advance(71); self.assertFalse(self.off_events())

    def test_probe_missing_lock_does_not_create_it_and_error_is_unknown(self):
        missing = AiPowerCoordinator(self.root / 'missing')
        self.assertIs(missing.guard()['backup_running'], False)
        self.assertFalse(missing.root.exists())
        with patch('backup_protocol.Path.open', side_effect=PermissionError):
            self.assertIsNone(self.service.ai_backup_running())
            self.assertFalse(self.service.backup_guard()['guard_known'])

    def test_guard_error_blocks_ssh_and_off_without_retry(self):
        with patch.object(self.coordinator, 'reserve_power', side_effect=PermissionError):
            self.assertEqual(self.service.shutdown_request(0, True)[1], 503)
        self.assertFalse(self.events)
        self.service.schedule_power_off(0)
        with patch.object(self.coordinator, 'reserve_power', side_effect=PermissionError):
            self.service.run_pending_power()
        self.service.run_pending_power(); self.assertFalse(self.events)
        self.assertTrue(self.service.backup_guard()['power_error'])

    def test_malformed_state_blocks_every_power_dispatch(self):
        self.coordinator.path.write_text('not json')
        self.assertEqual(self.service.shutdown_request(0, True)[1], 503)
        self.assertFalse(self.service.schedule_power_off(0)['scheduled'])
        self.assertFalse(self.events)

    def test_unavailable_power_guard_does_not_abort_unrelated_backend_startup(self):
        fresh = self.make_service()
        with patch.object(self.coordinator, 'locked', side_effect=PermissionError):
            self.assertFalse(fresh.start_power_guard())
            self.assertEqual(fresh.shutdown_request(0, True)[1], 503)
        self.assertFalse(self.events)

    def test_ssh_failure_only_schedules_cut_when_explicitly_requested(self):
        for error in (OSError('synthetic'), subprocess.TimeoutExpired('synthetic', 1)):
            self.service.remote_command = lambda action, error=error: (_ for _ in ()).throw(error)
            self.assertGreaterEqual(self.service.shutdown_request(1, False)[1], 500)
            self.assertIsNone(self.service._pending)
            result, status = self.service.shutdown_request(1, True)
            self.assertEqual(status, 202); self.assertTrue(result['power_off']['scheduled'])
            self.service.wake(); self.advance(1)
            self.assertFalse(self.off_events())

    def test_backup_held_completion_queues_without_self_deadlock(self):
        run_id = 'a' * 32
        with self.backup_lock('ai-backup.lock'), self.backup_lock():
            self.coordinator.begin_backup(run_id)
            result, status = self.service.shutdown_request(10, True, run_id)
            self.assertEqual(status, 202); self.assertTrue(result['deferred'])
            self.assertFalse(self.events)
            self.service.run_pending_power(); self.assertFalse(self.events)
            self.coordinator.finish_backup(run_id)
        self.service.run_pending_power()
        self.assertEqual(self.events, [('ssh', 'shutdown')])
        self.advance(9); self.assertFalse(self.off_events())
        self.advance(1); self.assertEqual(len(self.off_events()), 1)

    def test_own_backup_wake_preserves_completion_but_user_wake_revokes_it(self):
        run_id = 'a' * 32
        with self.backup_lock():
            self.coordinator.begin_backup(run_id)
            self.service.wake(run_id)
            self.assertEqual(self.service.shutdown_request(10, True, run_id)[1], 202)
        self.service.wake()
        self.assertEqual(self.service.shutdown_request(10, True, run_id)[1], 409)
        with self.backup_lock():
            self.coordinator.begin_backup(run_id)
            self.service.wake()
            self.service.wake(run_id)
            self.assertEqual(self.service.shutdown_request(10, True, run_id)[1], 409)
        self.advance(10); self.assertFalse(self.off_events())

    def test_new_backup_revokes_previous_completion_callback(self):
        self.coordinator.begin_backup('a' * 32)
        self.coordinator.finish_backup('a' * 32)
        self.coordinator.begin_backup('b' * 32)
        self.assertEqual(self.service.shutdown_request(0, True, 'a' * 32)[1], 409)
        self.assertFalse(self.events)

    def test_power_reservation_blocks_real_competing_backup_process(self):
        script = '''import fcntl,sys
with open(sys.argv[1], 'a') as lock:
 try: fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError: sys.exit(75)
'''
        path = str(self.root / 'homecontrol-backup.lock')
        def publish(row, value, source):
            result = subprocess.run([sys.executable, '-c', script, path], timeout=5)
            self.assertEqual(result.returncode, 75)
            self.events.append(('power', row['entity_id'], value))
            return True, 'requested', '', {}
        self.service.publish_power_wall_switch = publish
        self.service.schedule_power_off(0); self.service.run_pending_power()
        self.assertEqual(len(self.off_events()), 1)
        self.assertEqual(subprocess.run([sys.executable, '-c', script, path], timeout=5).returncode, 0)

    def test_two_concurrent_shutdowns_keep_only_one_current_intent(self):
        barrier = threading.Barrier(3)
        results = []
        def request():
            barrier.wait(); results.append(self.service.shutdown_request(5))
        threads = [threading.Thread(target=request) for _ in range(2)]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join(3); self.assertFalse(thread.is_alive())
        self.assertEqual([status for _, status in results], [200, 200])
        self.advance(5); self.assertEqual(len(self.off_events()), 1)

    def test_one_background_worker_survives_replaced_intents_and_can_close(self):
        service = self.make_service(worker=True)
        service.initialize_power_state()
        service.schedule_power_off(60); thread = service._power_thread
        for _ in range(3): service.schedule_power_off(60)
        self.assertIs(service._power_thread, thread)
        service.close(); self.assertFalse(thread.is_alive())


class AiPowerHttpTest(AiPowerFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        from flask import Flask
        from api_route_modules import register_ai_routes
        app = Flask(__name__)
        register_ai_routes(app, get_ai_proxy_service=lambda: None, get_ai_node_service=lambda: self.service)
        self.client = app.test_client()

    def test_false_defer_flag_cannot_bypass_running_backup(self):
        with self.backup_lock():
            result = self.client.post('/api/ai/node/command', json={
                'action': 'shutdown', 'defer_if_backup_running': False, 'power_off_delay_sec': 5})
            self.assertEqual(result.status_code, 202)
            self.assertTrue(result.json['deferred']); self.assertFalse(self.events)
        self.service.run_pending_power()
        self.assertEqual(self.events, [('ssh', 'shutdown')])
        self.advance(5); self.assertEqual(len(self.off_events()), 1)

    def test_wake_http_cancels_an_accepted_shutdown(self):
        result = self.client.post('/api/ai/node/command', json={'action': 'shutdown', 'power_off_delay_sec': 5})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.post('/api/ai/node/wake', json={}).status_code, 202)
        self.advance(5); self.assertFalse(self.off_events())

    def test_guard_failure_returns_unavailable_without_any_dispatch(self):
        with patch.object(self.coordinator, 'locked', side_effect=PermissionError):
            for path, body in [('/api/ai/node/command', {'action': 'shutdown', 'schedule_power_off_on_failure': True}),
                               ('/api/ai/node/wake', {})]:
                with self.subTest(path=path):
                    self.assertEqual(self.client.post(path, json=body).status_code, 503)
        self.assertFalse(self.events)

    def test_stale_backup_completion_returns_conflict(self):
        run_id = 'b' * 32
        self.coordinator.begin_backup(run_id)
        self.client.post('/api/ai/node/wake', json={})
        response = self.client.post('/api/ai/node/command', json={'action': 'shutdown', 'backup_run_id': run_id})
        self.assertEqual(response.status_code, 409)
        self.assertNotIn(('ssh', 'shutdown'), self.events)

    def test_non_shutdown_command_keeps_existing_route(self):
        response = self.client.post('/api/ai/node/command', json={'action': 'stop_stack'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.events, [('ssh', 'stop_stack')])


if __name__ == '__main__':
    unittest.main()
