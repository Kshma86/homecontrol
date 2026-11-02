import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from mower_service_read import MowerServiceRead, ServiceHttp, validate_status, register_mower_service_read
from mower_v3_service import RoverReadError
from settings import BackendSettings, load_rover_api_token
from tests.test_mower_parameters import fixture
import rover_parameters as rcp1


def status():
    return {"v": 3, "mode": "FIRST_INSTALL_SERVICE", "service_abi": 1,
            "esp_firmware": "esp-service-20261010-lan2", "stm_firmware": "service-20261010",
            "stm_connected": True, "stm_uid": "004C00333131511431333732", "stm_source_age_ms": 100,
            "can_parked": True, "disarmed": True, "outputs_inhibited": True, "motion_permitted": False,
            "commissioned": False, "applied": False, "esp_ota_enabled": False, "stm_remote_update_enabled": False,
            "storage": "EMPTY", "revision": 0, "code": "EMPTY", "parameters_crc": None,
            "stm_parameters_crc": None, "ip": "192.168.1.119", "ap_ip": "192.168.4.1", "free_heap": 200000,
            "wifi_connected": True, "wifi_configured": True, "setup_ap_active": False,
            "hostname": "rover-test", "mdns_ready": True, "wifi_storage": "SAVED", "parameters": None}


class Transport:
    def __init__(self):
        self.status = status()
        self.readback = status()
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        return copy.deepcopy(self.readback if path.endswith("parameters") else self.status)


class ServiceReadTest(unittest.TestCase):
    def setUp(self):
        self.transport = Transport()
        self.now = 10.0
        self.service = MowerServiceRead(transport=self.transport, clock=lambda: self.now)

    def test_get_only_service_pair_and_no_operational_or_legacy_evidence(self):
        result = self.service.snapshot()
        self.assertEqual(self.transport.calls, ["/api/v3/service/status", "/api/v3/service/parameters"])
        self.assertEqual(result["connection"]["status"], "SERVICE_CONNECTED")
        self.assertTrue(result["freshness"]["fresh"])
        self.assertTrue(result["read_only"])
        self.assertNotIn("identity", result)
        self.assertNotIn("state", result)
        self.assertNotIn("capabilities", result)
        self.assertFalse(result["service"]["motion_permitted"])

    def test_missing_credentials_never_contacts_rover(self):
        result = MowerServiceRead(origin="http://192.168.1.119").snapshot()
        self.assertFalse(result["configured"])
        self.assertTrue(result["configuration"]["origin_configured"])
        self.assertFalse(result["configuration"]["token_configured"])
        self.assertIsNone(result["service"])

    def test_unknown_peer_and_stale_source_are_not_current_stm(self):
        for payload in (dict(stm_source_age_ms=3001), dict(stm_connected=False, stm_uid=None,
                          stm_firmware=None, can_parked=False, stm_source_age_ms=None)):
            self.transport.status.update(payload)
            self.transport.readback.update(payload)
            result = self.service.snapshot()
            self.assertEqual(result["connection"]["status"], "STM_UNAVAILABLE")
            self.assertFalse(result["freshness"]["fresh"])

    def test_transit_and_first_request_wait_age_the_evidence(self):
        original = self.transport.get
        def slow(path):
            reply = original(path)
            self.now += 2
            return reply
        self.transport.get = slow
        result = self.service.snapshot()
        self.assertFalse(result["freshness"]["fresh"])
        self.assertGreaterEqual(result["freshness"]["effective_age_ms"], 4100)

    def test_uid_or_firmware_change_between_gets_rejects_pair(self):
        self.transport.readback["stm_uid"] = "1" * 24
        result = self.service.snapshot()
        self.assertEqual(result["connection"]["status"], "INVALID_RESPONSE")
        self.assertIsNone(result["service"])

    def test_unknown_response_keys_and_credentials_are_not_forwarded(self):
        self.transport.readback.update(api_token="A" * 64, password="hidden", unknown={"token": "secret"})
        result = self.service.snapshot()
        self.assertNotIn("hidden", json.dumps(result))
        self.assertNotIn("secret", json.dumps(result))
        self.assertNotIn("A" * 64, json.dumps(result))

    def test_wrong_mode_types_missing_flags_and_enabled_capabilities_fail_closed(self):
        for key, value in (("v", True), ("service_abi", True), ("mode", "NORMAL"),
                           ("motion_permitted", True), ("applied", None), ("commissioned", 0),
                           ("stm_remote_update_enabled", True), ("esp_ota_enabled", True),
                           ("can_parked", 1), ("revision", True), ("stm_source_age_ms", 1.0),
                           ("stm_uid", "0" * 24), ("ip", "invalid"), ("code", ["EMPTY"]),
                           ("wifi_connected", "true")):
            with self.subTest(key=key):
                payload = status(); payload[key] = value
                with self.assertRaises(RoverReadError): validate_status(payload)
        payload = status(); del payload["outputs_inhibited"]
        with self.assertRaises(RoverReadError): validate_status(payload)

    def test_saved_parameters_are_readback_not_applied_and_crc_must_match(self):
        parameters = fixture()
        self.transport.readback.update(storage="STAGED", revision=1, code="STAGED_NOT_APPLIED",
            parameters=parameters, parameters_crc=f"{rcp1.checksum(parameters):08X}")
        result = self.service.snapshot()
        self.assertEqual(result["parameters"], parameters)
        self.assertFalse(result["service"]["applied"])
        self.transport.readback["parameters_crc"] = "00000000"
        self.assertEqual(self.service.snapshot()["connection"]["status"], "INVALID_RESPONSE")
        self.transport.readback["parameters"] = {}
        self.assertEqual(self.service.snapshot()["connection"]["status"], "INVALID_RESPONSE")

    def test_shared_activity_lock_and_maintenance_guard_prevent_reads(self):
        lock = threading.Lock()
        service = MowerServiceRead(transport=self.transport, activity_lock=lock)
        lock.acquire()
        try:
            self.assertEqual(service.snapshot()["connection"]["status"], "BUSY")
        finally:
            lock.release()
        def blocked(): raise RoverReadError("HC_UPDATE_PENDING", "Frissítési zárolás.")
        service.guard = blocked
        self.assertEqual(service.snapshot()["connection"]["status"], "HC_UPDATE_PENDING")
        self.assertEqual(self.transport.calls, [])

    def test_route_is_uncached_read_only(self):
        app = Flask(__name__)
        register_mower_service_read(app, service=self.service)
        client = app.test_client()
        response = client.get("/api/mower/v3/service/snapshot")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(client.post("/api/mower/v3/service/snapshot").status_code, 405)
        self.assertEqual(client.post("/api/mower/v3/service/parameters").status_code, 404)


