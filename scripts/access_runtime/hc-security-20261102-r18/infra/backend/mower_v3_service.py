"""v3.1 rover HTTP transport and authoritative read model; no legacy fallback."""
import json
import math
import re
import threading
import time
import hashlib
from contextlib import contextmanager
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


CONTRACT = "3.1.0"
MANUAL_PROTOCOL = "homecontrol.mower.manual.v3"
MAX_RESPONSE_BYTES = 16384
STATE_TIMEOUT_MS = 1500
STATES = {"DISARMED", "IDLE", "MANUAL", "AUTO", "PAUSED", "FAULT", "MAINTENANCE"}


class RoverReadError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class UnknownMutation(RoverReadError):
    def __init__(self):
        super().__init__("REPLY_LOST", "A művelet eredménye ismeretlen; csak olvasási egyeztetés végezhető.")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("Non-finite JSON number")


def integer(value, minimum=0, maximum=0xFFFFFFFF):
    return type(value) is int and minimum <= value <= maximum


def hex_id(value, length, *, nonzero=False):
    return (type(value) is str and re.fullmatch(r"[0-9A-F]{%d}" % length, value)
            is not None and (not nonzero or value != "0" * length))


def require(condition):
    if not condition:
        raise RoverReadError("INVALID_RESPONSE", "Hibás vagy hiányos v3.1 roverválasz.")


