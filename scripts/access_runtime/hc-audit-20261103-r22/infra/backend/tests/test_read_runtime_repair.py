"""HC-13/14/21/40 failure and lifecycle contracts; no device I/O."""
import ast
import importlib.util
from pathlib import Path
import tempfile
import threading
import time
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ai_context_plan import context_sections
import ai_domain_replies
from ai_proxy_service import AiProxyService, AiKnowledgeLoader
from ai_node_service import AiNodeService
from context_service import ContextService
from mqtt_monitor_service import TopicMonitorState
from tests.test_irrigation_service import IrrigationServiceTest
from tests.test_startup_service import StartupServiceTest
from worker_runtime import BoundedJobs, Busy, ProcessOwner, RequestCapacity
import system_status_service as system


class RuntimeRepairTest(unittest.TestCase):
    def test_ai_power_stop_during_wait_does_not_dispatch_one_more_intent(self):
        service = AiNodeService(lambda *a: None, lambda *a: None, lambda *a: None, lambda *a: None,
                                start_worker=False)
        calls = []
        service.run_pending_power = lambda: calls.append('power dispatch')
        with patch.object(service._power_event, 'wait', side_effect=lambda timeout: service._power_stop.set()):
            service._power_loop()
        self.assertEqual(calls, [])
        service.stop_worker(0)

    def test_socket_deadline_is_total_even_if_data_keeps_arriving(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'docker.sock')
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(path)
            server.listen(1)
            def send():
                peer, _ = server.accept()
                try:
                    peer.recv(4096)
                    peer.sendall(b'{"ok":true,"value":"')
                    for _ in range(20):
                        peer.sendall(b'x')
                        time.sleep(.01)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    peer.close()
            thread = threading.Thread(target=send, daemon=True)
            thread.start()
            try:
                started = time.monotonic()
                with patch.dict('os.environ', {'HC_HOST_OPS_SOCKET': path}), self.assertRaises(TimeoutError):
                    system.docker_socket_request('GET', '/containers/json?all=1', timeout=.05)
                self.assertLess(time.monotonic()-started, .2)
            finally:
                server.close()
                thread.join(1)

    def test_unfinished_resource_keeps_control_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            service = StartupServiceTest().service([], False)
            service._owner = ProcessOwner(str(Path(directory) / 'owner'))
            other = ProcessOwner(service._owner.path)
            try:
                service.ensure_started()
                service.shutdown_resources = lambda timeout: False
                self.assertFalse(service.stop(2))
                with self.assertRaises(RuntimeError):
                    other.acquire()
                service.shutdown_resources = lambda timeout: True
                self.assertTrue(service.stop(2))
                other.acquire()
            finally:
                service.shutdown_resources = lambda timeout: True
                service.stop(2)
                other.release()

    def test_mqtt_stop_interrupts_retry_and_disconnect_failure_is_contained(self):
        monitor = TopicMonitorState(mqtt_host='unused', mqtt_port=1883, client_id='test',
                                    thread_name='test-mqtt', subscriptions=lambda: [])
        attempted = threading.Event()
        class Client:
            def connect(self, *args, **kwargs):
                attempted.set()
                raise OSError('offline')
            def disconnect(self):
                raise OSError('already closed')
        with patch('mqtt_monitor_service.mqtt.Client', return_value=Client()):
            thread = monitor.start()
            self.assertIs(monitor.start(), thread)
            self.assertTrue(attempted.wait(1))
            self.assertTrue(monitor.stop(1))
        state = monitor.worker_status()
        self.assertFalse(state['running'])
        self.assertTrue(state['stopping'])
        with self.assertRaises(RuntimeError):
            monitor.start()

    def test_owner_rejects_second_controller_before_bootstrap_and_releases_on_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            first = StartupServiceTest().service([], False)
            second_calls = []
            second = StartupServiceTest().service(second_calls, False)
            for service in (first, second):
                service._owner = ProcessOwner(str(Path(directory) / 'owner'))
            try:
                first.ensure_started()
                first.ensure_started()
                with self.assertRaises(RuntimeError):
                    second.ensure_started()
                self.assertEqual(second_calls, [])
                self.assertTrue(first.stop(2))
                second.ensure_started()
                self.assertIn('bootstrap', second_calls)
                self.assertTrue(second.stop(2))
            finally:
                first.stop(2)
                second.stop(2)

    def test_stalled_cycle_is_reported_and_keeps_owner_until_it_finishes(self):
        release, entered = threading.Event(), threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            service = StartupServiceTest().service([], False)
            path = str(Path(directory) / 'owner')
            service._owner = ProcessOwner(path)
            def refresh():
                entered.set()
                release.wait(3)
            service.summary_refresh = refresh
            other = ProcessOwner(path)
            try:
                service.ensure_started()
                self.assertTrue(entered.wait(1))
                with patch('startup_service.time.monotonic', return_value=time.monotonic() + 65):
                    state = next(w for w in service.status()['workers'] if w['name'] == 'summary-refresh')
                self.assertTrue(state['running'])
                self.assertTrue(state['stalled'])
                self.assertFalse(service.stop(.01))
                with self.assertRaises(RuntimeError):
                    other.acquire()
                release.set()
                self.assertTrue(service.stop(2))
                other.acquire()
            finally:
                release.set()
                service.stop(2)
                other.release()

    def test_cycle_error_does_not_claim_success_or_restart_worker(self):
        service = StartupServiceTest().service([], False)
        service._cycle('summary-refresh', lambda: ['database'])
        row = next(w for w in service.status()['workers'] if w['name'] == 'summary-refresh')
        self.assertEqual(row['error'], 'database')
        self.assertIsNotNone(row['last_cycle_age_sec'])
        self.assertIsNone(row['last_success_age_sec'])
        service._cycle('summary-refresh', lambda: None)
        self.assertEqual(service._progress['summary-refresh']['error'], '')

    def test_timed_out_jobs_keep_capacity_and_stop_is_bounded(self):
        jobs = BoundedJobs('synthetic', 1)
        release = threading.Event()
        try:
            future = jobs.submit(release.wait, 2)
            with self.assertRaises(TimeoutError):
                future.result(timeout=.01)
            with self.assertRaises(Busy):
                jobs.submit(lambda: None)
            started = time.monotonic()
            self.assertFalse(jobs.stop(.01))
            self.assertLess(time.monotonic() - started, .2)
            with self.assertRaises(Busy):
                jobs.submit(lambda: None)
            release.set()
            future.result(1)
            self.assertTrue(jobs.stop(1))
        finally:
            release.set()
            jobs.stop(1)

    def test_long_requests_have_five_slots_and_do_not_gate_controls(self):
        capacity = RequestCapacity()
        self.assertEqual(sum(capacity.limits.values()), 5)
        for category, limit in capacity.limits.items():
            for _ in range(limit):
                self.assertTrue(capacity.acquire(category))
            self.assertFalse(capacity.acquire(category))
            for _ in range(limit):
                capacity.release(category)
        self.assertIsNone(capacity.category('/api/irrigation/command'))
        self.assertEqual(capacity.category('/api/ai/chat'), 'ai')
        self.assertEqual(capacity.category('/api/mower/live', 'websocket'), 'websocket')

    def test_gunicorn_refuses_duplicate_or_preloaded_control_workers(self):
        import gunicorn_conf
        for workers, preload in [(2, False), (1, True)]:
            with self.assertRaises(RuntimeError):
                gunicorn_conf.on_starting(SimpleNamespace(cfg=SimpleNamespace(workers=workers, preload_app=preload)))
        gunicorn_conf.on_starting(SimpleNamespace(cfg=SimpleNamespace(workers=1, preload_app=False)))

    def test_docker_deadline_does_not_wait_for_second_stats_wave(self):
        jobs, requests = BoundedJobs('stats-test', 8), BoundedJobs('request-test', 1)
        containers = [{'state': 'running', 'id': str(i)} for i in range(16)]
        def slow(*args, **kwargs):
            time.sleep(2.4)
            return {'cpu_percent': 1}
        started = time.monotonic()
        try:
            with patch.object(system, 'DOCKER_STATS_JOBS', jobs), patch.object(system, 'DOCKER_REQUEST_JOBS', requests), \
                 patch.object(system, 'DOCKER_STATUS_CACHE', {'data': None, 'expires_at': 0}), \
                 patch.object(system, 'docker_socket_containers', return_value=containers), \
                 patch.object(system, 'docker_container_live_stats', side_effect=slow):
                result = system.docker_container_status()
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 4.3)
            self.assertGreater(elapsed, 3.8)
            self.assertLessEqual(jobs.status()['active'], 8)
            self.assertTrue(result.get('error') or any(c.get('stats_error') for c in result.get('containers', [])))
        finally:
            jobs.stop(2)
            requests.stop(2)


