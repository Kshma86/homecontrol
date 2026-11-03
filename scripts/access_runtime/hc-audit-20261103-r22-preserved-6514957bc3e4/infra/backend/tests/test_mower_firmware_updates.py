"""Native session coordinator tests. Synthetic peer only; no production app import."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
import psycopg
from mower_firmware_routes import register_mower_firmware_routes
from mower_firmware_service import FirmwareError, MowerFirmwareService
from mower_firmware_staging import MowerFirmwareStaging
from mower_firmware_updates import MowerFirmwareUpdates, validate_update
from mower_manual_service import ManualRelay
from mower_v3_service import MowerV3Service, RoverReadError, UnknownMutation
from tests.test_mower_firmware_staging import MemoryStore
from tests.mower_firmware_fixture import artifacts, envelope
from tests.test_mower_v3_service import Transport
from tests.test_mower_v3_commands import command, ack

JOB = "1234567890ABCDEF1234567890ABCDEF"
ROOT = "/api/mower/v3/firmware"


def status():
    return {"v":3,"update_id":None,"target":None,"locked":False,"phase":"IDLE","error":"NONE","detail":"NONE",
            "esp_boot":"0123456789ABCDEF","stm_service_boot":None,"source":"NONE","source_age_ms":None,"source_valid":False,
            "image_bytes":0,"http_received_bytes":0,"stm_written_bytes":0,"image_sha256":None,"fw_id":None,
            "confirmed_slot":None,"inactive_slot":None,"candidate_slot":None,"bootloader_fw":"loader-test",
            "last_phase_ms":10,"can_active":None,"outputs_inhibited":None,"stop_evidence":"UNKNOWN","stop_evidence_age_ms":None,
            "can_retry":False,"can_finish":False}


def ready():
    return {**status(), "update_id":JOB,"target":"STM","locked":True,"phase":"READY","stm_service_boot":"1122334455667788",
            "source":"STM_LOADER","source_valid":True,"source_age_ms":0,"can_active":False,"outputs_inhibited":True}


class MemorySessions:
    def __init__(self): self.rows = {}
    def request(self, id_): return deepcopy(self.rows.get(id_))
    def active(self): return next((deepcopy(row) for row in self.rows.values() if row["active"]), None)
    def reserve(self, id_, job_id, key, boot, profile, initial_stm_boot=None):
        if id_ in self.rows:
            row = self.rows[id_]
            if row["hc_job_id"] != job_id: raise FirmwareError("ID_CONFLICT", "Conflict", 409)
            return deepcopy(row), False
        if self.active(): raise FirmwareError("HC_UPDATE_PENDING", "Active", 409)
        row = {"request_id":id_,"hc_job_id":job_id,"connection_key":key,"esp_boot":boot,"profile_crc":profile,
               "state":"CREATE_INTENT","code":"SEND_INTENT","revision":1,"active":True,"update_id":None,
               "created_at":datetime.now(timezone.utc),"updated_at":datetime.now(timezone.utc)}
        row["initial_stm_boot"] = initial_stm_boot
        self.rows[id_] = row
        return deepcopy(row), True
    def complete(self, id_, state, code, update_id=None):
        row = self.rows[id_]
        if row["revision"] == 1: row.update(state=state,code=code,update_id=update_id,active=state!="REJECTED",revision=2)
        return deepcopy(row)


class UpdateTransport(Transport):
    def __init__(self, sessions):
        super().__init__(); self.identity["profile_crc"] = "AABBCCDD"
        self.sessions, self.progress, self.native_calls = sessions, status(), []
        self.create_reply, self.create_code, self.failure, self.read_failure = {"v":3,"update_id":JOB}, 202, None, None
        self.on_read = lambda: None
    def request(self, method, path, body=None):
        self.native_calls.append((method, path, deepcopy(body)))
        if method == "GET":
            if self.read_failure: raise self.read_failure
            if path.endswith("identity"): return 200, deepcopy(self.identity)
            self.on_read(); return 200, deepcopy(self.progress)
        if path == "/api/v3/stop": return 200, ack("stop", body["request_id"])
        row = self.sessions.request(body["request_id"])
        assert row and row["revision"] == 1 and row["active"], "Durable intent must precede native POST"
        if self.failure: raise self.failure
        if self.create_code == 202:
            self.progress = ready(); self.identity["update_locked"] = True
        return self.create_code, deepcopy(self.create_reply)


class MowerFirmwareUpdatesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hc-session-tests-"); self.addCleanup(self.temp.cleanup)
        self.image, self.elf, self.release = artifacts(); self.catalog = Path(self.temp.name) / "releases.json"
        self.catalog.write_text(json.dumps({"format":"HC_FIRMWARE_RELEASES_V1","releases":[self.release]}))
        self.preflight = MowerFirmwareService(self.catalog); self.artifacts = MemoryStore()
        self.artifacts.artifact = lambda id_: self.artifacts.files[id_]
        self.staging = MowerFirmwareStaging(self.preflight, self.artifacts)
        self.job = self.staging.stage(envelope(self.image, self.elf), "save-1", self.release["release_id"])
        self.sessions = MemorySessions(); self.transport = UpdateTransport(self.sessions); self.now = 100.0
        self.rover = MowerV3Service(transport=self.transport, clock=lambda:self.now)
        self.manual = SimpleNamespace(active=False)
        self.service = MowerFirmwareUpdates(rover=self.rover, preflight=self.preflight, staging=self.staging, sessions=self.sessions, manual=self.manual)
        self.auth = Mock(); self.auth.authenticated.return_value = True
        self.app = Flask(__name__); register_mower_firmware_routes(self.app, service=self.preflight, staging=self.staging, updates=self.service, auth=self.auth)
        self.client = self.app.test_client()

    def create(self, id_="native-1"):
        return self.service.create(self.job["hc_job_id"], {"request_id":id_,"confirm_runtime_discard":True})

    def post(self, body=None, origin="http://localhost"):
        return self.client.post(ROOT+"/jobs/"+self.job["hc_job_id"]+"/session", json=body or {"request_id":"native-1","confirm_runtime_discard":True}, headers={"Origin":origin})

    def test_exact_create_after_retained_review_and_current_identity_without_ordinary_state(self):
        self.transport.identity.update(compatible=False, stm_boot=None, conformant=False)
        result = self.create(); self.assertEqual(result["attempt"]["state"], "ADMITTED")
        self.assertEqual(self.transport.native_calls, [("GET","/api/v3/identity",None),("GET","/api/v3/update",None),
            ("POST","/api/v3/update",{"v":3,"request_id":"native-1","esp_boot":"0123456789ABCDEF","target":"STM"})])
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(result["attempt"]["update_id"], JOB); self.assertFalse(result["ready"])
        self.assertTrue(result["ordinary_blocked"]); self.assertFalse(result["upload_available"])

    def test_create_replay_never_resends_or_renews_stale_identity(self):
        first = self.create(); self.rover._configuration_error = "offline"
        replay = self.create()
        self.assertEqual(replay["attempt"], first["attempt"]); self.assertEqual(len(self.transport.native_calls), 3)
        with self.assertRaises(FirmwareError): self.create("new-request")

    def test_capability_profile_layout_capacity_slot_and_existing_lock_fail_before_reserve(self):
        for field, invalid in (("stm_remote_update",False),("update_service_abi",1),("update_service_abi",True),
                               ("stm_flash_layout","H743_2M_AB1"),("stm_image_max_bytes",786432),("profile_crc","00000000"),
                               ("profile_crc","11223344"),("stm_confirmed_slot","A"),("update_locked",True)):
            with self.subTest(field=field):
                original = deepcopy(self.transport.identity); self.transport.identity[field] = invalid
                with self.assertRaises(FirmwareError): self.create()
                self.transport.identity = original
                self.assertEqual(self.sessions.rows, {}); self.assertTrue(all(item[0]=="GET" for item in self.transport.native_calls))
        self.transport.progress = ready()
        with self.assertRaises(FirmwareError): self.create()

    def test_revoked_release_or_corrupted_retained_bytes_cannot_create(self):
        self.catalog.write_text('{"format":"HC_FIRMWARE_RELEASES_V1","releases":[]}')
        with self.assertRaises(FirmwareError): self.create()
        self.assertEqual(self.transport.native_calls, []); self.assertEqual(self.sessions.rows, {})
        self.catalog.write_text(json.dumps({"format":"HC_FIRMWARE_RELEASES_V1","releases":[self.release]}))
        self.artifacts.files[self.job["artifact_id"]] = (self.image, self.elf+b"extra")
        with self.assertRaises(FirmwareError) as error: self.create()
        self.assertEqual(error.exception.code, "ARTIFACT_CORRUPT")

    def test_busy_manual_and_cpu_audit_guards_are_pre_send_and_released(self):
        self.manual.active = True
        with self.assertRaises(FirmwareError) as error: self.create()
        self.assertEqual(error.exception.code, "MANUAL_ACTIVE"); self.manual.active = False
        self.rover.activity_lock.acquire()
        try:
            with self.assertRaises(FirmwareError): self.create()
        finally: self.rover.activity_lock.release()
        self.preflight.preflight_lock.acquire()
        try:
            with self.assertRaises(FirmwareError): self.create()
        finally: self.preflight.preflight_lock.release()
        self.assertEqual(self.transport.native_calls, []); self.assertFalse(self.rover.activity_lock.locked())

    def test_lost_or_malformed_admission_remains_unknown_and_never_adopts_current_job(self):
        for reply in ({"v":3},{"v":3,"update_id":"0"*32},{"v":3,"update_id":JOB,"request_id":"other"}):
            self.setUp(); self.transport.create_reply = reply
            result = self.create(); self.assertEqual(result["attempt"]["state"], "UNKNOWN")
            read = self.service.request_status("native-1")
            self.assertTrue(read["found"]); self.assertIsNone(read["attempt"]["update_id"])
            self.assertFalse(read["bound"]); self.assertFalse(read["ready"])
            self.assertEqual(read["connection"]["status"], "UNBOUND")
            self.create(); self.assertEqual(sum(call[0]=="POST" for call in self.transport.native_calls), 1)
        self.setUp(); self.transport.failure = UnknownMutation(); self.create()
        self.transport.progress = ready()
        self.assertFalse(self.service.current()["bound"])
        with self.assertRaises(FirmwareError): self.create("replacement")

    def test_only_retained_update_id_is_polled_and_reply_url_is_never_followed(self):
        self.transport.create_reply.update(progress_url="https://evil.test/?secret=stolen", credential="private")
        self.create(); read = self.service.current()
        self.assertTrue(read["bound"]); self.assertTrue(read["ready"])
        self.assertEqual(self.transport.native_calls[-1][1], "/api/v3/update/"+JOB)
        self.assertNotIn("evil", json.dumps(read)); self.assertNotIn("private", json.dumps(read))

    def test_age_transport_delay_null_and_trial_do_not_imply_fresh_ready_or_commit(self):
        self.create()
        for changes in ({"source_age_ms":2001},{"source_valid":False,"source_age_ms":None,"can_active":None,"outputs_inhibited":None},
                        {"source":"STM_TRIAL","phase":"COMPLETE"},{"phase":"TRIAL"},{"can_active":None},{"outputs_inhibited":None}):
            self.transport.progress = ready() | changes
            result = self.service.current()
            self.assertFalse(result["ready"]); self.assertFalse(result["installation_confirmed"])
        self.transport.progress = ready(); self.transport.on_read = lambda: setattr(self, "now", self.now+2.01)
        result = self.service.current(); self.assertFalse(result["freshness"]["fresh"])
        self.assertGreater(result["freshness"]["effective_age_ms"], 2000)

    def test_loader_complete_requires_exact_retained_image_and_never_unlocks_ordinary_control(self):
        self.create(); self.transport.progress = ready() | {"phase":"COMPLETE","image_bytes":len(self.image),
            "http_received_bytes":len(self.image),"stm_written_bytes":len(self.image),"image_sha256":self.release["image_sha256"],"fw_id":self.release["firmware_id"],"can_finish":True}
        result = self.service.current(); self.assertTrue(result["installation_confirmed"])
        self.assertTrue(result["ordinary_blocked"]); self.assertFalse(result["normal_mode_verified"]); self.assertFalse(result["finish_available"])
        self.transport.progress["image_sha256"] = "0"*64
        self.assertFalse(self.service.current()["installation_confirmed"])

    def test_reboot_endpoint_change_or_different_job_invalidates_binding_without_replay(self):
        self.create(); self.transport.progress["update_id"] = "F"*32
        result = self.service.current(); self.assertFalse(result["bound"]); self.assertFalse(result["ready"])
        self.assertTrue(result["ordinary_blocked"])
        self.transport.progress = ready()
        self.transport.identity["esp_boot"] = "1111111111111111"; self.transport.progress["esp_boot"] = "1111111111111111"
        result = self.service.current(); self.assertEqual(result["connection"]["status"], "BOOT_CHANGED"); self.assertFalse(result["ready"])
        self.rover.connection_key = "f"*64; before = len(self.transport.native_calls)
        result = self.service.current(); self.assertEqual(result["connection"]["status"], "ENDPOINT_CHANGED")
        self.assertEqual(len(self.transport.native_calls), before)
        self.assertEqual(sum(call[0]=="POST" for call in self.transport.native_calls), 1)

    def test_missing_retained_native_job_never_clears_intent_or_creates_replacement(self):
        self.create(); original = self.transport.request
        def missing(method, path, body=None):
            if path == "/api/v3/update/"+JOB:
                return 404, {"v":3,"code":"NOT_FOUND"}
            return original(method, path, body)
        with patch.object(self.transport, "request", side_effect=missing):
            result = self.service.current()
        self.assertEqual(result["connection"]["status"], "NOT_FOUND")
        self.assertFalse(result["bound"]); self.assertFalse(result["ready"])
        self.assertTrue(result["ordinary_blocked"]); self.assertTrue(self.sessions.active())
        self.create(); self.assertEqual(sum(call[0]=="POST" for call in self.transport.native_calls), 1)

    def test_last_moment_ordinary_post_guard_rechecks_durable_intent_and_activity_mutex(self):
        self.rover.activity_lock.acquire()
        try:
            with self.assertRaises(RoverReadError) as caught:
                self.rover.request("POST", "/api/v3/command", command())
            self.assertEqual(caught.exception.code, "BUSY")
        finally:
            self.rover.activity_lock.release()
        self.create(); before = len(self.transport.native_calls)
        with self.assertRaises(RoverReadError) as caught:
            self.rover.request("POST", "/api/v3/command", command())
        self.assertEqual(caught.exception.code, "HC_UPDATE_PENDING")
        self.assertEqual(len(self.transport.native_calls), before)

    def test_native_rejection_and_server_error_are_distinguished(self):
        self.transport.create_code = 409; self.transport.create_reply = {"v":3,"code":"STALE_SESSION"}
        result = self.create(); self.assertEqual(result["attempt"]["state"], "REJECTED"); self.assertFalse(self.sessions.active())
        self.transport.create_code = 503; self.transport.create_reply = {"v":3,"code":"NOT_READY"}
        result = self.create("next-explicit-request"); self.assertEqual(result["attempt"]["state"], "UNKNOWN"); self.assertTrue(result["ordinary_blocked"])

    def test_lost_intent_commit_never_sends_and_lost_result_commit_recovers_by_get(self):
        original = self.sessions.reserve
        def lost_intent(*args): original(*args); raise psycopg.OperationalError("private commit reply")
        with patch.object(self.sessions, "reserve", side_effect=lost_intent): self.assertEqual(self.post().status_code, 503)
        self.assertTrue(self.sessions.active()); self.assertTrue(all(call[0]=="GET" for call in self.transport.native_calls))
        self.create(); self.assertTrue(all(call[0]=="GET" for call in self.transport.native_calls))
        self.setUp(); original_complete = self.sessions.complete
        def lost_result(*args): original_complete(*args); raise psycopg.OperationalError("private committed reply")
        with patch.object(self.sessions, "complete", side_effect=lost_result):
            reply = self.post(); self.assertEqual(reply.status_code, 503); self.assertNotIn("private", reply.get_data(as_text=True))
            self.assertIsNone(reply.json["rover_contacted"])
            self.assertNotIn("mutation_sent", reply.json)
        self.assertTrue(self.service.request_status("native-1")["bound"])
        self.create(); self.assertEqual(sum(call[0]=="POST" for call in self.transport.native_calls), 1)

    def test_durable_guard_blocks_commands_snapshots_manual_but_not_stop(self):
        self.create(); result = self.rover.snapshot(); self.assertEqual(result["connection"]["status"], "HC_UPDATE_PENDING")
        self.assertIsNone(result["state"])
        self.assertEqual(self.rover.command_service().submit(command())[0]["result"], "REJECTED")
        browser = Mock(); upstream = Mock(); relay = ManualRelay(self.rover, connector=upstream)
        relay.run(browser, lambda:True); upstream.assert_not_called(); browser.close.assert_called_once()
        result, _ = self.rover.command_service().submit({"v":3,"request_id":"independent-stop"}, stop=True)
        self.assertEqual(result["result"], "APPLIED"); self.assertEqual(self.transport.native_calls[-1][1], "/api/v3/stop")

    def test_storage_outage_fails_closed_for_controls_but_not_stop(self):
        with patch.object(self.sessions, "active", side_effect=psycopg.OperationalError("private")):
            self.assertEqual(self.rover.snapshot()["connection"]["status"], "UPDATE_STORAGE_UNAVAILABLE")
            self.assertEqual(self.rover.command_service().submit(command())[0]["result"], "REJECTED")
            self.assertEqual(self.client.get(ROOT+"/session").status_code, 503)
            self.assertEqual(self.rover.command_service().submit({"v":3,"request_id":"stop"}, stop=True)[0]["result"], "APPLIED")

    def test_json_auth_origin_and_missing_confirmation_reject_before_native_access(self):
        for body in ({"request_id":"native-1","confirm_runtime_discard":False},{"request_id":"native-1","confirm_runtime_discard":1},
                     {"request_id":"native-1","confirm_runtime_discard":True,"target":"ESP"}):
            self.assertEqual(self.post(body).status_code, 400)
        for raw in ('{"request_id":"x","request_id":"y","confirm_runtime_discard":true}', "{}", "[1]", " "*1025):
            reply = self.client.post(ROOT+"/jobs/"+self.job["hc_job_id"]+"/session", data=raw, content_type="application/json", headers={"Origin":"http://localhost"})
            self.assertEqual(reply.status_code, 400)
        self.assertEqual(self.post(origin="https://evil.test").status_code, 403)
        self.auth.authenticated.return_value = False
        self.assertEqual(self.post().status_code, 401); self.assertEqual(self.client.get(ROOT+"/session").status_code, 401)
        self.assertEqual(self.transport.native_calls, [])

    def test_complete_status_schema_types_and_counter_limits_drop_private_extras(self):
        self.assertNotIn("credential", validate_update(ready() | {"credential":"private"}, 524288))
        for key, bad in (("source_age_ms",True),("source_valid",None),("phase","ACTIVATED"),("locked",1),("stm_service_boot","0"*16),
                         ("image_bytes",524289),("http_received_bytes",1),("can_active",0),("stop_evidence_age_ms",-1)):
            with self.subTest(key=key), self.assertRaises(RoverReadError): validate_update(ready() | {key:bad}, 524288)
        for key in ready():
            value = ready(); del value[key]
            with self.assertRaises(RoverReadError): validate_update(value, 524288)


if __name__ == "__main__": unittest.main()
