import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask, request
from werkzeug.security import generate_password_hash
from mower_operator_auth import COOKIE_NAME, MowerOperatorAuth, same_origin


class MowerOperatorAuthTest(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.auth = MowerOperatorAuth(password_hash=generate_password_hash("test-password", method="pbkdf2:sha256:1000"),
                                      secret="A" * 64, clock=lambda: self.now)
        self.app = Flask(__name__)

    def test_unconfigured_and_bad_password_never_authorize(self):
        self.assertFalse(MowerOperatorAuth().available)
        self.assertEqual(self.auth.login("wrong")[2], 401)
        with self.app.test_request_context():
            self.assertFalse(self.auth.authenticated(request))

    def test_cookie_session_expires_and_logout_revokes_existing_copy(self):
        cookie, _, status = self.auth.login("test-password")
        self.assertEqual(status, 200)
        headers = {"Cookie": f"{COOKIE_NAME}={cookie}"}
        with self.app.test_request_context(headers=headers):
            self.assertTrue(self.auth.authenticated(request))
            self.auth.logout(request)
            self.assertFalse(self.auth.authenticated(request))
        cookie, _, _ = self.auth.login("test-password")
        self.now += 3601
        with self.app.test_request_context(headers={"Cookie": f"{COOKIE_NAME}={cookie}"}):
            self.assertFalse(self.auth.authenticated(request))

    def test_five_attempt_limit_and_later_retry(self):
        for _ in range(5):
            self.assertEqual(self.auth.login("wrong")[2], 401)
        self.assertEqual(self.auth.login("test-password")[2], 429)
        self.now += 61
        self.assertEqual(self.auth.login("test-password")[2], 200)

    def test_cross_origin_missing_origin_and_userinfo_are_rejected(self):
        for origin in ("", "http://evil.local", "null", "http://user@hc.local", "http://hc.local/path"):
            with self.app.test_request_context(base_url="http://hc.local", headers={"Origin": origin}):
                self.assertFalse(same_origin(request))
        with self.app.test_request_context(base_url="http://hc.local", headers={"Origin": "http://hc.local"}):
            self.assertTrue(same_origin(request))


if __name__ == "__main__":
    unittest.main()
