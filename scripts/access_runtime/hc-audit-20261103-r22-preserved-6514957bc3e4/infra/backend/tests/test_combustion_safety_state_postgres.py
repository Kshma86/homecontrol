"""Opt-in HC-06 persistence checks. Disposable local database only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import urlparse

from combustion_state_store import CombustionStateStore
from tests import test_combustion_safety_service as fixtures


@unittest.skipUnless(os.environ.get('HC06_TEST_POSTGRES') == '1', 'requires dedicated HC-06 PostgreSQL')
class CombustionSafetyStatePostgresTest(unittest.TestCase):
    def setUp(self):
        from database_service import DatabaseService
        url = os.environ['HC06_TEST_DATABASE_URL']
        parsed = urlparse(url)
        if parsed.hostname != '127.0.0.1' or parsed.path != '/hc06_state_test':
            raise AssertionError('requires dedicated local hc06_state_test database')
        self.db = DatabaseService(url)
        self.db.execute_sql('create schema if not exists hc')
        self.migration = (Path(__file__).resolve().parents[2] / 'db/058_combustion_safety_runtime.sql').read_text()
        self.db.execute_sql(self.migration)
        self.db.execute_sql('truncate hc.combustion_safety_runtime; insert into hc.combustion_safety_runtime(singleton) values(true)')
        self.store = CombustionStateStore(self.db.fetch_one, self.db.execute_one)
        self.fixture = self.make_fixture()

    def make_fixture(self):
        fixture = fixtures.CombustionSafetyServiceTest()
        fixture.setUp()
        fixture.service.runtime_store = self.store
        return fixture

    def test_initial_migration_is_conservative_and_rerun_preserves_ack_and_history(self):
        self.assertTrue(self.store.load()['latched'])
        self.fixture.service.tick()
        self.fixture.service.acknowledge()
        before = self.store.load()
        self.assertFalse(before['latched'])
        self.assertIsNotNone(before['acknowledged_at'])
        self.db.execute_sql(self.migration)
        self.assertEqual(self.store.load(), before)

    def test_alarm_latch_survives_new_python_process_with_clear_inputs(self):
        self.fixture.states[3]['carbon_monoxide'] = True
        self.fixture.service.tick()
        script = '''
import json, os
from database_service import DatabaseService
from combustion_state_store import CombustionStateStore
from tests.test_combustion_safety_service import CombustionSafetyServiceTest
db=DatabaseService(os.environ['HC06_TEST_DATABASE_URL'])
f=CombustionSafetyServiceTest();f.setUp()
f.service.runtime_store=CombustionStateStore(db.fetch_one,db.execute_one)
result=f.service.tick()
print(json.dumps({'latched':result['latched'],'danger':result['danger']}))
'''
        child = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(json.loads(child.stdout), {'latched': True, 'danger': False})

    def test_acknowledgement_persists_across_service_restart(self):
        self.fixture.service.tick()
        self.fixture.service.acknowledge()
        restarted = self.make_fixture()
        self.assertFalse(restarted.service.tick()['latched'])
        self.assertIsNotNone(self.store.load()['acknowledged_at'])

    def test_two_connections_cannot_clear_using_same_old_revision(self):
        first, second = self.store.load(), self.store.load()
        self.store.save(first['revision'], dict(latched=True, co_warning_active=False, last_co=None, last_co_sample_at=None))
        with self.assertRaisesRegex(RuntimeError, 'revision changed'):
            self.store.save(second['revision'], dict(latched=False, co_warning_active=False, last_co=None, last_co_sample_at=None), acknowledge=True)
        self.assertTrue(self.store.load()['latched'])

    def test_latch_commit_precedes_actuation_and_read_requests_do_not_write(self):
        self.fixture.states[3]['carbon_monoxide'] = True
        self.fixture.service._shutdown = lambda snapshot: self.assertTrue(self.store.load()['latched'])
        self.fixture.service.tick()
        before = self.store.load()
        for _ in range(300):
            self.fixture.service.state_payload()
            self.fixture.service.evaluate()
        self.assertEqual(self.store.load(), before)

    def test_failed_ack_transaction_rolls_back_without_clearing_memory(self):
        self.fixture.service.tick()
        def execute(sql, params):
            with self.db.conn() as conn:
                conn.execute(sql, params)
                raise RuntimeError('injected transaction rollback')
        self.fixture.service.runtime_store = CombustionStateStore(self.db.fetch_one, execute)
        with self.assertRaisesRegex(RuntimeError, 'rollback'):
            self.fixture.service.acknowledge()
        self.assertTrue(self.store.load()['latched'])
        self.assertTrue(self.fixture.service.state_payload()['latched'])

    def test_lost_latch_commit_reply_does_not_lose_short_alarm(self):
        self.fixture.service.tick()
        self.fixture.service.acknowledge()
        def execute(sql, params):
            self.db.execute_one(sql, params)
            raise RuntimeError('commit succeeded; response lost')
        self.fixture.service.runtime_store = CombustionStateStore(self.db.fetch_one, execute)
        self.fixture.states[3]['carbon_monoxide'] = True
        result = self.fixture.service.tick()
        self.assertFalse(result['persistence']['restored'])
        self.assertTrue(result['latched'])
        self.assertTrue(self.make_fixture().service.tick()['latched'])

    def test_lost_ack_commit_reply_is_not_reported_as_success(self):
        self.fixture.service.tick()
        def execute(sql, params):
            self.db.execute_one(sql, params)
            raise RuntimeError('ack committed; response lost')
        self.fixture.service.runtime_store = CombustionStateStore(self.db.fetch_one, execute)
        with self.assertRaisesRegex(RuntimeError, 'response lost'):
            self.fixture.service.acknowledge()
        self.assertTrue(self.fixture.service.state_payload()['latched'])
        self.assertFalse(self.store.load()['latched'], 'the ACK transaction actually committed')
        self.assertFalse(self.fixture.service._runtime_loaded)

    def test_missing_schema_does_not_create_ddl_on_get_or_clear_latch(self):
        self.db.execute_sql('drop table hc.combustion_safety_runtime')
        result = self.fixture.service.tick()
        self.assertTrue(result['latched'])
        self.assertFalse(result['persistence']['restored'])
        self.fixture.service.state_payload()
        self.assertIsNone(self.db.fetch_one("select to_regclass('hc.combustion_safety_runtime') as name")['name'])
        self.db.execute_sql(self.migration)
        self.assertTrue(self.fixture.service.tick()['persistence']['restored'])

    def test_runtime_history_round_trips_without_modifying_config(self):
        self.db.execute_sql('create table if not exists hc.hc06_business_fixture(enabled boolean); truncate hc.hc06_business_fixture; insert into hc.hc06_business_fixture values(false)')
        self.fixture.states[3]['carbon_monoxide_value'] = 12
        self.fixture.service.tick()
        row = self.store.load()
        self.assertEqual(row['last_co'], 12)
        self.assertIsNotNone(row['last_co_sample_at'])
        self.assertTrue(row['co_warning_active'])
        self.db.execute_sql(self.migration)
        self.assertFalse(self.db.fetch_one('select enabled from hc.hc06_business_fixture')['enabled'])
        self.assertEqual(self.store.load(), row)


if __name__ == '__main__':
    unittest.main()
