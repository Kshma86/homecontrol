"""Single-send discrete requests. Results are correlated STM evidence, not HTTP success."""
import json
import re
import threading
import time
import uuid

from mower_v3_protocol import (
    STATES, RoverReadError, UnknownMutation, hex_id, integer, require, request_id, motor_identity,
)

COMMANDS = {"arm", "disarm", "pause", "reset_fault", "heading_set", "start", "resume"}
ACK_FIELDS = {"v", "request_id", "command", "result", "code", "detail", "stm_boot", "control_epoch", "state_seq", "state"}


def validate_command(body, stop=False):
    require(type(body) is dict and set(body) == ({"v", "request_id"} if stop else
            {"v", "request_id", "esp_boot", "stm_boot", "control_epoch", "command", "value"}))
    require(type(body["v"]) is int and body["v"] == 3 and request_id(body["request_id"]))
    if stop:
        return
    require(hex_id(body["esp_boot"], 16, nonzero=True) and hex_id(body["stm_boot"], 16, nonzero=True)
            and integer(body["control_epoch"], 1))
    require(type(body["command"]) is str and body["command"] in COMMANDS)
    value = body["value"]
    if body["command"] == "heading_set":
        require(type(value) is dict and set(value) == {"heading_mdeg"} and integer(value["heading_mdeg"], 0, 359999))
    elif body["command"] in ("start", "resume"):
        require(type(value) is dict and set(value) == {"mission_id", "revision", "crc32"})
        require(type(value["mission_id"]) is str and len(value["mission_id"]) == 36)
        try:
            mission = uuid.UUID(value["mission_id"])
        except ValueError:
            require(False)
        require(mission.int != 0 and str(mission) == value["mission_id"].lower()
                and integer(value["revision"], 1) and hex_id(value["crc32"], 8))
    else:
        require(value is None)


def validate_ack(payload, expected_id, expected_command=None, expected_boot=None):
    require(type(payload) is dict and ACK_FIELDS <= set(payload))
    require(type(payload["v"]) is int and payload["v"] == 3 and payload["request_id"] == expected_id)
    require(type(payload["command"]) is str and payload["command"] in COMMANDS | {"stop"})
    require(expected_command is None or payload["command"] == expected_command)
    require(payload["result"] in ("APPLIED", "REJECTED", "UNKNOWN"))
    require(type(payload["code"]) is str and re.fullmatch(r"[A-Z_]{1,32}", payload["code"]) is not None)
    require(integer(payload["detail"]))
    require(payload["stm_boot"] is None or hex_id(payload["stm_boot"], 16, nonzero=True))
    for key in ("control_epoch", "state_seq"):
        require(payload[key] is None or integer(payload[key], 1))
    require(payload["state"] is None or type(payload["state"]) is str and payload["state"] in STATES)
    if payload["result"] == "APPLIED":
        require(payload["code"] == "OK" and payload["stm_boot"] is not None
                and payload["control_epoch"] is not None and payload["state_seq"] is not None and payload["state"] is not None)
        require(expected_boot is None or payload["stm_boot"] == expected_boot)
    return {key: payload[key] for key in ACK_FIELDS}


def outcome(id_, command, result, code):
    return {"ok": True, "v": 3, "request_id": id_, "command": command, "result": result, "code": code,
            "detail": 0, "stm_boot": None, "control_epoch": None, "state_seq": None, "state": None}


