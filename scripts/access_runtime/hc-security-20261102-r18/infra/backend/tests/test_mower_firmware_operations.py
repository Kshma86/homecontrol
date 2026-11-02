"""Synthetic native peer only. No production app/device access."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from mower_firmware_service import FirmwareError
from mower_v3_service import UnknownMutation
from tests import test_mower_firmware_updates as fixtures
from tests.test_mower_firmware_updates import ready, status, ROOT


class MemoryOperations:
    def __init__(self, sessions): self.sessions, self.rows, self.exits = sessions, {}, {}
    def ensure_schema(self): pass
    def history(self, parent): return [deepcopy(row) for row in self.rows.values() if row["session_request_id"] == parent]
    def request(self, id_): return deepcopy(self.rows.get(id_))
    def exit_request(self, id_): return deepcopy(self.exits.get(id_))
    def reserve(self, id_, parent, action, boot):
        if id_ in self.rows: return self.request(id_), False
        if any(row["action"] == action for row in self.history(parent)): raise FirmwareError("ACTION_RECORDED", "Recorded", 409)
        now = datetime.now(timezone.utc)
        row = {"request_id":id_,"session_request_id":parent,"action":action,"state":"INTENT","code":"SEND_INTENT",
               "service_boot":boot,"created_at":now,"updated_at":now}
        self.rows[id_] = row
        return deepcopy(row), True
    def complete(self, id_, state, code):
        row = self.rows[id_]
        if row["state"] == "INTENT": row.update(state=state,code=code)
        return deepcopy(row)
    def close(self, id_, parent, proof, check=None):
        if check: check()
        row = {"request_id":id_,"session_request_id":parent,"proof":proof,"created_at":datetime.now(timezone.utc)}
        self.exits[id_] = row
        self.sessions.rows[parent].update(active=False,closed=True)
        return deepcopy(row)


class FirmwareOperationsTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.MowerFirmwareUpdatesTest(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.operations = MemoryOperations(self.f.sessions); self.f.service.operations = self.operations
        self.calls = []; self.native_failure = None; self.native_status = 202; self.native_reply = {"v":3}
        def mutation(action, id_, image, metadata):
            assert self.operations.history("native-1")[-1]["state"] == "INTENT"
            self.calls.append((action,id_,image,deepcopy(metadata)))
            if self.native_failure: raise self.native_failure
            return self.native_status, self.native_reply
        self.f.transport.update_mutation = mutation
        original = self.f.transport.request
        def request(method, path, body=None):
            if path == "/api/v3/state": return 200, deepcopy(self.f.transport.state)
            return original(method,path,body)
        self.f.transport.request = request
        self.f.create()

    def action(self, name, id_=None):
        return self.f.service.action("native-1",name,{"request_id":id_ or name.lower()+"-1"})

    def terminal(self, phase="COMPLETE"):
        self.f.transport.progress = ready() | {"phase":phase,"can_finish":True}

    def ordinary(self):
        self.f.transport.progress = status()
        self.f.transport.identity.update(update_locked=False,stm_boot="9988776655443322")
        self.f.transport.state.update(stm_boot="9988776655443322",control_epoch=1)

    def test_exact_image_only_after_current_review_and_durable_intent(self):
        self.assertTrue(self.f.service.current()["upload_available"])
        result = self.action("IMAGE")
        self.assertEqual(result["operation"]["state"],"ADMITTED")
        self.assertEqual(self.calls[0][2],self.f.image)
        self.assertEqual(self.calls[0][3]["image_sha256"],self.f.release["image_sha256"])
        self.assertNotIn(self.f.elf,self.calls[0][2])
        self.assertFalse(self.f.service.current()["upload_available"])
        self.assertTrue(self.f.sessions.active())

    def test_replay_offline_and_other_id_never_repeat_image(self):
        self.action("IMAGE"); self.f.transport.read_failure = UnknownMutation()
        self.action("IMAGE")
        with self.assertRaises(FirmwareError): self.action("IMAGE","different")
        self.assertEqual(len(self.calls),1)

    def test_lost_malformed_replies_are_durable_unknown_and_get_only(self):
        self.native_failure = UnknownMutation()
        result = self.action("IMAGE"); self.assertEqual(result["operation"]["state"],"UNKNOWN")
        self.assertEqual(self.f.service.action_status("image-1")["operation"]["state"],"UNKNOWN")
        self.action("IMAGE"); self.assertEqual(len(self.calls),1)

    def test_wrong_admission_id_is_unknown_not_a_new_binding(self):
        self.native_reply = {"v":3,"update_id":"F"*32}
        self.assertEqual(self.action("IMAGE")["operation"]["state"],"UNKNOWN")

    def test_revoked_catalog_and_corrupt_bytes_cannot_send_image(self):
        self.f.catalog.write_text(json.dumps({"format":"HC_FIRMWARE_RELEASES_V1","releases":[]}))
        with self.assertRaises(FirmwareError): self.action("IMAGE")
        self.assertFalse(self.calls); self.assertFalse(self.operations.rows)

    def test_stale_trial_can_unknown_and_existing_body_block_image(self):
        for changes in ({"source_age_ms":2001},{"source":"STM_TRIAL"},{"phase":"TRIAL"},{"outputs_inhibited":None},{"can_active":True},
                        {"image_bytes":len(self.f.image),"image_sha256":self.f.release["image_sha256"],"fw_id":self.f.release["firmware_id"]}):
            self.f.transport.progress = ready() | changes
            with self.assertRaises(FirmwareError): self.action("IMAGE")
        self.assertFalse(self.calls); self.assertFalse(self.operations.rows)

    def test_proof_cannot_gain_age_while_database_reserves_intent(self):
        original = self.operations.reserve
        def delayed(*args):
            result = original(*args); self.f.now += 2.01; return result
        with patch.object(self.operations,"reserve",side_effect=delayed):
            self.assertEqual(self.action("IMAGE")["operation"]["code"],"PROOF_EXPIRED")
        self.assertFalse(self.calls)

    def test_abort_has_empty_body_never_finishes_or_claims_rollback(self):
        result = self.action("ABORT"); self.assertEqual(result["operation"]["state"],"ADMITTED")
        self.assertEqual(self.calls[0][0],"ABORT"); self.assertIsNone(self.calls[0][2]); self.assertIsNone(self.calls[0][3])
        self.assertTrue(self.f.sessions.active()); self.assertFalse(self.f.service.current()["normal_mode_verified"])
        self.terminal("ABORTED"); self.assertTrue(self.f.service.current()["finish_available"])

    def test_finish_requires_native_permission_and_terminal_fresh_loader(self):
        for changes in ({"phase":"READY","can_finish":True},{"phase":"COMPLETE","can_finish":False},
                        {"phase":"COMPLETE","can_finish":True,"source":"STM_TRIAL"},{"phase":"COMPLETE","can_finish":True,"source_age_ms":2001}):
            self.f.transport.progress = ready() | changes
            with self.assertRaises(FirmwareError): self.action("FINISH")
        self.assertFalse(self.calls)
        self.terminal(); self.action("FINISH"); self.assertTrue(self.f.sessions.active())
        self.ordinary(); self.f.service.current(); self.assertTrue(self.f.sessions.active())

    def test_verified_exit_is_explicit_hc_only_new_boot_empty_and_durable(self):
        self.terminal(); self.action("FINISH"); self.ordinary()
        previous = object(); self.f.rover.commands = previous
        result = self.action("VERIFY_EXIT")
        self.assertEqual(result["exit"]["proof"]["store"],"EMPTY")
        self.assertFalse(self.f.sessions.active()); self.assertIsNone(self.f.rover.commands)
        self.assertEqual([call[0] for call in self.calls],["FINISH"])
        self.f.transport.read_failure = UnknownMutation()
        self.assertEqual(self.action("VERIFY_EXIT"),result)

    def test_exit_allows_physical_input_fault_but_not_other_faults(self):
        self.terminal(); self.action("FINISH"); self.ordinary()
        self.f.transport.state.update(state="FAULT",fault_mask=1,safety_active_mask=1,reason="FAULT",stopped=False)
        self.assertEqual(self.action("VERIFY_EXIT")["exit"]["proof"]["state"],"FAULT")

    def test_exit_rejects_old_boot_stale_armed_mission_and_nonphysical_fault(self):
        self.terminal(); self.action("FINISH"); self.ordinary(); baseline = deepcopy(self.f.transport.state)
        for changes in ({"source_age_ms":1501},{"store":"READY"},{"segment_count":1},{"manual_lease_id":1},
                        {"state":"IDLE","armed":True},{"state":"FAULT","fault_mask":8,"safety_active_mask":8,"reason":"IMU_TILT"},
                        {"stm_boot":"FEDCBA9876543210"},{"stm_boot":"1122334455667788"}):
            self.f.transport.state = baseline | changes
            self.f.transport.identity["stm_boot"] = self.f.transport.state["stm_boot"]
            with self.assertRaises(FirmwareError): self.action("VERIFY_EXIT")
            self.assertTrue(self.f.sessions.active())

    def test_unsolicited_idle_never_unlocks_without_finish_intent(self):
        self.ordinary()
        with self.assertRaises(FirmwareError): self.action("VERIFY_EXIT")
        self.assertTrue(self.f.sessions.active())

    def test_database_wait_cannot_renew_normal_exit_source_proof(self):
        self.terminal(); self.action("FINISH"); self.ordinary()
        original = self.operations.close
        def delayed(*args, **kwargs):
            self.f.now += 1.6
            return original(*args, **kwargs)
        with patch.object(self.operations,"close",side_effect=delayed):
            with self.assertRaises(FirmwareError) as error: self.action("VERIFY_EXIT")
        self.assertEqual(error.exception.code,"PROOF_EXPIRED")
        self.assertTrue(self.f.sessions.active()); self.assertFalse(self.operations.exits)

    def test_lost_database_result_stays_unknown_and_lookup_recovers(self):
        original = self.operations.complete
        def lost(*args): original(*args); raise psycopg.OperationalError("private")
        path = ROOT+"/sessions/requests/native-1/image"
        with patch.object(self.operations,"complete",side_effect=lost):
            reply = self.f.client.post(path,json={"request_id":"image-1"},headers={"Origin":"http://localhost"})
        self.assertEqual(reply.status_code,503); self.assertIsNone(reply.json["rover_contacted"])
        self.assertEqual(self.f.service.action_status("image-1")["operation"]["state"],"ADMITTED")
        self.action("IMAGE"); self.assertEqual(len(self.calls),1)

    def test_auth_origin_exact_json_guard_all_actions(self):
        for name in ("image","abort","finish","verify-exit"):
            path = ROOT+"/sessions/requests/native-1/"+name
            self.assertEqual(self.f.client.post(path,json={"request_id":"x"},headers={"Origin":"http://evil.test"}).status_code,403)
            self.assertEqual(self.f.client.post(path,json={"request_id":"x","override":True},headers={"Origin":"http://localhost"}).status_code,400)
        self.f.auth.authenticated.return_value=False
        self.assertEqual(self.f.client.get(ROOT+"/operations/requests/x").status_code,401)
        self.assertFalse(self.calls)


if __name__ == "__main__": unittest.main()