class RoverHttp:
    def __init__(self, origin, token):
        parsed = urlsplit(origin)
        if (re.search(r"\s", origin) or parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment):
            raise ValueError("Invalid rover origin")
        # Accessing port also rejects malformed ports before any connection.
        parsed.port
        if type(token) is not str or re.fullmatch(r"[0-9a-fA-F]{64}", token) is None:
            raise ValueError("Invalid rover token")
        self._origin, self._token = origin.rstrip("/"), token
        # Credentials go only to the provisioned origin, never to a redirect/proxy.
        self._opener = build_opener(ProxyHandler({}), NoRedirect())

    def get(self, path):
        try:
            code, payload = self.request("GET", path)
        except RoverReadError as error:
            if error.code != "ROVER_BUSY":
                raise
            # One bounded, serialized retry for a rejected read only. Never
            # retry any mutation or renew the timestamp of an old STATE.
            time.sleep(.05)
            try:
                code, payload = self.request("GET", path)
            except RoverReadError as retry:
                if retry.code == "ROVER_BUSY":
                    raise RoverReadError("BUSY", "A rover lekérdezési kapacitása átmenetileg foglalt.") from None
                raise
        if code != 200:
            raise RoverReadError("AUTH_FAILED" if code in (401, 403) else "HTTP_ERROR", f"Rover HTTP {code}.")
        return payload

    def request(self, method, path, payload=None):
        update_read = path == "/api/v3/update" or re.fullmatch(r"/api/v3/update/(?!0{32}$)[0-9A-F]{32}", path)
        read = path in ("/api/v3/identity", "/api/v3/state", "/api/v3/parameters", "/api/v3/health") or re.fullmatch(r"/api/v3/command/[A-Za-z0-9_-]{1,64}", path) or update_read
        if not (method == "GET" and read or method == "POST" and path in ("/api/v3/command", "/api/v3/stop", "/api/v3/update", "/api/v3/parameters")):
            raise ValueError("Unsupported read path")
        body = None if payload is None else json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("ascii")
        return self._exchange(method, path, body, {"Content-Type": "application/json"}, 1.5)

    def update_mutation(self, action, update_id, image=None, metadata=None):
        # No arbitrary path/header/target supplied by an HTTP caller.
        if action not in {"IMAGE", "ABORT", "FINISH"} or not hex_id(update_id, 32, nonzero=True):
            raise ValueError("Unsupported update mutation")
        body, headers = b"", {"Content-Type": "application/octet-stream", "Content-Length": "0"}
        if action == "IMAGE":
            if (type(image) is not bytes or not 1280 <= len(image) <= 524288 or len(image) % 32
                    or type(metadata) is not dict or metadata.get("image_bytes") != len(image)
                    or metadata.get("image_sha256") != hashlib.sha256(image).hexdigest()
                    or not hex_id(metadata.get("profile_crc"), 8, nonzero=True)
                    or type(metadata.get("fw_id")) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,48}", metadata["fw_id"])):
                raise ValueError("Invalid exact VG image")
            body = image
            headers.update({"Content-Length": str(len(image)), "X-Image-SHA256": metadata["image_sha256"],
                            "X-Firmware-ID": metadata["fw_id"], "X-Profile-CRC32": metadata["profile_crc"],
                            "X-Contract": CONTRACT, "X-Flash-Layout": "H743_1M_QSPI_REC2", "X-Image-Slot": "APP"})
        elif image is not None or metadata is not None:
            raise ValueError("Empty-body update action required")
        return self._exchange("POST", "/api/v3/update/" + update_id + "/" + action.lower(), body, headers, 10)

    def _exchange(self, method, path, body, headers, timeout):
        request = Request(self._origin + path, method=method, data=body, headers={
            "Authorization": "Bearer " + self._token, "Accept": "application/json",
            "Connection": "close", **headers,
        })
        try:
            try:
                response = self._opener.open(request, timeout=timeout)
            except HTTPError as error:
                if 300 <= error.code < 400:
                    error.close()
                    raise RoverReadError("REDIRECT_BLOCKED", "A rover átirányítása elutasítva.") from None
                if method == "GET":
                    if error.code == 404 and (path.startswith("/api/v3/command/") or path.startswith("/api/v3/update/")):
                        error.close()
                        return 404, {"v": 3, "code": "NOT_FOUND"}
                    if error.code == 503:
                        error.close()
                        raise RoverReadError("ROVER_BUSY", "A rover olvasási slotja átmenetileg foglalt.") from None
                    code = "AUTH_FAILED" if error.code in (401, 403) else "HTTP_ERROR"
                    error.close()
                    raise RoverReadError(code, "A rover elutasította a hitelesítést." if code == "AUTH_FAILED" else f"Rover HTTP {error.code}.") from None
                response = error
            with response:
                data = response.read(MAX_RESPONSE_BYTES + 1)
                require(len(data) <= MAX_RESPONSE_BYTES)
                result = json.loads(data, object_pairs_hook=unique_object,
                                     parse_constant=reject_constant)
                require(type(result) is dict and type(result.get("v")) is int and result["v"] == 3)
                return response.status if hasattr(response, "status") else response.code, result
        except (URLError, OSError, HTTPException, ValueError, UnicodeError, RoverReadError) as error:
            if method == "POST":
                raise UnknownMutation() from None
            if isinstance(error, RoverReadError):
                raise
            if isinstance(error, (ValueError, UnicodeError)):
                raise RoverReadError("INVALID_RESPONSE", "Nem értelmezhető v3.1 roverválasz.") from None
            raise RoverReadError("UNREACHABLE", "A rover v3.1 API nem érhető el.") from None

    def manual_socket(self):
        from mower_manual_service import connect_rover
        url = ("wss" if self._origin.startswith("https:") else "ws") + self._origin[self._origin.index(":"):]
        return connect_rover(url + "/api/v3/manual", self._token)


