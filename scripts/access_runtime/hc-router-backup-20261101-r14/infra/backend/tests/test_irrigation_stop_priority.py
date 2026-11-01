import contextlib
import threading
import time
import unittest
from unittest.mock import patch

from tests import test_irrigation_service as irrigation_fixtures
from tests import test_startup_service as startup_fixtures


class IrrigationStopPriorityTest(unittest.TestCase):
    stop_check_latencies_ms = []

    def fixture(self, **overrides):
        service = irrigation_fixtures.IrrigationServiceTest().service(**overrides)
        published = []
        closed = threading.Event()

        def publish(topic, payload):
            published.append(payload.get("value"))
            if payload.get("value") == "close":
                closed.set()
            return True, "fixture publish"

        def state(**kwargs):
            return {"motor_closed": closed.is_set(), "motor_closing": False,
                    "motor_fully_open": False, "motor_open": False,
                    "valve": "CLOSED" if closed.is_set() else "OPENING",
                    "manual_closed": False, "valve_current_a": 0}

        service.publish_mqtt = publish
        service.live_valve_state = state
        return service, published, closed

    def worker(self, name, callback):
        results, errors = [], []
        def run():
            try:
                results.append(callback())
            except BaseException as exc:
                errors.append(exc)
        thread = threading.Thread(name=name, target=run, daemon=True)
        thread.start()
        return thread, results, errors

    def test_overdue_stop_runs_while_scheduler_open_waits_and_cancels_retry(self):
        service, published, closed = self.fixture(open_confirm_attempts=3, open_reaction_delay_seconds=5, open_ready_delay_seconds=30)
        waiting, release = threading.Event(), threading.Event()
        updates = []
        service.fetch_all = lambda *args: [{"id": 7}]
        service.execute_one = lambda *args: updates.append(args) or {"id": 7}
        startup = startup_fixtures.StartupServiceTest().service([], safety_worker_enabled=True)
        startup.stop_overdue_sessions = service.stop_overdue_sessions
        scheduler_result = []
        def run_start():
            scheduler_result.append(service.publish_open_with_confirmation({"value": "open", "source": "scheduler"}))
        startup.irrigation_scheduler_tick = run_start

        def wait_for_open(seconds):
            self.assertEqual(seconds, 5)
            waiting.set()
            if not release.wait(2):
                raise AssertionError("fixture OPEN was not released")

        with patch("irrigation_service.time.sleep", side_effect=wait_for_open):
            thread, _, errors = self.worker("hc02-scheduler", startup._scheduler_tick)
            try:
                self.assertTrue(waiting.wait(2))
                started = time.perf_counter()
                startup._safety_tick()
                self.stop_check_latencies_ms.append((time.perf_counter() - started) * 1000)
                self.assertTrue(closed.is_set())
                self.assertTrue(thread.is_alive(), "scheduler was not still blocked in OPEN wait")
            finally:
                release.set()
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(published, ["open", "close"])
        self.assertFalse(scheduler_result[0][0])
        self.assertEqual(scheduler_result[0][2]["blocked_by"], "stop_request")
        self.assertEqual(updates[0][1][0], "auto_stopped")

    def test_simultaneous_manual_and_automatic_stop_do_not_allow_old_open_replay(self):
        service, published, closed = self.fixture(open_confirm_attempts=3, open_reaction_delay_seconds=5, open_ready_delay_seconds=30)
        waiting, release = threading.Event(), threading.Event()
        service.fetch_all = lambda *args: [{"id": 7}]
        service.execute_one = lambda *args: {"id": 7}
        def wait_for_open(seconds):
            waiting.set()
            if not release.wait(2):
                raise AssertionError("fixture OPEN was not released")
        barrier = threading.Barrier(3, timeout=2)
        def automatic():
            barrier.wait()
            return service.stop_overdue_sessions()
        def manual():
            barrier.wait()
            return service.stop_manual({"session_id": 7})
        with patch("irrigation_service.time.sleep", side_effect=wait_for_open):
            opening, results, open_errors = self.worker("hc02-opening", lambda: service.publish_open_with_confirmation({"value": "open"}))
            stops = []
            try:
                self.assertTrue(waiting.wait(2))
                stops = [self.worker("hc02-auto-stop", automatic), self.worker("hc02-manual-stop", manual)]
                barrier.wait()
                for worker, _, errors in stops:
                    worker.join(2)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(errors, [])
                self.assertTrue(closed.is_set())
            finally:
                release.set()
                opening.join(2)
                for worker, _, _ in stops:
                    worker.join(2)
        self.assertEqual(open_errors, [])
        self.assertFalse(results[0][0])
        self.assertEqual(published, ["open", "close", "close"])

    def test_stop_intent_is_registered_before_waiting_for_inflight_open_publish(self):
        service, published, closed = self.fixture(open_confirm_attempts=3)
        entered, release, stop_requested = threading.Event(), threading.Event(), threading.Event()
        normal_publish = service.publish_mqtt
        def blocked_publish(topic, payload):
            if payload.get("value") == "open":
                published.append("open")
                entered.set()
                if not release.wait(2):
                    raise AssertionError("fixture publish was not released")
                return False, "injected transport timeout"
            return normal_publish(topic, payload)
        service.publish_mqtt = blocked_publish
        original_guard = service._valve_stop_request
        @contextlib.contextmanager
        def notifying_guard():
            with original_guard():
                stop_requested.set()
                yield
        service._valve_stop_request = notifying_guard
        opening, results, errors = self.worker("hc02-publish", lambda: service.publish_open_with_confirmation({"value": "open"}))
        stop = None
        try:
            self.assertTrue(entered.wait(2))
            stop = self.worker("hc02-stop", lambda: service.publish_stop_with_confirmation("manual_stop"))
            self.assertTrue(stop_requested.wait(2))
            self.assertFalse(closed.is_set(), "close passed an unfinished OPEN publication")
        finally:
            release.set()
            opening.join(2)
            if stop:
                stop[0].join(2)
        self.assertFalse(opening.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(stop[2], [])
        self.assertTrue(stop[1][0][0])
        self.assertFalse(results[0][0])
        self.assertEqual(published, ["open", "close"])

    def test_stop_pending_blocks_new_open_until_stop_confirmation_finishes(self):
        service, published, _ = self.fixture(stop_reaction_delay_seconds=5, stop_closed_delay_seconds=30)
        waiting, release = threading.Event(), threading.Event()
        def wait_for_stop(seconds):
            waiting.set()
            if not release.wait(2):
                raise AssertionError("fixture STOP was not released")
        with patch("irrigation_service.time.sleep", side_effect=wait_for_stop):
            stopping, results, errors = self.worker("hc02-stopping", lambda: service.publish_stop_with_confirmation("manual_stop"))
            try:
                self.assertTrue(waiting.wait(2))
                opened = service.publish_open_with_confirmation({"value": "open"})
                self.assertFalse(opened[0])
                self.assertEqual(opened[2]["blocked_by"], "stop_request")
                self.assertEqual(published, ["close"])
            finally:
                release.set()
                stopping.join(2)
        self.assertEqual(errors, [])
        self.assertTrue(results[0][0])

    def test_raw_manual_valve_stop_invalidates_old_open(self):
        service, published, _ = self.fixture(open_reaction_delay_seconds=5, open_ready_delay_seconds=30)
        waiting, release = threading.Event(), threading.Event()
        def wait_for_open(seconds):
            waiting.set()
            if not release.wait(2):
                raise AssertionError("fixture OPEN was not released")
        with patch("irrigation_service.time.sleep", side_effect=wait_for_open):
            thread, results, errors = self.worker("hc02-opening", lambda: service.publish_open_with_confirmation({"value": "open"}))
            try:
                self.assertTrue(waiting.wait(2))
                payload, status = service.command({"name": "valve_stop"})
                self.assertEqual(status, 200)
                self.assertTrue(payload["ok"])
            finally:
                release.set()
                thread.join(2)
        self.assertEqual(errors, [])
        self.assertFalse(results[0][0])
        self.assertEqual(published, ["open", "stop"])

    def test_stop_during_snapshot_read_prevents_late_open_success(self):
        service, published, closed = self.fixture()
        reading, release = threading.Event(), threading.Event()
        original_state = service.live_valve_state
        def state(**kwargs):
            if threading.current_thread().name == "hc02-opening":
                reading.set()
                if not release.wait(2):
                    raise AssertionError("fixture observation was not released")
                return {"motor_fully_open": True}
            return original_state(**kwargs)
        service.live_valve_state = state
        opening, results, errors = self.worker("hc02-opening", lambda: service.publish_open_with_confirmation({"value": "open"}))
        try:
            self.assertTrue(reading.wait(2))
            self.assertTrue(service.publish_stop_with_confirmation("manual_stop")[0])
        finally:
            release.set()
            opening.join(2)
        self.assertEqual(errors, [])
        self.assertFalse(results[0][0])
        self.assertEqual(published, ["open", "close"])

    def test_publish_exception_does_not_leak_stop_pending_state(self):
        service, _, _ = self.fixture()
        service.publish_mqtt = lambda *args: (_ for _ in ()).throw(TimeoutError("injected publisher failure"))
        with self.assertRaises(TimeoutError):
            service.publish_stop_with_confirmation("manual_stop")
        self.assertEqual(service._valve_stops_pending, 0)
        self.assertEqual(service._valve_stop_generation, 1)

    def test_manual_and_v2_preparation_cannot_publish_open_after_intervening_stop(self):
        for scheduled in (False, True):
            with self.subTest(scheduled=scheduled):
                service, published, _ = self.fixture()
                preparing, release = threading.Event(), threading.Event()
                updates = []
                def fetch_one(*args):
                    preparing.set()
                    if not release.wait(2):
                        raise AssertionError("fixture DB preparation was not released")
                    return {"id": 7, "duration_minutes": 1, "label": "fixture"} if scheduled else None
                service.fetch_one = fetch_one
                service.execute_one = lambda *args: updates.append(args) or {"id": 7}
                service.evaluate_pilot = lambda **kwargs: {"mode": "navigator", "final_duration": 1}
                service.v2_stop_policy = lambda *args: {}
                service.mark_v2_execution = lambda *args: None
                callback = (lambda: service.start_v2_scheduled_session(7)) if scheduled else (lambda: service.start_manual({"duration_minutes": 1}))
                thread, results, errors = self.worker("hc02-preparing", callback)
                try:
                    self.assertTrue(preparing.wait(2))
                    self.assertTrue(service.publish_stop_with_confirmation("manual_stop")[0])
                finally:
                    release.set()
                    thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(published, ["close"])
                self.assertTrue(any("status = 'stop_failed'" in args[0] for args in updates))
                if not scheduled:
                    self.assertEqual(results[0][1], 502)
                    self.assertEqual(results[0][0]["confirmation"]["blocked_by"], "stop_request")

    def test_request_registered_during_stop_stays_invalid_after_stop_finishes(self):
        service, published, _ = self.fixture()
        with service._valve_stop_request():
            generation = service._open_request_generation()
        result = service.publish_open_with_confirmation({"value": "open"}, stop_generation=generation)
        self.assertFalse(result[0])
        self.assertEqual(result[2]["blocked_by"], "stop_request")
        self.assertEqual(published, [])


if __name__ == "__main__":
    unittest.main()
