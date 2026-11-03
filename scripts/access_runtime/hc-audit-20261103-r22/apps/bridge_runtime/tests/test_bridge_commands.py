"""Actual bridge callbacks/handlers with synthetic devices; no module startup."""
import ast
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, Optional
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bridge_runtime'))
from command_dispatcher import CommandDispatcher, CommandRejected
from test_command_dispatcher import until


def load(bridge, names, namespace):
    tree = ast.parse((ROOT / bridge).read_text())
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
             and node.name in names]
    assert len(nodes) == len(names)
    namespace.update(dict(Any=Any, Dict=Dict, Optional=Optional))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<bridge commands>', 'exec'), namespace)
    return namespace


def message(topic, payload, retained=False):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return SimpleNamespace(topic=topic, payload=data, retain=retained)


class TuyaFixture:
    def __init__(self, clock=time.monotonic):
        self.calls, self.results = [], []
        self.target = SimpleNamespace(name='fixture', device_id='device-id', lock=threading.Lock(),
            dp_map={'switch': 1}, ip='192.0.2.1', dev_kind='Device', last_state={})
        def send(value, dp):
            assert self.target.lock.locked()
            self.calls.append(value)
            return {'fixture': True}
        self.target.dev = SimpleNamespace(set_socketTimeout=lambda value: None, set_status=send)
        self.ns = load('tuya-poller/tuya_poller.py', ['mqtt_on_message', '_mqtt_topic_join',
            'command_bool', 'handle_switch_command', 'execute_queued_command', 'reject_queued_command'],
            dict(json=json, time=time, MQTT_COMMAND_TOPIC='homecontrol/cmd/tuya',
                 runtimes=[self.target], CommandRejected=CommandRejected, SLOW_TIMEOUT=.1,
                 cooldown_for=lambda error: 0,
                 publish_command_result=lambda *args, **kwargs: self.results.append(args)))
        self.dispatcher = CommandDispatcher(self.ns['execute_queued_command'], self.ns['reject_queued_command'],
            name='fixture-tuya-owner', capacity=4, clock=clock, max_age=3)
        self.ns['command_dispatcher'] = self.dispatcher
        self.dispatcher.set_online(True)

    def send(self, payload, retained=False, target='fixture'):
        self.ns['mqtt_on_message'](None, None, message('homecontrol/cmd/tuya/' + target + '/switch', payload, retained))


class GreeFixture:
    def __init__(self):
        self.calls, self.results = [], []
        async def apply(command, command_context=None):
            if command_context:
                command_context.check()
            self.calls.append(command)
            return {'ok': True, 'sampled_at': time.time()}
        ns = load('gree-climate/gree_climate_bridge.py', ['Bridge', 'validate_queued_command'], dict(
            threading=threading, asyncio=asyncio, time=time, datetime=datetime, json=json,
            BASE_TOPIC='homecontrol/gree_climate', apply_command=apply,
            error_text=str, CommandRejected=CommandRejected,
            MODE_MAP={'auto': 0, 'heat': 1}, FAN_MAP={'auto': 0}, FAN_EXTRA_MAP={'quiet': 0}))
        self.bridge = ns['Bridge'].__new__(ns['Bridge'])
        self.bridge.lock = threading.Lock()
        self.bridge.client = SimpleNamespace(publish=lambda topic, payload, **kw:
            self.results.append((topic, json.loads(payload), kw)))
        self.dispatcher = CommandDispatcher(self.bridge.execute_queued_command, self.bridge.reject_queued_command,
            name='fixture-gree-owner', capacity=4)
        self.bridge.command_dispatcher = self.dispatcher
        self.dispatcher.set_online(True)

    def send(self, payload, retained=False):
        self.bridge.on_message(None, None, message('homecontrol/gree_climate/command', payload, retained))