class ServiceHttpTest(unittest.TestCase):
    def setUp(self):
        self.token = "A" * 64
        self.http = ServiceHttp("http://192.168.1.119", self.token)
        self.calls = []

    def opener(self, raw=None, error=None):
        outer = self
        class Response(io.BytesIO):
            status = 200
        class Opener:
            def open(self, request, timeout):
                outer.calls.append((request, timeout))
                if error: raise error
                return Response(raw)
        self.http._opener = Opener()

    def test_fixed_authenticated_get_paths_and_three_second_timeout(self):
        self.opener(b'{"v":3}')
        for path in ("/api/v3/service/status", "/api/v3/service/parameters"):
            self.http.get(path)
            request, timeout = self.calls[-1]
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.get_header("Authorization"), "Bearer " + self.token)
            self.assertEqual(timeout, 3)
            self.assertNotIn(self.token, request.full_url)
        for path in ("/api/v3/identity", "/api/v3/command", "/api/v3/service/status?token=x"):
            with self.assertRaises(ValueError): self.http.get(path)
        with self.assertRaises(ValueError): self.http.request("POST", "/api/v3/service/parameters", {})
        with self.assertRaises(ValueError): self.http.update_mutation("FINISH", "C" * 32)
        with self.assertRaises(ValueError): self.http.manual_socket()

    def test_error_mapping_no_redirect_no_retry_and_no_remote_secret_echo(self):
        for http_code, body, code in ((401, b"secret", "AUTH_FAILED"), (302, b"secret", "REDIRECT_BLOCKED"),
                                     (404, b'{"code":"SETUP_ONLY"}', "SETUP_ONLY"),
                                     (404, b'{"code":"SERVICE_ONLY"}', "SERVICE_ONLY"),
                                     (404, b'{"code":[]}', "HTTP_ERROR")):
            self.opener(error=HTTPError("http://192.168.1.119", http_code, self.token, {}, io.BytesIO(body)))
            count = len(self.calls)
            with self.assertRaises(RoverReadError) as raised: self.http.get("/api/v3/service/status")
            self.assertEqual(raised.exception.code, code)
            self.assertNotIn(self.token, str(raised.exception))
            self.assertEqual(len(self.calls), count + 1)
        self.opener(error=URLError(self.token))
        with self.assertRaises(RoverReadError) as raised: self.http.get("/api/v3/service/status")
        self.assertEqual(raised.exception.code, "UNREACHABLE")

    def test_oversized_duplicate_nonfinite_and_nonobject_json_reject(self):
        for raw in (b" " * 8193, b'{"v":3,"v":3}', b'{"v":3,"x":NaN}', b"[]"):
            self.opener(raw)
            with self.assertRaises(RoverReadError): self.http.get("/api/v3/service/status")


class TokenFileTest(unittest.TestCase):
    def test_private_access_file_load_and_secret_safe_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "access.json"
            with path.open("w") as stream: json.dump({"api_token": "A" * 64}, stream)
            with patch.dict(os.environ, {"ROVER_API_TOKEN": "", "ROVER_API_TOKEN_FILE": str(path)}):
                self.assertEqual(load_rover_api_token(), "A" * 64)
                self.assertNotIn("A" * 64, repr(BackendSettings()))
                self.assertNotIn(str(path), repr(BackendSettings()))
            with patch.dict(os.environ, {"ROVER_API_TOKEN": "B" * 64, "ROVER_API_TOKEN_FILE": str(path)}):
                self.assertEqual(load_rover_api_token(), "")
            for text in ('{"api_token":"bad"}', '[]', '{"api_token":"a","api_token":"b"}', " " * 4097):
                with path.open("w") as stream: stream.write(text)
                with patch.dict(os.environ, {"ROVER_API_TOKEN": "", "ROVER_API_TOKEN_FILE": str(path)}):
                    self.assertEqual(load_rover_api_token(), "")
            with patch.dict(os.environ, {"ROVER_API_TOKEN": "", "ROVER_API_TOKEN_FILE": str(path) + ".missing"}):
                self.assertEqual(load_rover_api_token(), "")


if __name__ == "__main__":
    unittest.main()
