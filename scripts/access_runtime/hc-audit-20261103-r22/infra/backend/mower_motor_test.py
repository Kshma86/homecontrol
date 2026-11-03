"""Single rover configuration and explicit native RCP2 apply."""
import json
import threading
import os
from pathlib import Path

import rover_parameters as codec
from mower_parameters_service import DraftError, validate_draft
from mower_v3_protocol import (
    request_id, RoverReadError, hex_id, integer, require, motor_identity,
    validate_parameters_status, validate_motor_state, parameters_fresh,
)


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
