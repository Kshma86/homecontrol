import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from command_service import CommandService
from context_service import ContextService
from read_model_cache import ReadModelCache, ReadModelChanged
from runtime_utils import ApiCache
from tests import test_irrigation_service as irrigation_fixture


def production_function(name, namespace):
    tree = ast.parse((Path(__file__).parents[1] / 'app.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'app.py', 'exec'), namespace)
    return namespace[name]


class ReadModelCacheTest(unittest.TestCase):
    def race(self, read, invalidate, expected_calls=None):
        started, release = threading.Event(), threading.Event()
        version = [0]
        calls = []

        def build():
            captured = version[0]
            calls.append(captured)
            if len(calls) == 1:
                started.set()
                if not release.wait(3):
                    raise AssertionError('test builder not released')
            return {'value': captured, 'nested': []}

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = pool.submit(read, build)
            try:
                self.assertTrue(started.wait(3))
                version[0] = 1
                # Invalidating must complete without waiting for the slow builder.
                pool.submit(invalidate).result(2)
            finally:
                release.set()
            self.assertEqual(result.result(3)['value'], 1)
        self.assertEqual(read(build)['value'], 1)
        self.assertEqual(calls, [0, 1] if expected_calls is None else expected_calls)

    def test_context_invalidation_during_build_never_returns_old_result(self):
        builder = [None]
        context = ContextService({'irrigation': lambda: builder[0]()})
        def read(build):
            builder[0] = build
            return context.section('irrigation')
        self.race(read, lambda: context.invalidate('irrigation'))

    def test_api_prefix_invalidation_includes_first_inflight_miss(self):
        cache = ApiCache()
        self.race(lambda build: cache.cached_payload('statistics:24h', 60, build),
                  lambda: cache.delete_prefix('statistics:'))

    def test_invalidate_all_includes_inflight_build(self):
        cache = ReadModelCache()
        self.race(lambda build: cache.cached_payload('key', 60, build), cache.invalidate)

    def test_parallel_misses_use_one_builder(self):
        cache = ApiCache()
        gate = threading.Barrier(13)
        started, release, all_waiting = threading.Event(), threading.Event(), threading.Event()
        waiters = []
        original_wait = cache.condition.wait
        def wait(*args, **kwargs):
            waiters.append(threading.get_ident())
            if len(set(waiters)) == 11:
                all_waiting.set()
            return original_wait(*args, **kwargs)
        build = Mock(side_effect=lambda: (started.set(), release.wait(3), {'items': []})[-1])
        def read():
            gate.wait(3)
            return cache.cached_payload('one', 60, build)
        with patch.object(cache.condition, 'wait', side_effect=wait), ThreadPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(read) for _ in range(12)]
            gate.wait(3)
            try:
                self.assertTrue(started.wait(3))
                self.assertTrue(all_waiting.wait(3))
            finally:
                release.set()
            values = [f.result(3) for f in futures]
        self.assertEqual(build.call_count, 1)
        values[0]['items'].append('mutation')
        self.assertEqual(values[1], {'items': []})
        self.assertEqual(cache.get('one'), {'items': []})

    def test_force_refresh_joins_an_existing_refresh(self):
        cache = ReadModelCache()
        cache.cached_payload('key', 60, lambda: 0)
        started, release, waiting = threading.Event(), threading.Event(), threading.Event()
        def build():
            started.set()
            self.assertTrue(release.wait(3))
            return 1
        build = Mock(side_effect=build)
        original_wait = cache.condition.wait
        def wait(*args, **kwargs):
            waiting.set()
            return original_wait(*args, **kwargs)
        with patch.object(cache.condition, 'wait', side_effect=wait), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(cache.cached_payload, 'key', 60, build, force=True)
            try:
                self.assertTrue(started.wait(3))
                second = pool.submit(cache.cached_payload, 'key', 60, build, force=True)
                self.assertTrue(waiting.wait(3))
            finally:
                release.set()
            self.assertEqual([first.result(3), second.result(3)], [1, 1])
        self.assertEqual(build.call_count, 1)

    def test_slow_key_does_not_block_unrelated_keys(self):
        cache = ReadModelCache()
        started, release = threading.Event(), threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            slow = pool.submit(cache.cached_payload, 'slow', 60,
                               lambda: (started.set(), release.wait(3), 'slow')[-1])
            try:
                self.assertTrue(started.wait(3))
                self.assertEqual(pool.submit(cache.cached_payload, 'fast', 60, lambda: 'fast').result(1), 'fast')
            finally:
                release.set()
            slow.result(3)

    def test_builder_exception_releases_owner_and_waiter_recovers(self):
        cache = ReadModelCache()
        started, release, waiting = threading.Event(), threading.Event(), threading.Event()
        def fail():
            started.set()
            self.assertTrue(release.wait(3))
            raise ValueError('DB unavailable')
        original_wait = cache.condition.wait
        def wait(*args, **kwargs):
            waiting.set()
            return original_wait(*args, **kwargs)
        with patch.object(cache.condition, 'wait', side_effect=wait), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(cache.cached_payload, 'key', 60, fail)
            try:
                self.assertTrue(started.wait(3))
                second = pool.submit(cache.cached_payload, 'key', 60, lambda: 'recovered')
                self.assertTrue(waiting.wait(3))
            finally:
                release.set()
            with self.assertRaisesRegex(ValueError, 'DB unavailable'):
                first.result(3)
            self.assertEqual(second.result(3), 'recovered')

    def test_context_error_is_not_cached_and_trace_contract_is_preserved(self):
        build = Mock(side_effect=[ValueError('offline'), {'value': 1}])
        service = ContextService({'weather': build})
        self.assertFalse(service.section('weather')['ok'])
        trace = []
        value = service.section('weather', trace=trace)
        self.assertTrue(value['ok'])
        service.section('weather', trace=trace)
        self.assertEqual([r['cache_hit'] for r in trace], [False, True])
        self.assertEqual(build.call_count, 2)
        self.assertIn('built_at', value['_context'])

    def test_ttl_starts_when_slow_build_finishes(self):
        clock = [0]
        cache = ReadModelCache(clock=lambda: clock[0])
        def build():
            clock[0] = 100
            return 'ready'
        cache.cached_payload('key', 5, build)
        clock[0] = 104
        self.assertEqual(cache.get('key'), 'ready')
        clock[0] = 105
        self.assertIsNone(cache.get('key'))

    def test_prefix_invalidation_preserves_other_statistics(self):
        cache = ApiCache()
        cache.set('irrigation:24h', [1], 60)
        cache.set('home:24h', [2], 60)
        cache.delete_prefix('irrigation:')
        self.assertIsNone(cache.get('irrigation:24h'))
        self.assertEqual(cache.get('home:24h'), [2])

    def test_explicit_set_wins_over_old_inflight_builder(self):
        cache = ReadModelCache()
        self.race(lambda build: cache.cached_payload('key', 60, build),
                  lambda: cache.set('key', {'value': 1, 'nested': []}, 60), expected_calls=[0])

    def test_recursive_same_key_fails_instead_of_deadlocking(self):
        cache = ReadModelCache()
        with self.assertRaisesRegex(RuntimeError, 'recursive'):
            cache.cached_payload('key', 60, lambda: cache.cached_payload('key', 60, lambda: 1))
        self.assertEqual(cache.cached_payload('key', 60, lambda: 2), 2)

    def test_continuous_invalidation_is_bounded_and_recovers(self):
        cache = ReadModelCache()
        def build():
            cache.invalidate('key')
            return 'superseded'
        builder = Mock(side_effect=build)
        with self.assertRaises(ReadModelChanged):
            cache.cached_payload('key', 60, builder)
        self.assertEqual(builder.call_count, 3)
        self.assertEqual(cache.cached_payload('key', 60, lambda: 'recovered'), 'recovered')

    def test_context_reports_invalidation_storm_without_stale_success(self):
        context = ContextService({})
        context.builders['key'] = lambda: (context.invalidate('key'), {'value': 'stale'})[-1]
        value = context.section('key')
        self.assertFalse(value['ok'])
        self.assertEqual(value['error'], 'read_model_changed_during_build')
        context.builders['key'] = lambda: {'value': 'fresh'}
        self.assertEqual(context.section('key')['value'], 'fresh')

    def test_irrigation_owner_preserves_configured_domain_ttl(self):
        context = ContextService({'irrigation': lambda: {}}, realtime_ttl=5,
                                 section_ttls={'irrigation': 10})
        self.assertEqual(context.section('irrigation')['_context']['ttl_sec'], 10)

    def test_all_irrigation_read_caches_respect_inflight_invalidation(self):
        for read_method, build_method, invalidator in (
            ('snapshot', 'build_snapshot', 'invalidate_snapshot_cache'),
            ('cached_pilot_recommendation', 'evaluate_pilot', 'invalidate_pilot_cache'),
            ('cached_weather_summary', 'weather_summary', 'invalidate_weather_summary_cache'),
        ):
            with self.subTest(read=read_method):
                service = irrigation_fixture.IrrigationServiceTest().service()
                def read(build):
                    setattr(service, build_method, build)
                    return getattr(service, read_method)()
                self.race(read, getattr(service, invalidator))

    def test_mqtt_invalidation_clears_context_and_api_caches(self):
        api = ApiCache()
        domain = irrigation_fixture.IrrigationServiceTest().service()
        version = [0]
        build = Mock(side_effect=lambda: {'value': version[0]})
        invalidators = production_function('context_invalidators', {'API_CACHE': api, '_irrigation_service': domain})()
        for section, key, topic in (
            ('tuya', 'tuya_state', 'homecontrol/tele/tuya/device'),
            ('power_wall', 'power_wall_state', 'homecontrol/tele/tuya/device'),
            ('irrigation_statistics', 'irrigation_statistics:24h', 'zigbee/0xa4c13880b130079c'),
        ):
            with self.subTest(section=section):
                context = ContextService({section: lambda: api.cached_payload(key, 60, build)}, invalidators=invalidators)
                command = CommandService(lambda: context)
                version[0] += 1
                old = context.section(section)['value']
                version[0] += 1
                command.observe_mqtt_topic(topic)
                self.assertNotEqual(context.section(section)['value'], old)
                api.invalidate()

    def test_mqtt_invalidation_rebuilds_pilot_and_weather_dependencies(self):
        api = ApiCache()
        domain = irrigation_fixture.IrrigationServiceTest().service()
        version = [0]
        domain.weather_summary = lambda: {'value': version[0]}
        domain.evaluate_pilot = lambda: domain.cached_weather_summary()
        invalidators = production_function('context_invalidators', {'API_CACHE': api, '_irrigation_service': domain})()
        context = ContextService({'irrigation_pilot': domain.cached_pilot_recommendation}, invalidators=invalidators)
        self.assertEqual(context.section('irrigation_pilot')['value'], 0)
        version[0] = 1
        CommandService(lambda: context).observe_mqtt_topic('homecontrol/tele/irrigation/esp-irrigation-1/pump_metrics')
        self.assertEqual(context.section('irrigation_pilot')['value'], 1)

    def test_context_irrigation_uses_one_owner_instead_of_inner_ttl(self):
        domain = Mock()
        domain.build_snapshot.return_value = {'value': 1}
        builders = production_function('context_builders', {'get_irrigation_service': lambda: domain,
                                       'tuya_state_payload': lambda: {}, 'solar_state_payload': lambda: {}})()
        context = ContextService({'irrigation': builders['irrigation']}, realtime_ttl=5)
        context.section('irrigation')
        context.section('irrigation')
        domain.build_snapshot.assert_called_once()
        domain.snapshot.assert_not_called()

    def test_statistical_ttl_stays_longer_than_realtime(self):
        context = ContextService({'irrigation': lambda: {}, 'irrigation_statistics': lambda: {}},
                                 realtime_ttl=5, statistics_ttl=60)
        self.assertEqual(context.section('irrigation')['_context']['ttl_sec'], 5)
        self.assertEqual(context.section('irrigation_statistics')['_context']['ttl_sec'], 60)

    def test_command_pilot_invalidation_also_clears_context(self):
        domain = irrigation_fixture.IrrigationServiceTest().service()
        version = [0]
        domain.evaluate_pilot = lambda: {'value': version[0]}
        namespace = {'API_CACHE': ApiCache(), '_irrigation_service': domain}
        invalidators = production_function('context_invalidators', namespace)()
        context = ContextService({'irrigation_pilot': domain.cached_pilot_recommendation}, invalidators=invalidators)
        namespace['_context_service'] = context
        invalidate = production_function('invalidate_irrigation_pilot_cache', namespace)
        self.assertEqual(context.section('irrigation_pilot')['value'], 0)
        version[0] = 1
        invalidate()
        self.assertEqual(context.section('irrigation_pilot')['value'], 1)

    def test_api_prefix_command_invalidation_also_clears_outer_context(self):
        api = ApiCache()
        version = [0]
        namespace = {'API_CACHE': api}
        namespace['api_cache_context_sections'] = production_function('api_cache_context_sections', namespace)
        invalidators = production_function('context_invalidators', namespace)()
        context = ContextService({'irrigation_statistics': lambda: api.cached_payload(
            'irrigation_statistics:24h', 60, lambda: {'value': version[0]})}, invalidators=invalidators)
        namespace['_context_service'] = context
        invalidate = production_function('api_cache_delete_prefix', namespace)
        self.assertEqual(context.section('irrigation_statistics')['value'], 0)
        version[0] = 1
        invalidate('irrigation_statistics')
        self.assertEqual(context.section('irrigation_statistics')['value'], 1)

    def test_empty_api_prefix_also_clears_keys_without_context_owner(self):
        api = ApiCache()
        namespace = {'API_CACHE': api}
        namespace['api_cache_context_sections'] = production_function('api_cache_context_sections', namespace)
        context = ContextService({'tuya': lambda: {}})
        namespace['_context_service'] = context
        invalidate = production_function('api_cache_delete_prefix', namespace)
        api.set('custom_without_context', 1, 60)
        invalidate('')
        self.assertIsNone(api.get('custom_without_context'))

    def test_pilot_and_weather_dependency_invalidation_is_atomic(self):
        domain = irrigation_fixture.IrrigationServiceTest().service()
        version = [0]
        domain.weather_summary = lambda: {'value': version[0]}
        domain.evaluate_pilot = domain.cached_weather_summary
        self.assertEqual(domain.cached_pilot_recommendation()['value'], 0)
        halfway, release = threading.Event(), threading.Event()
        original = domain.invalidate_pilot_cache
        def invalidate_pilot():
            original()
            halfway.set()
            self.assertTrue(release.wait(3))
        invalidators = production_function('context_invalidators', {'API_CACHE': ApiCache(), '_irrigation_service': domain})()
        with patch.object(domain, 'invalidate_pilot_cache', side_effect=invalidate_pilot), ThreadPoolExecutor(max_workers=2) as pool:
            invalidation = pool.submit(invalidators['irrigation_pilot'])
            try:
                self.assertTrue(halfway.wait(3))
                version[0] = 1
                read = pool.submit(domain.cached_pilot_recommendation)
                with self.assertRaises(TimeoutError):
                    read.result(.1)
            finally:
                release.set()
            invalidation.result(3)
            self.assertEqual(read.result(3)['value'], 1)


if __name__ == '__main__':
    unittest.main()