def validate_identity(payload):
    require(type(payload) is dict and type(payload.get("v")) is int and payload["v"] == 3)
    if payload.get("contract") != CONTRACT:
        raise RoverReadError("INCOMPATIBLE_VERSION", "A rover nem a támogatott 3.1.0 szerződést jelzi.")
    require(hex_id(payload.get("esp_boot"), 16, nonzero=True))
    require("stm_boot" in payload and (payload["stm_boot"] is None or hex_id(payload["stm_boot"], 16, nonzero=True)))
    require(hex_id(payload.get("profile_crc"), 8))
    for key in ("compatible", "conformant", "stm_remote_update", "stm_reset_recovery", "update_locked"):
        require(type(payload.get(key)) is bool)
    for key in ("esp_fw", "stm_flash_layout", "manual_protocol"):
        require(type(payload.get(key)) is str and 0 < len(payload[key]) <= 48)
    for key in ("stm_fw", "stm_bootloader_fw"):
        require(key in payload and (payload[key] is None or type(payload[key]) is str and 0 < len(payload[key]) <= 48))
    for key in ("update_service_abi", "stm_image_max_bytes", "esp_ota_max_bytes"):
        require(integer(payload.get(key)))
    require(type(payload.get("max_mission_bytes")) is int and payload["max_mission_bytes"] == 131072)
    require(type(payload.get("max_segments")) is int and payload["max_segments"] == 4096)
    for key, allowed in (("stm_confirmed_slot", {"A", "B", "NONE", None}), ("stm_inactive_slot", {"A", "B", None})):
        require(key in payload and (payload[key] is None or type(payload[key]) is str) and payload[key] in allowed)
    if "runtime_parameters" in payload:
        require(type(payload["runtime_parameters"]) is bool)
    for key in ("manual_claim_from_disarmed", "minimal_erpm_parameters", "first_configuration_requires_motor_feedback", "test_manual_control", "manual_erpm", "commissioned", "profile_verified", "motion_permitted", "esp_ota_enabled", "autonomous_enabled"):
        if key in payload:
            require(type(payload[key]) is bool)
    if "mode" in payload:
        require(type(payload["mode"]) is str)
    if "parameter_versions_supported" in payload:
        require(type(payload["parameter_versions_supported"]) is list and all(type(v) is int and v in (1, 2) for v in payload["parameter_versions_supported"]))
    # Whitelist: a remote response can never add credentials to browser diagnostics.
    keys = ("v", "contract", "esp_boot", "stm_boot", "profile_crc", "compatible", "conformant",
            "esp_fw", "stm_fw", "stm_bootloader_fw", "stm_remote_update", "stm_reset_recovery",
            "update_locked", "stm_flash_layout", "update_service_abi", "stm_image_max_bytes",
            "esp_ota_max_bytes", "max_mission_bytes", "max_segments", "manual_protocol",
            "stm_confirmed_slot", "stm_inactive_slot", "runtime_parameters", "mode", "manual_claim_from_disarmed", "minimal_erpm_parameters", "first_configuration_requires_motor_feedback", "test_manual_control", "manual_erpm", "parameter_versions_supported", "commissioned", "profile_verified", "motion_permitted", "esp_ota_enabled", "autonomous_enabled")
    return {key: payload[key] for key in keys if key in payload}


