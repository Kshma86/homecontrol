"""Read-only FIRST_INSTALL_SERVICE ABI1; never operational state or admission."""
import ipaddress
import json
import math
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request
from http.client import HTTPException

import rover_parameters as rcp1
from mower_v3_service import RoverHttp, RoverReadError, hex_id, integer, unique_object, reject_constant

TIMEOUT_MS = 3000
READ_PATHS = {"/api/v3/service/status", "/api/v3/service/parameters"}


def require(condition):
    if not condition:
        raise RoverReadError("INVALID_RESPONSE", "Hibás vagy hiányos szervizválasz.")


class ServiceHttp(RoverHttp):
    read_paths = READ_PATHS

    def get(self, path):
        if path not in self.read_paths:
            raise ValueError("Only explicit service GETs are permitted")
        request = Request(self._origin + path, method="GET", headers={
            "Authorization": "Bearer " + self._token, "Accept": "application/json", "Connection": "close",
        })
        try:
            try:
                response = self._opener.open(request, timeout=3)
            except HTTPError as error:
                with error:
                    code = "AUTH_FAILED" if error.code in (401, 403) else "HTTP_ERROR"
                    if 300 <= error.code < 400:
                        code = "REDIRECT_BLOCKED"
                    elif error.code == 404:
                        raw = error.read(8193)
                        try:
                            body = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
                            if (len(raw) <= 8192 and type(body) is dict and type(body.get("code")) is str
                                    and body["code"] in {"SETUP_ONLY", "SERVICE_ONLY"}):
                                code = body["code"]
                        except (ValueError, UnicodeError):
                            pass
                raise RoverReadError(code, "A rover elutasította a szervizlekérdezést.") from None
            with response:
                raw = response.read(8193)
                require(response.status == 200 and len(raw) <= 8192)
                payload = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
                require(type(payload) is dict)
                return payload
        except RoverReadError:
            raise
        except (ValueError, UnicodeError, RecursionError):
            raise RoverReadError("INVALID_RESPONSE", "Nem értelmezhető szervizválasz.") from None
        except (URLError, OSError, HTTPException):
            raise RoverReadError("UNREACHABLE", "A rover szerviz API nem érhető el.") from None

    def request(self, *args, **kwargs):
        raise ValueError("Service transport is read-only")

    def update_mutation(self, *args, **kwargs):
        raise ValueError("Service transport is read-only")

    def manual_socket(self):
        raise ValueError("Service transport has no WebSocket")


def validate_status(payload, *, parameters=False):
    require(type(payload) is dict)
    if (type(payload.get("v")) is not int or payload["v"] != 3
            or payload.get("mode") != "FIRST_INSTALL_SERVICE"
            or type(payload.get("service_abi")) is not int or payload["service_abi"] != 1):
        raise RoverReadError("INCOMPATIBLE_VERSION", "Nem a támogatott FIRST_INSTALL_SERVICE / ABI1 kiadás.")
    for key in ("motion_permitted", "commissioned", "applied", "esp_ota_enabled", "stm_remote_update_enabled"):
        require(payload.get(key) is False)
    for key in ("stm_connected", "can_parked", "disarmed", "outputs_inhibited"):
        require(type(payload.get(key)) is bool)
    require(type(payload.get("esp_firmware")) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,48}", payload["esp_firmware"]) is not None)
    require("stm_source_age_ms" in payload and (payload["stm_source_age_ms"] is None or integer(payload["stm_source_age_ms"])))
    if payload["stm_connected"]:
        require(hex_id(payload.get("stm_uid"), 24, nonzero=True)
                and type(payload.get("stm_firmware")) is str
                and re.fullmatch(r"[A-Za-z0-9_.-]{1,48}", payload["stm_firmware"]) is not None
                and payload["stm_source_age_ms"] is not None)
    else:
        require("stm_uid" in payload and payload["stm_uid"] is None
                and "stm_firmware" in payload and payload["stm_firmware"] is None
                and payload["can_parked"] is False)
    require(type(payload.get("storage")) is str and payload["storage"] in {"EMPTY", "PENDING", "STAGED", "FAULT"})
    require(integer(payload.get("revision")))
    require(type(payload.get("code")) is str and re.fullmatch(r"[A-Z_]{1,48}", payload["code"]) is not None)
    for key in ("parameters_crc", "stm_parameters_crc"):
        require(key in payload and (payload[key] is None or hex_id(payload[key], 8)))
    result = {key: payload[key] for key in (
        "v", "mode", "service_abi", "esp_firmware", "stm_firmware", "stm_connected", "stm_uid",
        "stm_source_age_ms", "can_parked", "disarmed", "outputs_inhibited", "motion_permitted",
        "commissioned", "applied", "esp_ota_enabled", "stm_remote_update_enabled", "storage", "revision",
        "code", "parameters_crc", "stm_parameters_crc",
    )}
    for key in ("ip", "ap_ip"):
        require(type(payload.get(key)) is str)
        try:
            result[key] = str(ipaddress.IPv4Address(payload[key]))
        except ValueError:
            require(False)
    if "free_heap" in payload:
        require(integer(payload["free_heap"]))
        result["free_heap"] = payload["free_heap"]
    for key in ("wifi_connected", "wifi_configured", "setup_ap_active", "mdns_ready"):
        if key in payload:
            require(type(payload[key]) is bool)
            result[key] = payload[key]
    if "hostname" in payload:
        require(type(payload["hostname"]) is str and re.fullmatch(r"[A-Za-z0-9.-]{1,63}", payload["hostname"]) is not None)
        result["hostname"] = payload["hostname"]
    if "wifi_storage" in payload:
        require(type(payload["wifi_storage"]) is str and re.fullmatch(r"[A-Z_]{1,32}", payload["wifi_storage"]) is not None)
        result["wifi_storage"] = payload["wifi_storage"]
    if parameters:
        require("parameters" in payload)
        value = payload["parameters"]
        if value is not None:
            try:
                rcp1.validate(value)
                require(payload["parameters_crc"] == f"{rcp1.checksum(value):08X}")
            except ValueError:
                require(False)
        if payload["storage"] == "EMPTY":
            require(value is None and payload["revision"] == 0 and payload["parameters_crc"] is None)
        if payload["storage"] == "STAGED":
            require(value is not None and payload["revision"] > 0)
        result["parameters"] = value
    return result


