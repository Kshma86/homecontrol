import ast
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from health_routes import register_health_routes, PROBE_PATHS
from startup_runner import StartupRunner
from tests import test_startup_service as startup_fixture


class HealthRoutesTest(unittest.TestCase):
    def test_missing_worker_cannot_disappear_from_readiness(self):
        service = startup_fixture.StartupServiceTest().service([], safety_worker_enabled=True)
        service.bootstrap._ready = True
        self.assertFalse(service.readiness()['ok'])
        self.assertIn('scheduler', service.readiness()['missing_workers'])
        self.assertFalse(service.liveness()['ok'])

    def test_dependency_error_differs_from_stalled_worker(self):
        service = startup_fixture.StartupServiceTest().service([], safety_worker_enabled=True)
        service.bootstrap._ready = True
        service._started = service._required_workers()
        workers = [{'key':'mqtt-monitor','enabled':True,'running':True,'stalled':False,
                    'connected':False,'last_cycle_age_sec':0,'error':''}]
        service.status = lambda: {'workers':workers,'stopping':False}
        self.assertTrue(service.liveness()['ok'])
        self.assertFalse(service.readiness()['ok'])
        workers[0]['connected'] = True
        self.assertTrue(service.readiness()['ok'])
        workers[0]['stalled'] = True
        self.assertFalse(service.liveness()['ok'])
        self.assertFalse(service.readiness()['ok'])

    def test_live_before_bootstrap_and_readiness_without_creating_services(self):
        app = Flask(__name__)
        register_health_routes(app, lambda: None)
        client = app.test_client()
        self.assertEqual(client.get('/health/live').status_code, 200)
        self.assertEqual(client.get('/health/ready').status_code, 503)
        self.assertEqual(client.get('/health/workers').status_code, 200)

    def test_ready_and_stopping_are_separate_from_http_liveness(self):
        service = SimpleNamespace(_stop=threading.Event(), readiness=lambda: {'ok': False},
                                  liveness=lambda: {'ok': True})
        app = Flask(__name__)
        register_health_routes(app, lambda: service)
        client = app.test_client()
        self.assertEqual(client.get('/health/live').status_code, 200)
        self.assertEqual(client.get('/health/ready').status_code, 503)
        service.liveness = lambda: {'ok': False}
        self.assertEqual(client.get('/health/workers').status_code, 503)
        self.assertEqual(client.get('/health/live').status_code, 200)
        service.readiness = lambda: {'ok': True}
        self.assertEqual(client.get('/health/ready').status_code, 200)
        service._stop.set()
        self.assertEqual(client.get('/health/live').status_code, 503)

    def test_actual_request_hooks_skip_startup_and_performance_side_effects(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text())
        names = ('_start_worker_once', '_record_api_request')
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        for node in nodes:
            node.decorator_list = []
        def forbidden(*a, **kw):
            raise AssertionError('probe caused application side effect')
        for path in PROBE_PATHS:
            ns = {'request': SimpleNamespace(path=path), 'get_startup_service': forbidden,
                  'record_api_request': forbidden}
            exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual request hooks>', 'exec'), ns)
            self.assertIsNone(ns['_start_worker_once']())
            sentinel = object()
            self.assertIs(ns['_record_api_request'](sentinel), sentinel)

    def test_bootstrap_dependency_failure_retries_without_blocking_server(self):
        attempts, done = [], threading.Event()
        def start():
            attempts.append(True)
            if len(attempts) == 1:
                raise ConnectionError('fixture DB unavailable')
            done.set()
        runner = StartupRunner(start, delay=.01)
        runner.thread.start()
        self.assertTrue(done.wait(2))
        runner.stop()
        self.assertEqual(len(attempts), 2)
        self.assertFalse(runner.thread.is_alive())

    def test_stopping_interrupts_bootstrap_retry_wait(self):
        entered = threading.Event()
        def start():
            entered.set()
            raise ConnectionError()
        runner = StartupRunner(start, delay=100)
        runner.thread.start()
        self.assertTrue(entered.wait(2))
        runner.stop()
        self.assertFalse(runner.thread.is_alive())


if __name__ == '__main__':
    unittest.main()
