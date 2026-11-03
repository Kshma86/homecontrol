"""HC-26 one-snapshot polling, source ages and unchanged MQTT wire fields."""
import ast
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import requests
import ha_growatt_poller as poller

NOW = datetime(2026, 11, 2, 15, tzinfo=timezone.utc)
MAP = {'power_w': 'sensor.power', 'energy_kwh': 'sensor.energy'}


def state(entity='sensor.power', value='42', age=30, **extra):
    return dict(entity_id=entity, state=value, attributes={'unit_of_measurement': 'W', 'friendly_name': 'Fixture'},
                last_updated=(NOW-timedelta(seconds=age)).isoformat(), **extra)


class Response:
    def __init__(self, states=None, error=None, json_error=None):
        self.states = states
        self.error = error
        self.json_error = json_error
        self.closed = False
    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def raise_for_status(self):
        if self.error: raise self.error
    def json(self):
        if self.json_error: raise self.json_error
        return self.states


class Session:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes); self.gets = []; self.headers = {}; self.closed = False
        self.after_get = lambda: None
    def get(self, url, **options):
        self.gets.append((url, options)); self.after_get()
        value = self.outcomes.pop(0)
        if isinstance(value, BaseException): raise value
        return value
    def close(self): self.closed = True


class GrowattPollingTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(poller.socket, 'socket', side_effect=AssertionError('External sockets forbidden')).start()
        patch.object(poller.mqtt, 'Client', side_effect=AssertionError('Real MQTT forbidden')).start()
        patch.object(poller.requests, 'Session', side_effect=AssertionError('Real HA forbidden')).start()

    def test_one_request_filters_only_configured_entities(self):
        response = Response([state(), state('sensor.energy', '5.5'), state('sensor.private', 'secret'), None, {'entity_id': []}])
        session = Session(response)
        got = poller.ha_get_states(session, MAP.values())
        self.assertEqual(set(got), set(MAP.values()))
        self.assertEqual(session.gets, [(poller.HA_BASE_URL+'/api/states', {'timeout': poller.REQUEST_TIMEOUT_SECONDS})])
        self.assertTrue(response.closed)

    def test_27_metric_cycle_has_one_get(self):
        mapping = poller.DEFAULT_ENTITY_MAP
        session = Session(Response([state(entity, str(n)) for n, entity in enumerate(mapping.values())]))
        payload = poller.poll_payload(session, mapping)
        self.assertEqual(len(mapping), 27)
        self.assertEqual(len(session.gets), 1)
        self.assertEqual(payload['entity_count'], 27)
        self.assertEqual(set(payload['meta']), set(mapping))

    def test_missing_unknown_and_unavailable_do_not_remove_good_entities(self):
        mapping = dict(MAP, absent='sensor.absent', unavailable='sensor.offline', unknown='sensor.unknown')
        session = Session(Response([state(), state('sensor.energy', 'unknown'),
            state('sensor.offline', 'unavailable'), state('sensor.unknown', 'NaN')]))
        payload = poller.poll_payload(session, mapping)
        self.assertEqual(payload['entity_count'], 1)
        self.assertEqual(payload['power_w'], 42.0)
        self.assertEqual(set(payload['meta']), {'power_w'})
        self.assertNotIn('energy_kwh', payload)

    def test_two_metric_aliases_share_the_same_snapshot_without_extra_get(self):
        session = Session(Response([state()]))
        payload = poller.poll_payload(session, {'first': 'sensor.power', 'second': 'sensor.power'})
        self.assertEqual(payload['first'], payload['second'])
        self.assertEqual(payload['entity_count'], 2)
        self.assertEqual(len(session.gets), 1)

    def test_payload_preserves_original_fields_with_additive_age_metadata(self):
        source = state()
        payload = poller.build_payload({'sensor.power': source}, MAP, observed_at=NOW)
        self.assertEqual(payload['source'], 'home_assistant')
        self.assertEqual(payload['sample_time'], NOW.isoformat())
        self.assertEqual(payload['power_w'], 42.0)
        self.assertEqual(payload['entity_count'], 1)
        meta = payload['meta']['power_w']
        self.assertEqual(meta, dict(entity_id='sensor.power', unit='W', friendly_name='Fixture',
            last_updated=source['last_updated'], observed_at=NOW.isoformat(), ha_state_age_seconds=30.0))
        self.assertEqual(set(payload), {'source', 'sample_time', 'power_w', 'entity_count', 'meta'})

    def test_separate_entity_ages_do_not_refresh_older_ha_state(self):
        states = {'sensor.power': state(age=3), 'sensor.energy': state('sensor.energy', '10', age=86400)}
        payload = poller.build_payload(states, MAP, observed_at=NOW)
        self.assertEqual(payload['meta']['power_w']['ha_state_age_seconds'], 3)
        self.assertEqual(payload['meta']['energy_kwh']['ha_state_age_seconds'], 86400)
        self.assertEqual(payload['meta']['energy_kwh']['last_updated'], states['sensor.energy']['last_updated'])
        later = poller.build_payload(states, MAP, observed_at=NOW+timedelta(seconds=60))
        self.assertEqual(later['meta']['energy_kwh']['ha_state_age_seconds'], 86460)

    def test_invalid_naive_or_future_timestamps_are_unknown_age(self):
        for stamp in (None, '', 'broken', 123, '2026-11-02T15:00:00', (NOW+timedelta(seconds=1)).isoformat()):
            with self.subTest(stamp=stamp): self.assertIsNone(poller.ha_state_age(stamp, NOW))
        self.assertEqual(poller.ha_state_age('2026-11-02T15:00:00Z', NOW), 0)
        self.assertEqual(poller.ha_state_age('2026-11-02T16:59:30+02:00', NOW), 30)

    def test_observation_timestamp_is_taken_after_the_http_read(self):
        clock = [NOW]
        session = Session(Response([state()]))
        session.after_get = lambda: clock.__setitem__(0, NOW+timedelta(seconds=7))
        fake_datetime = SimpleNamespace(now=lambda tz: clock[0], fromisoformat=datetime.fromisoformat)
        with patch.object(poller, 'datetime', fake_datetime): payload = poller.poll_payload(session, MAP)
        self.assertEqual(payload['sample_time'], clock[0].isoformat())
        self.assertEqual(payload['meta']['power_w']['ha_state_age_seconds'], 37)

    def test_bad_attributes_do_not_drop_an_otherwise_usable_state(self):
        source = state(); source['attributes'] = 'invalid'
        payload = poller.build_payload({'sensor.power': source}, MAP, observed_at=NOW)
        self.assertEqual(payload['power_w'], 42)
        self.assertIsNone(payload['meta']['power_w']['unit'])
        self.assertIsNone(payload['meta']['power_w']['friendly_name'])

    def test_timeout_cycle_is_empty_then_next_snapshot_recovers_without_replay(self):
        session = Session(Response([state()]), requests.ReadTimeout('fixture'), Response([state(value='84')]))
        good = poller.poll_payload(session, MAP)
        with patch('sys.stdout', new=io.StringIO()): failed = poller.poll_payload(session, MAP)
        recovered = poller.poll_payload(session, MAP)
        self.assertEqual(good['power_w'], 42)
        self.assertEqual(failed['entity_count'], 0); self.assertEqual(failed['meta'], {})
        self.assertNotIn('power_w', failed)
        self.assertEqual(recovered['power_w'], 84)
        self.assertEqual(len(session.gets), 3)

    def test_http_json_and_mid_body_timeout_fail_once_and_close_response(self):
        for response in (Response(error=requests.HTTPError('401')), Response(json_error=ValueError('bad JSON')),
                         Response(json_error=requests.ReadTimeout('partial response'))):
            with self.subTest(error=response.error or response.json_error):
                session = Session(response)
                with patch('sys.stdout', new=io.StringIO()): payload = poller.poll_payload(session, MAP)
                self.assertEqual(payload['entity_count'], 0)
                self.assertTrue(response.closed); self.assertEqual(len(session.gets), 1)

    def test_non_list_response_fails_without_entity_fallback(self):
        for bad in ({'message': 'unauthorized'}, None, 'truncated snapshot'):
            session = Session(Response(bad))
            with patch('sys.stdout', new=io.StringIO()): payload = poller.poll_payload(session, MAP)
            self.assertEqual(payload['entity_count'], 0)
            self.assertEqual(len(session.gets), 1)

    def test_numeric_and_text_coercion_remains_compatible(self):
        for value, expected in (('1.25', 1.25), (' -2 ', -2.0), ('online', 'online'), ('', None),
                                ('unknown', None), ('unavailable', None), ('none', None), ('NaN', None), (None, None)):
            with self.subTest(value=value): self.assertEqual(poller.coerce_state(value), expected)

    def test_publish_keeps_topic_qos_retain_and_json_contract(self):
        calls = []
        client = SimpleNamespace(publish=lambda *a, **kw: calls.append((a, kw)))
        payload = poller.build_payload({'sensor.power': state()}, MAP, observed_at=NOW)
        with patch.object(poller, 'MQTT_QOS', 1): poller.publish_json(client, 'fixture/telemetry', payload, retain=True)
        args, options = calls[0]
        self.assertEqual(args[0], 'fixture/telemetry'); self.assertEqual(json.loads(args[1]), payload)
        self.assertEqual(options, dict(qos=1, retain=True))

    def test_actual_ingest_mapping_keeps_ha_metrics_and_existing_json_meta(self):
        source = Path(__file__).resolve().parents[2]/'hc_ingest/mqtt_ingest_multi.py'
        tree = ast.parse(source.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'growatt_metric_items')
        namespace = {}
        exec('from typing import Any, Optional, List, Tuple', namespace)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        payload = poller.build_payload({'sensor.power': state()}, {'system_power_w': 'sensor.power'}, observed_at=NOW)
        mapped = namespace['growatt_metric_items']('homecontrol/tele/growatt/cloud', payload)
        self.assertIsNone(mapped)  # The unchanged generic path consumes HA's flat keys.
        generic = dict(payload.items())
        self.assertEqual(generic['system_power_w'], 42)
        self.assertEqual(generic['meta']['system_power_w']['ha_state_age_seconds'], 30)

    def run_main(self, outcomes, cycles=1, mapping=MAP):
        session = Session(*outcomes)
        sent, progress = [], []
        clock = [0.0]
        class Client:
            def publish(self, topic, payload, **kw): sent.append((topic, payload, kw))
            def connect_async(self, *args, **kw): pass
            def loop_start(self): pass
            def loop_stop(self): self.stopped = True
            def disconnect(self): self.disconnected = True
            def is_connected(self): return True
        client = Client()
        class Health:
            def __init__(self, **kw): self.maximum = kw['maximum']; self.closed = False
            def start(self, callback): self.observations = callback()
            def progress(self, **kw):
                progress.append(kw)
                if len(progress) >= cycles: poller.running = False
            def close(self): self.closed = True
        health = Health(maximum=1)
        def make_health(**kw): health.maximum = kw['maximum']; return health
        with ExitStack() as stack:
            for name, value in dict(HA_TOKEN='synthetic-HA-token', running=True, POLL_SECONDS=1,
                    REQUEST_TIMEOUT_SECONDS=15, WorkerHealth=make_health, load_entity_map=lambda: mapping,
                    configure_mqtt_auth=lambda c: None).items():
                stack.enter_context(patch.object(poller, name, value))
            stack.enter_context(patch.object(poller.requests, 'Session', return_value=session))
            stack.enter_context(patch.object(poller.mqtt, 'Client', return_value=client))
            stack.enter_context(patch.object(poller.time, 'monotonic', side_effect=lambda: clock[0]))
            stack.enter_context(patch.object(poller.time, 'sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0]+seconds)))
            stack.enter_context(patch.object(poller.time, 'time', side_effect=AssertionError('Poll cadence must use monotonic time')))
            stack.enter_context(patch('sys.stdout', new=io.StringIO()))
            poller.main()
        return session, sent, progress, health, client, clock[0]

    def test_main_one_snapshot_one_publish_and_shutdown(self):
        session, sent, progress, health, client, elapsed = self.run_main([Response([state()])])
        telemetry = [(topic, json.loads(body), kw) for topic, body, kw in sent if topic == poller.BASE_TOPIC]
        self.assertEqual(len(telemetry), 1); self.assertEqual(len(session.gets), 1)
        self.assertEqual(telemetry[0][1]['entity_count'], 1)
        self.assertNotIn('synthetic-HA-token', json.dumps(telemetry))
        self.assertEqual(session.headers['Authorization'], 'Bearer synthetic-HA-token')
        self.assertEqual(progress, [{'success': True}]); self.assertTrue(health.closed)
        self.assertTrue(session.closed and client.stopped and client.disconnected)
        self.assertEqual(sent[-1], (poller.BASE_TOPIC+'/availability', 'offline', dict(qos=poller.MQTT_QOS, retain=True)))

    def test_main_timeout_then_recovery_keeps_one_attempt_per_cycle_and_monotonic_wait(self):
        session, sent, progress, health, client, elapsed = self.run_main([requests.Timeout('offline'), Response([state()])], cycles=2)
        payloads = [json.loads(body) for topic, body, kw in sent if topic == poller.BASE_TOPIC]
        self.assertEqual([p['entity_count'] for p in payloads], [0, 1])
        self.assertEqual(progress, [{'success': False}, {'success': True}])
        self.assertEqual(len(session.gets), 2); self.assertEqual(elapsed, 1)

    def test_health_stall_allowance_no_longer_scales_with_entity_count(self):
        maxima = []
        for mapping in ({'only': 'sensor.power'}, poller.DEFAULT_ENTITY_MAP):
            *_, health, client, elapsed = self.run_main([Response([state()])], mapping=mapping)
            maxima.append(health.maximum)
        self.assertEqual(maxima, [120, 120])  # Test interval=1; production interval=60 gives 180.


if __name__ == '__main__':
    unittest.main()