class X10Fixture:
    def __init__(self):
        self.calls, self.results = [], []
        tree = ast.parse((ROOT / 'xiaomi-x10/xiaomi_x10_bridge.py').read_text())
        names = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'COMMAND_NAMES' for t in n.targets))
        self.ns = load('xiaomi-x10/xiaomi_x10_bridge.py', ['on_message', 'on_disconnect',
            'run_command_worker', 'reject_queued_command', 'run_miio'], dict(
            threading=threading, command_lock=threading.Lock(), command_context=threading.local(),
            topic=lambda name: 'homecontrol/xiaomi_x10/' + name,
            publish=lambda *a, **kw: None, publish_room_clean_status=lambda *a: None,
            publish_command_result=lambda *args: self.results.append(args),
            handle_command=lambda command, payload: self.calls.append(command),
            COMMAND_NAMES=ast.literal_eval(names), CommandRejected=CommandRejected))
        self.dispatcher = CommandDispatcher(self.ns['run_command_worker'], self.ns['reject_queued_command'],
            name='fixture-x10-owner', capacity=4)
        self.ns['command_dispatcher'] = self.dispatcher
        self.dispatcher.set_online(True)

    def send(self, command, retained=False):
        self.ns['on_message'](None, None, message('homecontrol/xiaomi_x10/command/' + command, '', retained))


