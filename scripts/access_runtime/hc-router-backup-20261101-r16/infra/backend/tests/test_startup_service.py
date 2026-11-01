import unittest
from pathlib import Path
import sys
import ast
import contextlib
import io
import threading
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from startup_service import BootstrapService, StartupService, run_guarded_callbacks


class StartupServiceTest(unittest.TestCase):
    def test_bootstrap_runs_callbacks_in_order(self):
        calls = []
        service = BootstrapService([lambda: calls.append("a"), lambda: calls.append("b")])

        service.ensure_all()

        self.assertEqual(calls, ["a", "b"])

    def test_bootstrap_ensure_once_runs_only_once(self):
        calls = []
        service = BootstrapService([lambda: calls.append("bootstrap")])

        service.ensure_once()
        service.ensure_once()

        self.assertEqual(calls, ["bootstrap"])

    def test_monitors_start_once(self):
        calls = []
        service = self.service(calls, safety_worker_enabled=False)

        def fake_start_once(name, target):
            if name in service._started:
                return
            service._started.add(name)
            calls.append(name)

        service._start_once = fake_start_once

        service.ensure_started()
        service.ensure_started()

        self.assertEqual(calls.count("openweather-poll"), 1)
        self.assertEqual(calls.count("power-wall-guard"), 1)
        self.assertEqual(calls.count("mqtt"), 1)
        self.assertEqual(calls.count("x10"), 1)
        self.assertEqual(calls.count("climate"), 1)
        self.assertEqual(calls.count("bootstrap"), 1)

    def test_safety_and_scheduler_are_separate_single_workers(self):
        calls = []
        service = self.service(calls, safety_worker_enabled=True)
        with patch("startup_service.threading.Thread") as thread:
            service.ensure_started()
            service.ensure_started()
        names = [call.kwargs["name"] for call in thread.call_args_list]
        self.assertEqual(names.count("irrigation-safety"), 1)
        self.assertEqual(names.count("scheduler"), 1)
        self.assertLess(names.index("irrigation-safety"), names.index("scheduler"))

    def test_disabled_safety_worker_does_not_start_scheduler(self):
        service = self.service([], safety_worker_enabled=False)
        with patch("startup_service.threading.Thread") as thread:
            service.ensure_started()
        self.assertNotIn("scheduler", [call.kwargs["name"] for call in thread.call_args_list])

    def test_safety_tick_runs_stop_checks_first_without_scheduler_work(self):
        calls = []
        service = self.service(calls, safety_worker_enabled=True)
        service.irrigation_scheduler_stop_tick = lambda: calls.append("v2_stop")
        service.irrigation_recovery_tick = lambda: calls.append("recovery")
        service._safety_tick()
        self.assertEqual(calls, ["recovery", "v2_stop", "stop", "fail"])

    def test_each_callback_error_cannot_skip_other_callbacks(self):
        groups = {
            "_safety_tick": ["irrigation_recovery_tick", "irrigation_scheduler_stop_tick", "stop_overdue_sessions", "fail_sessions_without_physical_watering"],
            "_scheduler_tick": ["record_scheduler_shadow_audit", "climate_scheduler_tick", "irrigation_scheduler_tick", "x10_scheduler_tick"],
        }
        for method, names in groups.items():
            for broken in names:
                with self.subTest(method=method, broken=broken):
                    calls = []
                    service = self.service([], safety_worker_enabled=True)
                    def callback(name):
                        def run():
                            calls.append(name)
                            if name == broken:
                                raise TimeoutError("injected DB/transport timeout")
                        return run
                    for name in names:
                        setattr(service, name, callback(name))
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        getattr(service, method)()
                    self.assertEqual(calls, names)
                    self.assertIn("injected DB/transport timeout", output.getvalue())

    def test_scheduler_dispatch_is_explicit_and_follows_audit(self):
        calls = []
        service = self.service(calls, safety_worker_enabled=True)
        service.climate_scheduler_tick = lambda: calls.append('climate_dispatch')
        service._scheduler_tick()
        self.assertEqual(calls, ['audit', 'climate_dispatch', 'irrigation', 'x10_tick'])

    def test_app_audit_callback_only_delegates_to_recording(self):
        source = Path(__file__).resolve().parents[1] / 'app.py'
        tree = ast.parse(source.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'record_scheduler_shadow_audit')
        calls = []
        namespace = {'get_scheduler_service': lambda: SimpleNamespace(record_shadow_audit=lambda: calls.append('record') or 7)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        self.assertEqual(namespace['record_scheduler_shadow_audit'](), 7)
        self.assertEqual(calls, ['record'])
        constructor = next(node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'StartupService')
        callback = next(item.value for item in constructor.keywords if item.arg == 'climate_scheduler_tick')
        self.assertIsInstance(callback, ast.Lambda)
        self.assertEqual(callback.body.func.attr, 'climate_scheduler_tick')

    def test_scheduler_waits_until_initial_safety_check(self):
        service = self.service([], safety_worker_enabled=True)
        scheduler_called = threading.Event()
        class Finished(BaseException):
            pass
        def run_tick():
            scheduler_called.set()
            raise Finished()
        service._scheduler_tick = run_tick
        errors = []
        def run():
            try:
                service._scheduler_loop()
            except Finished:
                pass
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertFalse(scheduler_called.wait(.02))
            service._safety_ready.set()
            self.assertTrue(scheduler_called.wait(2))
        finally:
            service._safety_ready.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])

    def test_safety_loop_cadence_does_not_wait_for_a_scheduler(self):
        calls = []
        sleeps = []
        service = self.service(calls, safety_worker_enabled=True)
        service.scheduler_poll_seconds = 5
        class Finished(BaseException):
            pass
        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise Finished()
        with patch.object(service._stop, "wait", side_effect=sleep), self.assertRaises(Finished):
            service._safety_loop()
        self.assertEqual(calls, ["stop", "fail", "stop", "fail"])
        self.assertEqual(sleeps, [5, 5])
        self.assertTrue(service._safety_ready.is_set())

    def test_combustion_and_window_guard_have_independent_error_boundaries(self):
        # Compile only this wiring function; importing app starts live bootstrap.
        source = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(source.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "climate_and_combustion_tick")
        for broken in ("combustion", "window", None):
            with self.subTest(broken=broken):
                calls = []
                def tick(name):
                    calls.append(name)
                    if name == broken:
                        raise RuntimeError("injected safety failure")
                namespace = {
                    "run_guarded_callbacks": run_guarded_callbacks,
                    "CLIMATE_BASE_TOPIC": "audit/climate",
                    "get_combustion_safety_service": lambda: SimpleNamespace(tick=lambda: tick("combustion")),
                    "get_climate_window_guard": lambda: SimpleNamespace(tick=lambda topic: tick("window")),
                }
                exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
                with contextlib.redirect_stdout(io.StringIO()):
                    namespace["climate_and_combustion_tick"]()
                self.assertEqual(calls, ["combustion", "window"])

    def service(self, calls, safety_worker_enabled):
        return StartupService(
            bootstrap=BootstrapService([lambda: calls.append("bootstrap")]),
            scheduler_poll_seconds=999,
            weather_poll_seconds=999,
            power_wall_guard_seconds=999,
            safety_worker_enabled=safety_worker_enabled,
            record_scheduler_shadow_audit=lambda: calls.append("audit"),
            irrigation_scheduler_tick=lambda: calls.append("irrigation"),
            x10_scheduler_tick=lambda: calls.append("x10_tick"),
            stop_overdue_sessions=lambda: calls.append("stop"),
            fail_sessions_without_physical_watering=lambda: calls.append("fail"),
            openweather_ready=lambda: False,
            store_openweather_snapshot=lambda: {},
            power_wall_guard_tick=lambda: calls.append("guard"),
            power_wall_scheduler_tick=lambda: calls.append("scheduler"),
            mqtt_monitor_start=lambda: calls.append("mqtt"),
            x10_monitor_start=lambda: calls.append("x10"),
            climate_monitor_start=lambda: calls.append("climate"),
        )


if __name__ == "__main__":
    unittest.main()