class MowerV3Commands:
    def __init__(self, rover):
        self.rover = rover
        self._lock = threading.Lock()
        self._records = {}
        self._retired = {}

    def submit(self, body, *, stop=False):
        if getattr(self.rover, "read_only", False) and not (getattr(self.rover, "motor_test_enabled", False)
                and (not stop or getattr(self.rover, "_test_identity", None) is not None)):
            return {"ok": False, "code": "READ_ONLY", "error": "Csak olvasó roverkapcsolat; parancsküldés tiltva."}, 403
        try:
            validate_command(body, stop)
        except RoverReadError:
            return {"ok": False, "code": "INVALID_PAYLOAD", "error": "Hibás v3 parancs."}, 400
        id_, command = body["request_id"], "stop" if stop else body["command"]
        if not self.rover.configured:
            return {"ok": False, "code": "UNCONFIGURED", "error": "A roverkapcsolat nincs beállítva."}, 503
        fingerprint = json.dumps(body, sort_keys=True, separators=(",", ":"))
        with self._lock:
            if id_ in self._retired:
                if self._retired[id_] != fingerprint:
                    return {"ok": False, "code": "ID_CONFLICT"}, 409
                return outcome(id_, command, "UNKNOWN", "HISTORY_EXPIRED"), 202
            previous = self._records.get(id_)
            if previous:
                if previous["fingerprint"] != fingerprint:
                    return {"ok": False, "code": "ID_CONFLICT", "error": "Az azonosítóhoz más parancs tartozik."}, 409
                return previous["outcome"].copy(), 200 if previous["outcome"]["result"] in ("APPLIED", "REJECTED") else 202
            if len(self._records) >= 128:
                terminal = next((key for key, record in self._records.items() if record["outcome"]["result"] in ("APPLIED", "REJECTED")), None)
                if terminal is None:
                    if not stop and not getattr(self.rover,"simple_control",False):
                        return {"ok": False, "code": "BUSY", "error": "A korábbi parancsok egyeztetése szükséges."}, 429
                    # A full ordinary ledger must never suppress a new STOP.
                    terminal = next(iter(self._records))
                self._retired[terminal] = self._records[terminal]["fingerprint"]
                if len(self._retired) > 512:
                    del self._retired[next(iter(self._retired))]
                del self._records[terminal]
            record = {"fingerprint": fingerprint, "at": self.rover.clock(), "boot": None,
                      "outcome": outcome(id_, command, "PENDING", "PENDING")}
            self._records[id_] = record
        try:
            if not stop:
                snapshot = self.rover.snapshot()
                state, identity = snapshot.get("state"), snapshot.get("identity")
                if (not snapshot["freshness"]["fresh"] or identity is None or state is None
                        or (identity["update_locked"] and identity.get("mode") != "MOTOR_TEST") or identity["compatible"] is not True
                        or identity["profile_crc"] == "00000000" and not getattr(self.rover,"simple_control",False)):
                    result = outcome(id_, command, "REJECTED", "NOT_READY")
                    return self._save(record, result), 409
                if (body["esp_boot"], body["stm_boot"], body["control_epoch"]) != (identity["esp_boot"], identity["stm_boot"], state["control_epoch"]):
                    return self._save(record, outcome(id_, command, "REJECTED", "STALE_SESSION")), 409
                if identity.get("mode") == "HC_BRINGUP":
                    return self._save(record, outcome(id_, command, "REJECTED", "READ_ONLY")), 409
                if identity.get("mode") == "MOTOR_TEST":
                    if not motor_identity(identity) or command not in {"arm", "disarm", "reset_fault"}:
                        return self._save(record, outcome(id_, command, "REJECTED", "TEST_MODE_ONLY")), 409
                    if command == "arm" and not getattr(self.rover,"simple_control",False) and not snapshot["capabilities"].get("manual_erpm"):
                        return self._save(record, outcome(id_, command, "REJECTED", "CONFIG_NOT_APPLIED")), 409
                if self.rover.read_only and not (self.rover.motor_test_enabled and identity.get("mode") == "MOTOR_TEST"):
                    return self._save(record, outcome(id_, command, "REJECTED", "READ_ONLY")), 409
                record["boot"] = identity["stm_boot"]
            record["at"] = self.rover.clock()
            code, payload = self.rover.request("POST", "/api/v3/stop" if stop else "/api/v3/command", body)
            if code == 200:
                result = {"ok": True, **validate_ack(payload, id_, command, record["boot"])}
            elif code == 202:
                require(payload.get("request_id") == id_)
                result = outcome(id_, command, "PENDING", "PENDING")
            else:
                remote_code = payload.get("code")
                safe_code = remote_code if type(remote_code) is str and re.fullmatch(r"[A-Z_]{1,32}", remote_code) else f"HTTP_{code}"
                definite_rejection = code < 500 or code == 503 and safe_code == "NOT_READY"
                result = outcome(id_, command, "REJECTED" if definite_rejection else "UNKNOWN", safe_code)
            return self._save(record, result), 202 if result["result"] in ("PENDING", "UNKNOWN") else 200
        except RoverReadError as error:
            if not stop and error.code in ("BUSY", "HC_UPDATE_PENDING", "UPDATE_STORAGE_UNAVAILABLE"):
                return self._save(record, outcome(id_, command, "REJECTED", error.code)), 409
            return self._save(record, outcome(id_, command, "UNKNOWN", "REPLY_LOST")), 202

    def _save(self, record, result):
        with self._lock:
            if record["outcome"]["result"] in ("APPLIED", "REJECTED"):
                return record["outcome"].copy()
            record["outcome"] = result
        return result.copy()

    def status(self, id_):
        if not request_id(id_):
            return {"ok": False, "code": "INVALID_PAYLOAD"}, 400
        with self._lock:
            record = self._records.get(id_)
            if record and record["outcome"]["result"] in ("APPLIED", "REJECTED"):
                return record["outcome"].copy(), 200
            command = record["outcome"]["command"] if record else None
        try:
            code, payload = self.rover.request("GET", "/api/v3/command/" + id_)
            if code == 200:
                result = {"ok": True, **validate_ack(payload, id_, command, record["boot"] if record else None)}
            elif code == 202 and record and self.rover.clock() - record["at"] <= 1.5:
                require(payload.get("request_id") == id_)
                result = outcome(id_, command, "PENDING", "PENDING")
            else:
                result = outcome(id_, command, "UNKNOWN", "NOT_FOUND" if code == 404 else "TIMEOUT")
        except RoverReadError:
            result = outcome(id_, command, "UNKNOWN", "LINK_LOST")
        if record:
            result = self._save(record, result)
        return result, 202 if result["result"] in ("PENDING", "UNKNOWN") else 200
