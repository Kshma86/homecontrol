import copy
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mower_v3_service import MowerV3Service, RoverHttp, RoverReadError


def identity():
    return {
        "v": 3, "contract": "3.1.0", "esp_boot": "0123456789ABCDEF",
        "stm_boot": "FEDCBA9876543210", "esp_fw": "esp-test", "stm_fw": "stm-test",
        "profile_crc": "ABCDEF01", "compatible": True, "conformant": False,
        "max_mission_bytes": 131072, "max_segments": 4096,
        "manual_protocol": "homecontrol.mower.manual.v3", "stm_remote_update": True,
        "update_service_abi": 2, "stm_bootloader_fw": "loader-test",
        "stm_flash_layout": "H743_1M_QSPI2", "stm_image_max_bytes": 524288,
        "stm_confirmed_slot": None, "stm_inactive_slot": None,
        "stm_reset_recovery": True, "update_locked": False, "esp_ota_max_bytes": 1048576,
        "runtime_parameters": False,
    }


def state():
    return {
        "v": 3, "esp_boot": "0123456789ABCDEF", "stm_boot": "FEDCBA9876543210",
        "published_ms": 500, "source_seq": 15, "source_age_ms": 10, "source_valid": True,
        "state_seq": 14, "control_epoch": 3, "event_seq": 2, "state": "DISARMED",
        "phase": "NONE", "armed": False, "store": "EMPTY", "mission_id": None,
        "revision": None, "crc32": None, "segment_index": 0, "segment_count": 0,
        "outcome": "NONE", "reason": "NONE", "fault_mask": 0, "stopped": True,
        "ready_for_start": False, "ready_for_resume": False,
        "manual_lease_id": None, "manual_input_seq": None,
        "safety_installed_mask": 7, "safety_active_mask": 0,
    }


class Transport:
    def __init__(self):
        self.identity, self.state = identity(), state()
        self.calls = []
        self.failure = None

    def get(self, path):
        self.calls.append(path)
        if self.failure:
            raise self.failure
        return copy.deepcopy(self.identity if path.endswith("identity") else self.state)


