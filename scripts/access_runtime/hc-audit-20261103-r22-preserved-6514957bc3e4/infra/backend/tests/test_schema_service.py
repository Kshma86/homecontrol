import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schema_service import HcSchemaService
from startup_schema_contract import StartupSchemaError
from startup_schema_manifest import MIGRATIONS


class HcSchemaServiceTest(unittest.TestCase):
    def test_pilot_schema_runs_once(self):
        calls = []
        def fetch(query, params=()):
            calls.append(query)
            if 'to_regclass' in query: return {'present': True}
            if 'where not(version' in query: return None
            if 'select checksum' in query: return {'checksum': next(m[2] for m in MIGRATIONS if m[0]==params[0])}
            if 'with expected' in query: return {'missing': []}
            return {'id': 1}
        service = HcSchemaService(lambda sql: self.fail('Startup must not execute DDL/DML'), fetch)

        service.ensure_pilot_schema()
        service.ensure_pilot_schema()

        first = len(calls)
        service.ensure_pilot_schema()
        self.assertEqual(first, len(calls))
        self.assertTrue(all(query.lstrip().lower().startswith(('select', 'with')) for query in calls))

    def test_missing_journal_fails_without_writes_and_can_retry(self):
        service = HcSchemaService(lambda sql: self.fail('No runtime migration'), lambda *a: {'present': False})
        with self.assertRaises(StartupSchemaError): service.ensure_pilot_schema()
        self.assertFalse(service._pilot_ready)

    def test_power_wall_schema_runs_once(self):
        calls = []
        service = HcSchemaService(lambda sql: calls.append(sql))

        service.ensure_power_wall_schema()
        service.ensure_power_wall_schema()

        self.assertEqual(len(calls), 2)
        self.assertTrue(all(q.startswith("select ") for q in calls))
        self.assertIn("hc.power_wall_policy limit 0", calls[0])


if __name__ == "__main__":
    unittest.main()
