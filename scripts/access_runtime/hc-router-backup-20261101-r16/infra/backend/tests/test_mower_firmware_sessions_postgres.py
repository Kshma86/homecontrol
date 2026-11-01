"""Real SQL, pg_temp-only in force-rollback transactions; no live rover access."""
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg.rows import dict_row
import mower_firmware_store as staging_sql
import mower_firmware_sessions_store as sessions_sql
from mower_firmware_service import FirmwareError
from tests.mower_firmware_fixture import artifacts


class MowerFirmwareSessionsMigrationTest(unittest.TestCase):
    def test_historical_schema_matches_migration(self):
        self.assertEqual(sessions_sql.SCHEMA_SQL, (Path(__file__).resolve().parents[2] / "db/054_mower_firmware_sessions.sql").read_text())


@unittest.skipUnless(os.environ.get("MOWER_TEST_POSTGRES") == "1", "MOWER_TEST_POSTGRES=1; pg_temp / rollback only")
class MowerFirmwareSessionsPostgresTest(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
        self.transaction = self.connection.transaction(force_rollback=True); self.transaction.__enter__()
        self.patches = [patch.object(staging_sql, "ARTIFACT_TABLE", "pg_temp.mower_firmware_artifact"),
            patch.object(staging_sql, "JOB_TABLE", "pg_temp.mower_firmware_job"),
            patch.object(staging_sql, "LOCK_KEY", "hc.mower.firmware.staging:session-test"),
            patch.object(sessions_sql, "TABLE", "pg_temp.mower_firmware_session"),
            patch.object(sessions_sql, "LOCK_KEY", "hc.mower.firmware.native-session:test-only")]
        for item in self.patches: item.start()

        @contextmanager
        def db_conn(row_factory):
            with self.connection.transaction(): yield self.connection

        def execute_sql(sql):
            self.connection.execute(sql.replace("hc.mower_firmware_", "pg_temp.mower_firmware_"))

        execute_sql(staging_sql.SCHEMA_SQL)
        execute_sql(sessions_sql.SCHEMA_SQL)
        self.staging = staging_sql.MowerFirmwareStore(db_conn, execute_sql)
        image, elf, _ = artifacts()
        self.job = self.staging.save("local-1", "a"*64, "reviewed", image, elf, {})[0]
        self.factory = lambda: sessions_sql.MowerFirmwareSessionsStore(db_conn, execute_sql, self.staging)
        self.store = self.factory()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.transaction.__exit__(None, None, None); self.connection.close()

    def reserve(self, id_="native-1", job_id=None):
        return self.store.reserve(id_, job_id or self.job["hc_job_id"], "b"*64, "0123456789ABCDEF", "AABBCCDD")

    def test_intent_restart_replay_unknown_and_compare_and_set_never_resend(self):
        row, send = self.reserve(); self.assertTrue(send); self.assertEqual(row["state"], "CREATE_INTENT")
        self.store = self.factory(); replay, send = self.reserve(); self.assertFalse(send); self.assertEqual(replay, row)
        row = self.store.complete("native-1", "UNKNOWN", "REPLY_LOST")
        self.assertEqual(row["revision"], 2); self.assertTrue(row["active"])
        self.assertEqual(self.store.complete("native-1", "ADMITTED", "ADMITTED", "C"*32)["state"], "UNKNOWN")
        self.assertFalse(self.reserve()[1]); self.assertEqual(self.store.active()["request_id"], "native-1")

    def test_conflicts_and_single_active_admission_are_atomic(self):
        self.reserve()
        with self.assertRaises(FirmwareError) as error: self.reserve(job_id="D"*32)
        self.assertEqual(error.exception.code, "ID_CONFLICT")
        with self.assertRaises(FirmwareError) as error: self.reserve("native-2")
        self.assertEqual(error.exception.code, "HC_UPDATE_PENDING")
        self.assertEqual(self.connection.execute("SELECT count(*) AS n FROM pg_temp.mower_firmware_session").fetchone()["n"], 1)

    def test_admitted_id_is_durable_and_only_explicit_rejected_request_allows_new_intent(self):
        self.reserve(); self.store.complete("native-1", "REJECTED", "STALE_SESSION")
        self.assertIsNone(self.store.active()); self.reserve("native-2")
        row = self.store.complete("native-2", "ADMITTED", "ADMITTED", "C"*32)
        self.store = self.factory()
        self.assertEqual(self.store.request("native-2")["update_id"], "C"*32)
        self.assertEqual(self.store.active(), row)
        self.assertEqual(self.store.request("native-1")["state"], "REJECTED")

    def test_unique_index_and_constraints_cannot_make_a_second_active_or_unbound_admitted_row(self):
        row, _ = self.reserve()
        sql = "INSERT INTO pg_temp.mower_firmware_session (request_id,hc_job_id,connection_key,esp_boot,profile_crc,state,code,revision,active) VALUES (%s,%s,%s,%s,%s,'CREATE_INTENT','SEND_INTENT',1,true)"
        with self.assertRaises(psycopg.errors.UniqueViolation), self.connection.transaction():
            self.connection.execute(sql, ("bypass", row["hc_job_id"], "b"*64, row["esp_boot"], row["profile_crc"]))
        with self.assertRaises(psycopg.errors.CheckViolation): self.store.complete("native-1", "ADMITTED", "ADMITTED")
        self.assertEqual(self.store.active()["state"], "CREATE_INTENT")

    def test_transaction_lock_excludes_other_admission_connection(self):
        self.reserve()
        with psycopg.connect(os.environ["DATABASE_URL"]) as other:
            result = other.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", (sessions_sql.LOCK_KEY,)).fetchone()
            self.assertFalse(result[0])


if __name__ == "__main__": unittest.main()
