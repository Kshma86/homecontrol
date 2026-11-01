"""HC-39 opt-in role matrix: disposable loopback database, no live signals/data."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from database_service import DatabaseService
from migrate_hc39 import CHECKSUM, FILENAME, PrivilegeError, provision
from runtime_schema_contract import REQUIRED, check_runtime_schema
from sql_lab_database import SqlLabDatabase
from sql_lab_service import SqlLabService


class SqlLabIsolationTest(unittest.TestCase):
    def test_http_endpoints_report_missing_reader_as_unavailable(self):
        from flask import Flask
        from api_route_modules import register_sql_lab_routes
        database = SqlLabDatabase('')
        service = SqlLabService(db_conn=database.conn,fetch_all=database.fetch_all,fetch_one=database.fetch_one)
        app = Flask(__name__)
        register_sql_lab_routes(app,get_sql_lab_service=lambda:service,json_ready=lambda value:value)
        client = app.test_client()
        responses = [client.get('/api/sql-lab/schema'),
                     client.get('/api/sql-lab/preview?schema=hc&table=device'),
                     client.post('/api/sql-lab/query',json={'sql':'select 1'})]
        for response in responses:
            self.assertEqual(response.status_code,503)
            self.assertIn('SQL_LAB_DATABASE_URL',response.get_json()['error'])

    def test_missing_reader_dsn_never_connects_or_falls_back(self):
        with patch('sql_lab_database.psycopg.connect') as connect:
            with self.assertRaisesRegex(RuntimeError, 'SQL_LAB_DATABASE_URL'):
                SqlLabDatabase('').conn()
            connect.assert_not_called()

    def test_connection_error_does_not_expose_credentials(self):
        with patch('sql_lab_database.psycopg.connect', side_effect=RuntimeError('password=private-fixture')):
            with self.assertRaises(RuntimeError) as error:
                SqlLabDatabase('private-fixture').conn()
            self.assertNotIn('private-fixture', str(error.exception))


@unittest.skipUnless(os.environ.get('HC39_TEST_POSTGRES') == '1', 'requires disposable HC-39 PostgreSQL')
class DatabasePrivilegePostgresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ['HC39_TEST_DATABASE_URL']
        parsed = urlparse(url)
        if parsed.hostname != '127.0.0.1' or parsed.path != '/hc39_privilege_test':
            raise AssertionError('HC-39 requires its dedicated loopback test database')
        cls.admin = psycopg.connect(url, autocommit=True)
        if cls.admin.execute('select current_database()').fetchone()[0] != 'hc39_privilege_test':
            cls.admin.close()
            raise AssertionError('Wrong HC-39 target database')
        cls.addClassCleanup(cls.admin.close)
        cls.sql_dir = Path(__file__).resolve().parents[2] / 'db'
        if not cls.admin.execute("select to_regclass('hc.db_privilege_migration')").fetchone()[0]:
            import secrets
            from migrate_hc38 import install
            from migrate_hc07 import migrate
            install(cls.admin, cls.sql_dir, apply=True)
            cls.admin.execute((cls.sql_dir / '058_combustion_safety_runtime.sql').read_text())
            migrate(cls.admin, cls.sql_dir, apply=True, seed_initial=True)
            provision(cls.admin, cls.sql_dir, apply=True,
                      passwords={r: secrets.token_hex(24) for r in ('hc_app','hc_lab')})
        config = conninfo_to_dict(url)
        cls.reader_url = make_conninfo(**{**config, 'user':'hc_lab', 'password':''})
        cls.app_url = make_conninfo(**{**config, 'user':'hc_app', 'password':''})
        cls.reader = SqlLabDatabase(cls.reader_url)
        cls.application = DatabaseService(cls.app_url, expected_role='hc_app')

    def service(self, **kwargs):
        return SqlLabService(db_conn=self.reader.conn, fetch_all=self.reader.fetch_all,
                             fetch_one=self.reader.fetch_one, **kwargs)

    def test_01_role_attributes_and_no_memberships(self):
        rows = self.admin.execute('''select rolname,rolsuper,rolcreatedb,rolcreaterole,
            rolreplication,rolbypassrls,rolinherit from pg_roles where rolname in ('hc_app','hc_lab') order by 1''').fetchall()
        self.assertEqual(rows, [(r,False,False,False,False,False,False) for r in ('hc_app','hc_lab')])
        self.assertEqual(self.admin.execute("select count(*) from pg_auth_members m join pg_roles r on r.oid=m.member where r.rolname in ('hc_app','hc_lab')").fetchone()[0], 0)

    def test_02_plan_reapply_preserve_operator_configuration_and_trigger_state(self):
        from baseline_contract import catalog
        before = catalog(self.admin)
        config = self.admin.execute('select row_to_json(c) from hc.climate_window_guard c').fetchall()
        self.assertFalse(provision(self.admin, self.sql_dir)['pending'])
        self.assertFalse(provision(self.admin, self.sql_dir, apply=True)['applied'])
        self.assertEqual(before, catalog(self.admin))
        self.assertEqual(config, self.admin.execute('select row_to_json(c) from hc.climate_window_guard c').fetchall())

    def test_03_reader_schema_preview_and_row_limit(self):
        service = self.service()
        schema = service.schema()
        self.assertTrue(schema['tables'])
        self.assertTrue(all(t['schema_name']=='hc' for t in schema['tables']))
        self.assertEqual(service.preview('hc','climate_window_guard')[1], 200)
        self.assertEqual(service.preview('public','fixture')[1], 400)
        result, status = service.run({'sql':'select n from generate_series(1,1000) n','limit':9999})
        self.assertEqual(status,200); self.assertEqual(result['row_count'],500)

    def test_04_privileged_catalog_read_denied(self):
        result, status = self.service().run({'sql':'select count(*) from pg_catalog.pg_authid'})
        self.assertEqual(status,400); self.assertIn('permission denied',result['error'])

    def test_05_signaling_other_role_is_denied_and_target_survives(self):
        with self.application.conn() as target:
            pid = target.execute('select pg_backend_pid()').fetchone()[0]
            for function in ('pg_cancel_backend','pg_terminate_backend'):
                result, status = self.service().run({'sql':f'select {function}({pid})'})
                self.assertEqual(status,400); self.assertIn('permission denied',result['error'])
                self.assertEqual(target.execute('select 1').fetchone()[0],1)

    def test_06_reader_cannot_assume_application_role(self):
        result, status = self.service().run({'sql':"select set_config('role','hc_app',true)"})
        self.assertEqual(status,400); self.assertIn('permission denied',result['error'])

    def test_07_reader_database_acls_enforce_read_only_even_when_transaction_flag_is_off(self):
        statements = ["update hc.climate_window_guard set suspended=true where id=1",
                      "select nextval('hc.device_id_seq')", "select setval('hc.device_id_seq',1)",
                      'create table hc.hc39_forbidden(id int)', 'create temp table hc39_forbidden(id int)',
                      'create role hc39_forbidden']
        for statement in statements:
            with self.subTest(statement=statement), self.reader.conn() as conn:
                conn.read_only = False
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(statement)

    def test_08_app_sequence_dml_and_validation_triggers(self):
        with self.application.conn() as conn, conn.transaction(force_rollback=True):
            device = conn.execute("insert into hc.device(platform,ext_id,name) values('system','hc39-fixture','HC39') returning id").fetchone()[0]
            entity = conn.execute("insert into hc.entity(device_id,name) values(%s,'HC39') returning id",(device,)).fetchone()[0]
            conn.execute("insert into hc.metric(key,value_type,min_num,max_num,enforce_validation) values('hc39_fixture','num',0,10,true)")
            conn.execute("insert into hc.entity_state(entity_id,key,v_num) values(%s,'hc39_fixture',5)",(entity,))
            with self.assertRaises(psycopg.Error), conn.transaction():
                conn.execute("insert into hc.measurement(ts,entity_id,key,v_num) values(now(),%s,'hc39_fixture',11)",(entity,))
            conn.execute('update hc.device set name=%s where id=%s',('HC39 edited',device))
            conn.execute('delete from hc.entity_state where entity_id=%s',(entity,))

    def test_09_app_cannot_do_schema_or_journal_or_role_administration(self):
        for statement in ('alter table hc.device add column hc39_forbidden int',
                          "update hc.db_privilege_migration set policy='forbidden'",
                          'create table hc.hc39_forbidden(id int)', 'create role hc39_forbidden'):
            with self.subTest(statement=statement), self.application.conn() as conn:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege): conn.execute(statement)
        with self.application.conn() as conn:
            with self.assertRaises(PrivilegeError): provision(conn,self.sql_dir,apply=True)

    def test_10_former_lazy_paths_only_validate_with_restricted_app(self):
        from baseline_contract import catalog
        before = catalog(self.admin)
        for domain in REQUIRED:
            check_runtime_schema(self.application.execute_sql, domain)
        self.assertEqual(before,catalog(self.admin))

    def test_11_missing_schema_check_fails_without_repair_and_can_retry(self):
        self.admin.execute('alter table hc.page_usage_event rename to hc39_hidden_usage')
        try:
            with self.assertRaisesRegex(RuntimeError,'migrate_hc39'):
                check_runtime_schema(self.application.execute_sql,'page_usage')
            self.assertIsNone(self.admin.execute("select to_regclass('hc.page_usage_event')").fetchone()[0])
        finally:
            self.admin.execute('alter table hc.hc39_hidden_usage rename to page_usage_event')
        check_runtime_schema(self.application.execute_sql,'page_usage')

    def test_12_admin_and_runtime_dsns_are_rejected_by_lab(self):
        for url in (os.environ['HC39_TEST_DATABASE_URL'],self.app_url):
            with self.assertRaisesRegex(RuntimeError,'unsafe privileges'): SqlLabDatabase(url).conn()
        with self.assertRaisesRegex(RuntimeError,'restricted HC-39'):
            DatabaseService(os.environ['HC39_TEST_DATABASE_URL'],expected_role='hc_app').conn()

    def test_13_privilege_drift_is_rejected_on_next_connection(self):
        self.admin.execute('grant pg_signal_backend to hc_lab')
        try:
            with self.assertRaises(RuntimeError): self.reader.conn()
            with self.assertRaises(PrivilegeError): provision(self.admin,self.sql_dir)
        finally:
            self.admin.execute('revoke pg_signal_backend from hc_lab')
        self.assertEqual(self.reader.fetch_one('select current_user as role')['role'],'hc_lab')

    def test_14_timeout_rolls_back_and_next_connection_works(self):
        result, status = self.service(statement_timeout_ms=50).run({'sql':'select pg_sleep(1)'})
        self.assertEqual(status,400); self.assertIn('statement timeout',result['error'])
        self.assertEqual(self.service().run({'sql':'select 1'})[1],200)

    def test_15_checksum_mismatch_is_refused_before_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,FILENAME).write_text('select 1')
            with self.assertRaises(PrivilegeError): provision(self.admin,folder,apply=True)
        self.assertEqual(self.admin.execute('select checksum from hc.db_privilege_migration').fetchone()[0],CHECKSUM)

    def test_16_public_read_grant_fails_closed(self):
        self.admin.execute('create role hc39_legacy_client login; create table public.hc39_fixture(id int); grant select on public.hc39_fixture to public')
        try:
            with self.assertRaises(RuntimeError): self.reader.conn()
            provision(self.admin,self.sql_dir,apply=True)
            self.assertEqual(self.reader.fetch_one('select 1 as n')['n'],1)
            self.assertTrue(self.admin.execute("select has_table_privilege('hc39_legacy_client','public.hc39_fixture','SELECT')").fetchone()[0])
            with self.reader.conn() as conn:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege): conn.execute('select * from public.hc39_fixture')
        finally:
            self.admin.execute('drop table public.hc39_fixture')
            self.admin.execute('drop owned by hc39_legacy_client; drop role hc39_legacy_client')

    def test_17_direct_column_grant_is_unsafe_and_failed_repair_is_atomic(self):
        self.admin.execute('create table public.hc39_fixture(id int); grant select(id) on public.hc39_fixture to hc_lab')
        try:
            with self.assertRaises(RuntimeError): self.reader.conn()
            with self.assertRaises(PrivilegeError): provision(self.admin,self.sql_dir,apply=True)
            self.assertTrue(self.admin.execute("select has_column_privilege('hc_lab','public.hc39_fixture','id','SELECT')").fetchone()[0])
        finally:
            self.admin.execute('drop table public.hc39_fixture')

    def test_18_security_definer_access_is_rejected_before_user_query(self):
        self.admin.execute("create function public.hc39_fixture() returns int language sql security definer as 'select 1'; grant execute on function public.hc39_fixture() to hc_lab")
        try:
            with self.assertRaises(RuntimeError): self.reader.conn()
            with self.assertRaises(PrivilegeError): provision(self.admin,self.sql_dir,apply=True)
        finally:
            self.admin.execute('drop function public.hc39_fixture()')


if __name__ == '__main__':
    unittest.main()