class MowerV3ServiceTest(unittest.TestCase):
    def setUp(self):
        self.transport = Transport()
        self.now = 100.0
        self.service = MowerV3Service(transport=self.transport, clock=lambda: self.now)

    def test_unconfigured_never_connects_and_never_claims_stopped(self):
        result = MowerV3Service().snapshot()
        self.assertEqual(result["connection"]["status"], "UNCONFIGURED")
        self.assertIsNone(result["state"])
        self.assertFalse(result["freshness"]["fresh"])

    def test_reads_v3_only_and_keeps_conformance_distinct_from_freshness(self):
        result = self.service.snapshot()
        self.assertEqual(self.transport.calls, ["/api/v3/identity", "/api/v3/state"])
        self.assertEqual(result["connection"]["status"], "LIVE")
        self.assertFalse(result["identity"]["conformant"])
        self.assertTrue(result["read_only"])
        self.assertTrue(result["capabilities"]["stm_update"])
        self.assertFalse(result["capabilities"]["runtime_parameters"])

    def test_republished_same_sequence_cannot_renew_freshness(self):
        self.service.snapshot()
        self.now += 1.6
        self.transport.state["published_ms"] += 1600
        self.transport.state["source_age_ms"] = 0
        result = self.service.snapshot()
        self.assertFalse(result["freshness"]["fresh"])
        self.assertGreater(result["freshness"]["effective_age_ms"], 1500)

    def test_new_source_sequence_can_refresh(self):
        self.service.snapshot()
        self.now += 2
        self.transport.state["source_seq"] += 1
        self.assertTrue(self.service.snapshot()["freshness"]["fresh"])

    def test_transport_time_counts_towards_source_age(self):
        original = self.transport.get
        def slow_get(path):
            response = original(path)
            if path.endswith("state"):
                self.now += 2
            return response
        self.transport.get = slow_get
        self.assertFalse(self.service.snapshot()["freshness"]["fresh"])

    def test_older_source_sequence_is_not_live(self):
        self.service.snapshot()
        self.transport.state["source_seq"] -= 1
        self.assertFalse(self.service.snapshot()["freshness"]["fresh"])

    def test_sequence_wrap_accepts_new_sample(self):
        self.transport.state["source_seq"] = 0xFFFFFFFF
        self.service.snapshot()
        self.transport.state["source_seq"] = 1
        self.assertTrue(self.service.snapshot()["freshness"]["fresh"])

    def test_identity_state_boot_mismatch_rejects_snapshot(self):
        self.transport.state["stm_boot"] = "123456789ABCDEF0"
        result = self.service.snapshot()
        self.assertEqual(result["connection"]["status"], "INVALID_RESPONSE")
        self.assertIsNone(result["state"])

    def test_new_boot_clears_old_freshness(self):
        self.service.snapshot()
        self.now += 3
        self.transport.identity["stm_boot"] = "123456789ABCDEF0"
        self.transport.state["stm_boot"] = "123456789ABCDEF0"
        self.transport.state["source_seq"] = 1
        self.assertTrue(self.service.snapshot()["freshness"]["fresh"])

    def test_missing_null_and_wrong_types_fail_closed(self):
        for key, invalid in (("source_age_ms", None), ("source_seq", True), ("source_age_ms", 1.0),
                             ("stopped", None), ("state", "ARMED"), ("source_valid", "true")):
            with self.subTest(key=key, invalid=invalid):
                self.transport.state = state()
                self.transport.state[key] = invalid
                result = self.service.snapshot()
                self.assertIsNone(result["state"])
                self.assertFalse(result["freshness"]["fresh"])
        self.transport.state = state()
        del self.transport.state["source_age_ms"]
        self.assertIsNone(self.service.snapshot()["state"])

    def test_unknown_stm_is_not_disarmed(self):
        self.transport.identity["stm_boot"] = None
        self.transport.identity["compatible"] = False
        self.transport.state.update(stm_boot=None, source_valid=False, source_age_ms=None,
                                    state=None, state_seq=None, control_epoch=None, stopped=None)
        result = self.service.snapshot()
        self.assertFalse(result["freshness"]["fresh"])
        self.assertIsNone(result["state"]["state"])
        self.assertIsNone(result["state"]["stopped"])

    def test_update_mode_does_not_query_ordinary_state(self):
        self.transport.identity["update_locked"] = True
        result = self.service.snapshot()
        self.assertEqual(self.transport.calls, ["/api/v3/identity"])
        self.assertEqual(result["connection"]["status"], "UPDATE_MODE")
        self.assertIsNone(result["state"])

    def test_capability_missing_false_or_unknown_layout_never_enables_updater(self):
        for updates in ({"stm_remote_update": False}, {"update_service_abi": 3},
                        {"stm_image_max_bytes": 786432}, {"stm_confirmed_slot": "A"},
                        {"profile_crc": "00000000"}):
            with self.subTest(updates=updates):
                self.transport.identity = {**identity(), **updates}
                self.assertFalse(self.service.snapshot()["capabilities"]["stm_update"])
        del self.transport.identity["stm_remote_update"]
        self.assertIsNone(self.service.snapshot()["identity"])

    def test_optional_runtime_capability_absence_is_unavailable(self):
        del self.transport.identity["runtime_parameters"]
        self.assertFalse(self.service.snapshot()["capabilities"]["runtime_parameters"])

    def test_incompatible_contract_does_not_use_state_or_legacy(self):
        self.transport.identity["contract"] = "2.4.0"
        self.assertEqual(self.service.snapshot()["connection"]["status"], "INCOMPATIBLE_VERSION")
        self.assertEqual(self.transport.calls, ["/api/v3/identity"])

    def test_failure_clears_browser_state_and_unknown_extra_fields_are_removed(self):
        self.transport.identity["api_token"] = "secret"
        self.transport.state["api_token"] = "secret"
        self.assertNotIn("secret", json.dumps(self.service.snapshot()))
        self.transport.failure = RoverReadError("AUTH_FAILED", "Hitelesítési hiba")
        result = self.service.snapshot()
        self.assertIsNone(result["state"])
        self.assertIsNone(result["identity"])

    def test_a_reflected_64_hex_token_in_identity_text_is_never_returned(self):
        token = "A" * 64
        for key in ("esp_fw", "stm_fw", "stm_bootloader_fw", "manual_protocol", "stm_flash_layout"):
            with self.subTest(key=key):
                self.transport.identity = {**identity(), key: token}
                self.assertNotIn(token, json.dumps(self.service.snapshot()))


