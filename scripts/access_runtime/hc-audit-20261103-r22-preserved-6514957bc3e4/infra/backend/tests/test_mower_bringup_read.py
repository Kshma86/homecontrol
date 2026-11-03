"""Captured handoff GET fixture, synthetic clocks/transports; never a real rover."""
import copy
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from mower_bringup_read import MowerBringupRead, BringupHttp, PATHS, register_mower_bringup_read
from mower_v3_service import MowerV3Service, RoverReadError, validate_state
from mower_v3_commands import MowerV3Commands
from mower_firmware_updates import MowerFirmwareUpdates, validate_update
from mower_firmware_service import FirmwareError

FIXTURE = json.loads((Path(__file__).parent / "fixtures/mower_hc_bringup_20261010.json").read_text())


class Transport:
    def __init__(self):
        self.bodies = {row["path"]: copy.deepcopy(row["body"]) for row in FIXTURE["responses"] if row["path"] in PATHS}
        self.calls = []
        self.failure = None

    def get(self, path):
        self.calls.append(path)
        if self.failure:
            raise self.failure
        return copy.deepcopy(self.bodies[path])


class BringupReadTest(unittest.TestCase):
    def setUp(self):
        self.transport, self.now = Transport(), 10.0
        self.reader = MowerBringupRead(transport=self.transport, clock=lambda: self.now)
        self.identity = self.transport.bodies["/api/v3/identity"]
        self.state = self.transport.bodies["/api/v3/state"]
        self.health = self.transport.bodies["/api/v3/health"]
        self.update = self.transport.bodies["/api/v3/update"]

    def test_real_fixture_native_state_is_read_despite_metadata_lock(self):
        result = self.reader.snapshot()
        self.assertEqual(result["connection"]["status"], "BRINGUP_CONNECTED")
        self.assertEqual(self.transport.calls, ["/api/v3/identity", "/api/v3/state", "/api/v3/update", "/api/v3/health"])
        self.assertTrue(result["freshness"]["fresh"])
        self.assertFalse(any(result["capabilities"].values()))
        self.assertFalse(result["hardware_qualified"])
        self.assertFalse(result["state"]["stopped"])
        self.assertIsNone(result["state"]["safety_installed_mask"])
        self.assertEqual(result["update"]["error"], "METADATA_ERROR")
        self.assertFalse(result["update"]["can_finish"])
        self.assertIsNone(result["health"]["task_service"]["gnss"])
        self.assertIsNone(result["health"]["can_tx_errors"])

    def test_no_operational_schema_relaxation_or_synthetic_update_session(self):
        with self.assertRaises(RoverReadError):
            validate_state(self.state, self.identity)
        with self.assertRaises(RoverReadError):
            validate_update(self.update, 0)
        operational = MowerV3Service(transport=self.transport, read_only=True).snapshot()
        self.assertEqual(operational["connection"]["status"], "UPDATE_MODE")
        self.assertFalse(any(operational["capabilities"].values()))

    def test_incompatible_mode_firmware_or_schema_never_reads_state(self):
        for patch in ({"mode": "UNKNOWN"}, {"mode": "FIRST_INSTALL_SERVICE"}, {"esp_fw": "esp-other"},
                      {"stm_fw": "stm-other"}, {"commissioned": True}, {"profile_crc": "00000001"},
                      {"stm_image_max_bytes": 524288}, {"esp_ota_enabled": True}, {"update_locked": False},
                      {"runtime_parameters": None}, {"update_service_abi": True}, {"v": True}):
            with self.subTest(patch=patch):
                self.setUp()
                self.identity.update(patch)
                result = self.reader.snapshot()
                self.assertIn(result["connection"]["status"], {"INVALID_RESPONSE", "INCOMPATIBLE_VERSION"})
                self.assertEqual(self.transport.calls, ["/api/v3/identity"])
                self.assertIsNone(result["state"])

    def test_boot_bindings_and_epoch_source_fields_are_required(self):
        for patch in ({"esp_boot": "1122334455667788"}, {"stm_boot": "1122334455667788"},
                      {"source_seq": 0}, {"source_seq": True}, {"source_age_ms": None},
                      {"control_epoch": 0}, {"state_seq": None}, {"fault_mask": 0},
                      {"safety_source_valid": True}, {"armed": True}, {"stopped": True},
                      {"store": "READY"}, {"mission_id": "00000000-0000-0000-0000-000000000001"}):
            with self.subTest(patch=patch):
                self.setUp()
                self.state.update(patch)
                result = self.reader.snapshot()
                self.assertEqual(result["connection"]["status"], "INVALID_RESPONSE")
                self.assertFalse(result["freshness"]["fresh"])

    def test_update_and_health_boot_must_match_and_never_advertise_unlock(self):
        for endpoint, patch in (("update", {"esp_boot": "1122334455667788"}), ("health", {"esp_boot": "1122334455667788"}),
                                ("update", {"can_finish": True}), ("update", {"phase": "IDLE"}),
                                ("health", {"rssi_dbm": True}), ("health", {"stm_busy_permille": 1001})):
            with self.subTest(endpoint=endpoint, patch=patch):
                self.setUp()
                self.transport.bodies["/api/v3/" + endpoint].update(patch)
                result = self.reader.snapshot()
                self.assertEqual(result["connection"]["status"], "INVALID_RESPONSE")
                self.assertIsNone(result["state"])

    def test_same_seq_cannot_rejuvenate_source_or_health(self):
        self.reader.snapshot()
        self.now += 1.4
        self.state["source_age_ms"] = 0
        self.state["published_ms"] += 1400
        result = self.reader.snapshot()
        self.assertFalse(result["freshness"]["fresh"])
        self.assertGreater(result["freshness"]["effective_age_ms"], 1500)
        self.now += 2
        self.health["network_source_age_ms"] = 0
        self.assertFalse(self.reader.snapshot()["health_freshness"]["fresh"])

    def test_changed_same_seq_or_regressing_epoch_cannot_be_fresh(self):
        self.reader.snapshot()
        self.state["state_seq"] += 1
        self.assertEqual(self.reader.snapshot()["connection"]["status"], "INVALID_RESPONSE")
        self.setUp()
        self.state["control_epoch"] = 2
        self.reader.snapshot()
        self.state["source_seq"] += 1
        self.state["control_epoch"] = 1
        self.assertEqual(self.reader.snapshot()["connection"]["status"], "INVALID_RESPONSE")

    def test_forward_sequence_wrap_old_sequence_and_new_boot(self):
        self.state["source_seq"] = 0xFFFFFFFF
        self.reader.snapshot()
        self.state["source_seq"] = 1
        self.assertTrue(self.reader.snapshot()["freshness"]["fresh"])
        self.state["source_seq"] = 0xFFFFFFFE
        self.assertFalse(self.reader.snapshot()["freshness"]["fresh"])
        self.identity["stm_boot"] = self.state["stm_boot"] = "1122334455667788"
        self.state["source_seq"] = 2
        self.assertTrue(self.reader.snapshot()["freshness"]["fresh"])

    def test_wait_for_health_ages_state(self):
        original = self.transport.get
        def slow(path):
            result = original(path)
            if path.endswith("health"):
                self.now += 1.5
            return result
        self.transport.get = slow
        result = self.reader.snapshot()
        self.assertFalse(result["freshness"]["fresh"])
        self.assertGreater(result["freshness"]["effective_age_ms"], 1500)

    def test_invalid_source_outage_auth_and_capacity_errors_never_infer_current(self):
        for code in ("UNREACHABLE", "AUTH_FAILED", "HTTP_ERROR"):
            self.transport.failure = RoverReadError(code, "Diagnosztikai lekérés sikertelen.")
            result = self.reader.snapshot()
            self.assertEqual(result["connection"]["status"], code)
            self.assertIsNone(result["state"])
        self.transport.failure = None
        self.state["source_valid"] = False
        self.assertFalse(self.reader.snapshot()["freshness"]["fresh"])
        self.state["source_valid"] = True
        self.state["source_age_ms"] = 1501
        self.assertFalse(self.reader.snapshot()["freshness"]["fresh"])

    def test_maintenance_lock_busy_and_missing_config_send_no_get(self):
        self.reader.guard = Mock(side_effect=RoverReadError("HC_UPDATE_PENDING", "Zárolva."))
        self.assertEqual(self.reader.snapshot()["connection"]["status"], "HC_UPDATE_PENDING")
        self.assertEqual(self.transport.calls, [])
        self.reader.lock.acquire()
        try:
            self.assertEqual(self.reader.snapshot()["connection"]["status"], "BUSY")
        finally:
            self.reader.lock.release()
        result = MowerBringupRead(origin="http://192.168.1.119").snapshot()
        self.assertEqual(result["connection"]["status"], "UNCONFIGURED")

    def test_no_private_remote_fields_in_browser_or_nested_diagnostics(self):
        for payload in self.transport.bodies.values():
            payload["api_token"] = "SYNTHETIC_SECRET"
        self.health["task_service"]["bridge"]["password"] = "SYNTHETIC_SECRET"
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(self.reader.snapshot()))

    def test_route_no_store_get_only(self):
        app = Flask(__name__)
        register_mower_bringup_read(app, service=self.reader)
        client = app.test_client()
        response = client.get("/api/mower/v3/bringup/snapshot")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.json["connection"]["status"], "BRINGUP_CONNECTED")
        self.transport.calls.clear()
        self.assertEqual(client.post("/api/mower/v3/bringup/snapshot").status_code, 405)
        self.assertEqual(self.transport.calls, [])

    def test_deployment_read_only_rejects_stop_and_all_native_writes_before_transport(self):
        rover = MowerV3Service(transport=self.transport, read_only=True)
        commands = MowerV3Commands(rover)
        for stop, body in ((True, {"v": 3, "request_id": "stop-1"}), (False, {})):
            result, code = commands.submit(body, stop=stop)
            self.assertEqual((code, result["code"]), (403, "READ_ONLY"))
        for call in (lambda: rover.request("POST", "/api/v3/stop", {}), rover.manual_socket,
                     lambda: rover.update_mutation("IMAGE", "test")):
            with self.assertRaises(RoverReadError) as error:
                call()
            self.assertEqual(error.exception.code, "READ_ONLY")
        self.assertEqual(self.transport.calls, [])

    def test_read_only_firmware_denied_before_db_reservation_or_preflight(self):
        rover = MowerV3Service(transport=self.transport, read_only=True)
        updates = MowerFirmwareUpdates(rover=rover, preflight=None, staging=None, sessions=None, manual=None)
        for call in (lambda: updates.create("test", {}), lambda: updates.action("test", "IMAGE", {}),
                     lambda: updates.action("test", "ABORT", {}), lambda: updates.action("test", "FINISH", {})):
            with self.assertRaises(FirmwareError) as error:
                call()
            self.assertEqual(error.exception.code, "READ_ONLY")
        self.assertEqual(self.transport.calls, [])


