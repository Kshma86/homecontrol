"""Single rover configuration and explicit native RCP2 apply."""
import json
import threading
import os
from pathlib import Path

import rover_parameters as codec
from mower_parameters_service import DraftError, validate_draft
from mower_v3_commands import request_id
from mower_v3_service import RoverReadError, hex_id, integer, require


def motor_identity(identity):
    return (identity.get("mode") == "MOTOR_TEST" and identity.get("contract") == "3.1.0"
            and identity.get("compatible") is True and identity.get("manual_protocol") == "homecontrol.mower.manual.v3")


def validate_parameters_status(payload):
    require(type(payload) is dict and type(payload.get("v")) is int and payload["v"] == 3)
    for key in ("available", "source_valid", "can_apply", "busy", "applied", "commissioned", "motion_permitted"):
        require(type(payload.get(key)) is bool)
    require(payload["commissioned"] is False and payload["motion_permitted"] is False)
    require(payload.get("storage") in ("EMPTY", "ACTIVE", "PENDING", "FAULT"))
    require(type(payload.get("parameters_version")) is int and payload["parameters_version"] in (1, 2))
    for key in ("control_epoch", "revision"):
        require(integer(payload.get(key)))
    require(payload.get("source_age_ms") is None or integer(payload["source_age_ms"]))
    for key in ("esp_boot", "stm_boot"):
        require(type(payload.get(key)) is str and (payload[key] == "" or hex_id(payload[key], 16)))
    require(payload.get("request_id") is None or request_id(payload["request_id"]))
    require(payload.get("parameters_crc") is None or hex_id(payload["parameters_crc"], 8))
    require(type(payload.get("code")) is str and len(payload["code"]) <= 64)
    parameters = payload.get("parameters")
    if parameters is not None:
        try:
            codec.validate(parameters)
            require(parameters["parameters_version"] == payload["parameters_version"]
                    and f"{codec.checksum(parameters):08X}" == payload["parameters_crc"])
        except (ValueError, TypeError):
            require(False)
    if payload.get("necessary_parameters") is not None:
        try:
            codec.validate(payload["necessary_parameters"])
            require(parameters is not None and codec.necessary(parameters) == payload["necessary_parameters"])
        except (ValueError, TypeError):
            require(False)
    if "stored_parameters_valid" in payload or "stored_parameters" in payload:
        require(type(payload.get("stored_parameters_valid")) is bool)
        stored = payload.get("stored_parameters")
        require((stored is not None) == payload["stored_parameters_valid"])
        if stored is not None:
            try:
                codec.validate(stored)
                require(stored["parameters_version"] == payload["parameters_version"]
                        and f"{codec.checksum(stored):08X}" == payload["parameters_crc"])
            except (ValueError, TypeError):
                require(False)
    keys = ("v", "parameters_version", "esp_boot", "stm_boot", "control_epoch", "revision", "request_id",
            "parameters_crc", "storage", "busy", "available", "source_valid", "source_age_ms", "can_apply",
            "applied", "code", "parameters", "commissioned", "motion_permitted", "necessary_parameters", "stored_parameters_valid", "stored_parameters")
    return {key: payload.get(key) for key in keys}


def validate_motor_state(payload, identity):
    # Native MOTOR_TEST uses hex masks and independently timestamped SAFE evidence.
    # Keep the ordinary deployed schema unchanged.
    from mower_v3_service import validate_state
    require(type(payload) is dict)
    normalized = dict(payload, source_valid=False)
    for key in ("fault_mask", "safety_installed_mask", "safety_active_mask"):
        value = payload.get(key)
        require(value is None or hex_id(value, 8))
        normalized[key] = int(value, 16) if value is not None else None
    require(type(payload.get("source_valid")) is bool)
    require(type(payload.get("safety_source_valid")) is bool and integer(payload.get("safety_source_seq")))
    require(payload.get("safety_source_age_ms") is None or integer(payload["safety_source_age_ms"]))
    result = validate_state(normalized, identity)
    if payload["source_valid"]:
        require(integer(payload["source_seq"], 1) and integer(payload["source_age_ms"])
                and integer(payload["state_seq"], 1) and integer(payload["control_epoch"], 1)
                and integer(payload["event_seq"]) and result["fault_mask"] is not None
                and payload["state"] in {"DISARMED", "IDLE", "MANUAL", "FAULT"}
                and payload["armed"] == (payload["state"] in {"IDLE", "MANUAL"})
                and payload["phase"] == "NONE" and payload["store"] == "EMPTY"
                and payload["mission_id"] is None and payload["revision"] is None and payload["crc32"] is None
                and payload["segment_index"] == payload["segment_count"] == 0
                and payload["ready_for_start"] is False and payload["ready_for_resume"] is False)
        if payload["state"] == "MANUAL":
            require(integer(payload["manual_lease_id"], 1) and integer(payload["manual_input_seq"]))
        else:
            require(payload["manual_lease_id"] is None and payload["manual_input_seq"] is None)
    safe = payload["safety_source_valid"] and payload["safety_source_age_ms"] is not None and payload["safety_source_age_ms"] <= 1500
    if safe:
        require(integer(payload["safety_source_seq"], 1) and all(result[key] is not None for key in ("safety_installed_mask", "safety_active_mask")))
    else:
        result["safety_installed_mask"] = result["safety_active_mask"] = None
    return result | {"source_valid": payload["source_valid"], "safety_source_valid": bool(safe),
                     "safety_source_seq": payload["safety_source_seq"], "safety_source_age_ms": payload["safety_source_age_ms"]}