class MowerServiceRead:
    def __init__(self, *, origin="", token="", transport=None, clock=time.monotonic, activity_lock=None, guard=None):
        self.clock = clock
        self.lock = activity_lock if activity_lock is not None else threading.Lock()
        self.guard = guard or (lambda: None)
        self.transport = transport
        self.configuration = {"origin_configured": bool(origin), "token_configured": bool(token)}
        self.error = None
        if transport is None:
            if not origin or not token:
                self.error = "A backendben rover LAN-cím és privát API-token szükséges."
            else:
                try:
                    self.transport = ServiceHttp(origin, token)
                except ValueError:
                    self.error = "Hibás rover alapcím vagy tokenformátum."

    def snapshot(self):
        result = {"ok": True, "read_only": True, "configured": self.error is None,
                  "configuration": self.configuration.copy(), "service": None, "parameters": None,
                  "connection": {"status": "UNCONFIGURED", "detail": self.error},
                  "freshness": {"fresh": False, "effective_age_ms": None, "timeout_ms": TIMEOUT_MS}}
        if self.error:
            return result
        if not self.lock.acquire(blocking=False):
            result["connection"] = {"status": "BUSY", "detail": "Egy roverlekérés vagy művelet már folyamatban van."}
            return result
        try:
            self.guard()
            started = self.clock()
            status = validate_status(self.transport.get("/api/v3/service/status"))
            status_age = status["stm_source_age_ms"]
            started_parameters = self.clock()
            readback = validate_status(self.transport.get("/api/v3/service/parameters"), parameters=True)
            now = self.clock()
            require((status["stm_uid"], status["esp_firmware"], status["stm_firmware"]) ==
                    (readback["stm_uid"], readback["esp_firmware"], readback["stm_firmware"]))
            age = readback["stm_source_age_ms"]
            age = age + max(0, math.ceil((now - started_parameters) * 1000)) if age is not None else None
            first_age = status_age + max(0, math.ceil((now - started) * 1000)) if status_age is not None else None
            if first_age is not None and age is not None:
                age = max(age, first_age)
            fresh = status["stm_connected"] and readback["stm_connected"] and age is not None and age <= TIMEOUT_MS
            result.update(service={key: value for key, value in readback.items() if key != "parameters"},
                          parameters=readback["parameters"],
                          freshness={"fresh": fresh, "effective_age_ms": age, "timeout_ms": TIMEOUT_MS})
            result["connection"] = {"status": "SERVICE_CONNECTED" if fresh else "STM_UNAVAILABLE",
                                    "detail": "Szervizmód — hajtás/kés tiltva." if fresh else "Az ESP elérhető, de nincs friss STM-kapcsolat."}
        except RoverReadError as error:
            result["connection"] = {"status": error.code, "detail": str(error)}
        finally:
            self.lock.release()
        return result


def register_mower_service_read(app, *, service):
    from flask import jsonify

    @app.get("/api/mower/v3/service/snapshot")
    def mower_service_snapshot():
        response = jsonify(service.snapshot())
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
