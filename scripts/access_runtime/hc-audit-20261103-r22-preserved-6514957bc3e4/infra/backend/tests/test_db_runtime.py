"""HC-15: measured access preserves its role, arguments and error boundary."""
import threading
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from psycopg.rows import dict_row

from db_runtime import DatabaseRuntime
from runtime_utils import current_db_query_count


class DatabaseRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.database = Mock()
        with patch('db_runtime.DatabaseService', return_value=self.database) as factory:
            self.runtime = DatabaseRuntime('postgresql://fixture.invalid/test')
        factory.assert_called_once_with('postgresql://fixture.invalid/test', expected_role='hc_app')
        self.app = Flask(__name__)

    def test_each_helper_counts_once_and_preserves_result_and_parameters(self):
        with self.app.test_request_context():
            for name, params in [('fetch_all',(1,)), ('fetch_one',()), ('execute_one',[2]), ('execute_sql',None)]:
                result = object()
                getattr(self.database,name).return_value = result
                before = current_db_query_count()
                self.assertIs(getattr(self.runtime,name)('select %s',params),result)
                getattr(self.database,name).assert_called_once_with('select %s',params)
                self.assertEqual(current_db_query_count(), before+1)

    def test_default_parameter_contracts_are_unchanged(self):
        for name in ('fetch_all','fetch_one','execute_one','execute_sql'):
            getattr(self.runtime,name)('select 1')
            getattr(self.database,name).assert_called_once_with('select 1',None if name=='execute_sql' else ())

    def test_failed_attempt_counts_once_and_preserves_the_exception(self):
        with self.app.test_request_context():
            for index,name in enumerate(('fetch_all','fetch_one','execute_one','execute_sql'),1):
                error = RuntimeError('fixture SQL failure')
                getattr(self.database,name).side_effect = error
                with self.assertRaises(RuntimeError) as caught:getattr(self.runtime,name)('bad SQL')
                self.assertIs(caught.exception,error)
                self.assertEqual(current_db_query_count(),index)

    def test_raw_connection_context_is_not_replaced_or_counted(self):
        with self.app.test_request_context():
            self.assertIs(self.runtime.conn(dict_row),self.database.conn.return_value)
            self.database.conn.assert_called_once_with(dict_row)
            self.assertEqual(current_db_query_count(),0)

    def test_health_check_does_not_change_query_count(self):
        self.database.check.return_value = False
        with self.app.test_request_context():
            self.assertFalse(self.runtime.check())
            self.assertEqual(current_db_query_count(),0)

    def test_helpers_work_outside_a_request_context(self):
        self.runtime.fetch_one('select 1')
        self.assertIsNone(current_db_query_count())

    def test_request_counters_remain_thread_local(self):
        counts=[];errors=[];barrier=threading.Barrier(2,timeout=3)
        def work(number):
            try:
                with self.app.test_request_context():
                    for _ in range(number):self.runtime.fetch_one('select 1')
                    barrier.wait();counts.append(current_db_query_count())
            except BaseException as error:errors.append(error)
        threads=[threading.Thread(target=work,args=(n,)) for n in (1,3)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors,[]);self.assertEqual(sorted(counts),[1,3])
