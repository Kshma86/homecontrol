"""HC-38 opt-in contracts on a dedicated, disposable PostgreSQL 16 database."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from baseline_contract import catalog, differences
from migrate_hc38 import BaselineError, install, load_files, SQL_FILE, CATALOG_FILE
from migrate_hc07 import migrate
from startup_schema_contract import check_domain
from startup_schema_manifest import DOMAIN_TABLES


@unittest.skipUnless(os.environ.get('HC38_TEST_POSTGRES') == '1', 'requires isolated HC-38 PostgreSQL')
class BaselinePostgresTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.psycopg, self.dict_row = psycopg, dict_row
        url = os.environ['HC38_TEST_DATABASE_URL']
        parsed = urlparse(url)
        if parsed.hostname != '127.0.0.1' or parsed.path != '/hc38_schema_test':
            raise AssertionError('HC-38 tests require their dedicated local database')
        self.conn = psycopg.connect(url, autocommit=True)
        self.addCleanup(self.conn.close)
        if self.conn.execute('select current_database()').fetchone()[0] != 'hc38_schema_test':
            raise AssertionError('HC-38 connection resolved to a different database')
        self.conn.execute('drop schema if exists hc cascade')
        self.sql_dir = Path(__file__).resolve().parents[2] / 'db'

    def scalar(self, query, params=()):
        return self.conn.execute(query, params).fetchone()[0]

    def apply(self):
        return install(self.conn, self.sql_dir, apply=True)

    def snapshot(self):
        with self.conn.transaction():
            return catalog(self.conn)

    def inventory(self):
        self.apply()
        device = self.scalar("insert into hc.device(platform,ext_id,name) values('system','fixture','fixture') returning id")
        entity = self.scalar("insert into hc.entity(device_id,name) values(%s,'fixture') returning id", (device,))
        self.conn.execute("""insert into hc.metric(key,value_type,enforce_validation,min_num,max_num)
          values('number','num',true,0,100),('flag','bool',true,null,null),
          ('text','text',true,null,null),('json','json',true,null,null),
          ('loose','num',false,0,1)""")
        return device, entity

    def test_plan_and_verify_empty_are_read_only(self):
        result = install(self.conn, self.sql_dir)
        self.assertEqual(result['state'], 'empty')
        self.assertTrue(result['pending'])
        self.assertFalse(install(self.conn, self.sql_dir, verify=True)['matched'])
        self.assertIsNone(self.scalar("select to_regnamespace('hc')"))

    def test_full_catalog_and_no_business_rows_or_extensions(self):
        result = self.apply()
        self.assertTrue(result['matched'])
        self.assertEqual(self.snapshot(), load_files(self.sql_dir)[1])
        names = self.conn.execute("select tablename from pg_tables where schemaname='hc' and tablename<>'schema_baseline'").fetchall()
        self.assertEqual(len(names), 52)
        for (name,) in names:
            self.assertEqual(self.scalar('select count(*) from hc.'+name), 0, name)
        self.assertEqual(self.scalar('select count(*) from pg_extension'), 1)  # plpgsql only
        self.assertEqual(self.scalar("select column_default from information_schema.columns where table_schema='hc' and table_name='irrigation_pilot_config' and column_name='soil_sensor_topic_base'"), "''::text")

    def test_replay_preserves_operator_data_and_sequence(self):
        self.inventory()
        before = self.conn.execute('select * from hc.device').fetchall()
        counter = self.scalar('select last_value from hc.device_id_seq')
        self.assertFalse(self.apply()['applied'])
        self.assertEqual(self.conn.execute('select * from hc.device').fetchall(), before)
        self.assertEqual(self.scalar('select last_value from hc.device_id_seq'), counter)

    def test_unversioned_schema_is_compared_but_never_adopted(self):
        self.apply()
        self.conn.execute('drop table hc.schema_baseline')
        before = self.snapshot()
        self.assertTrue(install(self.conn, self.sql_dir, verify=True)['matched'])
        with self.assertRaisesRegex(BaselineError, 'Existing HC schema refused'):
            self.apply()
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.scalar("select to_regclass('hc.schema_baseline')"))

    def test_partial_schema_and_unrelated_database_refused(self):
        self.conn.execute('create schema hc; create table hc.device(id integer)')
        with self.assertRaises(BaselineError): self.apply()
        self.assertEqual(self.scalar('select count(*) from hc.device'), 0)
        self.conn.execute('drop schema hc cascade; create table public.hc38_fixture(id integer)')
        try:
            with self.assertRaisesRegex(BaselineError, 'empty database'): self.apply()
            self.assertIsNone(self.scalar("select to_regnamespace('hc')"))
        finally:
            self.conn.execute('drop table public.hc38_fixture')
        self.conn.execute("create function public.hc38_fixture() returns int language sql as 'select 1'")
        try:
            with self.assertRaisesRegex(BaselineError, 'empty database'): self.apply()
        finally:
            self.conn.execute('drop function public.hc38_fixture()')

    def test_concurrent_installers_serialize_and_record_once(self):
        def run():
            with self.psycopg.connect(os.environ['HC38_TEST_DATABASE_URL'], autocommit=True) as conn:
                return install(conn, self.sql_dir, apply=True)['applied']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        self.assertEqual(sorted(results), [False,True])
        self.assertEqual(self.scalar('select count(*) from hc.schema_baseline'), 1)

    def test_file_checksum_and_missing_file_refused_before_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'baselines'
            target.mkdir()
            for name in (SQL_FILE, CATALOG_FILE):
                (Path(folder)/name).write_bytes((self.sql_dir/name).read_bytes())
            (Path(folder)/SQL_FILE).write_text('-- changed')
            with self.assertRaisesRegex(BaselineError, 'checksum'): install(self.conn, folder, apply=True)
            (Path(folder)/SQL_FILE).unlink()
            with self.assertRaisesRegex(BaselineError, 'Missing'): install(self.conn, folder, apply=True)
        self.assertIsNone(self.scalar("select to_regnamespace('hc')"))

    def test_changed_journal_refused(self):
        self.apply()
        self.conn.execute("update hc.schema_baseline set checksum=repeat('0',64)")
        with self.assertRaisesRegex(BaselineError, 'journal'): self.apply()
        self.assertEqual(self.scalar('select checksum from hc.schema_baseline'), '0'*64)

    def test_trigger_drift_reported_without_automatic_repair(self):
        self.apply()
        self.conn.execute('alter table hc.measurement enable trigger trg_touch_presence_measurement')
        result = install(self.conn, self.sql_dir, verify=True)
        self.assertFalse(result['matched'])
        self.assertEqual(set(result['differences']), {'triggers'})
        with self.assertRaises(BaselineError): self.apply()
        self.assertEqual(self.scalar("select tgenabled from pg_trigger where tgname='trg_touch_presence_measurement'"), 'O')

    def test_interrupted_sql_rolls_back_and_can_retry(self):
        body, expected = load_files(self.sql_dir)
        with patch('migrate_hc38.load_files', return_value=(body+"\nDO $$BEGIN RAISE EXCEPTION 'fixture interrupted'; END$$;", expected)):
            with self.assertRaises(self.psycopg.Error): self.apply()
        self.assertIsNone(self.scalar("select to_regnamespace('hc')"))
        self.assertTrue(self.apply()['matched'])

    def test_reference_mismatch_rolls_back_whole_install(self):
        body, expected = load_files(self.sql_dir)
        expected = deepcopy(expected)
        expected['functions'].clear()
        with patch('migrate_hc38.load_files', return_value=(body, expected)):
            with self.assertRaisesRegex(BaselineError, 'differs'): self.apply()
        self.assertIsNone(self.scalar("select to_regnamespace('hc')"))

    def test_enums_sequences_uniqueness_and_foreign_keys(self):
        device, entity = self.inventory()
        self.assertEqual((device, entity), (1,1))
        with self.assertRaises(self.psycopg.Error):
            self.conn.execute("insert into hc.device(platform,name) values('invalid','fixture')")
        with self.assertRaises(self.psycopg.errors.UniqueViolation):
            self.conn.execute("insert into hc.entity(device_id,name) values(%s,'fixture')", (device,))
        with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
            self.conn.execute("insert into hc.measurement(ts,entity_id,key,v_num) values(now(),99999,'number',5)")

    def test_validated_value_types_and_ranges_on_both_ingest_tables(self):
        _, entity = self.inventory()
        for table in ('measurement','entity_state'):
            for key, field, value in [('number','v_num',50),('flag','v_bool',True),('text','v_text','fixture'),('json','v_json','{}')]:
                self.conn.execute('insert into hc.'+table+'(ts,entity_id,key,'+field+') values(now(),%s,%s,%s)', (entity,key,value))
            for key, field, value in [('number','v_bool',True),('number','v_num',-1),('number','v_num',101),('flag','v_text','true'),('text','v_num',1),('json','v_text','{}')]:
                with self.assertRaises(self.psycopg.Error):
                    self.conn.execute('insert into hc.'+table+'(ts,entity_id,key,'+field+') values(now(),%s,%s,%s)', (entity,key,value))

    def test_state_update_validator_and_loose_unknown_metrics_preserved(self):
        _, entity = self.inventory()
        self.conn.execute("insert into hc.entity_state(entity_id,key,v_num) values(%s,'number',50)", (entity,))
        with self.assertRaises(self.psycopg.Error):
            self.conn.execute("update hc.entity_state set v_num=101 where entity_id=%s", (entity,))
        for key in ('loose','unknown'):
            self.conn.execute("insert into hc.entity_state(entity_id,key,v_text) values(%s,%s,'allowed historically')", (entity,key))
        self.assertEqual(self.scalar('select count(*) from hc.entity_state'), 3)

    def test_presence_touch_stays_disabled_after_real_inserts(self):
        _, entity = self.inventory()
        self.conn.execute("insert into hc.measurement(ts,entity_id,key,v_num) values(now(),%s,'number',5)", (entity,))
        self.conn.execute("insert into hc.entity_state(entity_id,key,v_num) values(%s,'number',5)", (entity,))
        self.assertEqual(self.scalar('select count(*) from hc.entity_presence'), 0)
        states = [(r[1],r[2]) for r in self.snapshot()['triggers']]
        self.assertEqual(sum(state=='D' for _,state in states), 2)
        self.assertEqual(sum(state=='O' for _,state in states), 3)

    def test_updated_at_and_explicit_presence_refresh_contract(self):
        device, entity = self.inventory()
        self.conn.execute("update hc.device set updated_at='2000-01-01' where id=%s", (device,))
        self.assertTrue(self.scalar("select updated_at>now()-interval '1 minute' from hc.device where id=%s", (device,)))
        self.conn.execute("insert into hc.entity_metric(entity_id,metric_key,max_interval_sec) values(%s,'number',10)", (entity,))
        self.conn.execute("insert into hc.entity_presence(entity_id,last_seen_ts,status) values(%s,now()-interval '1 minute','online')", (entity,))
        self.conn.execute('select hc.refresh_presence()')
        self.assertEqual(self.scalar('select status from hc.entity_presence'), 'offline')
        self.assertEqual(self.scalar("select v_text from hc.entity_state where key='availability'"), 'offline')

    def test_touch_function_on_temp_fixture_without_enabling_original_triggers(self):
        _, entity = self.inventory()
        self.conn.execute('create temporary table hc38_touch_fixture(entity_id bigint)')
        self.conn.execute('create trigger touch after insert on hc38_touch_fixture for each row execute function hc.tg_touch_presence()')
        self.conn.execute('insert into hc38_touch_fixture values(%s)', (entity,))
        self.assertEqual(self.scalar('select status from hc.entity_presence'), 'online')
        self.assertEqual(self.scalar("select v_text from hc.entity_state where key='availability'"), 'online')
        self.assertEqual(sum(row[2]=='D' for row in self.snapshot()['triggers']), 2)

    def test_outbox_defaults_and_delete_semantics_preserved(self):
        device, entity = self.inventory()
        self.conn.execute("insert into hc.command_outbox(entity_id,topic,payload) values(%s,'fixture/topic','{}')", (entity,))
        self.assertEqual(self.conn.execute('select id,status,retain,qos from hc.command_outbox').fetchone(), (1,'new',True,1))
        self.conn.execute('delete from hc.device where id=%s', (device,))
        self.assertEqual(self.scalar('select count(*) from hc.entity'), 0)
        self.assertIsNone(self.scalar('select entity_id from hc.command_outbox'))

    def test_baseline_then_explicit_migrations_and_optional_seed(self):
        self.apply()
        before = self.snapshot()
        result = migrate(self.conn, self.sql_dir, apply=True, seed_initial=True)
        self.assertTrue(result['ready'], result)
        self.assertEqual(result['applied'], ['059','060','hc07-initial-v1'])
        def fetch(query, params=()):
            with self.conn.cursor(row_factory=self.dict_row) as cur:
                return cur.execute(query, params).fetchone()
        for domain in DOMAIN_TABLES:
            check_domain(fetch, domain)
        after = self.snapshot()
        self.assertEqual(after['functions'], before['functions'])
        self.assertEqual(after['triggers'], before['triggers'])
        self.assertEqual(self.scalar('select soil_sensor_topic_base from hc.irrigation_pilot_config'), '')
        self.assertEqual(migrate(self.conn, self.sql_dir, apply=True, seed_initial=True)['applied'], [])
        # The fresh baseline must never be reapplied to an upgraded database.
        with self.assertRaises(BaselineError): self.apply()