class BridgeCommandTest(unittest.TestCase):
    def make(self, cls, **kwargs):
        fixture = cls(**kwargs)
        self.addCleanup(fixture.dispatcher.close)
        return fixture

    def test_actual_tuya_on_off_handlers_preserve_order_under_blocked_device(self):
        fixture = self.make(TuyaFixture)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = fixture.target.dev.set_status
        def send(value, dp):
            result = original(value, dp)
            if value:
                entered.set()
                self.assertTrue(release.wait(2))
            return result
        fixture.target.dev.set_status = send
        fixture.dispatcher.start()
        fixture.send({'value': True})
        self.assertTrue(entered.wait(2))
        fixture.send({'value': False})
        release.set()
        until(lambda: len(fixture.calls) == 2)
        self.assertEqual(fixture.calls, [True, False])

    def test_tuya_alias_off_cancels_on_waiting_behind_poll_lock(self):
        fixture = self.make(TuyaFixture)
        with fixture.target.lock:
            fixture.dispatcher.start()
            fixture.send({'value': True})
            until(lambda: fixture.dispatcher.snapshot()['in_flight'])
            fixture.send({'value': False}, target='device-id')
        until(lambda: fixture.calls == [False])
        self.assertTrue(any(args[-1].get('code') == 'superseded_by_stop' for args in fixture.results))

    def test_tuya_expiry_is_rechecked_after_poll_lock(self):
        now = [10.]
        fixture = self.make(TuyaFixture, clock=lambda: now[0])
        with fixture.target.lock:
            fixture.dispatcher.start()
            fixture.send({'value': True})
            until(lambda: fixture.dispatcher.snapshot()['in_flight'])
            now[0] = 14.
        until(lambda: bool(fixture.results))
        self.assertEqual(fixture.calls, [])
        self.assertEqual(fixture.results[-1][-1]['code'], 'expired')

    def test_tuya_retained_oversized_invalid_and_unknown_do_not_enter_queue(self):
        fixture = self.make(TuyaFixture)
        for payload, retained, target in [({'value': True}, True, 'fixture'),
                (b'x' * 4097, False, 'fixture'), ({'value': 'invalid'}, False, 'fixture'),
                ({'value': True}, False, 'unknown')]:
            fixture.send(payload, retained, target)
        self.assertEqual(fixture.dispatcher.snapshot()['pending'], 0)
        self.assertEqual(len(fixture.results), 4)
        self.assertEqual(fixture.calls, [])

    def test_tuya_queue_rejection_never_enters_legacy_reconnect_publisher(self):
        calls = []
        ns = load('tuya-poller/tuya_poller.py', ['publish_command_result', '_mqtt_topic_join'], dict(
            time=time, json=json, MQTT_BASE_TOPIC='fixture/tuya', SINK_MQTT=True,
            mqtt_connected=False,
            mqtt_client=SimpleNamespace(publish=lambda *a, **kw: calls.append((a, kw))),
            mqtt_publish=lambda *a, **kw: self.fail('Legacy reconnect publisher used')))
        ns['publish_command_result']('fixture', False, 'rejected', {'code': 'offline'}, transient=True)
        self.assertEqual(calls, [])
        ns['mqtt_connected'] = True
        ns['publish_command_result']('fixture', False, 'rejected', {'code': 'queue_full'}, transient=True)
        self.assertEqual(calls[0][1], {'qos': 0, 'retain': False})

    def test_gree_off_cancels_old_commands_after_poll_lock(self):
        fixture = self.make(GreeFixture)
        with fixture.bridge.lock:
            fixture.dispatcher.start()
            fixture.send({'power': 'on', 'hc_execution_id': 'fixture-on'})
            until(lambda: fixture.dispatcher.snapshot()['in_flight'])
            fixture.send({'target_temperature': 24})
            fixture.send({'power': 'off'})
        until(lambda: len(fixture.calls) == 1)
        self.assertEqual(fixture.calls, [{'power': 'off'}])
        rejected = [row[1] for row in fixture.results if row[1].get('code') == 'superseded_by_stop']
        self.assertEqual(len(rejected), 2)
        self.assertTrue(any(row['command'].get('hc_execution_id') == 'fixture-on' for row in rejected))

    def test_gree_regular_settings_are_fifo_without_merging(self):
        fixture = self.make(GreeFixture)
        for value in [20, 21, 22]:
            fixture.send({'target_temperature': value})
        fixture.dispatcher.start()
        until(lambda: len(fixture.calls) == 3)
        self.assertEqual(fixture.calls, [{'target_temperature': value} for value in [20, 21, 22]])

    def test_invalid_mixed_gree_off_does_not_cancel_valid_intent(self):
        fixture = self.make(GreeFixture)
        fixture.send({'power': 'on', 'hc_execution_id': 'fixture-id'})
        fixture.send({'power': 'off', 'target_temperature': 99})
        self.assertEqual(fixture.dispatcher.snapshot()['pending'], 1)
        fixture.dispatcher.start()
        until(lambda: len(fixture.calls) == 1)
        self.assertEqual(fixture.calls[0]['power'], 'on')

    def test_gree_retained_oversized_and_invalid_json_do_not_spawn_workers(self):
        fixture = self.make(GreeFixture)
        with patch('threading.Thread', side_effect=AssertionError('Per-message thread forbidden')):
            fixture.send({'power': 'on'}, True)
            fixture.send(b'x' * 4097)
            fixture.send(b'not-json')
        self.assertEqual(fixture.dispatcher.snapshot()['pending'], 0)
        self.assertEqual(len(fixture.results), 3)

    def test_x10_stop_cancels_motion_but_keeps_pending_read(self):
        fixture = self.make(X10Fixture)
        with fixture.ns['command_lock']:
            fixture.dispatcher.start()
            fixture.send('start')
            until(lambda: fixture.dispatcher.snapshot()['in_flight'])
            fixture.send('home')
            fixture.send('status')
            fixture.send('stop')
        until(lambda: len(fixture.calls) == 2)
        self.assertEqual(fixture.calls, ['stop', 'status'])
        self.assertIsNone(getattr(fixture.ns['command_context'], 'current', None))

    def test_x10_retained_unknown_and_burst_do_not_spawn_per_message_threads(self):
        fixture = self.make(X10Fixture)
        with patch('threading.Thread', side_effect=AssertionError('Per-message thread forbidden')):
            fixture.send('start', True)
            fixture.send('unknown')
            for _ in range(10):
                fixture.send('start')
        self.assertEqual(fixture.dispatcher.snapshot()['pending'], 3)
        self.assertTrue(any(args[-1].get('code') == 'queue_full'
                            for args in fixture.results if isinstance(args[-1], dict)))

    def test_x10_transport_receives_current_command_guard_only_on_command_thread(self):
        fixture = self.make(X10Fixture)
        calls = []
        fixture.ns['transport_miio'] = lambda args, before_send=None: calls.append(before_send)
        fixture.ns['run_miio'](['poll'])
        check = lambda: None
        fixture.ns['command_context'].current = SimpleNamespace(check=check)
        fixture.ns['run_miio'](['command'])
        self.assertEqual(calls, [None, check])

    def test_x10_motion_commands_are_not_last_value_coalesced(self):
        fixture = self.make(X10Fixture)
        for command in ['start', 'home', 'room_clean']:
            fixture.send(command)
        fixture.dispatcher.start()
        until(lambda: len(fixture.calls) == 3)
        self.assertEqual(fixture.calls, ['start', 'home', 'room_clean'])

    def test_x10_stop_withdraws_local_automatic_start_even_if_stop_transport_fails(self):
        statuses = []
        def failed_stop(*args):
            raise RuntimeError('fixture transport failure')
        ns = load('xiaomi-x10/xiaomi_x10_bridge.py', ['handle_command'], dict(
            active_room_clean={'direct_start_sent': False}, call_action=failed_stop,
            publish_room_clean_status=lambda *args: statuses.append(args)))
        with self.assertRaises(RuntimeError):
            ns['handle_command']('stop', '')
        self.assertIsNone(ns['active_room_clean'])
        self.assertEqual(statuses[-1][1]['reason'], 'stop')

    def test_x10_internal_watch_uses_same_owner_and_does_not_accumulate(self):
        fixture = self.make(X10Fixture)
        load('xiaomi-x10/xiaomi_x10_bridge.py', ['enqueue_room_watch'], fixture.ns)
        fixture.ns['active_room_clean'] = {'fixture': True}
        calls = []
        fixture.ns['watch_room_clean'] = lambda: calls.append('watch')
        self.assertTrue(fixture.ns['enqueue_room_watch']())
        self.assertFalse(fixture.ns['enqueue_room_watch']())
        fixture.dispatcher.start()
        until(lambda: calls == ['watch'])

    def test_x10_internal_watch_cannot_be_submitted_from_mqtt(self):
        fixture = self.make(X10Fixture)
        fixture.send('_watch_room_clean')
        self.assertEqual(fixture.dispatcher.snapshot()['pending'], 0)
        self.assertEqual(fixture.calls, [])

    def test_gree_rechecks_expiry_after_the_initial_network_read_before_push(self):
        calls = []
        async def connect():
            calls.append('initial-read')
            return SimpleNamespace()
        def expired():
            raise CommandRejected('expired')
        ns = load('gree-climate/gree_climate_bridge.py', ['apply_command'], dict(
            time=time, asyncio=asyncio, connect_device=connect, CommandRejected=CommandRejected))
        with self.assertRaises(CommandRejected):
            asyncio.run(ns['apply_command']({'power': 'on'}, SimpleNamespace(check=expired)))
        self.assertEqual(calls, ['initial-read'])

    def test_tuya_has_no_second_consumer_and_each_bridge_packages_dispatcher(self):
        tree = ast.parse((ROOT / 'tuya-poller/tuya_poller.py').read_text())
        self.assertFalse(any(isinstance(n, ast.Name) and n.id in {'command_queue', 'drain_commands', 'command_worker'}
                             for n in ast.walk(tree)))
        for bridge in ['tuya-poller', 'gree-climate']:
            self.assertIn('command_dispatcher.py mqtt_credentials.py', (ROOT / bridge / 'Dockerfile').read_text())


if __name__ == '__main__':
    unittest.main()
