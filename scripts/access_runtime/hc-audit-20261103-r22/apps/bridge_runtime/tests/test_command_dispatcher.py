"""No broker, credentials, application startup or physical device is used here."""
from pathlib import Path
import sys
import os
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bridge_runtime'))
from command_dispatcher import CommandDispatcher, CommandRejected


def until(predicate, timeout=3):
    end = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= end:
            raise AssertionError('Timed out waiting for fixture')
        time.sleep(.002)


class DispatcherTest(unittest.TestCase):
    def make(self, handler=None, **kwargs):
        self.rejected = []
        dispatcher = CommandDispatcher(handler or (lambda item: None),
            lambda item, code: self.rejected.append((item.payload, code)),
            name='test-hc12-owner', **kwargs)
        dispatcher.set_online(True)
        self.addCleanup(dispatcher.close)
        return dispatcher

    def gate(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def handle(item):
            if item.payload == 'gate':
                entered.set()
                if not release.wait(3):
                    raise AssertionError('Gate fixture timeout')
            else:
                self.calls.append(item.payload)
        self.calls = []
        dispatcher = self.make(handle)
        dispatcher.start()
        self.assertTrue(dispatcher.submit('gate', 'gate', size=1))
        self.assertTrue(entered.wait(2))
        return dispatcher, release

    def test_fifo_has_exactly_one_idempotent_worker(self):
        calls = []
        dispatcher = self.make(lambda item: calls.append(item.payload), capacity=64)
        worker = dispatcher.start()
        self.assertIs(dispatcher.start(), worker)
        for value in range(20):
            self.assertTrue(dispatcher.submit('socket', value, size=4))
        until(lambda: len(calls) == 20)
        self.assertEqual(calls, list(range(20)))
        self.assertEqual(sum(t.name == 'test-hc12-owner' for t in threading.enumerate()), 1)

    def test_slow_device_burst_is_bounded_and_off_uses_reserved_slot(self):
        dispatcher, release = self.gate()
        accepted = [dispatcher.submit('normal-' + str(i), i, size=4096) for i in range(2000)]
        self.assertEqual(sum(accepted), 31)
        state = dispatcher.snapshot()
        self.assertEqual(state['pending'], 31)
        self.assertEqual(state['pending_bytes'], 31 * 4096)
        self.assertTrue(dispatcher.submit('off-target', 'OFF', size=10, priority=True))
        self.assertEqual(dispatcher.snapshot()['pending'], 32)
        self.assertFalse(dispatcher.submit('another-stop', 'OFF-full', size=10, priority=True))
        release.set()
        until(lambda: len(self.calls) == 32)
        self.assertEqual(self.calls[0], 'OFF')

    def test_stop_cancels_prior_same_target_intents_but_preserves_other_fifo(self):
        dispatcher, release = self.gate()
        dispatcher.submit('robot', 'start', size=1)
        dispatcher.submit('other', 'other-1', size=1)
        dispatcher.submit('robot', 'room-clean', size=1)
        dispatcher.submit('robot', 'status', size=1, cancellable=False)
        dispatcher.submit('other', 'other-2', size=1)
        dispatcher.submit('robot', 'stop', size=1, priority=True)
        dispatcher.submit('robot', 'new-start', size=1)
        release.set()
        until(lambda: len(self.calls) == 5)
        self.assertEqual(self.calls, ['stop', 'other-1', 'status', 'other-2', 'new-start'])
        self.assertEqual(set(self.rejected), {('start', 'superseded_by_stop'), ('room-clean', 'superseded_by_stop')})

    def test_in_flight_on_then_off_never_becomes_off_then_old_on(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []
        def handle(item):
            calls.append(item.payload)
            if item.payload == 'ON':
                entered.set()
                self.assertTrue(release.wait(2))
        dispatcher = self.make(handle)
        dispatcher.start()
        dispatcher.submit('socket', 'ON', size=1)
        self.assertTrue(entered.wait(2))
        dispatcher.submit('socket', 'OFF', size=1, priority=True)
        release.set()
        until(lambda: len(calls) == 2)
        self.assertEqual(calls, ['ON', 'OFF'])

    def test_unfinished_command_checks_stop_barrier_before_subsequent_io(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []
        def handle(item):
            if item.payload == 'multi-step':
                calls.append('first-io')
                entered.set()
                self.assertTrue(release.wait(2))
                item.check()
                calls.append('old-second-io')
            else:
                calls.append(item.payload)
        dispatcher = self.make(handle)
        dispatcher.start()
        dispatcher.submit('robot', 'multi-step', size=1)
        self.assertTrue(entered.wait(2))
        dispatcher.submit('robot', 'stop', size=1, priority=True)
        release.set()
        until(lambda: len(calls) == 2)
        self.assertEqual(calls, ['first-io', 'stop'])
        self.assertIn(('multi-step', 'superseded_by_stop'), self.rejected)

    def test_retained_and_oversize_commands_have_no_side_effects(self):
        dispatcher = self.make(max_payload=8)
        self.assertFalse(dispatcher.submit('socket', 'retained', size=1, retained=True, priority=True))
        self.assertFalse(dispatcher.submit('socket', 'large', size=9, priority=True))
        self.assertEqual(dispatcher.snapshot()['pending'], 0)
        self.assertEqual(self.rejected, [('retained', 'retained'), ('large', 'payload_too_large')])

    def test_expiry_and_new_admission_remove_old_commands_without_replay(self):
        now = [10.]
        calls = []
        dispatcher = self.make(lambda item: calls.append(item.payload), clock=lambda: now[0], max_age=3)
        dispatcher.submit('socket', 'old', size=1)
        now[0] = 14.
        dispatcher.submit('socket', 'fresh', size=1)
        dispatcher.start()
        until(lambda: calls == ['fresh'])
        self.assertIn(('old', 'expired'), self.rejected)

    def test_disconnect_and_reconnect_never_replay_a_previous_generation(self):
        dispatcher, release = self.gate()
        dispatcher.submit('socket', 'old', size=1)
        dispatcher.set_online(False)
        self.assertFalse(dispatcher.submit('socket', 'offline', size=1))
        dispatcher.set_online(True)
        dispatcher.submit('socket', 'fresh', size=1)
        release.set()
        until(lambda: self.calls == ['fresh'])
        self.assertIn(('old', 'connection_lost'), self.rejected)
        self.assertIn(('offline', 'offline'), self.rejected)

    def test_reconnect_callback_alone_is_a_new_generation(self):
        dispatcher = self.make()
        dispatcher.submit('socket', 'old', size=1)
        dispatcher.set_online(True)
        self.assertEqual(dispatcher.snapshot()['pending'], 0)
        self.assertEqual(self.rejected, [('old', 'connection_reset')])

    def test_rejected_stop_does_not_cancel_an_active_intent(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        active = []
        def handle(item):
            active.append(item)
            entered.set()
            self.assertTrue(release.wait(2))
        dispatcher = self.make(handle, capacity=2)
        dispatcher.start()
        dispatcher.submit('active', 'active', size=1)
        self.assertTrue(entered.wait(2))
        dispatcher.submit('one', 'stop-1', size=1, priority=True)
        dispatcher.submit('two', 'stop-2', size=1, priority=True)
        self.assertFalse(dispatcher.submit('active', 'rejected-stop', size=1, priority=True))
        self.assertEqual(active[0].cancelled, '')
        release.set()

    def test_handler_exception_does_not_kill_the_only_owner(self):
        calls = []
        def handle(item):
            if item.payload == 'fail':
                raise RuntimeError('fixture')
            calls.append(item.payload)
        dispatcher = self.make(handle)
        dispatcher.submit('socket', 'fail', size=1)
        dispatcher.submit('socket', 'next', size=1)
        dispatcher.start()
        until(lambda: calls == ['next'])
        self.assertIn(('fail', 'execution_error'), self.rejected)

    def test_shutdown_discards_pending_and_no_restart_is_allowed(self):
        dispatcher = self.make()
        dispatcher.submit('socket', 'old', size=1)
        self.assertTrue(dispatcher.close())
        self.assertEqual(self.rejected, [('old', 'shutdown')])
        with self.assertRaises(ValueError):
            dispatcher.start()
        self.assertFalse(dispatcher.submit('socket', 'new', size=1))

    def test_invalid_configuration_fails_at_startup(self):
        for kwargs in [dict(capacity=0), dict(capacity=1), dict(capacity=2.5),
                       dict(max_age=0), dict(max_age=float('nan')), dict(max_payload=0)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.make(**kwargs)

    def test_build_context_copies_are_identical(self):
        canonical = (ROOT / 'bridge_runtime/command_dispatcher.py').read_bytes()
        for bridge in ['tuya-poller', 'gree-climate', 'xiaomi-x10']:
            self.assertEqual((ROOT / bridge / 'command_dispatcher.py').read_bytes(), canonical)

    def test_domain_limits_are_configurable_and_x10_can_allow_long_map_operations(self):
        with patch.dict(os.environ, {'X10_COMMAND_QUEUE_SIZE': '8',
                'X10_COMMAND_MAX_AGE_SEC': '240', 'X10_COMMAND_MAX_PAYLOAD_BYTES': '1024'}, clear=True):
            dispatcher = CommandDispatcher.configured(lambda item: None, lambda *a: None,
                name='config-test', prefix='X10', default_max_age=180)
        self.assertEqual((dispatcher.capacity, dispatcher.max_age, dispatcher.max_payload), (8, 240, 1024))
        with patch.dict(os.environ, {}, clear=True):
            dispatcher = CommandDispatcher.configured(lambda item: None, lambda *a: None,
                name='config-test', prefix='X10', default_max_age=180)
        self.assertEqual(dispatcher.max_age, 180)


if __name__ == '__main__':
    unittest.main()