def validate_state(payload, identity):
    require(type(payload) is dict and type(payload.get("v")) is int and payload["v"] == 3)
    require(payload.get("esp_boot") == identity["esp_boot"])
    require("stm_boot" in payload and payload["stm_boot"] == identity["stm_boot"])
    require(type(payload.get("source_valid")) is bool)
    require(integer(payload.get("published_ms")) and integer(payload.get("source_seq")))
    require("source_age_ms" in payload and (payload["source_age_ms"] is None or integer(payload["source_age_ms"])))
    enums = {
        "state": STATES, "phase": {"NONE", "ALIGN", "TRACK"},
        "store": {"EMPTY", "RECEIVING", "VALIDATING", "READY"},
        "outcome": {"NONE", "RUNNING", "PAUSED", "COMPLETED", "STOPPED", "FAULTED"},
    }
    for key, allowed in enums.items():
        require(key in payload and (payload[key] is None or type(payload[key]) is str and payload[key] in allowed))
    for key in ("state_seq", "control_epoch", "event_seq", "revision", "segment_index",
                "segment_count", "manual_lease_id", "manual_input_seq"):
        require(key in payload and (payload[key] is None or integer(payload[key])))
    for key in ("armed", "stopped", "ready_for_start", "ready_for_resume"):
        require(key in payload and (payload[key] is None or type(payload[key]) is bool))
    require("mission_id" in payload and (payload["mission_id"] is None or type(payload["mission_id"]) is str and
            re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", payload["mission_id"]) is not None))
    require("crc32" in payload and (payload["crc32"] is None or hex_id(payload["crc32"], 8)))
    require("reason" in payload and (payload["reason"] is None or type(payload["reason"]) is str and re.fullmatch(r"[A-Z_]{1,32}", payload["reason"]) is not None))
    for key in ("fault_mask", "safety_installed_mask", "safety_active_mask"):
        require(key in payload and (payload[key] is None or integer(payload[key])))
    if payload["source_valid"]:
        require(identity["stm_boot"] is not None and payload["source_seq"] > 0
                and payload["source_age_ms"] is not None)
        for key in (*enums, "armed", "stopped", "ready_for_start", "ready_for_resume", "fault_mask",
                    "safety_installed_mask", "safety_active_mask", "event_seq", "segment_index", "segment_count", "reason"):
            require(payload[key] is not None)
        require(integer(payload["state_seq"], 1) and integer(payload["control_epoch"], 1))
        require(payload["segment_index"] <= payload["segment_count"] <= 4096)
        require(payload["armed"] == (payload["state"] in ("IDLE", "MANUAL", "AUTO", "PAUSED")))
    keys = ("v", "esp_boot", "stm_boot", "published_ms", "source_seq", "source_age_ms", "source_valid",
            "state_seq", "control_epoch", "event_seq", "state", "phase", "armed", "store", "mission_id",
            "revision", "crc32", "segment_index", "segment_count", "outcome", "reason", "fault_mask",
            "stopped", "ready_for_start", "ready_for_resume", "manual_lease_id", "manual_input_seq",
            "safety_installed_mask", "safety_active_mask")
    return {key: payload[key] for key in keys}


class MowerV3Service:
    def __init__(self, *, origin="", token="", transport=None, clock=time.monotonic, read_only=False, motor_test_enabled=False, simple_control=False):
        self.simple_control = simple_control
        self.read_only = read_only
        self.motor_test_enabled = motor_test_enabled
        self._test_identity = None
        self.clock = clock
        self._lock = threading.RLock()
        self._commands_lock = threading.Lock()
        self.activity_lock = threading.Lock()
        self.maintenance_guard = lambda: None
        self.motor_test_guard = lambda: True
        self.connection_key = hashlib.sha256((origin.rstrip("/") or "injected-transport").encode()).hexdigest()
        self._sample = None
        self.commands = None
        self._transport = transport
        self._configuration_error = None
        if transport is None:
            if not origin or not token:
                self._configuration_error = "A backendben állítsd be a MOWER_V3_REMOTE_URL és ROVER_API_TOKEN értékét."
            else:
                try:
                    self._transport = RoverHttp(origin, token)
                except ValueError:
                    self._configuration_error = "A backend rovercíme vagy tokenformátuma hibás."

    def snapshot(self):
        result = {"ok": True, "contract": CONTRACT, "simple_control": self.simple_control, "read_only": True, "controls_disabled": self.read_only,
                  "configured": self._configuration_error is None,
                  "connection": {"status": "UNCONFIGURED", "detail": self._configuration_error},
                  "identity": None, "state": None,
                  "freshness": {"fresh": False, "effective_age_ms": None, "timeout_ms": STATE_TIMEOUT_MS},
                  "capabilities": {"manual": False, "stm_update": False, "esp_update": False, "runtime_parameters": False}}
        if self._configuration_error:
            return result
        if not self._lock.acquire(blocking=False):
            result["connection"] = {"status": "BUSY", "detail": "Egy roverlekérés már folyamatban van."}
            return result
        try:
            self.maintenance_guard()
            identity = validate_identity(self._transport.get("/api/v3/identity"))
            result["identity"] = identity
            from mower_motor_test import motor_identity, validate_motor_state
            test_mode = identity.get("mode") == "MOTOR_TEST"
            if test_mode:
                require(motor_identity(identity))
                self._test_identity = identity
            else:
                self._test_identity = None
            result["controls_disabled"] = self.read_only and not (test_mode and self.motor_test_enabled)
            profile_known = identity["profile_crc"] != "00000000"
            pair = identity["update_service_abi"], identity["stm_flash_layout"]
            recognized_update = ((pair == (1, "H743_2M_AB1") and identity["stm_image_max_bytes"] == 786432)
                                 or (pair == (2, "H743_1M_QSPI2") and identity["stm_image_max_bytes"] == 524288
                                     and identity["stm_confirmed_slot"] is None and identity["stm_inactive_slot"] is None))
            result["capabilities"] = {
                "manual": identity["compatible"] and (profile_known or self.simple_control) and identity["manual_protocol"] == MANUAL_PROTOCOL,
                "stm_update": identity["stm_remote_update"] and profile_known and recognized_update,
                "esp_update": identity["esp_ota_max_bytes"] > 0,
                "runtime_parameters": identity.get("runtime_parameters") is True,
            }
            if identity.get("mode") in ("HC_BRINGUP", "MOTOR_TEST"):
                result["capabilities"].update(manual=False, stm_update=False, esp_update=False)
            if result["controls_disabled"]:
                result["capabilities"] = {key: False for key in result["capabilities"]}
            if identity["update_locked"] and not test_mode:
                self._sample = None
                result["connection"] = {"status": "UPDATE_MODE", "detail": "A rover frissítési módban van; az üzemi állapot nem elérhető."}
                return result
            started = self.clock()
            raw_state = self._transport.get("/api/v3/state")
            state = validate_motor_state(raw_state, identity) if test_mode else validate_state(raw_state, identity)
            now = self.clock()
            sample_key = (state["esp_boot"], state["stm_boot"], state["source_seq"])
            independent = {"safety_source_valid", "safety_source_seq", "safety_source_age_ms", "safety_installed_mask", "safety_active_mask"} if test_mode else set()
            evidence = {key: value for key, value in state.items() if key not in independent | {"published_ms", "source_age_ms", "source_valid"}}
            age = state["source_age_ms"]
            if age is not None:
                age += max(0, math.ceil((now - started) * 1000))
            fresh = state["source_valid"] and age is not None and age <= STATE_TIMEOUT_MS and identity["compatible"]
            if self._sample and self._sample["key"][:2] == sample_key[:2]:
                delta = (sample_key[2] - self._sample["key"][2]) & 0xFFFFFFFF
                if delta == 0:
                    require(not state["source_valid"] or self._sample.get("evidence") == evidence)
                    # Repeated HTTP snapshots cannot renew original source freshness.
                    old_age = self._sample["age"] + math.ceil((now - self._sample["at"]) * 1000)
                    age = max(age, old_age) if age is not None else None
                    fresh = fresh and age is not None and age <= STATE_TIMEOUT_MS
                elif delta >= 0x80000000:
                    fresh = False
                else:
                    self._sample = None
            else:
                self._sample = None
            if self._sample is None and age is not None:
                self._sample = {"key": sample_key, "age": age, "at": now, "evidence": evidence}
            result["state"] = state
            if identity.get("mode") == "MOTOR_TEST":
                from mower_motor_test import motor_identity, validate_parameters_status, parameters_fresh
                require(motor_identity(identity))
                recovering = False
                if identity.get("manual_claim_from_disarmed") is True:
                    try:
                        health = self._transport.get("/api/v3/health")
                        require(type(health) is dict and type(health.get("v")) is int and health["v"] == 3
                                and health.get("esp_boot") == identity["esp_boot"])
                        for key in ("uart_recovering", "uart_rx_closed", "stm_peer_alive"):
                            require(type(health.get(key)) is bool)
                        for key in ("uart_recovery_attempts", "uart_recovery_completed"):
                            require(integer(health.get(key)))
                        result["health"] = {key: health[key] for key in ("uart_recovering", "uart_rx_closed", "stm_peer_alive", "uart_recovery_attempts", "uart_recovery_completed")}
                        stack = health.get("esp_stack_min_bytes")
                        if type(stack) is dict and "manual_ws" in stack:
                            value = stack["manual_ws"]
                            if value is None or integer(value):
                                result["health"]["esp_stack_min_bytes"] = {"manual_ws": value}
                        recovering = health["uart_recovering"] or health["uart_rx_closed"] or not health["stm_peer_alive"]
                    except RoverReadError as error:
                        result["health_error"] = {"code": error.code, "detail": str(error)}
                parameters_started = self.clock()
                try:
                    parameters = validate_parameters_status(self._transport.get("/api/v3/parameters"))
                except RoverReadError as error:
                    if not self.simple_control:
                        raise
                    result["parameters_error"] = {"code": error.code, "detail": str(error)}
                    parameters = {"source_age_ms": None, "available": False, "source_valid": False,
                        "storage": "UNKNOWN", "applied": False, "busy": False, "parameters": None,
                        "esp_boot": None, "stm_boot": None, "control_epoch": None}
                parameters["source_age_ms"] = (parameters["source_age_ms"] + math.ceil((self.clock() - parameters_started) * 1000)
                                                   if parameters["source_age_ms"] is not None else None)
                result["parameters"] = parameters
                if age is not None:
                    age += math.ceil((self.clock() - now) * 1000)
                    fresh = fresh and age <= STATE_TIMEOUT_MS
                matching = parameters_fresh(parameters, identity, state)
                result["capabilities"]["manual"] = bool(fresh and matching and parameters["storage"] == "ACTIVE"
                    and parameters["applied"] and not parameters["busy"] and parameters["parameters"] is not None
                    and identity.get("runtime_parameters") is True and self.motor_test_guard() and identity.get("test_manual_control") is True and identity.get("manual_erpm") is True and (not self.read_only or self.motor_test_enabled))
                if self.simple_control:
                    result["capabilities"]["manual"] = bool(fresh and identity["compatible"] and identity.get("test_manual_control") is True
                        and identity["manual_protocol"] == MANUAL_PROTOCOL and not result["controls_disabled"])
                result["capabilities"]["manual"] = result["capabilities"]["manual"] and not recovering
                result["capabilities"]["manual_erpm"] = result["capabilities"]["manual"]
            result["freshness"] = {"fresh": bool(fresh), "effective_age_ms": age, "timeout_ms": STATE_TIMEOUT_MS}
            result["connection"] = {"status": "LIVE" if fresh else "STALE", "detail": "Friss STM-forrás." if fresh else "Az STM-állapot nem friss vagy nem igazolt."}
            return result
        except RoverReadError as error:
            result["connection"] = {"status": error.code, "detail": str(error)}
            return result
        finally:
            self._lock.release()

    def command_service(self):
        from mower_v3_commands import MowerV3Commands
        # Construction is guarded separately from network reads.
        with self._commands_lock:
            if self.commands is None:
                self.commands = MowerV3Commands(self)
            return self.commands

    @contextmanager
    def ordinary_operation(self):
        if not self.activity_lock.acquire(blocking=False):
            raise RoverReadError("BUSY", "Másik vezérlési vagy session-művelet folyamatban van.")
        try:
            self.maintenance_guard()
            yield
        finally:
            self.activity_lock.release()

    @property
    def configured(self):
        return self._configuration_error is None

    def request(self, method, path, body=None):
        if self.read_only and method != "GET" and not (self.motor_test_enabled and self._test_identity is not None
                and (path in ("/api/v3/command", "/api/v3/stop", "/api/v3/parameters"))):
            raise RoverReadError("READ_ONLY", "A HC roverkapcsolata csak olvasó módban van.")
        if self._configuration_error or self._transport is None:
            raise RoverReadError("UNCONFIGURED", "A roverkapcsolat nincs beállítva.")
        if method == "POST" and path == "/api/v3/command":
            with self.ordinary_operation():
                with self._lock:
                    return self._transport.request(method, path, body)
        if path == "/api/v3/stop":
            return self._transport.request(method, path, body)
        if not self._lock.acquire(blocking=False):
            raise RoverReadError("BUSY", "Egy roverlekérés már folyamatban van.")
        try:
            return self._transport.request(method, path, body)
        finally:
            self._lock.release()

    def manual_socket(self):
        if self.read_only and not (self.motor_test_enabled and self._test_identity is not None):
            raise RoverReadError("READ_ONLY", "A HC roverkapcsolata csak olvasó módban van.")
        if self._configuration_error or self._transport is None:
            raise RoverReadError("UNCONFIGURED", "A roverkapcsolat nincs beállítva.")
        return self._transport.manual_socket()

    def update_mutation(self, action, update_id, image=None, metadata=None):
        if self.read_only:
            raise RoverReadError("READ_ONLY", "A HC roverkapcsolata csak olvasó módban van.")
        if not self.configured or self._transport is None:
            raise RoverReadError("UNCONFIGURED", "A roverkapcsolat nincs beállítva.")
        return self._transport.update_mutation(action, update_id, image, metadata)
