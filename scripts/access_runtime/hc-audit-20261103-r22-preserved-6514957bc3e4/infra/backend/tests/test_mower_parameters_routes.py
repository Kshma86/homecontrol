import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
import psycopg
from mower_operator_auth import COOKIE_NAME, MowerOperatorAuth
from mower_parameters_routes import register_mower_parameter_routes
from mower_parameters_service import MowerParametersService, template
from tests.test_mower_parameters import MemoryStore, fixture
from werkzeug.security import generate_password_hash

ROOT = "/api/mower/v3/parameters"


class MowerParametersRoutesTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.service = MowerParametersService(self.store)
        self.auth = MowerOperatorAuth(password_hash=generate_password_hash("test-only", method="pbkdf2:sha256:1000"), secret="ab" * 32)
        app = Flask(__name__)
        register_mower_parameter_routes(app, service=self.service, auth=self.auth)
        self.client = app.test_client()
        self.origin = {"Origin": "http://localhost"}

    def login(self):
        self.client.set_cookie(COOKIE_NAME, self.auth.login("test-only")[0], path="/api/mower/v3")

    def save(self, parameters=None):
        return self.client.post(ROOT + "/drafts/hc-test", json={"request_id": "save-1", "expected_revision": 0,
                   "parameters": template() if parameters is None else parameters}, headers=self.origin)

    def test_schema_template_and_validation_available_without_rover_or_login(self):
        response = self.client.get(ROOT + "/schema")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertFalse(response.json["apply_available"])
        report = self.client.post(ROOT + "/validate", json=template(), headers=self.origin)
        self.assertTrue(report.json["validation"]["saveable"])
        self.assertFalse(report.json["validation"]["valid"])
        self.assertEqual(self.store.rows, [])

    def test_save_requires_operator_before_any_durable_change(self):
        self.assertEqual(self.save().status_code, 401)
        self.assertEqual(self.store.rows, [])
        self.login()
        self.assertEqual(self.save().status_code, 200)
        self.assertEqual(len(self.store.rows), 1)

    def test_cross_origin_validation_import_and_save_rejected(self):
        self.login()
        for path in ("/validate", "/import", "/drafts/hc-test"):
            for headers in ({}, {"Origin": "https://evil.test"}):
                self.assertEqual(self.client.post(ROOT + path, json=template(), headers=headers).status_code, 403)
        self.assertEqual(self.store.rows, [])

    def test_hardware_flags_duplicate_keys_nonfinite_and_array_reject(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', "[]", "x" * 16385):
            self.assertEqual(self.client.post(ROOT + "/validate", data=raw, content_type="application/json", headers=self.origin).status_code, 400)
        response = self.client.post(ROOT + "/validate", json=fixture() | {"commissioned": True}, headers=self.origin)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.store.rows, [])

    def test_import_and_json_export_never_imply_live_apply(self):
        result = self.client.post(ROOT + "/import", data=json.dumps(fixture()), content_type="application/json", headers=self.origin)
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json["saved"])
        self.assertFalse(result.json["apply_available"])
        self.login(); self.save(fixture())
        exported = self.client.get(ROOT + "/drafts/hc-test/revisions/1/export.rcp1")
        self.assertEqual(len(exported.data), 256)
        self.assertIn("hc-test-hc-r1.rcp1", exported.headers["Content-Disposition"])
        self.assertEqual(exported.headers["X-HC-Parameter-Source"], "HC_DRAFT_NOT_APPLIED")
        imported = self.client.post(ROOT + "/import", data=exported.data, content_type="application/octet-stream", headers=self.origin)
        self.assertEqual(imported.json["parameters"], fixture())
        self.assertEqual(len(self.store.rows), 1)

    def test_incomplete_binary_export_conflict_and_unknown_request(self):
        self.login(); self.save()
        exported = self.client.get(ROOT + "/drafts/hc-test/revisions/1/export.rcp1")
        self.assertEqual(exported.status_code, 409)
        self.assertEqual(exported.json["code"], "DRAFT_INCOMPLETE")
        self.assertEqual(self.client.get(ROOT + "/drafts/hc-test/requests/unknown").status_code, 404)
        self.assertEqual(self.client.get(ROOT + "/drafts/hc-test/requests/save-1").json["draft_revision"], 1)

    def test_database_errors_sanitize_and_lost_write_is_unknown(self):
        self.login()
        with patch.object(self.store, "save", side_effect=psycopg.OperationalError("private connection details")):
            result = self.save()
        self.assertEqual((result.status_code, result.json["code"]), (503, "SAVE_UNKNOWN"))
        self.assertNotIn(b"private", result.data)
        with patch.object(self.store, "latest", side_effect=psycopg.OperationalError("private connection details")):
            result = self.client.get(ROOT + "/drafts/hc-test")
        self.assertEqual((result.status_code, result.json["code"]), (503, "STORAGE_UNAVAILABLE"))

    def test_no_apply_route_exists_and_invalid_revision_format_cannot_export(self):
        self.assertEqual(self.client.post(ROOT + "/apply", json={}).status_code, 404)
        self.assertEqual(self.client.get(ROOT + "/drafts/hc-test/revisions/0/export.rcp1").status_code, 400)
        self.assertEqual(self.client.get(ROOT + "/drafts/hc-test/revisions/1/export.bin").status_code, 400)


if __name__ == "__main__":
    unittest.main()
