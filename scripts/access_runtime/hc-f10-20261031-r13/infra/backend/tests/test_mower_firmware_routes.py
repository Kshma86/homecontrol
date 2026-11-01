from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from mower_firmware_routes import register_mower_firmware_routes
from mower_firmware_service import BODY_LIMIT, MowerFirmwareService
from tests.mower_firmware_fixture import artifacts, envelope

ROOT = "/api/mower/v3/firmware"


class MowerFirmwareRoutesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hc-preflight-routes-"); self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "approved.json"
        path.write_text(json.dumps({"format":"HC_FIRMWARE_RELEASES_V1","releases":[]}))
        self.service = MowerFirmwareService(path)
        app = Flask(__name__); register_mower_firmware_routes(app, service=self.service)
        self.client = app.test_client(); self.image, self.elf, _ = artifacts()
        self.body = envelope(self.image, self.elf)

    def post(self, **kwargs):
        return self.client.post(ROOT + "/preflight", data=self.body, content_type="application/octet-stream", headers={"Origin":"http://localhost"}, **kwargs)

    def test_catalog_and_preflight_without_rover_or_auth_are_no_store(self):
        for response in (self.client.get(ROOT+"/releases"), self.post()):
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertFalse(response.json["upload_available"])
        self.assertFalse(self.post().json["rover_contacted"])

    def test_cross_origin_missing_origin_rejected_before_parsing(self):
        with patch.object(self.service, "preflight") as invoked:
            for origin in (None, "https://evil.test"):
                result = self.client.post(ROOT+"/preflight", data=self.body, content_type="application/octet-stream", headers={} if origin is None else {"Origin":origin})
                self.assertEqual(result.status_code, 403)
            invoked.assert_not_called()

    def test_bad_type_encoding_length_transfer_and_busy_are_rejected_before_audit(self):
        with patch.object(self.service, "preflight") as invoked:
            for headers in ({"Content-Type":"application/json"}, {"Content-Encoding":"gzip"}, {"Transfer-Encoding":"chunked"}):
                result = self.client.post(ROOT+"/preflight", data=self.body, headers={"Origin":"http://localhost","Content-Type":"application/octet-stream",**headers})
                self.assertIn(result.status_code, (400,413))
            self.assertEqual(self.post(environ_overrides={"CONTENT_LENGTH": str(BODY_LIMIT+1)}).status_code, 413)
            self.service.preflight_lock.acquire()
            try: self.assertEqual(self.post().status_code, 429)
            finally: self.service.preflight_lock.release()
            invoked.assert_not_called()

    def test_truncated_body_cannot_report_success_and_lock_is_released(self):
        self.assertEqual(self.post(environ_overrides={"wsgi.input":BytesIO(b"partial")}).status_code, 400)
        self.assertTrue(self.service.preflight_lock.acquire(blocking=False)); self.service.preflight_lock.release()

    def test_metadata_json_and_unknown_release_never_create_approval(self):
        for release in ("fabricated", "../bad"):
            response = self.client.post(ROOT+"/preflight", data=self.body, content_type="application/octet-stream", headers={"Origin":"http://localhost","X-HC-Release":release})
            self.assertEqual(response.status_code, 400)
        for path in ("/upload", "/update", "/activate", "/approve"):
            self.assertEqual(self.client.post(ROOT+path).status_code, 404)


if __name__ == "__main__": unittest.main()
