"""HC-07 real SQL checks: opt-in, dedicated disposable database only."""
import concurrent.futures
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from migrate_hc07 import migrate
import migrate_hc07
from startup_schema_contract import StartupSchemaError, check_domain
from startup_schema_manifest import DOMAIN_TABLES, MIGRATIONS


CORE = '''create schema hc;
create table hc.metric(key text primary key,value_type text,unit text,min_num numeric,max_num numeric,
 description text,enforce_validation boolean,is_active boolean);
create table hc.device(id bigserial primary key,platform text,ext_id text,name text,location text,model text,
 manufacturer text,is_active boolean,updated_at timestamptz default now(),unique(platform,ext_id));
create table hc.entity(id bigserial primary key,device_id bigint references hc.device(id),name text,
 topic_base text,is_active boolean,unique(device_id,name));
create table hc.entity_metric(entity_id bigint references hc.entity(id),metric_key text references hc.metric(key),
 store_mode text,deadband_num double precision,min_interval_sec integer,max_interval_sec integer,is_enabled boolean,
 primary key(entity_id,metric_key));
create function hc.hc07_fixture_trigger() returns trigger language plpgsql as $$begin return new; end$$;
create trigger fixture_disabled before update on hc.entity for each row execute function hc.hc07_fixture_trigger();
alter table hc.entity disable trigger fixture_disabled;
'''


