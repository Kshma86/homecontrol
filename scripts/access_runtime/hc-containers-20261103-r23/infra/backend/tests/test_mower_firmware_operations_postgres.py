"""Real PostgreSQL schema/action/exit checks, pg_temp and force rollback only."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
import mower_firmware_operations_store as module
from mower_firmware_service import FirmwareError
from tests import test_mower_firmware_sessions_postgres as fixtures


class OperationsMigrationTest(unittest.TestCase):
    def test_migration_matches_historical_fixture(self):
        self.assertEqual(module.SCHEMA_SQL,(Path(__file__).resolve().parents[2]/"db/055_mower_firmware_operations.sql").read_text())


@unittest.skipUnless(os.environ.get("MOWER_TEST_POSTGRES")=="1","Opt-in pg_temp / rollback only")
class OperationsPostgresTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.MowerFirmwareSessionsPostgresTest(); self.f.setUp(); self.addCleanup(self.f.tearDown)
        for attr, value in (("TABLE","pg_temp.mower_firmware_operation"),("EXIT_TABLE","pg_temp.mower_firmware_exit"),
                            ("SESSION_TABLE","pg_temp.mower_firmware_session"),("LOCK_KEY","hc.mower.firmware.native-session:test-only")):
            p=patch.object(module,attr,value);p.start();self.addCleanup(p.stop)
        self.f.store.execute_sql(module.SCHEMA_SQL)
        self.factory=lambda:module.MowerFirmwareOperationsStore(self.f.store.db_conn,self.f.store.execute_sql,self.f.store)
        self.store=self.factory();self.store.ensure_schema()
        self.f.reserve();self.f.store.complete("native-1","ADMITTED","ADMITTED","C"*32)

    def reserve(self,action="IMAGE",id_="image-1"):
        return self.store.reserve(id_,"native-1",action,"1122334455667788")

    def test_durable_intent_restart_cas_replay_and_one_send_per_action(self):
        row,send=self.reserve();self.assertTrue(send);self.assertEqual(row["state"],"INTENT")
        self.store=self.factory();self.assertFalse(self.reserve()[1])
        self.store.complete("image-1","UNKNOWN","REPLY_LOST")
        self.assertEqual(self.store.complete("image-1","ADMITTED","ADMITTED")["state"],"UNKNOWN")
        with self.assertRaises(FirmwareError):self.reserve(id_="another")
        with self.assertRaises(FirmwareError):self.reserve("FINISH","image-1")
        self.assertTrue(self.f.store.active())

    def test_exit_is_atomic_persisted_and_replay_cannot_close_other_session(self):
        self.reserve("FINISH","finish-1");self.store.complete("finish-1","UNKNOWN","REPLY_LOST")
        proof={"stm_boot":"9988776655443322","store":"EMPTY"}
        with self.assertRaises(FirmwareError):self.store.close("finish-1","native-1",proof)
        result=self.store.close("exit-1","native-1",proof)
        self.assertFalse(self.f.store.active());self.assertTrue(self.f.store.request("native-1")["closed"])
        self.store=self.factory();self.assertEqual(self.store.close("exit-1","native-1",{}),result)
        with self.assertRaises(FirmwareError):self.store.close("exit-1","other",proof)
        self.assertTrue(self.f.reserve("next-explicit")[1])

    def test_no_finish_or_rejected_finish_cannot_close_and_unique_constraints_hold(self):
        with self.assertRaises(FirmwareError):self.store.close("exit-1","native-1",{})
        self.reserve("FINISH","finish-1");self.store.complete("finish-1","REJECTED","NOT_READY")
        with self.assertRaises(FirmwareError):self.store.close("exit-1","native-1",{})
        with self.assertRaises(psycopg.errors.UniqueViolation), self.f.connection.transaction():
            self.f.connection.execute("INSERT INTO pg_temp.mower_firmware_operation(request_id,session_request_id,action,state,code,service_boot) VALUES ('bypass','native-1','FINISH','INTENT','SEND_INTENT','1122334455667788')")
        self.assertTrue(self.f.store.active())


if __name__ == "__main__":unittest.main()
