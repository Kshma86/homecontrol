"""Opt-in HC-03 SQL tests. Use only the isolated hc03_recovery_test database."""
import json
import os
from pathlib import Path
import re
import threading
import unittest
from urllib.parse import urlparse

from tests import test_irrigation_service as fixtures


@unittest.skipUnless(os.environ.get('HC03_TEST_POSTGRES') == '1', 'requires dedicated isolated HC-03 PostgreSQL')
class IrrigationRecoveryPostgresTest(unittest.TestCase):
    def setUp(self):
        from database_service import DatabaseService
        url = os.environ['HC03_TEST_DATABASE_URL']
        parsed = urlparse(url)
        if parsed.hostname != '127.0.0.1' or parsed.path != '/hc03_recovery_test':
            raise AssertionError('HC-03 test URL must select its dedicated local database')
        self.db = DatabaseService(url)
        self.assertEqual(self.db.fetch_one('select current_database() as name')['name'], 'hc03_recovery_test')
        source = (Path(__file__).resolve().parents[2] / 'db/001_irrigation_admin.sql').read_text()
        self.ddl = re.search(r'create table if not exists hc\.irrigation_manual_session \(.*?\n\);', source, re.S).group()
        self.db.execute_sql('create schema if not exists hc; ' + self.ddl)
        self.db.execute_sql('truncate hc.irrigation_manual_session restart identity')
        self.calls = []
        self.confirm = False
        self.closed = False
        self.service = self.make_service()

    def make_service(self):
        service = fixtures.IrrigationServiceTest().service(fetch_all=self.db.fetch_all, fetch_one=self.db.fetch_one,
            execute_one=self.db.execute_one, execute_sql=self.db.execute_sql)
        service.session_recovery.initialized = False
        service.live_valve_state = lambda **kw: {'motor_closed': self.closed}
        def stop(reason, **kw):
            self.calls.append((reason, kw))
            return self.confirm, 'fixture confirmation', {}
        service.publish_stop_with_confirmation = stop
        return service

    def add(self, status='stop_failed', started_by='admin', age=240, metadata=None):
        payload = {'recovery': metadata} if metadata is not None else {}
        return self.db.execute_one(
            """insert into hc.irrigation_manual_session
               (status, started_by, started_at, requested_stop_at, safety_stop_at, stop_payload)
               values (%s, %s, now() - (%s * interval '1 second'), now() + interval '10 minutes',
                       now() + interval '20 minutes', %s::jsonb) returning *""",
            (status, started_by, age, json.dumps(payload)))['id']

    def row(self, ident):
        return self.db.fetch_one('select * from hc.irrigation_manual_session where id = %s', (ident,))

    def expire_backoff(self, ident):
        self.db.execute_sql("""update hc.irrigation_manual_session set stop_payload =
          jsonb_set(stop_payload, '{recovery,next_attempt_at}', to_jsonb((now() - interval '1 second')::text)) where id = %s""", (ident,))

    def test_startup_orphan_is_closed_and_not_reported_as_completed_watering(self):
        ident = self.add('starting', age=1)
        self.confirm = True
        self.service.session_recovery.tick()
        row = self.row(ident)
        self.assertEqual(row['status'], 'start_failed')
        self.assertIsNotNone(row['stopped_at'])
        self.assertTrue(row['stop_payload']['confirmation']['ok'])
        self.assertEqual(row['stop_payload']['recovery']['attempts'], 1)
        self.assertEqual(self.service.published, [])

    def test_real_json_budget_and_backoff_survive_restarts(self):
        ident = self.add()
        for attempt in range(1, 4):
            service = self.make_service()
            service.session_recovery.tick()
            self.assertEqual(self.row(ident)['stop_payload']['recovery']['attempts'], attempt)
            self.make_service().session_recovery.tick()
            self.assertEqual(len(self.calls), attempt)
            self.expire_backoff(ident)
        self.make_service().session_recovery.tick()
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.row(ident)['status'], 'stop_failed')
        self.assertIsNone(self.row(ident)['stopped_at'])

    def test_manual_stop_preserves_retry_budget_and_can_settle_failed_stop(self):
        ident = self.add(metadata={'attempts': 3, 'origin_status': 'running'})
        self.service.stop_manual_session(ident, 'manual_stop')
        self.assertEqual(self.row(ident)['stop_payload']['recovery']['attempts'], 3)
        self.make_service().session_recovery.tick()
        self.assertEqual(len(self.calls), 1, 'automatic budget reset after explicit stop')
        self.confirm = True
        self.service.stop_manual_session(ident, 'manual_stop')
        self.assertEqual(self.row(ident)['status'], 'stopped')
        self.assertEqual(self.row(ident)['stop_payload']['recovery']['attempts'], 3)
        self.assertEqual(self.row(ident)['stop_payload']['recovery']['state'], 'confirmed')

    def test_manual_stop_of_starting_row_prevents_late_running_commit(self):
        ident = self.add('starting')
        self.confirm = True
        self.service.stop_manual_session(ident, 'manual_stop')
        self.assertEqual(self.row(ident)['status'], 'stopped')
        updated = self.db.execute_one("update hc.irrigation_manual_session set status='running' where id=%s and status='starting' returning *", (ident,))
        self.assertIsNone(updated)

    def test_physical_manual_rows_are_unchanged(self):
        ident = self.add('starting', started_by='physical_manual')
        before = self.row(ident)
        self.service.session_recovery.tick()
        self.assertEqual(self.row(ident), before)
        self.assertEqual(self.calls, [])

    def test_recovery_is_independent_of_schedule_day_and_season(self):
        ident = self.add('starting', age=3 * 86400)
        self.db.execute_sql("update hc.irrigation_manual_session set started_at='2026-03-29 01:55:00+01'::timestamptz where id=%s", (ident,))
        self.service.capability_allowed = lambda capability: False
        self.confirm = True
        self.service.session_recovery.tick()
        self.assertEqual(self.row(ident)['status'], 'start_failed')
        self.assertEqual(len(self.calls), 1)

    def test_claim_transaction_rollback_sends_no_command(self):
        ident = self.add()
        def execute(sql, params):
            if "'attempts', %s::int" in sql:
                with self.db.conn() as conn:
                    conn.execute(sql, params)
                    raise RuntimeError('injected claim rollback')
            return self.db.execute_one(sql, params)
        self.service.execute_one = execute
        self.service.session_recovery.tick()
        self.assertEqual(self.calls, [])
        self.assertNotIn('recovery', self.row(ident)['stop_payload'])

    def test_lost_claim_commit_reply_spends_slot_without_replay(self):
        ident = self.add()
        def execute(sql, params):
            result = self.db.execute_one(sql, params)
            if "'attempts', %s::int" in sql:
                raise RuntimeError('claim committed but reply lost')
            return result
        self.service.execute_one = execute
        self.service.session_recovery.tick()
        self.assertEqual(self.row(ident)['stop_payload']['recovery']['attempts'], 1)
        self.assertEqual(self.calls, [])
        self.make_service().session_recovery.tick()
        self.assertEqual(self.calls, [])

    def test_failed_final_commit_preserves_uncertainty_and_budget(self):
        ident = self.add()
        self.confirm = True
        def execute(sql, params):
            if 'stopped_at = case when %s' in sql:
                raise RuntimeError('DB unavailable after physical close')
            return self.db.execute_one(sql, params)
        self.service.execute_one = execute
        self.service.session_recovery.tick()
        self.assertEqual(self.row(ident)['status'], 'stop_failed')
        self.assertEqual(self.row(ident)['stop_payload']['recovery']['attempts'], 1)
        self.closed = True
        self.make_service().session_recovery.tick()
        self.assertEqual(self.row(ident)['status'], 'auto_stopped')
        self.assertEqual(len(self.calls), 1)

    def test_two_recovery_connections_cannot_spend_the_same_claim(self):
        ident = self.add()
        first, second = self.make_service(), self.make_service()
        first.session_recovery.initialize()
        second.session_recovery.initialize()
        barrier = threading.Barrier(2, timeout=3)
        def execute(sql, params):
            if "'attempts', %s::int" in sql:
                barrier.wait()
            return self.db.execute_one(sql, params)
        first.execute_one = second.execute_one = execute
        workers = [threading.Thread(target=service.session_recovery.tick) for service in (first, second)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.row(ident)['stop_payload']['recovery']['attempts'], 1)

    def test_runtime_grace_and_due_deadline_use_database_time(self):
        self.service.session_recovery.initialize()
        recent = self.add('starting', age=1)
        stale = self.add('starting')
        self.service.session_recovery.tick()
        self.assertEqual(self.row(recent)['status'], 'starting')
        self.assertEqual(self.row(stale)['status'], 'stop_failed')
        self.db.execute_sql('update hc.irrigation_manual_session set requested_stop_at=now() where id=%s', (recent,))
        self.service.session_recovery.tick()
        self.assertEqual(self.row(recent)['status'], 'stop_failed')

    def test_stop_failed_blocks_new_manual_and_v2_starts(self):
        self.add()
        result, status = self.service.start_manual({'duration_minutes': 1})
        self.assertEqual(status, 409)
        self.service.start_v2_scheduled_session(7)
        self.assertEqual(self.service.published, [])
        self.assertEqual(self.db.fetch_one('select count(*) as n from hc.irrigation_manual_session')['n'], 1)


if __name__ == '__main__':
    unittest.main()