@unittest.skipUnless(os.environ.get('HC07_TEST_POSTGRES') == '1', 'requires isolated HC-07 PostgreSQL')
class StartupSchemaPostgresTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.psycopg, self.dict_row = psycopg, dict_row
        self.url = os.environ['HC07_TEST_DATABASE_URL']
        parsed = urlparse(self.url)
        if parsed.hostname != '127.0.0.1' or parsed.path != '/hc07_schema_test':
            raise AssertionError('HC-07 tests require their dedicated local database')
        self.conn = psycopg.connect(self.url, autocommit=True)
        self.addCleanup(self.conn.close)
        self.conn.execute('drop schema if exists hc cascade')
        self.conn.execute(CORE)
        self.sql_dir = Path(__file__).resolve().parents[2] / 'db'

    def apply(self, seed=True):
        return migrate(self.conn, self.sql_dir, apply=True, seed_initial=seed)

    def fetch(self, query, params=()):
        # Enforce read-only connections for the actual runtime compatibility path.
        with self.psycopg.connect(self.url, row_factory=self.dict_row) as conn:
            conn.execute('set transaction read only')
            return conn.execute(query, params).fetchone()

    def scalar(self, query, params=()):
        return self.conn.execute(query, params).fetchone()[0]

    def business(self):
        result = {}
        for table in ['device','entity','metric','entity_metric','irrigation_pilot_config',
                      'irrigation_solar_pump_config','scheduler_config','climate_schedule_rule',
                      'domain_season_profile','domain_season_active','notes']:
            if self.scalar('select to_regclass(%s)', ('hc.'+table,)):
                result[table] = self.scalar('select coalesce(jsonb_agg(t order by to_jsonb(t)::text),\'[]\'::jsonb) from hc.'+table+' t')
        return result

    def test_plan_has_no_ddl_or_dml(self):
        before = self.business()
        result = migrate(self.conn, self.sql_dir)
        self.assertEqual(result['pending'], ['059','060'])
        self.assertFalse(result['ready'])
        self.assertIsNone(self.scalar("select to_regclass('hc.startup_schema_migration')"))
        self.assertEqual(self.business(), before)

    def test_empty_database_requires_core_without_creating_it(self):
        self.conn.execute('drop schema hc cascade')
        with self.assertRaisesRegex(StartupSchemaError, 'HC-38'):
            self.apply()
        self.assertIsNone(self.scalar("select to_regclass('hc.device')"))
        self.assertIsNone(self.scalar("select to_regclass('hc.startup_schema_migration')"))

    def test_first_domain_install_explicit_seed_and_read_only_checks(self):
        result = self.apply()
        self.assertTrue(result['ready'], result)
        self.assertEqual(result['applied'], ['059','060','hc07-initial-v1'])
        self.assertEqual(self.scalar('select count(*) from hc.climate_schedule_rule'), 7)
        self.assertEqual(self.scalar('select count(*) from hc.device'), 2)
        self.assertEqual(self.scalar('select count(*) from hc.entity'), 2)
        for domain in DOMAIN_TABLES:
            check_domain(self.fetch, domain)
        self.assertEqual(self.scalar("select tgenabled from pg_trigger where tgname='fixture_disabled'"), 'D')

    def test_restart_and_upgrade_preserve_operator_changes_exactly(self):
        self.apply()
        self.conn.execute("""update hc.device set is_active=false,name='operator device';
          update hc.entity set is_active=false,name='operator entity',topic_base='custom/topic';
          update hc.metric set is_active=false,description='custom',enforce_validation=false;
          update hc.entity_metric set is_enabled=false,min_interval_sec=17,max_interval_sec=18;
          update hc.scheduler_config set mode='v2_execute_irrigation',notes='keep';
          update hc.climate_schedule_rule set label='operator schedule',target_temperature=19,is_enabled=true;
          insert into hc.climate_schedule_rule(label,day_of_week,start_time) values('Climate morning comfort',0,'09:00');
          update hc.domain_season_active set profile='winter';
          insert into hc.notes(type,text,done,status) values('issues','operator note',true,'open');""")
        before = self.business()
        for _ in range(3):
            for domain in DOMAIN_TABLES: check_domain(self.fetch, domain)
        result = self.apply()
        self.assertEqual(result['applied'], [])
        self.assertEqual(self.business(), before)

    def test_unsupported_legacy_mode_and_historical_rules_are_never_converted(self):
        self.apply()
        self.conn.execute("update hc.scheduler_config set mode='v2_shadow'; drop table hc.startup_schema_migration")
        self.conn.execute("insert into hc.climate_schedule_rule(label,day_of_week,start_time) values('Climate morning comfort',0,'08:15')")
        before = self.business()
        result = self.apply(seed=False)
        self.assertFalse(result['ready'])
        self.assertIn('scheduler', result['readiness_errors'])
        self.assertEqual(self.business(), before)
        with self.assertRaisesRegex(StartupSchemaError, 'No automatic mode conversion'):
            check_domain(self.fetch, 'scheduler')
        self.assertEqual(self.scalar('select mode from hc.scheduler_config'), 'v2_shadow')

    def test_explicit_operator_mode_change_can_complete_readiness(self):
        self.apply()
        self.conn.execute("update hc.scheduler_config set mode='legacy'")
        with self.assertRaises(StartupSchemaError): check_domain(self.fetch, 'scheduler')
        self.conn.execute("update hc.scheduler_config set mode='v2_execute_irrigation'")
        check_domain(self.fetch, 'scheduler')

    def test_initial_seed_refuses_existing_installation(self):
        result = self.apply(seed=False)
        self.assertFalse(result['ready'])
        self.conn.execute('insert into hc.irrigation_pilot_config(id) values(1)')
        before = self.business()
        with self.assertRaisesRegex(StartupSchemaError, 'Initial seed refused'):
            self.apply()
        self.assertEqual(self.business(), before)

    def test_seed_is_once_only_even_after_operator_deletes_defaults(self):
        self.apply()
        self.conn.execute('delete from hc.climate_schedule_rule where day_of_week=0; delete from hc.entity_metric')
        before = self.business()
        self.assertEqual(self.apply()['applied'], [])
        self.assertEqual(self.business(), before)
        self.assertEqual(self.scalar('select count(*) from hc.climate_schedule_rule'), 6)

    def test_missing_configuration_is_not_recreated_by_checks_or_seed_replay(self):
        self.apply()
        self.conn.execute('delete from hc.irrigation_pilot_config')
        with self.assertRaises(StartupSchemaError): check_domain(self.fetch, 'pilot')
        self.assertFalse(self.apply()['ready'])
        self.assertEqual(self.scalar('select count(*) from hc.irrigation_pilot_config'), 0)

    def test_column_type_drift_fails_without_repair(self):
        self.apply()
        self.conn.execute('alter table hc.irrigation_pilot_config alter column base_duration_minutes type bigint')
        with self.assertRaisesRegex(StartupSchemaError, 'columns/types'):
            check_domain(self.fetch, 'pilot')

    def test_missing_index_fails_without_recreating_it(self):
        self.apply()
        self.conn.execute('drop index hc.ux_scheduler_run_idempotency')
        with self.assertRaisesRegex(StartupSchemaError, 'index'):
            check_domain(self.fetch, 'scheduler')
        self.assertIsNone(self.scalar("select to_regclass('hc.ux_scheduler_run_idempotency')"))

    def test_checksum_or_unknown_journal_version_refuses_rewrite(self):
        self.apply()
        self.conn.execute("update hc.startup_schema_migration set checksum=repeat('0',64) where version='059'")
        with self.assertRaises(StartupSchemaError): self.apply()
        with self.assertRaises(StartupSchemaError): check_domain(self.fetch, 'pilot')
        self.conn.execute('update hc.startup_schema_migration set checksum=%s where version=%s', (MIGRATIONS[0][2], '059'))
        self.conn.execute("update hc.startup_schema_migration set checksum=repeat('0',64) where version='hc07-initial-v1'")
        with self.assertRaises(StartupSchemaError): check_domain(self.fetch, 'pilot')
        self.conn.execute('update hc.startup_schema_migration set checksum=%s where version=%s', (MIGRATIONS[2][2], 'hc07-initial-v1'))
        self.conn.execute("insert into hc.startup_schema_migration(version,checksum) values('future',repeat('0',64))")
        with self.assertRaises(StartupSchemaError): self.apply()
        with self.assertRaises(StartupSchemaError): check_domain(self.fetch, 'scheduler')

    def test_sql_file_tampering_is_detected_before_writes(self):
        with tempfile.TemporaryDirectory() as name:
            dest=Path(name)
            for _,filename,_ in MIGRATIONS:
                (dest/filename).parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(self.sql_dir/filename, dest/filename)
            with (dest/MIGRATIONS[0][1]).open('a') as stream: stream.write('\n-- drift\n')
            with self.assertRaisesRegex(StartupSchemaError, 'checksum'):
                migrate(self.conn, dest, apply=True, seed_initial=True)
            shutil.copy2(self.sql_dir/MIGRATIONS[0][1], dest/MIGRATIONS[0][1])
            (dest/MIGRATIONS[2][1]).unlink()
            with self.assertRaisesRegex(StartupSchemaError, 'Missing/unreadable'):
                migrate(self.conn, dest, apply=True, seed_initial=True)
        self.assertIsNone(self.scalar("select to_regclass('hc.startup_schema_migration')"))

    def test_interruption_rolls_back_schema_data_and_journal_then_resumes(self):
        original=migrate_hc07.apply_one
        def interrupted(conn,version,body,checksum):
            original(conn,version,body,checksum)
            raise RuntimeError('simulated interruption before commit')
        with patch.object(migrate_hc07,'apply_one',interrupted):
            with self.assertRaises(RuntimeError): self.apply()
        self.assertIsNone(self.scalar("select to_regclass('hc.irrigation_pilot_config')"))
        self.assertIsNone(self.scalar("select to_regclass('hc.startup_schema_migration')"))
        self.assertTrue(self.apply()['ready'])

    def test_two_migrators_serialize_and_apply_once(self):
        barrier=threading.Barrier(2)
        def task():
            with self.psycopg.connect(self.url,autocommit=True) as conn:
                barrier.wait(timeout=5)
                return migrate(conn,self.sql_dir,apply=True,seed_initial=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _: task(),range(2)))
        self.assertEqual(sorted(len(r['applied']) for r in results), [0,3])
        self.assertTrue(all(r['ready'] for r in results))

    def test_lost_commit_reply_replay_uses_journal_without_reapplying(self):
        real=self.conn
        class LostReply:
            def __getattr__(self,key): return getattr(real,key)
            @contextmanager
            def transaction(self):
                outer=real.info.transaction_status==self_psycopg.pq.TransactionStatus.IDLE
                with real.transaction(): yield
                if outer: raise self_psycopg.OperationalError('simulated lost reply after committed transaction')
        self_psycopg=self.psycopg
        with self.assertRaises(self.psycopg.OperationalError):
            migrate(LostReply(),self.sql_dir,apply=True,seed_initial=True)
        before=self.business()
        self.assertEqual(self.scalar('select count(*) from hc.startup_schema_migration'),3)
        replay=self.apply()
        self.assertEqual(replay['applied'],[])
        self.assertEqual(self.business(),before)

    def test_legacy_capabilities_and_missing_note_status_migrate_once(self):
        self.conn.execute("""create table hc.domain_season_profile(domain text,profile text,settings jsonb,
          updated_at timestamptz default now(),primary key(domain,profile));
          create table hc.domain_season_active(domain text primary key,profile text,activated_at timestamptz default now());
          insert into hc.domain_season_profile values('irrigation','winter','{"control_enabled":false,"manual_watering":true}',now());
          insert into hc.domain_season_active(domain,profile) values('irrigation','winter');
          create table hc.notes(id bigserial primary key,type text,text text,done boolean,
              created_at timestamptz default now(),updated_at timestamptz default now());
          insert into hc.notes(type,text,done) values('issues','legacy',true);""")
        self.apply(seed=False)
        settings=self.scalar('select settings from hc.domain_season_profile')
        self.assertNotIn('control_enabled', settings)
        self.assertTrue(settings['manual_watering'])
        self.assertFalse(settings['scheduled_watering'])
        self.assertEqual(self.scalar('select profile from hc.domain_season_active'), 'winter')
        self.assertEqual(self.scalar('select status from hc.notes'), 'tested')
        self.conn.execute("update hc.notes set status='open'")
        before=self.business()
        self.apply(seed=False)
        self.assertEqual(self.business(), before)


if __name__ == '__main__':
    unittest.main()
