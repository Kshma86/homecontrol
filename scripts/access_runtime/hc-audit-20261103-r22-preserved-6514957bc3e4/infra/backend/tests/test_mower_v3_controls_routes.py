import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from werkzeug.security import generate_password_hash
from mower_operator_auth import MowerOperatorAuth
from mower_v3_routes import register_mower_v3_controls
from mower_v3_service import MowerV3Service
from tests.test_mower_v3_commands import CommandTransport, ack


class MowerV3ControlsRoutesTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.transport = CommandTransport()
        self.rover = MowerV3Service(transport=self.transport)
        self.auth = MowerOperatorAuth(password_hash=generate_password_hash("test-only", method="pbkdf2:sha256:1000"), secret="ab" * 32)
        register_mower_v3_controls(self.app, rover=self.rover, auth=self.auth, relay=None)
        self.client = self.app.test_client()
        self.origin = {"Origin": "http://localhost"}

    def login(self):
        return self.client.post("/api/mower/v3/operator/login", json={"password": "test-only"}, headers=self.origin)

    def test_mutation_requires_operator_and_same_origin_before_rover_contact(self):
        for path in ("command", "stop"):
            self.assertEqual(self.client.post("/api/mower/v3/" + path, json={}, headers=self.origin).status_code, 401)
            self.assertEqual(self.client.post("/api/mower/v3/" + path, json={}).status_code, 403)
        self.assertEqual(self.transport.calls + self.transport.mutations, [])

    def test_login_cookie_flags_status_and_logout_revoke_access(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        cookie = response.headers["Set-Cookie"]
        for required in ("HttpOnly", "SameSite=Strict", "Path=/api/mower/v3", "Max-Age=3600"):
            self.assertIn(required, cookie)
        status = self.client.get("/api/mower/v3/operator")
        self.assertTrue(status.json["authenticated"])
        self.assertEqual(status.headers["Cache-Control"], "no-store")
        self.client.post("/api/mower/v3/operator/logout", headers=self.origin)
        self.assertFalse(self.client.get("/api/mower/v3/operator").json["authenticated"])
        self.assertEqual(self.client.get("/api/mower/v3/command/test").status_code, 401)

    def test_https_origin_sets_secure_cookie_behind_proxy(self):
        response = self.client.post("/api/mower/v3/operator/login", json={"password": "test-only"}, headers={"Origin": "https://localhost"})
        self.assertIn("Secure", response.headers["Set-Cookie"])

    def test_strict_json_rejects_duplicate_nonfinite_array_and_oversize(self):
        self.login()
        for raw in ('{"v":3,"v":3}', '{"v":NaN}', "[]", "x" * 1025):
            with self.subTest(raw=raw):
                response = self.client.post("/api/mower/v3/stop", data=raw, content_type="application/json", headers=self.origin)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.transport.mutations, [])

    def test_authenticated_stop_uses_only_v3_and_result_is_not_cached_by_browser(self):
        self.login()
        self.transport.responses = [(200, ack("stop", "stop-1"))]
        result = self.client.post("/api/mower/v3/stop", json={"v": 3, "request_id": "stop-1"}, headers=self.origin)
        self.assertEqual(result.json["result"], "APPLIED")
        status = self.client.get("/api/mower/v3/command/stop-1")
        self.assertEqual(status.headers["Cache-Control"], "no-store")
        self.assertEqual(len(self.transport.mutations), 1)
        self.assertEqual(self.transport.calls, [])

    def test_cross_origin_remains_rejected_after_login(self):
        self.login()
        response = self.client.post("/api/mower/v3/stop", json={"v": 3, "request_id": "stop-1"}, headers={"Origin": "https://evil.test"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.transport.mutations, [])

    def test_authenticated_read_only_stop_and_command_do_not_contact_rover(self):
        self.rover.read_only = True
        self.login()
        for path in ("stop", "command"):
            response = self.client.post("/api/mower/v3/" + path, json={"v": 3, "request_id": "read-only-1"}, headers=self.origin)
            self.assertEqual((response.status_code, response.json["code"]), (403, "READ_ONLY"))
        self.assertEqual(self.transport.calls + self.transport.mutations, [])

    def test_read_only_manual_is_denied_before_websocket_upgrade(self):
        self.rover.read_only = True
        self.login()
        cookie = self.client.get_cookie("hc_mower_operator", path="/api/mower/v3")
        with self.app.test_request_context("/api/mower/v3/manual", headers={**self.origin,
                "Cookie": "hc_mower_operator=" + cookie.value}):
            response, code = self.app.view_functions["mower_v3_manual"]()
            self.assertEqual((code, response.json["code"]), (403, "READ_ONLY"))
        self.assertEqual(self.transport.calls + self.transport.mutations, [])


if __name__ == "__main__":
    unittest.main()