class SummaryRepairTest(unittest.TestCase):
    def test_refresh_failure_does_not_consume_success_ttl(self):
        calls = []
        def execute(sql):
            calls.append(sql)
            if len(calls) == 1:
                raise RuntimeError('synthetic rollback')
        service = IrrigationServiceTest().service(execute_sql=execute)
        service._summary_schema_ready = True
        with self.assertRaises(RuntimeError):
            service.refresh_daily_summaries()
        self.assertEqual(service._daily_summary_refresh['next_at'], 0)
        self.assertTrue(service.refresh_daily_summaries())
        self.assertFalse(service.refresh_daily_summaries())
        self.assertEqual(len(calls), 2)
        self.assertIn('summary_input', calls[-1])
        self.assertNotIn('latest_decision', calls[-1])

    def test_refresh_ttl_starts_after_completion_and_only_one_owner_writes(self):
        clock = [10.0]
        service = None
        def execute(sql):
            self.assertFalse(service.refresh_daily_summaries(force=True))
            clock[0] = 50.0
        service = IrrigationServiceTest().service(execute_sql=execute)
        service._summary_schema_ready = True
        with patch('irrigation_service.time.monotonic', side_effect=lambda: clock[0]):
            self.assertTrue(service.refresh_daily_summaries())
        self.assertEqual(service._daily_summary_refresh['next_at'], 350.0)

    def test_decision_refreshes_without_writing_disabled_ready_and_stale_states(self):
        writes = []
        service = IrrigationServiceTest().service(execute_one=lambda *args: writes.append(args))
        config = {'enabled': False}
        live = {'telemetry_age_sec': 1, 'pv_voltage_v': 22, 'battery_voltage_v': 13, 'charge_current_a': .1}
        service.fetch_solar_pump_config = lambda: config
        service.solar_pump_live_snapshot = lambda: dict(live)
        service.solar_pump_completed_minutes_today = lambda: 0
        service.active_solar_pump_run = lambda: None
        self.assertEqual(service.evaluate_solar_pump_scheduler()['state'], 'disabled')
        config['enabled'] = True
        self.assertTrue(service.evaluate_solar_pump_scheduler()['can_start'])
        live['telemetry_age_sec'] = 500
        self.assertEqual(service.evaluate_solar_pump_scheduler()['state'], 'waiting_telemetry')
        self.assertEqual(writes, [])