class Response(io.BytesIO):
    status = 200


class RoverHttpTest(unittest.TestCase):
    def setUp(self):
        self.token = "A" * 64
        self.http = RoverHttp("http://rover.local/", self.token)

    def respond(self, data):
        class Opener:
            def open(inner, request, timeout):
                self.request = request
                return Response(data)
        self.http._opener = Opener()

    def test_token_is_only_in_authorization_and_only_get_is_supported(self):
        self.respond(b'{"v":3}')
        self.http.get("/api/v3/identity")
        self.assertEqual(self.request.get_header("Authorization"), "Bearer " + self.token)
        self.assertEqual(self.request.get_method(), "GET")
        self.assertNotIn(self.token, self.request.full_url)
        for path in ("/api/stm_update", "/api/v3/stop", "/api/v3/state?token=x"):
            with self.assertRaises(ValueError):
                self.http.get(path)

    def test_oversized_duplicate_nonfinite_and_nonobject_json_rejected(self):
        for body in (b" " * 16385, b'{"v":3,"v":3}', b'{"v":3,"x":NaN}', b'[]', b'{"v":true}'):
            with self.subTest(body=body[:50]):
                self.respond(body)
                with self.assertRaises(RoverReadError):
                    self.http.get("/api/v3/identity")

    def test_auth_redirect_and_network_errors_never_echo_remote_secret(self):
        for error, code in ((HTTPError("http://rover.local", 401, self.token, {}, io.BytesIO(self.token.encode())), "AUTH_FAILED"),
                            (HTTPError("http://rover.local", 302, self.token, {}, io.BytesIO()), "REDIRECT_BLOCKED"),
                            (URLError(self.token), "UNREACHABLE")):
            class Opener:
                def open(inner, request, timeout):
                    raise error
            self.http._opener = Opener()
            with self.assertRaises(RoverReadError) as context:
                self.http.get("/api/v3/identity")
            self.assertEqual(context.exception.code, code)
            self.assertNotIn(self.token, str(context.exception))

    def test_get_503_has_one_serial_retry_and_repeated_busy_is_bounded(self):
        calls = []
        class Opener:
            def open(inner, request, timeout):
                calls.append(request)
                raise HTTPError("http://rover.local", 503, "Busy", {}, io.BytesIO())
        self.http._opener = Opener()
        with patch("mower_v3_service.time.sleep") as sleep:
            with self.assertRaises(RoverReadError) as error:
                self.http.get("/api/v3/state")
        self.assertEqual(error.exception.code, "BUSY")
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once_with(.05)
        calls.clear()
        with self.assertRaises(RoverReadError):
            self.http.get("/api/v3/identity")
        self.assertEqual(len(calls), 2)

    def test_get_retry_returns_only_newly_read_evidence_and_post_503_is_never_retried(self):
        calls = []
        class Response(io.BytesIO):
            status = 200
        class Opener:
            def open(inner, request, timeout):
                calls.append(request)
                if len(calls) == 1:
                    raise HTTPError("http://rover.local", 503, "Busy", {}, io.BytesIO())
                return Response(b'{"v":3,"source_seq":42}')
        self.http._opener = Opener()
        with patch("mower_v3_service.time.sleep"):
            self.assertEqual(self.http.get("/api/v3/state")['source_seq'], 42)
        self.assertEqual(len(calls), 2)
        calls.clear()
        # POST still returns the native rejection after exactly one send.
        from mower_v3_service import UnknownMutation
        with self.assertRaises(UnknownMutation):
            self.http.request("POST", "/api/v3/parameters", {"v":3})
        self.assertEqual(len(calls), 1)

    def test_redirect_handler_and_no_proxy_are_installed(self):
        from mower_v3_service import NoRedirect
        handlers = self.http._opener.handlers
        self.assertTrue(any(isinstance(handler, NoRedirect) for handler in handlers))
        redirect = next(handler for handler in handlers if isinstance(handler, NoRedirect))
        self.assertIsNone(redirect.redirect_request(None, None, 302, "", {}, "http://other.local"))

    def test_invalid_configuration_never_connects(self):
        for origin in ("http://user:pass@rover.local", "http://rover.local/path", "http://rover.local?x=y", "http://rover.local:bad", "ftp://rover.local"):
            result = MowerV3Service(origin=origin, token=self.token).snapshot()
            self.assertFalse(result["configured"])
            self.assertNotIn(self.token, json.dumps(result))
        self.assertFalse(MowerV3Service(origin="http://rover.local", token="invalid").snapshot()["configured"])

    def test_update_transport_has_exact_bounded_paths_but_no_image_abort_finish_or_legacy_fallback(self):
        self.respond(b'{"v":3,"update_id":"CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"}')
        for path in ("/api/v3/update", "/api/v3/update/"+"C"*32):
            self.http.get(path)
            self.assertEqual(self.request.get_header("Authorization"), "Bearer "+self.token)
        body = {"v":3,"request_id":"explicit-create","esp_boot":"0123456789ABCDEF","target":"STM"}
        self.http.request("POST", "/api/v3/update", body)
        self.assertEqual(json.loads(self.request.data), body)
        for path in ("/api/v3/update/"+"0"*32, "/api/v3/update/"+"c"*32, "/api/v3/update?token=x", "/api/v3/update/../other"):
            with self.assertRaises(ValueError): self.http.get(path)
        for action in ("image", "abort", "finish", "activate"):
            with self.assertRaises(ValueError): self.http.request("POST", "/api/v3/update/"+"C"*32+"/"+action, {})

    def test_update_post_lost_malformed_or_redirect_reply_is_unknown_and_never_retried(self):
        from mower_v3_service import UnknownMutation
        for data in (b'{"v":true}', b'{"v":3,"v":3}', b'[]', b" "*16385):
            self.respond(data)
            with self.assertRaises(UnknownMutation): self.http.request("POST", "/api/v3/update", {"v":3})
        for failure in (URLError(self.token), HTTPError("http://rover.local",302,self.token,{},io.BytesIO())):
            class Opener:
                def open(inner, request, timeout): raise failure
            self.http._opener = Opener()
            with self.assertRaises(UnknownMutation) as error: self.http.request("POST", "/api/v3/update", {"v":3})
            self.assertNotIn(self.token, str(error.exception))

    def test_native_vg_image_has_exact_raw_bytes_and_image_layout_not_identity_layout(self):
        import hashlib
        image = b"x"*1280
        metadata = {"image_bytes":len(image),"image_sha256":hashlib.sha256(image).hexdigest(),"profile_crc":"AABBCCDD","fw_id":"reviewed"}
        self.respond(b'{"v":3}')
        self.http.update_mutation("IMAGE","C"*32,image,metadata)
        self.assertEqual(self.request.data,image)
        self.assertEqual(self.request.get_header("Content-length"),"1280")
        self.assertEqual(self.request.get_header("X-flash-layout"),"H743_1M_QSPI_REC2")
        self.assertEqual(self.request.get_header("X-image-slot"),"APP")
        self.assertIsNone(self.request.get_header("Transfer-encoding"))
        for action in ("ABORT","FINISH"):
            self.http.update_mutation(action,"C"*32)
            self.assertEqual(self.request.data,b"")
            self.assertEqual(self.request.get_header("Content-length"),"0")
        for action, id_ in (("ACTIVATE","C"*32),("IMAGE","0"*32),("FINISH","c"*32)):
            with self.assertRaises(ValueError): self.http.update_mutation(action,id_)

    def test_native_image_transport_uncertainty_never_retries_or_follows_redirects(self):
        from mower_v3_service import UnknownMutation
        calls=[]
        class Opener:
            def open(inner, request, timeout):
                calls.append(request)
                raise HTTPError("http://rover.local",302,self.token,{},io.BytesIO())
        self.http._opener=Opener()
        with self.assertRaises(UnknownMutation): self.http.update_mutation("ABORT","C"*32)
        self.assertEqual(len(calls),1)


if __name__ == "__main__":
    unittest.main()
