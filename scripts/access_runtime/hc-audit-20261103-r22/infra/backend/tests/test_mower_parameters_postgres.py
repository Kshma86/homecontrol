"""Opt-in real SQL checks; only transaction-local pg_temp tables, rolled back."""
from contextlib import contextmanager
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg.rows import dict_row
import mower_parameters_store as storage
from mower_parameters_service import DraftError, MowerParametersService, template
from tests.test_mower_parameters import fixture


@unittest.skipUnless(os.environ.get("MOWER_TEST_POSTGRES") == "1", "Opt in with MOWER_TEST_POSTGRES=1; uses only pg_temp/rollback")
class MowerParametersPostgresTest(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
        self.transaction = self.connection.transaction(force_rollback=True)
        self.transaction.__enter__()
        self.table_patch = patch.object(storage, "TABLE", "pg_temp.mower_parameter_revision")
        self.table_patch.start()

        @contextmanager
        def db_conn(row_factory):
            with self.connection.transaction():
                yield self.connection

        def execute_sql(sql):
            self.connection.execute(sql.replace("hc.mower_parameter_revision", "pg_temp.mower_parameter_revision"))

        execute_sql(storage.SCHEMA_SQL)
        self.factory = lambda: storage.MowerParametersStore(db_conn, execute_sql)
        self.store = self.factory()
        self.service = MowerParametersService(self.store)

    def tearDown(self):
        self.table_patch.stop()
        self.transaction.__exit__(None, None, None)
        self.connection.close()

    def save(self, id_, expected, parameters):
        return self.service.save("test_sql_only", {"request_id": id_, "expected_revision": expected, "parameters": parameters})

    def test_real_sql_cas_replay_history_and_multiple_rovers(self):
        saved = self.save("save-1", 0, fixture())
        self.assertEqual(saved["draft_revision"], 1)
        self.service = MowerParametersService(self.factory())
        self.assertTrue(self.save("save-1", 0, fixture())["replayed"])
        self.save("save-2", 1, template())
        self.assertEqual([row["draft_revision"] for row in self.service.history("test_sql_only")["revisions"]], [2, 1])
        self.assertEqual(self.service.request_status("test_sql_only", "save-1")["parameters"], fixture())
        self.assertEqual(self.service.latest("test_sql_only")["draft_revision"], 2)
        self.assertEqual(self.service.revision("test_sql_only", 1)["parameters"], fixture())
        self.service.save("test_second", {"request_id": "save-1", "expected_revision": 0, "parameters": template()})
        self.assertEqual(len(self.service.list_drafts()["drafts"]), 2)

    def test_real_sql_conflicts_are_atomic_and_previous_version_survives(self):
        self.save("save-1", 0, fixture())
        for id_, expected, parameters, code in (("save-1", 0, template(), "ID_CONFLICT"),
                                               ("save-2", 0, template(), "REVISION_CONFLICT"),
                                               ("save-1", 1, fixture(), "ID_CONFLICT")):
            with self.assertRaises(DraftError) as error:
                self.save(id_, expected, parameters)
            self.assertEqual(error.exception.code, code)
        self.assertEqual(len(self.store.history("test_sql_only")), 1)
        self.assertEqual(self.store.latest("test_sql_only")["parameters"], fixture())

    def test_transaction_scoped_lock_blocks_other_connection_during_cas(self):
        self.save("save-1", 0, template())
        with psycopg.connect(os.environ["DATABASE_URL"]) as other:
            locked = other.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", ("hc.mower.parameters:test_sql_only",)).fetchone()[0]
            self.assertFalse(locked)


class MowerParametersMigrationTest(unittest.TestCase):
    def test_historical_fixture_matches_migration_exactly(self):
        migration = Path(__file__).resolve().parents[2] / "db/052_mower_parameter_drafts.sql"
        self.assertEqual(migration.read_text(), storage.SCHEMA_SQL)


if __name__ == "__main__":
    unittest.main()