class AiContextRepairTest(unittest.TestCase):
    def test_ai_node_health_does_not_join_stuck_probes_after_deadline(self):
        release = threading.Event()
        service = AiNodeService(lambda *a: None, lambda *a: None, lambda *a: None, lambda *a: None,
                                start_worker=False)
        service.status_timeout = .5
        service.ollama_url_override = 'http://synthetic'
        service.tcp_probe = lambda *a: (release.wait(2), 'test')
        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self):
                release.wait(2)
                return b'{}'
        try:
            with patch('ai_node_service.ai_disabled', return_value=False), \
                 patch('ai_node_service.urlopen', return_value=Response()):
                started = time.monotonic()
                result = service.health()
                self.assertFalse(result['ok'])
                self.assertLess(time.monotonic()-started, 1.3)
                self.assertEqual(service.worker_status()['health_jobs']['active'], 2)
                self.assertFalse(service.health()['ok'])
                self.assertEqual(service.worker_status()['health_jobs']['active'], 2)
        finally:
            release.set()
            service.stop_worker(1)

    def test_hung_provider_body_has_one_transport_slot_and_total_deadline(self):
        release = threading.Event()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                release.wait(2)
                return b'{"ok":true}'
        service = AiProxyService('http://synthetic', .03, context_summary=lambda: {},
                                 json_ready=lambda x: x, urlopen_func=lambda *a, **k: Response())
        try:
            with patch('deployment_policy.ai_disabled', return_value=False):
                self.assertEqual(service.config()[1], 504)
                self.assertEqual(service.config()[1], 503)
                self.assertEqual(service.worker_status()['transport']['active'], 1)
                release.set()
                self.assertTrue(service.stop_worker(1))
        finally:
            release.set()
            service.stop_worker(1)

    def test_routing_names_current_domain_and_only_uses_history_for_followup(self):
        history = [{'role': 'user', 'content': 'klíma fogyasztása'}]
        self.assertEqual(context_sections('Mennyi az X10 akkumulátora?', history), ['robot'])
        self.assertEqual(context_sections('És 7 nap alatt?', history), ['climate_power_history'])
        self.assertEqual(context_sections('Mi Franciaország fővárosa?'), [])
        self.assertEqual(context_sections('klíma fogyasztása', images=True), [])
        self.assertEqual(context_sections('HC szerver fogyasztása'), ['server_power'])
        self.assertEqual(context_sections('moisture szenzor elemzése'), ['irrigation', 'irrigation_statistics'])

    def test_targeted_summary_builds_only_requested_sections_and_empty_means_none(self):
        calls = []
        service = ContextService({name: (lambda name=name: calls.append(name) or {})
                                  for name in ('robot', 'climate', 'irrigation', 'weather')})
        trace = []
        summary = service.ai_summary(sections=['robot'], trace=trace)
        self.assertEqual(calls, ['robot'])
        self.assertEqual([row['section'] for row in trace], ['robot'])
        self.assertNotIn('backup', summary)
        self.assertNotIn('climate', summary)
        self.assertEqual(summary['context_sections'], ['robot'])
        calls.clear()
        service.ai_summary(sections=[])
        self.assertEqual(calls, [])

    def test_proxy_and_server_share_identical_reply_functions(self):
        path = Path(__file__).resolve().parents[3] / 'apps/ai-server/ai_server.py'
        spec = importlib.util.spec_from_file_location('hc_ai_repair_server', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIs(module.direct_context_reply, ai_domain_replies.direct_context_reply)
        context = {'climate_power': {'today_energy_kwh': 3.14, 'current_power_w': 35, 'meter_name': 'test'}}
        expected = module.direct_context_reply('klíma fogyasztása', context, [])
        self.assertIn('3.14', expected)
        self.assertEqual(AiProxyService.direct_context_reply('klíma fogyasztása', context, []), expected)

    def test_canonical_domain_scenarios_and_missing_data_do_not_invent_facts(self):
        scenarios = [
            ('Sorold fel a locsolási ciklusokat', {'irrigation': {'analysis': {'cycles': {'recent': []}}}}, 'Nem látok naplózott'),
            ('HC szerver fogyasztása', {'server_power': {'ok': False, 'error': 'test missing'}}, 'test missing'),
            ('klíma fogyasztása', {'climate_power': {}}, 'nem elérhető'),
            ('Elemezd az AI kérések trendjét', {'ai_chat_audit': {'ok': False, 'error': 'audit missing'}}, 'audit missing'),
            ('Mik a beállítások?', {}, 'melyik modul'),
            ('Sorold fel a locsolási ciklusokat', {'irrigation': {'analysis': {'cycles': {'last_30d': [
                {'started_at': '2026-10-28T10:00:00+01:00', 'ended_at': '2026-10-28T10:05:00+01:00',
                 'duration_min': 5, 'status': 'completed', 'start_source': 'manual', 'stop_source': 'manual'}]}}}}, '5 perc'),
        ]
        for message, context, expected in scenarios:
            with self.subTest(message=message):
                self.assertIn(expected, ai_domain_replies.direct_context_reply(message, context, []))
        history = [{'role': 'user', 'content': 'klíma beállításai'}]
        self.assertEqual(ai_domain_replies.direct_context_reply('X10 beállításai', {'robot': {}}, history), '')
        self.assertIn('klíma', ai_domain_replies.direct_context_reply('És a beállítások?', {'climate': {}}, history))

    def test_context_error_keeps_only_target_trace_and_audits_provider_failure(self):
        from urllib.error import URLError
        calls, audits = [], []
        def broken():
            calls.append('robot')
            raise RuntimeError('fixture robot unavailable')
        contexts = ContextService({'robot': broken, 'backup': lambda: self.fail('unrequested backup')})
        def unavailable(*args, **kwargs):
            raise URLError('fixture provider unavailable')
        service = AiProxyService('http://synthetic', 1, context_summary=contexts.ai_summary,
                                 json_ready=lambda x: x, urlopen_func=unavailable, audit_logger=audits.append)
        try:
            with patch('deployment_policy.ai_disabled', return_value=False):
                payload, status = service.chat({'message': 'X10 állapot'})
            self.assertEqual(status, 502)
            self.assertIn('fixture provider unavailable', payload['error'])
            self.assertEqual(calls, ['robot'])
            self.assertEqual(audits[-1]['request_meta']['context_sections'], ['robot'])
            self.assertEqual(audits[-1]['source'], 'ai_server')
            self.assertTrue(any(row.get('error') for row in audits[-1]['context_timings']))
        finally:
            service.stop_worker(1)

    def test_context_internal_typeerror_is_not_retried_or_hidden(self):
        calls = []
        def context(*, trace=None, sections=None):
            calls.append(sections)
            raise TypeError('inside builder')
        service = AiProxyService('http://synthetic', 1, context_summary=context, json_ready=lambda x: x)
        with self.assertRaisesRegex(TypeError, 'inside builder'):
            service.chat({'message': 'X10 állapot'})
        self.assertEqual(calls, [['robot']])
        service.stop_worker(1)

    def test_ai_total_deadline_rejects_new_work_until_stuck_job_finishes(self):
        release = threading.Event()
        def context(**kwargs):
            release.wait(2)
            return {}
        audits = []
        service = AiProxyService('http://synthetic', .03, context_summary=context, json_ready=lambda x: x,
                                 audit_logger=audits.append)
        try:
            started = time.monotonic()
            self.assertEqual(service.chat({'message': 'hello'})[1], 504)
            self.assertLess(time.monotonic() - started, .3)
            self.assertEqual(service.chat({'message': 'hello'})[1], 503)
            self.assertEqual(service.worker_status()['active'], 1)
        finally:
            release.set()
            service.stop_worker(2)
        self.assertEqual(audits[-1]['status_code'], 504)
        self.assertEqual(audits[-1]['source'], 'deadline_exceeded')