def parameters_fresh(parameters, identity, state):
    return (parameters["available"] and parameters["source_valid"] and parameters["source_age_ms"] is not None
            and parameters["source_age_ms"] <= 1500
            and (parameters["esp_boot"], parameters["stm_boot"], parameters["control_epoch"]) ==
                (identity["esp_boot"], identity["stm_boot"], state["control_epoch"]))


class MotorTestService:
    """One evolving HC configuration; no Apply ledger, history or global pending gate."""
    def __init__(self, rover, manual, config_path=None, pending_path=None):
        self.rover, self.manual = rover, manual
        self.config_path = Path(config_path) if config_path else None
        self._config = None
        self._lock = threading.Lock()

    def pending_info(self):
        return None

    def initial(self):
        parameters = json.loads((Path(__file__).parent / "static/rover_motor_test.initial.json").read_text())
        return {"ok": True, "parameters": parameters, "validation": validate_draft(parameters), "necessary_parameters": codec.necessary(parameters)}

    @staticmethod
    def committed(status):
        if status.get("stored_parameters_valid") is True:
            return status["stored_parameters"], "rover_stored"
        if (status.get("applied") is True and status.get("storage") == "ACTIVE"
                and status.get("source_valid") is True and status.get("source_age_ms") is not None
                and status["source_age_ms"] <= 1500 and status.get("parameters") is not None):
            return status["parameters"], "rover_applied"
        return None, None

    def configuration(self):
        status, error = None, None
        try:
            with self.rover.ordinary_operation():
                code, payload = self.rover.request("GET", "/api/v3/parameters")
                require(code == 200)
                status = validate_parameters_status(payload)
            parameters, source = self.committed(status)
        except RoverReadError as failure:
            parameters, source = None, None
            error = {"code": failure.code, "detail": str(failure)}
        if parameters is not None:
            self._config = parameters  # Read cache only; never writes the rover or HC file.
        else:
            parameters = self._config
            if parameters is None and self.config_path and self.config_path.exists():
                try:
                    parameters = json.loads(self.config_path.read_text())
                    codec.validate(parameters)
                except (ValueError, TypeError, OSError):
                    parameters = None
            source = "hc_cache" if parameters is not None else "unavailable"
        return {"ok": True, "parameters": parameters, "source": source, "rover_status": status, "read_error": error,
                "canonical_rcp": codec.encode(parameters).hex() if parameters is not None else None,
                "validation": validate_draft(parameters) if parameters is not None else None,
                "necessary_parameters": codec.necessary(parameters) if parameters is not None else None}

    def save_configuration(self, parameters):
        try:
            codec.validate(parameters)
        except (ValueError, TypeError, RoverReadError):
            raise DraftError("INVALID_PARAMETERS", "Valid RCP1, teljes RCP2 vagy kompakt ERPM konfiguráció szükséges.") from None
        if self.config_path:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.config_path.with_suffix(".tmp")
            with self._lock:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(descriptor, "w") as stream:
                    json.dump(parameters, stream, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.config_path)
        self._config = parameters
        return {"ok": True, "parameters": parameters, "validation": validate_draft(parameters), "saved": True}

    def status(self):
        with self.rover.ordinary_operation():
            snapshot = self.rover.snapshot()
        return {"ok": True, "snapshot": snapshot, "pending_apply": None}

    def apply(self, body):
        keys = {"v", "request_id", "esp_boot", "stm_boot", "control_epoch", "expected_revision", "parameters"}
        if (type(body) is not dict or set(body) != keys or type(body["v"]) is not int or body["v"] != 3
                or not request_id(body["request_id"]) or not integer(body["expected_revision"], 0, 0xfffffffe)
                or not integer(body["control_epoch"], 1)
                or not all(hex_id(body[key], 16, nonzero=True) for key in ("esp_boot", "stm_boot"))):
            raise DraftError("INVALID_PAYLOAD", "Hibás konfigurációs kérés.")
        try:
            codec.validate(body["parameters"])
        except (ValueError, TypeError, RoverReadError):
            raise DraftError("INVALID_PARAMETERS", "Valid RCP1/RCP2 konfiguráció szükséges.") from None
        if len(json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode("ascii")) > 2048:
            raise DraftError("INVALID_PAYLOAD", "A natív kérés legfeljebb 2048 bájt lehet.")
        with self.rover.ordinary_operation():
            snapshot = self.rover.snapshot()
            identity, state = snapshot.get("identity"), snapshot.get("state")
            if not identity or not state or not snapshot["freshness"]["fresh"]:
                raise DraftError("NOT_READY", "A rover jelenleg nem érhető el friss állapottal.", 409)
            if (body["esp_boot"],body["stm_boot"],body["control_epoch"]) != (identity["esp_boot"],identity["stm_boot"],state["control_epoch"]):
                raise DraftError("STALE_SESSION", "A rover közben újraindult vagy állapotot váltott; frissítsd az állapotot.",409)
            status = snapshot.get("parameters")
            if not status:
                raise DraftError("NOT_READY", "A rover konfigurációja nem olvasható.", 409)
            committed, _ = self.committed(status)
            if committed is not None and codec.encode(committed) == codec.encode(body["parameters"]):
                return {"ok": True, "result": "UNCHANGED", "code": "NO_CHANGE", "request_id": body["request_id"],
                        "expected_revision": status["revision"], "parameters_crc": status["parameters_crc"], "snapshot": snapshot}, 200
            if body["expected_revision"] != status.get("revision"):
                raise DraftError("CONFIG_CONFLICT", "A rover konfigurációja közben megváltozott; olvasd vissza és hasonlítsd össze.", 409, snapshot=snapshot)
            if not parameters_fresh(status, identity, state) or status.get("can_apply") is not True:
                raise DraftError("CONFIG_NOT_READY", f"A rover most nem fogad mentést: {status.get('code', 'NOT_READY')}.", 409, snapshot=snapshot)
            # Native CFG owns the remaining physical checks. Exactly one POST.
            result = {"ok": True, "result": "UNKNOWN", "code": "REPLY_LOST", "request_id": body["request_id"],
                      "expected_revision": body["expected_revision"]+1, "parameters_crc": f"{codec.checksum(body['parameters']):08X}"}
            try:
                code, reply = self.rover.request("POST", "/api/v3/parameters", body)
                if code == 202 and reply.get("request_id") == body["request_id"]:
                    result.update(result="PENDING",code="QUEUED")
                elif 400 <= code < 500:
                    remote_code = reply.get("code")
                    result.update(result="REJECTED",code=remote_code if type(remote_code) is str and remote_code.isascii() and remote_code.replace("_","").isalnum() else "CONFIG_REJECTED")
            except RoverReadError:
                pass
            return result,202

    def reconcile(self, body):
        require(type(body) is dict and set(body) == {"request_id","esp_boot","stm_boot","expected_revision","parameters_crc"})
        require(request_id(body["request_id"]) and integer(body["expected_revision"],1) and hex_id(body["parameters_crc"],8))
        snapshot = self.status()["snapshot"]
        status,identity,state = snapshot.get("parameters"),snapshot.get("identity"),snapshot.get("state")
        applied = bool(status and identity and state and snapshot["freshness"]["fresh"]
            and parameters_fresh(status,identity,state) and status["storage"] == "ACTIVE" and status["applied"]
            and status.get("request_id") == body["request_id"] and status.get("revision") == body["expected_revision"]
            and status.get("parameters_crc") == body["parameters_crc"])
        return {"ok":True,"result":"APPLIED" if applied else "UNKNOWN","request_id":body["request_id"],"snapshot":snapshot,"pending_apply":None}
