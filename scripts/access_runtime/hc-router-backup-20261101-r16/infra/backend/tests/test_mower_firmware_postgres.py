"""Opt-in SQL verification: only pg_temp tables inside force-rollback transactions."""
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg.rows import dict_row
import mower_firmware_store as storage
from mower_firmware_service import FirmwareError
from tests.mower_firmware_fixture import artifacts


class MowerFirmwareMigrationTest(unittest.TestCase):
    def test_historical_schema_matches_migration(self):
        self.assertEqual(storage.SCHEMA_SQL, (Path(__file__).resolve().parents[2] / "db/053_mower_firmware_staging.sql").read_text())


@unittest.skipUnless(os.environ.get("MOWER_TEST_POSTGRES") == "1", "Opt in with MOWER_TEST_POSTGRES=1; pg_temp/rollback only")
class MowerFirmwarePostgresTest(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
        self.transaction = self.connection.transaction(force_rollback=True); self.transaction.__enter__()
        self.patches = [patch.object(storage, "ARTIFACT_TABLE", "pg_temp.mower_firmware_artifact"),
                        patch.object(storage, "JOB_TABLE", "pg_temp.mower_firmware_job"),
                        patch.object(storage, "LOCK_KEY", "hc.mower.firmware.staging:test-only")]
        for item in self.patches: item.start()

        @contextmanager
        def db_conn(row_factory):
            with self.connection.transaction(): yield self.connection

        def execute_sql(sql):
            self.connection.execute(sql.replace("hc.mower_firmware_", "pg_temp.mower_firmware_"))

        execute_sql(storage.SCHEMA_SQL)
        self.factory = lambda: storage.MowerFirmwareStore(db_conn, execute_sql)
        self.store = self.factory(); self.image, self.elf, _ = artifacts()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.transaction.__exit__(None, None, None); self.connection.close()

    def save(self, id_="save-1", artifact_id="a"*64, release_id="reviewed"):
        return self.store.save(id_, artifact_id, release_id, self.image, self.elf, {"metadata":{"fw_id":"synthetic-test-only"}})

    def test_exact_blobs_dedup_restart_replay_and_bounded_history(self):
        row, replayed = self.save(); self.assertFalse(replayed)
        self.store = self.factory(); replay, replayed = self.save()
        self.assertTrue(replayed); self.assertEqual(replay["hc_job_id"], row["hc_job_id"])
        for index in range(24): self.save(f"save-{index+2}")
        self.assertEqual(len(self.store.history()), 20)
        self.assertEqual(self.store.job(row["hc_job_id"])["request_id"], "save-1")
        retained = self.connection.execute("SELECT image, elf FROM pg_temp.mower_firmware_artifact").fetchall()
        self.assertEqual(len(retained), 1)
        self.assertEqual(bytes(retained[0]["image"]), self.image); self.assertEqual(bytes(retained[0]["elf"]), self.elf)

    def test_replay_conflicts_are_atomic(self):
        self.save()
        for artifact_id, release_id in (("b"*64, "reviewed"), ("a"*64, "different")):
            with self.assertRaises(FirmwareError) as error: self.save(artifact_id=artifact_id, release_id=release_id)
            self.assertEqual(error.exception.code, "ID_CONFLICT")
        self.assertEqual(len(self.store.history()), 1)
        self.assertEqual(self.connection.execute("SELECT count(*) AS n FROM pg_temp.mower_firmware_artifact").fetchone()["n"], 1)

    def test_quota_checks_allow_replay_and_blob_dedup_but_not_new_artifact(self):
        self.save()
        with patch.object(storage, "MAX_ARTIFACTS", 1), patch.object(storage, "MAX_BYTES", len(self.image)+len(self.elf)):
            self.save("save-2")
            with self.assertRaises(FirmwareError) as error: self.save("save-3", "b"*64)
            self.assertEqual(error.exception.code, "STORAGE_QUOTA")
        with patch.object(storage, "MAX_JOBS", 2):
            self.assertTrue(self.save()[1])
            with self.assertRaises(FirmwareError): self.save("save-3")
        with patch.object(storage, "MAX_ARTIFACTS", 2), patch.object(storage, "MAX_BYTES", len(self.image)+len(self.elf)):
            with self.assertRaises(FirmwareError) as error: self.save("save-3", "b"*64)
            self.assertEqual(error.exception.code, "STORAGE_QUOTA")
        self.assertEqual(len(self.store.history()), 2)

    def test_global_quota_lock_blocks_other_connection_and_invalid_job_rolls_back_blob(self):
        self.save()
        with psycopg.connect(os.environ["DATABASE_URL"]) as other:
            result = other.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", (storage.LOCK_KEY,)).fetchone()
            self.assertFalse(result[0])
        with self.assertRaises(psycopg.errors.CheckViolation): self.save("bad.id", "b"*64)
        self.assertEqual(self.connection.execute("SELECT count(*) AS n FROM pg_temp.mower_firmware_artifact").fetchone()["n"], 1)


if __name__ == "__main__": unittest.main()