class BringupTransportTest(unittest.TestCase):
    def test_exact_get_allowlist_and_no_write_or_socket(self):
        transport = BringupHttp("http://192.168.1.119", "ab" * 32)
        for path in ("/api/v3/profile", "/api/v3/parameters", "/api/v3/mission", "/api/v3/service/status", "https://evil.test/"):
            with self.assertRaises(ValueError):
                transport.get(path)
        for call in (lambda: transport.request("GET", "/api/v3/state"), transport.manual_socket,
                     lambda: transport.update_mutation("IMAGE", "test")):
            with self.assertRaises(ValueError):
                call()

    def test_auth_503_501_redirect_errors_strip_remote_message(self):
        for status, expected in ((401, "AUTH_FAILED"), (503, "HTTP_ERROR"), (501, "HTTP_ERROR"), (302, "REDIRECT_BLOCKED")):
            transport = BringupHttp("http://192.168.1.119", "ab" * 32)
            transport._opener = Mock()
            transport._opener.open.side_effect = HTTPError("http://rover", status, "secret", {}, io.BytesIO(b'{"token":"secret"}'))
            with self.assertRaises(RoverReadError) as error:
                transport.get("/api/v3/identity")
            self.assertEqual(error.exception.code, expected)
            self.assertNotIn("secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()
