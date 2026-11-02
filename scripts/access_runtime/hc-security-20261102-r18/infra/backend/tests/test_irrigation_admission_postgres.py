"""Opt-in: run only against a disposable hc04_admission_test PostgreSQL."""
import json
import os
from pathlib import Path
import re
import threading
import time
import unittest
from urllib.parse import urlparse

from irrigation_admission import IrrigationSessionAdmission
from tests import test_irrigation_service as fixtures


class ProcessCrash(BaseException):
    pass


@unittest.skipUnless(os.environ.get('HC04_TEST_POSTGRES') == '1', 'requires isolated HC-04 PostgreSQL')
class IrrigationAdmissionPostgresTest(unittest.TestCase):
    def setUp(self):
        from database_service import DatabaseService
        from psycopg.rows import dict_row
        url = os.environ['HC04_TEST_DATABASE_URL']
        parsed = urlparse(url)
        if parsed.hostname != '127.0.0.1' or parsed.path != '/hc04_admission_test':
            raise AssertionError('HC-04 test requires its dedicated local database')
        self.db = DatabaseService(url)
        self.connect = lambda: self.db.conn(dict_row)
        self.admission = IrrigationSessionAdmission(self.connect)
        source = (Path(__file__).resolve().parents[2] / 'db/001_irrigation_admin.sql').read_text()
        ddl = '\n'.join(re.search(r'create table if not exists hc\.' + table + r' \(.*?\n\);', source, re.S).group()
                        for table in ('irrigation_manual_session', 'irrigation_schedule'))
        self.db.execute_sql('create schema if not exists hc; ' + ddl)
        self.db.execute_sql('truncate hc.irrigation_manual_session, hc.irrigation_schedule restart identity')
        self.calls = []
        self.service = self.make_service()

    def make_service(self):
        service = fixtures.IrrigationServiceTest().service(
            fetch_all=self.db.fetch_all, fetch_one=self.db.fetch_one,
            execute_one=self.db.execute_one, execute_sql=self.db.execute_sql,
            reserve_session=self.admission.reserve)
        service.evaluate_pilot = lambda **kw: {'mode': 'navigator', 'final_duration': 5, 'reason': 'fixture'}
        service.v2_stop_policy = lambda *a: {}
        service.mark_v2_execution = lambda *a, **kw: None
        service.log_pilot_decision = lambda *a, **kw: None
        def opened(payload, **kw):
            self.calls.append(payload['value'])
            return True, 'fake fresh OPEN confirmation', {}
        service.publish_open_with_confirmation = opened
        return service

    def reserve(self, **options):
        values = dict(minutes=5, safety_minutes=180, started_by='admin', start_payload={'value': 'open'})
        values.update(options)
        return self.admission.reserve(**values)

    def schedule(self):
        return self.db.execute_one("""insert into hc.irrigation_schedule
            (day_of_week, label, start_time, stop_time, is_active)
            values (extract(isodow from now())::int - 1, 'test', '00:00', '23:59:59', true)
            returning id""")['id']

    def rows(self):
        return self.db.fetch_all('select * from hc.irrigation_manual_session order by id')

    def parallel(self, *callbacks):
        results, errors = [], []
        def run(callback):
            try:
                results.append(callback())
            except BaseException as exc:
                errors.append(exc)
        threads = [threading.Thread(target=run, args=(callback,)) for callback in callbacks]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive(), 'DB worker did not terminate')
        self.assertEqual(errors, [])
        return results

    def barrier_reservations(self, *services):
        barrier = threading.Barrier(len(services), timeout=5)
        def reserve(**kw):
            barrier.wait()
            return self.admission.reserve(**kw)
        for service in services:
            service.reserve_session = reserve

    def test_same_service_two_manual_requests_have_one_winner(self):
        self.barrier_reservations(self.service, self.service)
        results = self.parallel(*(lambda: self.service.start_manual({}) for _ in range(2)))
        self.assertEqual(sorted(result[1] for result in results), [200, 409])
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.calls, ['open'])

    def test_independent_service_instances_share_database_admission(self):
        second = self.make_service()
        self.barrier_reservations(self.service, second)
        results = self.parallel(lambda: self.service.start_manual({}), lambda: second.start_manual({}))
        self.assertEqual(sorted(result[1] for result in results), [200, 409])
        self.assertEqual(len(self.rows()), 1)

    def test_manual_and_scheduler_only_advance_winning_schedule(self):
        schedule = self.schedule()
        second = self.make_service()
        self.barrier_reservations(self.service, second)
        self.parallel(lambda: self.service.start_manual({}), lambda: second.start_v2_scheduled_session(schedule))
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.calls, ['open'])
        day = self.db.fetch_one('select last_started_on from hc.irrigation_schedule where id=%s', (schedule,))['last_started_on']
        self.assertEqual(day is not None, rows[0]['started_by'] == 'v2_scheduler')

    def test_same_or_different_schedules_cannot_both_reserve(self):
        for same in (True, False):
            with self.subTest(same=same):
                self.db.execute_sql('truncate hc.irrigation_manual_session, hc.irrigation_schedule restart identity')
                self.calls.clear()
                first = self.schedule()
                second = first if same else self.schedule()
                services = [self.make_service(), self.make_service()]
                self.barrier_reservations(*services)
                self.parallel(lambda: services[0].start_v2_scheduled_session(first), lambda: services[1].start_v2_scheduled_session(second))
                self.assertEqual(len(self.rows()), 1)
                self.assertEqual(self.calls, ['open'])
                self.assertEqual(self.db.fetch_one('select count(*) as n from hc.irrigation_schedule where last_started_on=current_date')['n'], 1)

    def test_legacy_and_v2_use_the_same_reservation(self):
        schedule = self.schedule()
        second = self.make_service()
        self.barrier_reservations(self.service, second)
        self.parallel(lambda: self.service.start_scheduled_session(schedule), lambda: second.start_v2_scheduled_session(schedule))
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.calls, ['open'])

    def test_late_prepared_schedule_cannot_replay_after_first_session_closed(self):
        schedule = self.schedule()
        self.assertIsNotNone(self.reserve(schedule_id=schedule)['session'])
        self.db.execute_sql("update hc.irrigation_manual_session set status='stopped', stopped_at=now()")
        result = self.reserve(schedule_id=schedule)
        self.assertIsNone(result['session'])
        self.assertEqual(result['blocked_by'], 'schedule_not_due')
        self.assertEqual(len(self.rows()), 1)

    def test_schedule_eligibility_is_rechecked_after_preparation(self):
        schedule = self.schedule()
        def decision(**kw):
            self.db.execute_sql('update hc.irrigation_schedule set is_active=false where id=%s', (schedule,))
            return {'mode': 'navigator', 'final_duration': 5, 'reason': 'fixture'}
        self.service.evaluate_pilot = decision
        self.service.start_v2_scheduled_session(schedule)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.db.fetch_one('select last_started_on from hc.irrigation_schedule')['last_started_on'])

    def test_committed_starting_or_failed_stop_blocks_reservation(self):
        row = self.reserve()['session']
        for status in ('starting', 'running', 'stop_failed'):
            with self.subTest(status=status):
                self.db.execute_sql('update hc.irrigation_manual_session set status=%s where id=%s', (status, row['id']))
                result = self.reserve()
                self.assertIsNone(result['session'])
                self.assertEqual(result['blocking_session']['id'], row['id'])
        self.assertEqual(len(self.rows()), 1)

    def test_physical_manual_observation_blocks_without_reclassification(self):
        self.reserve()
        self.db.execute_sql("update hc.irrigation_manual_session set started_by='physical_manual', status='running'")
        before = self.rows()
        self.assertEqual(self.service.start_manual({})[1], 409)
        self.assertIsNone(self.reserve()['session'])
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.calls, [])

    def test_physical_observations_can_coexist_without_becoming_hc_owners(self):
        self.reserve()
        self.db.execute_sql("""insert into hc.irrigation_manual_session
            (requested_stop_at, safety_stop_at, started_by)
            values (now(), now(), 'physical_manual')""")
        self.assertEqual(len(self.rows()), 2)
        self.assertIsNone(self.reserve()['session'])

    def test_pending_physical_writer_is_seen_after_admission_lock_wait(self):
        entered = threading.Event()
        results, errors = [], []
        def reserve(**kw):
            entered.set()
            return self.admission.reserve(**kw)
        self.service.reserve_session = reserve
        def start():
            try:
                results.append(self.service.start_manual({}))
            except BaseException as exc:
                errors.append(exc)
        with self.connect() as writer:
            writer.execute("""insert into hc.irrigation_manual_session
                (requested_stop_at, safety_stop_at, started_by)
                values (now(), now(), 'physical_manual')""")
            worker = threading.Thread(target=start)
            worker.start()
            self.assertTrue(entered.wait(3))
            deadline = time.monotonic() + 1.5
            while not self.db.fetch_one("""select exists (
                select 1 from pg_stat_activity where datname=current_database()
                  and wait_event_type='Lock'
                  and query='lock table hc.irrigation_manual_session in share row exclusive mode'
                ) as waiting""")['waiting']:
                self.assertLess(time.monotonic(), deadline, 'admission did not wait for physical writer')
                time.sleep(.01)
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results[0][1], 409)
        self.assertEqual(results[0][0]['blocked_by'], 'active_session')
        self.assertEqual(self.calls, [])
        self.assertEqual([row['started_by'] for row in self.rows()], ['physical_manual'])

    def test_existing_duplicate_rows_are_preserved_and_block_new_start(self):
        self.reserve()
        self.db.execute_sql("""insert into hc.irrigation_manual_session
            (requested_stop_at, safety_stop_at, started_by) values (now(), now(), 'old-scheduler')""")
        before = self.rows()
        self.assertIsNone(self.reserve()['session'])
        self.assertEqual(self.rows(), before)

    def wrapped_connection(self, *, fail_before_commit=False, lose_commit_reply=False):
        connect = self.connect
        class Connection:
            def __enter__(self):
                self.conn = connect()
                self.conn.__enter__()
                return self.conn
            def __exit__(self, kind, value, traceback):
                if fail_before_commit and kind is None:
                    self.conn.__exit__(RuntimeError, RuntimeError('injected rollback'), None)
                    raise RuntimeError('injected rollback')
                result = self.conn.__exit__(kind, value, traceback)
                if lose_commit_reply and kind is None:
                    raise RuntimeError('commit happened but response was lost')
                return result
        return Connection

    def test_failed_commit_rolls_back_session_and_schedule_day_without_open(self):
        schedule = self.schedule()
        self.service.reserve_session = IrrigationSessionAdmission(self.wrapped_connection(fail_before_commit=True)).reserve
        with self.assertRaisesRegex(RuntimeError, 'injected rollback'):
            self.service.start_v2_scheduled_session(schedule)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.rows(), [])
        self.assertIsNone(self.db.fetch_one('select last_started_on from hc.irrigation_schedule')['last_started_on'])

    def test_insert_error_rolls_back_the_already_claimed_schedule_day(self):
        from psycopg.errors import NotNullViolation
        schedule = self.schedule()
        with self.assertRaises(NotNullViolation):
            self.reserve(minutes=None, schedule_id=schedule)
        self.assertEqual(self.rows(), [])
        self.assertIsNone(self.db.fetch_one('select last_started_on from hc.irrigation_schedule')['last_started_on'])
        self.assertIsNotNone(self.reserve(schedule_id=schedule)['session'])

    def test_lost_commit_reply_never_replays_open_and_recovery_can_close(self):
        schedule = self.schedule()
        self.service.reserve_session = IrrigationSessionAdmission(self.wrapped_connection(lose_commit_reply=True)).reserve
        with self.assertRaisesRegex(RuntimeError, 'response was lost'):
            self.service.start_v2_scheduled_session(schedule)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.rows()[0]['status'], 'starting')
        restarted = self.make_service()
        restarted.session_recovery.initialized = False
        restarted.live_valve_state = lambda **kw: {'motor_closed': False}
        restarted.publish_stop_with_confirmation = lambda *a, **kw: (True, 'fresh CLOSED', {})
        restarted.session_recovery.tick()
        self.assertEqual(self.rows()[0]['status'], 'start_failed')
        restarted.start_v2_scheduled_session(schedule)
        self.assertEqual(self.calls, [])

    def test_crash_after_reservation_does_not_authorize_second_start(self):
        def crash(**kw):
            result = self.admission.reserve(**kw)
            raise ProcessCrash('committed reservation before MQTT')
        self.service.reserve_session = crash
        with self.assertRaises(ProcessCrash):
            self.service.start_manual({})
        self.assertEqual(self.make_service().start_manual({})[1], 409)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.rows()[0]['status'], 'starting')

    def test_start_final_commit_failure_leaves_recoverable_reservation(self):
        def execute(sql, params=()):
            if "set status = 'running'" in sql:
                raise RuntimeError('DB unavailable after OPEN')
            return self.db.execute_one(sql, params)
        self.service.execute_one = execute
        with self.assertRaisesRegex(RuntimeError, 'after OPEN'):
            self.service.start_manual({})
        self.assertEqual(self.calls, ['open'])
        self.assertEqual(self.rows()[0]['status'], 'starting')
        self.assertEqual(self.make_service().start_manual({})[1], 409)

    def test_no_admission_transaction_or_table_lock_survives_into_mqtt_wait(self):
        def opened(payload, **kw):
            self.assertEqual(self.rows()[0]['status'], 'starting', 'reservation not committed')
            with self.connect() as conn:
                conn.execute('lock table hc.irrigation_manual_session in share row exclusive mode nowait')
                conn.execute("update hc.irrigation_manual_session set error='test concurrent stop writer'")
            return True, 'fresh OPEN', {}
        self.service.publish_open_with_confirmation = opened
        self.assertEqual(self.service.start_manual({})[1], 200)

    def test_stop_between_committed_reservation_and_open_cancels_old_request(self):
        ready, release = threading.Event(), threading.Event()
        result, errors = [], []
        def reserve(**kw):
            reservation = self.admission.reserve(**kw)
            ready.set()
            if not release.wait(5):
                raise AssertionError('reservation not released')
            return reservation
        self.service.reserve_session = reserve
        self.service.publish_open_with_confirmation = self.service.__class__.publish_open_with_confirmation.__get__(self.service)
        self.service.live_valve_state = lambda **kw: {'motor_closed': True}
        def run():
            try:
                result.append(self.service.start_manual({}))
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=run)
        worker.start()
        try:
            self.assertTrue(ready.wait(5))
            self.assertEqual(self.service.stop_manual({})[1], 200)
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result[0][1], 502)
        self.assertEqual(result[0][0]['confirmation']['blocked_by'], 'stop_request')
        self.assertEqual(self.rows()[0]['status'], 'stopped')
        self.assertEqual([payload['value'] for _, payload in self.service.published], ['close'])

    def test_failed_open_retains_slot_until_recovery_reconciles(self):
        self.service.publish_open_with_confirmation = lambda *a, **kw: (False, 'timeout', {})
        self.assertEqual(self.service.start_manual({})[1], 502)
        self.assertEqual(self.make_service().start_manual({})[1], 409)
        self.service.live_valve_state = lambda **kw: {'motor_closed': True}
        self.service.session_recovery.tick()
        self.service.session_recovery.tick()
        self.assertEqual(self.rows()[0]['status'], 'start_failed')
        self.assertIsNotNone(self.reserve()['session'])

    def test_lock_timeout_fails_closed_and_next_attempt_can_reserve(self):
        from psycopg.errors import LockNotAvailable
        with self.connect() as blocker:
            blocker.execute('lock table hc.irrigation_manual_session in row exclusive mode')
            with self.assertRaises(LockNotAvailable):
                self.service.start_manual({})
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.service.start_manual({})[1], 200)

    def test_physical_origin_is_rejected_by_repository(self):
        with self.assertRaises(ValueError):
            self.reserve(started_by='physical_manual')
        self.assertEqual(self.rows(), [])


if __name__ == '__main__':
    unittest.main()
