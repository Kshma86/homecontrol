import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schema_service import HcSchemaService, PILOT_SCHEMA_SQL, POWER_WALL_SCHEMA_SQL


class HcSchemaServiceTest(unittest.TestCase):
    def test_pilot_schema_runs_once(self):
        calls = []
        service = HcSchemaService(lambda sql: calls.append(sql))

        service.ensure_pilot_schema()
        service.ensure_pilot_schema()

        self.assertEqual(calls, [PILOT_SCHEMA_SQL])

    def test_power_wall_schema_runs_once(self):
        calls = []
        service = HcSchemaService(lambda sql: calls.append(sql))

        service.ensure_power_wall_schema()
        service.ensure_power_wall_schema()

        self.assertEqual(calls, [POWER_WALL_SCHEMA_SQL])


if __name__ == "__main__":
    unittest.main()
