from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
import psycopg
from mower_firmware_routes import register_mower_firmware_routes
from mower_firmware_service import MowerFirmwareService, FirmwareError
from mower_firmware_staging import MowerFirmwareStaging
from mower_firmware_store import check_replay
from tests.mower_firmware_fixture import artifacts, envelope

ROOT = "/api/mower/v3/firmware"


class MemoryStore:
    def __init__(self):
        self.rows, self.files = {}, {}

    def request(self, id_): return deepcopy(self.rows.get(id_))
    def job(self, id_): return next((deepcopy(row) for row in self.rows.values() if row["hc_job_id"] == id_), None)
    def history(self): return list(self.rows.values())[-20:][::-1]

    def save(self, request_id, artifact_id, release_id, image, elf, report):
        if request_id in self.rows:
            row = self.rows[request_id]; check_replay(row, artifact_id, release_id); return deepcopy(row), True
        self.files.setdefault(artifact_id, (image, elf))
        row = {"hc_job_id": f"{len(self.rows)+1:032X}", "request_id": request_id, "artifact_id": artifact_id,
               "release_id": release_id, "state": "HC_STAGED", "report": deepcopy(report), "saved_at": datetime.now(timezone.utc)}
        self.rows[request_id] = row
        return deepcopy(row), False


class MowerFirmwareStagingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hc-firmware-staging-"); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "releases.json"
        self.image, self.elf, self.release = artifacts(); self.body = envelope(self.image, self.elf)
        self.path.write_text(json.dumps({"format":"HC_FIRMWARE_RELEASES_V1", "releases":[self.release]}))
        self.preflight = MowerFirmwareService(self.path); self.store = MemoryStore()
        self.service = MowerFirmwareStaging(self.preflight, self.store)
        self.auth = Mock(); self.auth.authenticated.return_value = True
        app = Flask(__name__); register_mower_firmware_routes(app, service=self.preflight, staging=self.service, auth=self.auth)
        self.client = app.test_client()

    def save(self, **headers):
        return self.client.post(ROOT+"/jobs", data=self.body, content_type="application/octet-stream", headers={
            "Origin":"http://localhost", "X-HC-Request-ID":"save-1", "X-HC-Release":self.release["release_id"], **headers})

    def test_verified_exact_files_retained_job_is_not_native_session(self):
        result = self.save(); self.assertEqual(result.status_code, 200, result.data)
        job = result.json
        self.assertTrue(job["persisted"]); self.assertEqual(job["scope"], "HC_LOCAL_STAGING")
        self.assertEqual(job["state"], "HC_STAGED"); self.assertIsNone(job["update_id"])
        for key in ("upload_available", "rover_contacted", "hardware_qualified"): self.assertFalse(job[key])
        self.assertEqual(self.store.files[job["artifact_id"]], (self.image, self.elf))
        for path in ("/jobs", "/jobs/"+job["hc_job_id"], "/jobs/requests/save-1"):
            response = self.client.get(ROOT+path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertNotIn("image", response.json); self.assertNotIn("elf", response.json)
        self.assertTrue(self.client.get(ROOT+"/jobs/requests/save-1").json["found"])
        self.assertFalse(self.client.get(ROOT+"/jobs/requests/unknown").json["found"])

    def test_durable_replay_is_historical_not_new_review_and_changed_content_conflicts(self):
        first = self.save().json
        self.path.write_text('{"format":"HC_FIRMWARE_RELEASES_V1","releases":[]}')
        with patch.object(self.preflight, "preflight", side_effect=AssertionError("Replay must not manufacture a new review")):
            replay = self.save().json
        self.assertTrue(replay["replayed"]); self.assertEqual(replay["hc_job_id"], first["hc_job_id"])
        self.assertNotIn("release_verified", replay)
        self.assertTrue(replay["release_verified_at_staging"])
        self.assertEqual(self.save(**{"X-HC-Request-ID":"new-save"}).json["code"], "RELEASE_NOT_APPROVED")
        self.assertEqual(self.save(**{"X-HC-Release":"changed-release"}).json["code"], "ID_CONFLICT")
        self.body += b"extra"
        self.assertEqual(self.save().json["code"], "ID_CONFLICT")
        self.assertEqual(len(self.store.rows), 1)

    def test_no_user_supplied_approval_or_unchecked_files_can_be_persisted(self):
        for release in ("", "missing", "../bad"):
            result = self.save(**{"X-HC-Release":release}); self.assertEqual(result.status_code, 400)
        self.body = self.body[:-1] + bytes([self.body[-1] ^ 1])
        self.assertEqual(self.save().status_code, 400)
        self.assertEqual(self.store.rows, {}); self.assertEqual(self.store.files, {})

    def test_origin_and_auth_reject_before_audit_or_storage_access(self):
        with patch.object(self.service, "stage") as stage, patch.object(self.service, "history") as read:
            for origin in ("", "https://evil.test"):
                self.assertEqual(self.save(Origin=origin).status_code, 403)
            self.auth.authenticated.return_value = False
            self.assertEqual(self.save().status_code, 401)
            for path in ("/jobs", "/jobs/requests/save-1", "/jobs/"+"1"*32):
                self.assertEqual(self.client.get(ROOT+path).status_code, 401)
            stage.assert_not_called(); read.assert_not_called()

    def test_bad_ids_and_missing_job_do_not_expose_blobs(self):
        for value in ("", "bad.token", "a"*65):
            self.assertEqual(self.save(**{"X-HC-Request-ID":value}).json["code"], "INVALID_REQUEST_ID")
        self.assertEqual(self.client.get(ROOT+"/jobs/requests/bad.token").status_code, 400)
        for id_ in ("0"*32, "a"*32, "x"):
            self.assertEqual(self.client.get(ROOT+"/jobs/"+id_).status_code, 400)
        self.assertEqual(self.client.get(ROOT+"/jobs/"+"1"*32).status_code, 404)

    def test_db_failure_is_unknown_sanitized_and_followed_only_by_lookup(self):
        with patch.object(self.store, "save", side_effect=psycopg.OperationalError("private credentials/body")):
            result = self.save()
        self.assertEqual(result.status_code, 503); self.assertEqual(result.json["code"], "SAVE_UNKNOWN")
        self.assertNotIn("private", result.get_data(as_text=True))
        self.assertFalse(self.client.get(ROOT+"/jobs/requests/save-1").json["found"])
        self.assertTrue(self.preflight.preflight_lock.acquire(blocking=False)); self.preflight.preflight_lock.release()

    def test_native_actions_and_approval_still_absent(self):
        for path in ("/upload", "/update", "/approve", "/jobs/"+"1"*32+"/create", "/abort", "/finish"):
            self.assertEqual(self.client.post(ROOT+path).status_code, 404)

    def test_lost_reply_after_retention_can_be_recovered_without_resubmitting_files(self):
        original = self.store.save

        def lost_after_save(*args):
            original(*args)
            raise psycopg.OperationalError("Synthetic lost commit reply")

        with patch.object(self.store, "save", side_effect=lost_after_save):
            self.assertEqual(self.save().json["code"], "SAVE_UNKNOWN")
        result = self.client.get(ROOT+"/jobs/requests/save-1")
        self.assertTrue(result.json["found"]); self.assertTrue(result.json["persisted"])
        self.assertEqual(result.json["state"], "HC_STAGED"); self.assertFalse(result.json["rover_contacted"])
        self.assertEqual(len(self.store.rows), 1); self.assertEqual(len(self.store.files), 1)


if __name__ == "__main__": unittest.main()
