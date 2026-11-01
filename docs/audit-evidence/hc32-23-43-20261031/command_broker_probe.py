"""Run only in the isolated HC-12 lab network; all actuators are fixtures."""
import json
import sys
import threading
import time
sys.path.insert(0, '/work/apps/bridge_runtime/tests')
from test_bridge_commands import TuyaFixture, GreeFixture, X10Fixture
from test_command_dispatcher import until
import paho.mqtt.client as mqtt

HOST = 'hc-f10-queue-broker'
sender = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id='hc12-fixture-sender')
for attempt in range(30):
    try:
        sender.connect(HOST, 1883, 10)
        break
    except OSError:
        time.sleep(.2)
else:
    raise RuntimeError('Isolated broker not ready')
sender.loop_start()

def publish(topic, payload, retain=False):
    info = sender.publish(topic, json.dumps(payload) if not isinstance(payload, str) else payload,
                          qos=1, retain=retain)
    info.wait_for_publish(timeout=3)
    assert info.is_published()

report = []
try:
    for label, cls, topic, normal, stop in [
        ('tuya', TuyaFixture, 'homecontrol/cmd/tuya/fixture/switch', {'value': True}, {'value': False}),
        ('gree', GreeFixture, 'homecontrol/gree_climate/command', {'power': 'on'}, {'power': 'off'}),
        ('x10', X10Fixture, 'homecontrol/xiaomi_x10/command/start', '{}', '{}')]:
        fixture = cls()
        entered, release = threading.Event(), threading.Event()
        original = fixture.dispatcher.handler
        def blocked(item, original=original, fixture=fixture):
            original(item)
            if len(fixture.calls) == 1:
                entered.set()
                assert release.wait(8), 'Fixture gate timeout'
        fixture.dispatcher.handler = blocked
        fixture.dispatcher.start()
        publish(topic, normal, retain=True)
        subscribed = threading.Event()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id='hc12-fixture-' + label)
        def connected(c, userdata, flags, rc, properties=None, fixture=fixture, label=label, topic=topic):
            assert rc == 0
            fixture.dispatcher.set_online(True)
            c.subscribe('homecontrol/xiaomi_x10/command/#' if label == 'x10' else topic, qos=1)
        client.on_connect = connected
        client.on_subscribe = lambda *args: subscribed.set()
        if label == 'gree':
            client.on_message = fixture.bridge.on_message
        else:
            client.on_message = fixture.ns['mqtt_on_message' if label == 'tuya' else 'on_message']
        client.on_disconnect = lambda *args, fixture=fixture: fixture.dispatcher.set_online(False)
        def codes(fixture=fixture, label=label):
            if label == 'gree':
                return [row[1].get('code') for row in fixture.results]
            return [row[-1].get('code') for row in fixture.results if isinstance(row[-1], dict)]
        try:
            client.connect(HOST, 1883, 10)
            client.loop_start()
            assert subscribed.wait(3)
            until(lambda: 'retained' in codes())
            assert fixture.calls == []
            publish(topic, normal)
            assert entered.wait(3)
            for _ in range(16):
                publish(topic, normal)
            until(lambda: codes().count('queue_full') == 13)
            assert fixture.dispatcher.snapshot()['pending'] == 3
            stop_topic = 'homecontrol/xiaomi_x10/command/stop' if label == 'x10' else topic
            started = time.monotonic()
            publish(stop_topic, stop)
            until(lambda: codes().count('superseded_by_stop') == 3)
            delay = time.monotonic() - started
            assert fixture.dispatcher.snapshot()['pending'] == 1
            release.set()
            until(lambda: len(fixture.calls) == 2)
            def projected(fixture=fixture, label=label):
                return [r['power'] for r in fixture.calls] if label == 'gree' else list(fixture.calls)
            expected = [True, False] if label == 'tuya' else ['on', 'off'] if label == 'gree' else ['start', 'stop']
            assert projected() == expected
            count = codes().count('retained')
            client.disconnect()
            client.loop_stop()
            subscribed.clear()
            client.connect(HOST, 1883, 10)
            client.loop_start()
            assert subscribed.wait(3)
            until(lambda: codes().count('retained') == count + 1)
            assert projected() == expected
            report.append(dict(bridge=label, cases_passed=3, retained_replay_rejected=True,
                queue_full_replies=13, queued_intents_cancelled_by_stop=3, observed_calls=expected,
                reconnect_did_not_replay=True, stop_admission_seconds=round(delay, 4),
                max_pending_observed=3, physical_actuators=False))
        finally:
            release.set()
            client.disconnect()
            client.loop_stop()
            fixture.dispatcher.close()
finally:
    sender.disconnect()
    sender.loop_stop()
print('HC12_BROKER_RESULT=' + json.dumps(dict(ok=True, cases_passed=9, bridges=report,
    isolated_network=True, host_ports_published=False, device_transport='fixture',
    actual_connection_callbacks='fixture adapter; actual bridge on_message and handlers exercised')))
