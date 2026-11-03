import copy
from datetime import datetime, timedelta, timezone
import json
import threading
import unittest
from unittest.mock import patch

from tests import test_irrigation_service as fixtures


class ProcessCrash(BaseException):
    pass


class RecoveryStore:
    """Small transactional fixture; real PostgreSQL tests verify the actual SQL."""
    def __init__(self):
        self.now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
        self.monotonic = 1000.0
        self.rows = {}
        self.lock = threading.RLock()
        self.fault = None

    def add(self, status='stop_failed', started_by='admin', age=240, metadata=None):
        ident = len(self.rows) + 1
        self.rows[ident] = dict(id=ident, status=status, started_by=started_by,
            started_at=self.now - timedelta(seconds=age), created_at=self.now - timedelta(seconds=age),
            requested_stop_at=self.now + timedelta(minutes=10), safety_stop_at=self.now + timedelta(minutes=20),
            stopped_at=None, start_payload={}, stop_payload={'recovery': metadata} if metadata is not None else None, error='uncertain')
        return ident

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.monotonic += seconds

    def fetch_all(self, sql, params=()):
        with self.lock:
            if 'update hc.irrigation_manual_session' in sql:
                if self.fault == 'initialize':
                    raise RuntimeError('injected DB initialization failure')
                startup, grace = params
                changed = []
                for row in self.rows.values():
                    if row['started_by'] == 'physical_manual' or row['status'] != 'starting':
                        continue
                    if not (startup or (self.now - row['started_at']).total_seconds() >= grace or min(row['requested_stop_at'], row['safety_stop_at']) <= self.now):
                        continue
                    row['status'] = 'stop_failed'
                    row['stopped_at'] = None
                    metadata = {'origin_status': 'starting', 'state': 'pending', **(row.get('stop_payload') or {}).get('recovery', {})}
                    row['stop_payload'] = {**(row.get('stop_payload') or {}), 'recovery': metadata}
                    changed.append({'id': row['id']})
                return changed
            statuses = ('starting', 'stop_failed') if "status in ('starting', 'stop_failed')" in sql else ('stop_failed',)
            return [dict(copy.deepcopy(row), recovery_checked_at=self.now,
                         recovery_age_sec=(self.now - row['started_at']).total_seconds())
                    for row in self.rows.values() if row['status'] in statuses and row['started_by'] != 'physical_manual']

    def fetch_one(self, sql, params=()):
        return next((copy.deepcopy(row) for row in self.rows.values() if row['status'] in ('starting', 'running', 'stop_failed')), None)

    def execute_one(self, sql, params=()):
        with self.lock:
            if "'attempts', %s::int" in sql:
                attempts, seconds, ident, expected = params
                row = self.rows[ident]
                metadata = (row.get('stop_payload') or {}).get('recovery', {})
                if row['status'] != 'stop_failed' or metadata != json.loads(expected):
                    return None
                if metadata.get('next_attempt_at') and datetime.fromisoformat(metadata['next_attempt_at']) > self.now:
                    return None
                if self.fault == 'before_claim':
                    raise RuntimeError('injected failure before claim commit')
                row['stop_payload'] = {**(row.get('stop_payload') or {}), 'recovery': {
                    **metadata, 'attempts': attempts, 'state': 'attempting',
                    'last_attempt_at': self.now.isoformat(), 'next_attempt_at': (self.now + timedelta(seconds=seconds)).isoformat()}}
                if self.fault == 'after_claim':
                    raise ProcessCrash('claim committed, process died before publish')
                return copy.deepcopy(row)
            if 'stopped_at = case when %s' in sql:
                status, ok, payload, error, ident, expected = params
                row = self.rows[ident]
                if row['status'] != 'stop_failed' or (row.get('stop_payload') or {}).get('recovery', {}) != json.loads(expected):
                    return None
                if self.fault == 'before_finish':
                    raise RuntimeError('injected failure after publish before DB commit')
                row.update(status=status, stopped_at=self.now if ok else None,
                    stop_payload={**(row.get('stop_payload') or {}), **json.loads(payload)}, error=error)
                if self.fault == 'after_finish':
                    raise RuntimeError('finish committed but reply lost')
                return copy.deepcopy(row)
            raise AssertionError('unexpected SQL in recovery fixture')


class IrrigationRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.store = RecoveryStore()
        self.calls = []
        self.confirm = False
        self.closed = False
        self.addCleanup(patch.stopall)
        patch('time.monotonic', side_effect=lambda: self.store.monotonic).start()
        self.service = self.make_service()

    def make_service(self, **kwargs):
        service = fixtures.IrrigationServiceTest().service(
            fetch_all=self.store.fetch_all, fetch_one=self.store.fetch_one, execute_one=self.store.execute_one, **kwargs)
        service.session_recovery.initialized = False
        service.live_valve_state = lambda **kw: {'motor_closed': self.closed}
        def stop(reason, **options):
            self.calls.append((reason, options))
            return self.confirm, 'fixture confirmation', {}
        service.publish_stop_with_confirmation = stop
        return service

    def test_restart_reconciles_even_a_young_start_without_reopening(self):
        ident = self.store.add('starting', age=1)
        self.confirm = True
        self.service.session_recovery.tick()
        self.assertEqual(self.store.rows[ident]['status'], 'start_failed')
        self.assertEqual(self.store.rows[ident]['stop_payload']['recovery']['attempts'], 1)
        self.assertEqual(self.calls, [('session_recovery', {'attempt_limit': 1})])
        self.assertEqual(self.service.published, [])

    def test_recent_live_start_is_not_reconciled_but_stale_or_due_start_is(self):
        self.service.session_recovery.initialize()
        recent = self.store.add('starting', age=1)
        stale = self.store.add('starting', age=180)
        due = self.store.add('starting', age=1)
        self.store.rows[due]['requested_stop_at'] = self.store.now
        self.service.session_recovery.tick()
        self.assertEqual(self.store.rows[recent]['status'], 'starting')
        self.assertEqual(self.store.rows[stale]['status'], 'stop_failed')
        self.assertEqual(self.store.rows[due]['status'], 'stop_failed')
        self.assertEqual(len(self.calls), 1, 'more than one physical recovery in one pass')

    def test_retry_budget_and_backoff_survive_service_restarts(self):
        ident = self.store.add()
        for attempt in range(1, 4):
            self.service = self.make_service()
            self.service.session_recovery.tick()
            self.assertEqual(self.store.rows[ident]['stop_payload']['recovery']['attempts'], attempt)
            self.service = self.make_service()
            self.service.session_recovery.tick()
            self.assertEqual(len(self.calls), attempt)
            self.store.advance(61)
        self.store.advance(1000)
        self.make_service().session_recovery.tick()
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.store.rows[ident]['status'], 'stop_failed')
        self.assertTrue(self.service.session_recovery.payload()['unresolved'][0]['requires_attention'])

    def test_fresh_closed_can_settle_exhausted_budget_without_another_command(self):
        ident = self.store.add(metadata={'attempts': 3})
        self.service.session_recovery.tick()
        self.closed = True
        self.store.advance(2)
        self.service.session_recovery.tick()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.rows[ident]['status'], 'auto_stopped')
        self.assertEqual(self.store.rows[ident]['stop_payload']['recovery']['attempts'], 3)

    def test_retained_or_offline_closed_does_not_settle_uncertainty(self):
        ident = self.store.add(metadata={'attempts': 3})
        original = self.service.__class__.live_valve_state.__get__(self.service)
        self.service.live_valve_state = original
        def snapshot():
            return {'mqtt_connected': False, 'connection_generation': 1, 'topics': {
                'esp_nano_status': {'retain': True, 'timestamp': self.store.now.timestamp(),
                    'received_monotonic': self.store.monotonic, 'connection_generation': 1,
                    'json': {'online': True, 'valve': 'CLOSED', 'last_status_sec_ago': 0}}}}
        self.service.mqtt_snapshot = snapshot
        self.service.session_recovery.tick()
        self.store.advance(5)
        self.service.session_recovery.tick()
        self.assertEqual(self.store.rows[ident]['status'], 'stop_failed')
        self.assertEqual(self.calls, [])

    def test_physical_manual_records_are_never_recovered(self):
        ids = [self.store.add(status, started_by='physical_manual') for status in ('starting', 'stop_failed', 'running')]
        before = copy.deepcopy(self.store.rows)
        self.service.session_recovery.tick()
        self.assertEqual(self.store.rows, before)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.service.session_recovery.payload()['unresolved'], [])

    def test_initialization_failure_does_not_allow_open_and_is_retried(self):
        self.store.fault = 'initialize'
        self.store.add('starting')
        with self.assertRaises(RuntimeError):
            self.service.publish_open_with_confirmation({'value': 'open'})
        self.assertFalse(self.service.session_recovery.initialized)
        self.assertEqual(self.service.published, [])
        self.store.fault = None
        self.service.session_recovery.tick()
        self.assertTrue(self.service.session_recovery.initialized)

    def test_failure_before_claim_spends_no_attempt_and_sends_no_command(self):
        ident = self.store.add()
        self.store.fault = 'before_claim'
        self.service.session_recovery.tick()
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.store.rows[ident]['stop_payload'])
        self.store.fault = None
        self.service.session_recovery.tick()
        self.assertEqual(len(self.calls), 1)

    def test_crash_after_claim_before_publish_consumes_a_persistent_slot(self):
        ident = self.store.add()
        self.store.fault = 'after_claim'
        with self.assertRaises(ProcessCrash):
            self.service.session_recovery.tick()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.rows[ident]['stop_payload']['recovery']['attempts'], 1)
        self.store.fault = None
        restarted = self.make_service()
        restarted.session_recovery.tick()
        self.assertEqual(self.calls, [])
        self.store.advance(61)
        restarted.session_recovery.tick()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.store.rows[ident]['stop_payload']['recovery']['attempts'], 2)

    def test_confirmed_close_with_failed_commit_settles_later_without_replay(self):
        ident = self.store.add()
        self.confirm = True
        self.store.fault = 'before_finish'
        self.service.session_recovery.tick()
        self.assertEqual(self.store.rows[ident]['status'], 'stop_failed')
        self.assertEqual(len(self.calls), 1)
        self.store.fault = None
        self.closed = True
        self.service.session_recovery.tick()
        self.assertEqual(self.store.rows[ident]['status'], 'auto_stopped')
        self.assertEqual(len(self.calls), 1)

    def test_lost_commit_reply_does_not_make_a_terminal_session_retry(self):
        ident = self.store.add()
        self.confirm = True
        self.store.fault = 'after_finish'
        self.service.session_recovery.tick()
        self.assertEqual(self.store.rows[ident]['status'], 'auto_stopped')
        self.store.fault = None
        self.make_service().session_recovery.tick()
        self.assertEqual(len(self.calls), 1)

    def test_crash_after_command_send_does_not_reset_budget_or_replay_open(self):
        ident = self.store.add('starting')
        def publish_then_die(*args, **kwargs):
            self.calls.append('close delivered, result unknown')
            raise ProcessCrash()
        self.service.publish_stop_with_confirmation = publish_then_die
        with self.assertRaises(ProcessCrash):
            self.service.session_recovery.tick()
        self.assertEqual(self.store.rows[ident]['stop_payload']['recovery']['attempts'], 1)
        restarted = self.make_service()
        restarted.session_recovery.tick()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(restarted.published, [])

    def test_grace_covers_configured_open_confirmation_window(self):
        service = self.make_service(start_recovery_grace_seconds=1, open_confirm_attempts=3,
                                    open_ready_delay_seconds=30, open_reaction_delay_seconds=100)
        self.assertGreaterEqual(service.session_recovery.start_grace_seconds, 330)

    def test_late_open_commit_does_not_resurrect_reconciled_session(self):
        service = fixtures.IrrigationServiceTest().service()
        writes = []
        service.fetch_one = lambda *args: None
        service.publish_open_with_confirmation = lambda *a, **k: (True, 'fresh open', {})
        def execute(sql, params):
            writes.append(sql)
            return {'id': 7} if 'insert into' in sql else None
        service.execute_one = execute
        result, status = service.start_manual({'duration_minutes': 1})
        self.assertEqual(status, 409)
        self.assertFalse(result['ok'])
        self.assertEqual(len(writes), 2)

    def test_failed_start_does_not_overwrite_recovered_terminal_status(self):
        service = fixtures.IrrigationServiceTest().service()
        writes = []
        service.execute_one = lambda sql, params: writes.append(sql) or {'id': 7}
        service.start_manual({'duration_minutes': 1})
        self.assertIn("where id = %s and status = 'starting'", writes[-1])

    def test_publisher_exception_is_persisted_and_later_retry_is_bounded(self):
        ident = self.store.add()
        self.service.publish_stop_with_confirmation = lambda *a, **k: (_ for _ in ()).throw(TimeoutError('broker unavailable'))
        self.service.session_recovery.tick()
        self.assertEqual(self.store.rows[ident]['status'], 'stop_failed')
        self.assertIn('broker unavailable', self.store.rows[ident]['error'])
        self.assertEqual(self.store.rows[ident]['stop_payload']['recovery']['attempts'], 1)

    def test_uncertainty_blocks_manual_and_v2_admission(self):
        self.store.add()
        result, status = self.service.start_manual({'duration_minutes': 1})
        self.assertEqual(status, 409)
        self.service.start_v2_scheduled_session(7)
        self.assertEqual(self.service.published, [])

    def test_closed_recovery_can_release_interlock_on_next_scan(self):
        self.store.add()
        self.confirm = True
        self.service.session_recovery.tick()
        self.service.session_recovery.tick()
        self.assertFalse(self.service.session_recovery.blocked)

    def test_invalid_budget_metadata_requires_attention_without_retry(self):
        self.store.add(metadata={'attempts': 'broken'})
        self.service.session_recovery.tick()
        self.assertEqual(self.calls, [])
        self.assertTrue(self.service.session_recovery.payload()['unresolved'][0]['requires_attention'])

    def test_configurable_retry_budget_and_interval(self):
        ident = self.store.add()
        service = self.make_service(recovery_retry_seconds=10, recovery_max_attempts=1)
        service.session_recovery.tick()
        self.store.advance(100)
        service.session_recovery.tick()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.store.rows[ident]['stop_payload']['recovery']['attempts'], 1)

    def test_concurrent_recovery_tick_does_not_duplicate_a_claim(self):
        self.store.add()
        entered, release = threading.Event(), threading.Event()
        def stop(*args, **kwargs):
            self.calls.append('close')
            entered.set()
            if not release.wait(2):
                raise AssertionError('fixture not released')
            return False, 'fixture', {}
        self.service.publish_stop_with_confirmation = stop
        worker = threading.Thread(target=self.service.session_recovery.tick)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.service.session_recovery.tick()
            self.assertEqual(len(self.calls), 1)
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())


if __name__ == '__main__':
    unittest.main()
