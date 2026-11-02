"""HC-15 real connection/rollback and former-query parity on a disposable DB."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from urllib.parse import urlparse,urlunparse

from flask import Flask
import psycopg
from psycopg.rows import dict_row

from climate_service import ClimateService
from db_runtime import DatabaseRuntime
from irrigation_service import IrrigationService
from runtime_utils import current_db_query_count,normalize_text

QUERIES=json.loads((Path(__file__).with_name('fixtures')/'hc15_queries.json').read_text())


@unittest.skipUnless(os.environ.get('HC15_TEST_POSTGRES')=='1','requires isolated HC-15 PostgreSQL')
class DatabaseRuntimePostgresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url=os.environ['HC15_TEST_DATABASE_URL'];parsed=urlparse(url)
        if parsed.hostname!='127.0.0.1' or parsed.path!='/hc15_runtime_test':
            raise AssertionError('HC-15 requires its dedicated loopback test database')
        cls.admin=psycopg.connect(url,autocommit=True);cls.addClassCleanup(cls.admin.close)
        cls.admin.execute('''
          create schema hc;
          create role hc_app login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
          revoke create on database hc15_runtime_test from public;
          grant connect on database hc15_runtime_test to hc_app;
          grant usage on schema hc to hc_app;
          create table hc.runtime_receipt(id integer primary key,value text);
          create table hc.domain_season_active(domain text primary key,profile text);
          insert into hc.domain_season_active values('climate','winter');
          create table hc.climate_schedule_rule(
            id bigint primary key,label text,day_of_week integer,start_time time,is_enabled boolean,
            season_profile text,power text,mode text,target_temperature integer,fan_speed text,
            light text,extra_fan text,rule_engine text,updated_at timestamptz default now());
          insert into hc.climate_schedule_rule(id,label,day_of_week,start_time,is_enabled,season_profile,power,mode,target_temperature,fan_speed,light,extra_fan,rule_engine)
          select n,'fixture-'||n,
            case when n=4 then (extract(isodow from now())::int)%7 else extract(isodow from now())::int-1 end,
            case when n=3 then (date_trunc('minute',localtimestamp)+interval '1 minute')::time else date_trunc('minute',localtimestamp)::time end,
            n<>2,case when n=5 then 'summer' else 'winter' end,'on','heat',22,'auto','off',null,'v2'
          from generate_series(1,5) n;
          create table hc.irrigation_manual_session(started_by text,start_payload jsonb,started_at timestamptz,requested_stop_at timestamptz);
          insert into hc.irrigation_manual_session values
            ('v2_scheduler','{"schedule_id":"42"}',now()-interval '1 minute',now()+interval '10 minutes'),
            ('v2_scheduler','{"schedule_id":"42"}',now(),now()+interval '20 minutes'),
            ('manual','{"schedule_id":"42"}',now(),now()+interval '30 minutes'),
            ('v2_scheduler','{"schedule_id":"42"}',current_date-interval '1 minute',now()+interval '40 minutes');
          grant select,insert,update,delete on all tables in schema hc to hc_app;
        ''')
        app_url=urlunparse(parsed._replace(netloc='hc_app@127.0.0.1'+(':'+str(parsed.port) if parsed.port else '')))
        cls.runtime=DatabaseRuntime(app_url);cls.admin_url=url

    def setUp(self):
        self.admin.execute('truncate hc.runtime_receipt')
        self.app=Flask(__name__)

    def rows(self):
        return self.admin.execute('select id from hc.runtime_receipt order by id').fetchall()

    def test_helpers_preserve_results_commits_and_exact_query_counter(self):
        with self.app.test_request_context():
            self.runtime.execute_sql("insert into hc.runtime_receipt values(1,'first')")
            self.assertEqual(self.runtime.execute_one("insert into hc.runtime_receipt values(2,'second') returning id"),{'id':2})
            self.assertEqual(self.runtime.fetch_one('select value from hc.runtime_receipt where id=%s',(1,)),{'value':'first'})
            self.assertEqual(self.runtime.fetch_all('select id from hc.runtime_receipt order by id'),[{'id':1},{'id':2}])
            self.assertEqual(current_db_query_count(),4)
            self.assertTrue(self.runtime.check());self.assertEqual(current_db_query_count(),4)
            self.assertIsNone(self.runtime.execute_one("update hc.runtime_receipt set value='updated' where id=2"))
            self.assertEqual(current_db_query_count(),5)
        self.assertEqual(self.rows(),[(1,),(2,)])

    def test_raw_context_exception_rolls_back_and_closes_the_connection(self):
        connection=None
        with self.assertRaisesRegex(ValueError,'abort'),self.runtime.conn(dict_row) as connection:
            connection.execute("insert into hc.runtime_receipt values(1,'rolled-back')")
            raise ValueError('abort')
        self.assertTrue(connection.closed);self.assertEqual(self.rows(),[])

    def test_nested_transaction_preserves_savepoint_rollback_and_outer_commit(self):
        with self.runtime.conn(dict_row) as connection:
            connection.execute("insert into hc.runtime_receipt values(1,'outer')")
            try:
                with connection.transaction():
                    connection.execute("insert into hc.runtime_receipt values(2,'savepoint')")
                    raise ValueError('cancel inner')
            except ValueError:pass
            connection.execute("insert into hc.runtime_receipt values(3,'outer')")
        self.assertTrue(connection.closed);self.assertEqual(self.rows(),[(1,),(3,)])

    def test_sql_failure_rolls_back_prior_statement_and_counts_one_attempt(self):
        with self.app.test_request_context():
            with self.assertRaises(psycopg.errors.DivisionByZero):
                self.runtime.execute_sql("insert into hc.runtime_receipt values(1,'rolled-back'); select 1/0")
            self.assertEqual(current_db_query_count(),1)
        self.assertEqual(self.rows(),[])

    def test_unrestricted_role_is_still_rejected_before_domain_sql(self):
        with self.assertRaisesRegex(RuntimeError,'restricted HC-39 application role'):
            DatabaseRuntime(self.admin_url).fetch_one('select 1')

    def test_climate_payload_and_statuses_match_the_original_sql_in_one_transaction(self):
        with self.runtime.conn(dict_row) as connection:
            # Both SQL versions see the same transaction clock, including if
            # setup crossed a minute/day boundary.
            connection.execute('''update hc.climate_schedule_rule set
              day_of_week=case when id=4 then extract(isodow from now())::int%7 else extract(isodow from now())::int-1 end,
              start_time=case when id=3 then (date_trunc('minute',localtimestamp)+interval '1 minute')::time else date_trunc('minute',localtimestamp)::time end''')
            service=ClimateService.__new__(ClimateService)
            service.normalize_text=normalize_text
            service.ensure_season_profile_schema=lambda:None;service.ensure_scheduler_schema=lambda:None
            calls=[]
            def query(sql,params=()):
                calls.append((sql,params));return connection.execute(sql,params).fetchall()
            service.fetch_all=query
            for profile in (None,'winter','summer',' winter '):
                old=connection.execute(QUERIES['fetch_climate_schedule_rules'],(normalize_text(profile) or None,)).fetchall()
                self.assertEqual(service.fetch_schedule_rules(profile),old)
            self.assertEqual(len(calls),4)
            statuses={row['schedule_status'] for row in service.fetch_schedule_rules('winter')}
            self.assertEqual(statuses,{'due_now','disabled','armed_today','armed'})
            self.assertTrue(all(row['extra_fan']=='keep' for row in service.fetch_schedule_rules('winter')))

    def test_v2_session_latest_day_source_and_missing_row_match_original_sql(self):
        with self.runtime.conn(dict_row) as connection:
            service=SimpleNamespace(fetch_one=lambda sql,params=():connection.execute(sql,params).fetchone())
            for ref in ('42',42,'missing',None):
                old=connection.execute(QUERIES['fetch_irrigation_v2_session'],(str(ref),)).fetchone()
                self.assertEqual(IrrigationService.fetch_v2_session(service,ref),old)
