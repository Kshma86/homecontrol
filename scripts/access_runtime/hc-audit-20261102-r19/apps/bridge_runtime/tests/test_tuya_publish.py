import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tuya-poller'))
from telemetry_publish import ChangedPublisher


class TuyaPublishTest(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.cache = ChangedPublisher(clock=lambda: self.now, rate=10, burst=10)
        self.cache.connection(True)
        tree = ast.parse((ROOT / 'tuya-poller/tuya_poller.py').read_text())
        names = ['mqtt_publish', 'mqtt_publish_changed', 'mqtt_publish_device', 'mqtt_on_connect', 'mqtt_on_disconnect', '_mqtt_topic_join']
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        self.calls = []
        def publish(*args, **kw):
            self.calls.append((args, kw))
            return SimpleNamespace(rc=0)
        self.client = SimpleNamespace(publish=publish, subscribe=lambda *a, **kw: None)
        self.ns = dict(Any=Any, Optional=Optional, DevRuntime=object, json=json, MQTT_QOS=0, SINK_MQTT=True,
            mqtt_client=self.client, mqtt_connected=True, mqtt=SimpleNamespace(MQTT_ERR_SUCCESS=0),
            telemetry_publisher=self.cache, command_dispatcher=None, MQTT_COMMAND_TOPIC='fixture/cmd',
            MQTT_BASE_TOPIC='fixture', MQTT_RETAIN_STATE=False, MQTT_RETAIN_METRICS=False)
        self.ns['publish_poller_info'] = lambda: None
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual Tuya publish>', 'exec'), self.ns)

    def send(self, value=1, **kw):
        return self.ns['mqtt_publish_changed']('fixture/state', {'value': value}, **kw)

    def test_success_boundary_is_local_admission_for_qos_zero_and_one(self):
        for qos in (0, 1):
            self.cache.connection(True)
            self.assertTrue(self.send(qos=qos))
            self.assertFalse(self.send(qos=qos))
        self.assertEqual(len(self.calls), 2)

    def test_offline_never_calls_reconnect_or_creates_fingerprint(self):
        self.ns['mqtt_on_disconnect'](self.client, None, 7)
        self.assertFalse(self.send())
        self.assertEqual(self.cache.last, {})
        self.ns['mqtt_on_connect'](self.client, None, None, 0)
        self.assertTrue(self.send())
        self.assertEqual(len(self.calls), 1)

    def test_nonzero_rc_keeps_unchanged_value_publishable(self):
        self.client.publish = lambda *a, **kw: SimpleNamespace(rc=4)
        self.assertFalse(self.send())
        self.assertEqual(self.cache.last, {})
        self.client.publish = lambda *a, **kw: SimpleNamespace(rc=0)
        self.assertTrue(self.send())

    def test_publish_exception_is_not_admission(self):
        def failed(*a, **kw):
            raise OSError('fixture')
        self.client.publish = failed
        self.assertFalse(self.send())
        self.assertEqual(self.cache.last, {})

    def test_disconnect_between_publish_and_bookkeeping_cannot_mark_sent(self):
        def disconnect(*a, **kw):
            self.ns['mqtt_on_disconnect'](self.client, None, 7)
            return SimpleNamespace(rc=0)
        self.client.publish = disconnect
        self.assertFalse(self.send())
        self.assertEqual(self.cache.last, {})

    def test_fast_disconnect_reconnect_invalidates_old_inflight_generation(self):
        def reconnect(*a, **kw):
            self.cache.connection(False)
            self.cache.connection(True)
            return SimpleNamespace(rc=0)
        self.client.publish = reconnect
        self.assertFalse(self.send())
        self.assertEqual(self.cache.last, {})

    def test_reconnect_republishes_same_value_on_next_poll(self):
        self.assertTrue(self.send())
        self.cache.connection(False)
        self.cache.connection(True)
        self.assertTrue(self.send())

    def test_heartbeat_and_explicit_fingerprint_preserve_payload(self):
        self.assertTrue(self.send(1, fingerprint='stable'))
        self.now = 1
        self.assertFalse(self.send(2, fingerprint='stable'))
        self.now = 60
        self.assertTrue(self.send(3, fingerprint='stable'))
        self.assertEqual(json.loads(self.calls[-1][0][1]), {'value': 3})

    def test_burst_is_bounded_and_reconnect_does_not_refill(self):
        accepted = [self.cache.publish(str(i), i, lambda *a: True) for i in range(2000)]
        self.assertEqual(sum(accepted), 10)
        self.cache.connection(False)
        self.cache.connection(True)
        self.assertFalse(self.send())
        self.now = 1
        self.assertTrue(self.send())
        self.assertEqual(self.cache.snapshot()['counts']['rate_limited'], 1991)

    def test_only_latest_poll_payload_is_retried_no_stale_payload_queue(self):
        self.cache.tokens = 0
        self.assertFalse(self.send(1))
        self.now = 1
        self.assertTrue(self.send(2))
        self.assertEqual(json.loads(self.calls[0][0][1]), {'value': 2})

    def test_cache_size_is_bounded(self):
        cache = ChangedPublisher(capacity=2)
        cache.connection(True)
        for i in range(5):
            self.assertTrue(cache.publish(str(i), i, lambda *a: True))
        self.assertEqual(len(cache.last), 2)

    def test_invalid_configuration_rejected(self):
        for options in ({'rate': 0}, {'burst': float('inf')}, {'heartbeat': -1}, {'capacity': 0}):
            with self.assertRaises(ValueError):
                ChangedPublisher(**options)

    def test_many_devices_recover_under_rate_limit_and_current_metric_name_is_preserved(self):
        devices=[SimpleNamespace(name='device'+str(i),location='') for i in range(20)]
        for cycle in range(60):
            self.now=cycle
            offset=cycle % len(devices)
            for dr in devices[offset:]+devices[:offset]:
                self.ns['mqtt_publish_device'](dr,{'device_name':dr.name,'switch':False,
                    'current_a':.01,'recv_ts':cycle,'ts':cycle},None)
        states={call[0][0] for call in self.calls if call[0][0].endswith('/state')}
        self.assertEqual(len(states),20)
        topics={call[0][0] for call in self.calls}
        self.assertTrue(any(name.endswith('/m/current_a') for name in topics))
        self.assertFalse(any('pump_current' in name for name in topics))
        self.assertLessEqual(len(self.calls),600)


if __name__ == '__main__':
    unittest.main()
