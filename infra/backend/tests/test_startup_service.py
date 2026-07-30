import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from startup_service import BootstrapService, StartupService


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
