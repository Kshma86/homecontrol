"""Explicit VG single-send update operations and independently verified HC exit."""
import hashlib
import math
import re
import struct

import psycopg
from mower_firmware_service import FirmwareError, valid_token
from mower_firmware_staging import request_token
from mower_v3_service import RoverReadError, hex_id, integer, require, validate_identity, validate_state

PHASES = {"IDLE", "QUIESCING", "READY", "RECEIVING", "ERASING", "WRITING", "VERIFYING", "TRIAL", "COMPLETE", "ABORTED", "ERROR", "EXITING"}
FIELDS = {"v", "update_id", "target", "locked", "phase", "error", "detail", "esp_boot", "stm_service_boot", "source",
          "source_age_ms", "source_valid", "image_bytes", "http_received_bytes", "stm_written_bytes", "image_sha256", "fw_id",
          "confirmed_slot", "inactive_slot", "candidate_slot", "bootloader_fw", "last_phase_ms", "can_active", "outputs_inhibited",
          "stop_evidence", "stop_evidence_age_ms", "can_retry", "can_finish"}


def validate_update(payload, capacity):
    require(type(payload) is dict and FIELDS <= set(payload) and type(payload["v"]) is int and payload["v"] == 3)
    require(payload["update_id"] is None or hex_id(payload["update_id"], 32, nonzero=True))
    require(payload["target"] is None or type(payload["target"]) is str and payload["target"] in {"STM", "ESP"})
    require(type(payload["phase"]) is str and payload["phase"] in PHASES)
    require(type(payload["error"]) is str and re.fullmatch(r"[A-Z_]{1,32}", payload["error"]) is not None)
    require(type(payload["detail"]) is str and re.fullmatch(r"[A-Za-z0-9_.-]{0,48}", payload["detail"]) is not None)
    require(hex_id(payload["esp_boot"], 16, nonzero=True))
    require(payload["stm_service_boot"] is None or hex_id(payload["stm_service_boot"], 16, nonzero=True))
    for key in ("locked", "source_valid", "can_retry", "can_finish"):
        require(type(payload[key]) is bool)
    require(type(payload["source"]) is str and payload["source"] in {"ESP", "STM_APP", "STM_LOADER", "STM_TRIAL", "NONE"})
    for key in ("source_age_ms", "stop_evidence_age_ms"):
        require(payload[key] is None or integer(payload[key]))
    require(integer(payload["last_phase_ms"]))
    require(integer(payload["image_bytes"], 0, capacity) and integer(payload["http_received_bytes"], 0, payload["image_bytes"]))
    require(payload["stm_written_bytes"] is None and payload["target"] != "STM" or integer(payload["stm_written_bytes"], 0, payload["image_bytes"]))
    require(payload["image_sha256"] is None or type(payload["image_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", payload["image_sha256"]) is not None)
    require(payload["fw_id"] is None or valid_token(payload["fw_id"], 48))
    require(payload["bootloader_fw"] is None or valid_token(payload["bootloader_fw"], 48))
    for key, allowed in (("confirmed_slot", {"A", "B", "NONE"}), ("inactive_slot", {"A", "B"}), ("candidate_slot", {"A", "B", "NONE"})):
        require(payload[key] is None or type(payload[key]) is str and payload[key] in allowed)
    for key in ("can_active", "outputs_inhibited"):
        require(payload[key] is None or type(payload[key]) is bool)
    require(type(payload["stop_evidence"]) is str and payload["stop_evidence"] in {"MEASURED", "POWER_INHIBIT", "UNKNOWN"})
    if payload["update_id"] is None:
        require(payload["target"] is None and payload["phase"] == "IDLE" and not payload["locked"])
    if payload["source_valid"]:
        require(payload["source"] != "NONE" and payload["source_age_ms"] is not None)
        if payload["source"].startswith("STM_"):
            require(payload["stm_service_boot"] is not None)
    if payload["image_bytes"] == 0:
        require(payload["image_sha256"] is None and payload["fw_id"] is None)
    else:
        require(payload["image_sha256"] is not None and payload["fw_id"] is not None)
    return {key: payload[key] for key in FIELDS}


def vg_identity(identity):
    return (identity["stm_remote_update"] is True and identity["update_service_abi"] == 2
            and identity["stm_flash_layout"] == "H743_1M_QSPI2" and identity["stm_image_max_bytes"] == 524288
            and identity["profile_crc"] != "00000000" and identity["stm_confirmed_slot"] is None and identity["stm_inactive_slot"] is None)


def attempt_descriptor(row):
    return {"request_id": row["request_id"], "hc_job_id": row["hc_job_id"], "state": row["state"], "active": row["active"],
            "update_id": row["update_id"], "esp_boot": row["esp_boot"], "profile_crc": row["profile_crc"], "revision": row["revision"],
            "code": row["code"], "persisted": True, "created_at": row["created_at"].isoformat(), "updated_at": row["updated_at"].isoformat(),
            "closed": row.get("closed", False),
            "progress_path": "/api/v3/update/" + row["update_id"] if row["update_id"] else None}


class MowerFirmwareUpdates:
    def __init__(self, *, rover, preflight, staging, sessions, manual, operations=None):
        self.rover, self.preflight, self.staging, self.sessions, self.manual = rover, preflight, staging, sessions, manual
        self.operations = operations
        rover.maintenance_guard = self.guard

    def guard(self):
        if getattr(self.rover, "simple_control", False):
            return
        try:
            if self.operations:
                self.operations.ensure_schema()
            if self.sessions.active():
                raise RoverReadError("HC_UPDATE_PENDING", "A HC frissítési szándék/session miatt az üzemi vezérlés zárolva van.")
        except psycopg.Error:
            raise RoverReadError("UPDATE_STORAGE_UNAVAILABLE", "A tartós frissítési zárolás nem ellenőrizhető; az üzemi vezérlés letiltva.") from None

    def result(self, row=None, code="WAITING"):
        actions = self.operations.history(row["request_id"]) if self.operations and row else []
        return {"ok": True, "scope": "HC_NATIVE_SESSION", "configured": self.rover.configured,
                "attempt": attempt_descriptor(row) if row else None, "identity": None, "observation": None,
                "connection": {"status": code}, "bound": False, "can_create": False,
                "ordinary_blocked": bool(row and row["active"]), "ready": False, "installation_confirmed": False,
                "freshness": {"fresh": False, "effective_age_ms": None, "timeout_ms": 2000},
                "upload_available": False, "abort_available": False, "finish_available": False,
                "hardware_qualified": False, "normal_mode_verified": False,
                "operations": [operation_descriptor(action) for action in actions],
                "exit_check_available": bool(row and row["active"] and any(action["action"] == "FINISH" and action["state"] != "REJECTED" for action in actions))}

    def create(self, job_id, body):
        if getattr(self.rover, "read_only", False):
            raise FirmwareError("READ_ONLY", "Csak olvasó roverkapcsolat; frissítési session tiltva.", 403)
        if type(body) is not dict or set(body) != {"request_id", "confirm_runtime_discard"} or body["confirm_runtime_discard"] is not True:
            raise FirmwareError("INVALID_PAYLOAD", "A futó küldetés/heading/kézi session törlésének explicit megerősítése szükséges.")
        id_ = request_token(body["request_id"])
        # Validate the HC ID before any native access, including exact replay.
        self.staging.job(job_id)
        previous = self.sessions.request(id_)
        if previous:
            if previous["hc_job_id"] != job_id:
                raise FirmwareError("ID_CONFLICT", "A session kérésazonosítójához más HC-feladat tartozik.", 409)
            return self.result(previous, previous["state"])
        if not self.rover.configured:
            raise FirmwareError("UNCONFIGURED", "A natív roverkapcsolat nincs beállítva.", 503)
        if not self.rover.activity_lock.acquire(blocking=False):
            raise FirmwareError("BUSY", "Másik vezérlési művelet folyamatban van.", 409)
        audited = False
        try:
            self.guard()
            if self.manual.active:
                raise FirmwareError("MANUAL_ACTIVE", "A kézi kapcsolatot előbb kifejezetten le kell zárni.", 409)
            if not self.preflight.preflight_lock.acquire(blocking=False):
                raise FirmwareError("PREFLIGHT_BUSY", "Másik firmware-ellenőrzés folyamatban van.", 429)
            audited = True
            stored = self.staging.store.job(job_id)
            image, elf = self.staging.store.artifact(stored["artifact_id"])
            envelope = struct.pack("<I", len(image)) + image + elf
            if hashlib.sha256(envelope).hexdigest() != stored["artifact_id"]:
                raise FirmwareError("ARTIFACT_CORRUPT", "A megőrzött firmware-fájlok nem egyeznek a mentés lenyomatával.", 409)
            report = self.preflight.preflight(envelope, stored["release_id"])
            identity, current, _ = self.observe()
            if not vg_identity(identity):
                raise FirmwareError("UPDATE_UNSUPPORTED", "Telepített VG / ABI2 natív frissítési képesség szükséges.", 409)
            if report["metadata"]["profile_crc"] != identity["profile_crc"]:
                raise FirmwareError("PROFILE_MISMATCH", "A kiadás nem a jelenleg telepített roverprofilhoz tartozik.", 409)
            if identity["update_locked"] or current["locked"] or current["phase"] != "IDLE":
                raise FirmwareError("UPDATE_MODE", "A rover korábbi frissítési állapotának explicit egyeztetése szükséges.", 409)
            kwargs = {"initial_stm_boot": identity["stm_boot"]} if self.operations else {}
            row, send = self.sessions.reserve(id_, job_id, self.rover.connection_key, identity["esp_boot"], identity["profile_crc"], **kwargs)
            if not send:
                return self.result(row, row["state"])
            # reserve() MUST commit before this call. No code ever retries it.
            state, code, update_id = "UNKNOWN", "REPLY_LOST", None
            try:
                status, reply = self.rover.request("POST", "/api/v3/update", {"v": 3, "request_id": id_, "esp_boot": identity["esp_boot"], "target": "STM"})
                if status == 202:
                    require(hex_id(reply.get("update_id"), 32, nonzero=True))
                    require("request_id" not in reply or reply["request_id"] == id_)
                    require("esp_boot" not in reply or reply["esp_boot"] == identity["esp_boot"])
                    require("target" not in reply or reply["target"] == "STM")
                    state, code, update_id = "ADMITTED", "ADMITTED", reply["update_id"]
                elif status in (400, 401, 403, 404, 409, 413, 422, 423, 501):
                    remote_code = reply.get("code")
                    state, code = "REJECTED", remote_code if type(remote_code) is str and re.fullmatch(r"[A-Z_0-9]{1,32}", remote_code) else f"HTTP_{status}"
            except RoverReadError:
                pass
            row = self.sessions.complete(id_, state, code, update_id)
            return self.result(row, row["state"])
        except RoverReadError as error:
            # Only pre-send reads/guard reach here; mutation errors stay durable UNKNOWN.
            raise FirmwareError(error.code, str(error), 409 if error.code == "HC_UPDATE_PENDING" else 503) from None
        finally:
            if audited:
                self.preflight.preflight_lock.release()
            self.rover.activity_lock.release()

    def observe(self, update_id=None):
        status, payload = self.rover.request("GET", "/api/v3/identity")
        require(status == 200)
        identity = validate_identity(payload)
        started = self.rover.clock()
        status, payload = self.rover.request("GET", "/api/v3/update" + ("/" + update_id if update_id else ""))
        if status == 404:
            raise RoverReadError("NOT_FOUND", "A megőrzött natív session nem található; nincs újraküldés.")
        require(status == 200)
        capacity = identity["stm_image_max_bytes"] if payload.get("target") == "STM" else max(identity["stm_image_max_bytes"], identity["esp_ota_max_bytes"])
        current = validate_update(payload, capacity)
        require(current["esp_boot"] == identity["esp_boot"])
        age = current["source_age_ms"]
        if age is not None:
            age += max(0, math.ceil((self.rover.clock() - started) * 1000))
        return identity, current, age

    def current(self):
        return self.read(self.sessions.active())

    def request_status(self, id_):
        row = self.sessions.request(request_token(id_))
        result = self.read(row) if row else self.result(code="NOT_FOUND")
        result["found"] = row is not None
        return result

    def read(self, row):
        result = self.result(row)
        if not self.rover.configured:
            result["connection"] = {"status": "UNCONFIGURED"}
            return result
        if row and row["connection_key"] != self.rover.connection_key:
            result["connection"] = {"status": "ENDPOINT_CHANGED"}
            return result
        try:
            identity, current, age = self.observe(row["update_id"] if row else None)
            result.update(identity=identity, observation=current)
            result["ordinary_blocked"] = result["ordinary_blocked"] or identity["update_locked"] or current["locked"]
            if row and row["esp_boot"] != identity["esp_boot"]:
                result["connection"] = {"status": "BOOT_CHANGED"}
                return result
            if row and row["update_id"]:
                require(current["update_id"] == row["update_id"] and current["target"] == "STM" and vg_identity(identity)
                        and identity["profile_crc"] == row["profile_crc"]
                        and all(current[key] is None for key in ("confirmed_slot", "inactive_slot", "candidate_slot")))
                result["bound"] = True
            fresh = (current["source_valid"] and current["source"].startswith("STM_") and age is not None and age <= 2000)
            result["freshness"] = {"fresh": bool(fresh), "effective_age_ms": age, "timeout_ms": 2000}
            loader = (result["bound"] and fresh and current["source"] == "STM_LOADER" and current["locked"]
                      and current["can_active"] is False and current["outputs_inhibited"] is True and current["error"] == "NONE")
            result["ready"] = bool(loader and current["phase"] == "READY")
            recorded = {action["action"] for action in result["operations"]}
            enabled = self.operations is not None and bool(row and row["active"] and result["bound"])
            result["upload_available"] = bool(enabled and result["ready"] and current["image_bytes"] == 0 and "IMAGE" not in recorded)
            result["abort_available"] = bool(enabled and fresh and current["locked"] and current["phase"] in {"QUIESCING", "READY", "RECEIVING", "ERASING", "WRITING", "VERIFYING", "TRIAL"} and "ABORT" not in recorded)
            result["finish_available"] = bool(enabled and fresh and current["source"] == "STM_LOADER" and current["locked"]
                and current["can_active"] is False and current["outputs_inhibited"] is True and current["can_finish"]
                and current["phase"] in {"COMPLETE", "ABORTED", "ERROR"} and "FINISH" not in recorded)
            if loader and current["phase"] == "COMPLETE":
                job = self.staging.job(row["hc_job_id"])
                metadata = job["metadata"]
                result["installation_confirmed"] = (current["image_bytes"] == metadata["image_bytes"]
                    and current["image_sha256"] == metadata["image_sha256"] and current["fw_id"] == metadata["fw_id"])
            result["can_create"] = not row and vg_identity(identity) and not result["ordinary_blocked"] and current["phase"] == "IDLE"
            result["connection"] = {"status": "UNBOUND" if row and not result["bound"] else "LIVE" if fresh else "IDLE" if current["phase"] == "IDLE" else "STALE"}
            return result
        except (RoverReadError, FirmwareError) as error:
            result["connection"] = {"status": error.code}
            return result

    def action_status(self, id_):
        if not self.operations:
            raise FirmwareError("UPDATE_UNAVAILABLE", "A natív műveletkezelés nem érhető el.", 503)
        id_ = request_token(id_)
        row = self.operations.request(id_)
        if row:
            return action_result(row)
        closed = self.operations.exit_request(id_)
        return exit_result(closed) if closed else {"ok": True, "scope": "HC_UPDATE_ACTION", "found": False}

    def action(self, session_id, action, body):
        if getattr(self.rover, "read_only", False) and action != "VERIFY_EXIT":
            raise FirmwareError("READ_ONLY", "Csak olvasó roverkapcsolat; frissítési művelet tiltva.", 403)
        if not self.operations or action not in {"IMAGE", "ABORT", "FINISH", "VERIFY_EXIT"}:
            raise FirmwareError("UPDATE_UNAVAILABLE", "Nem támogatott frissítési művelet.", 503)
        if type(body) is not dict or set(body) != {"request_id"}:
            raise FirmwareError("INVALID_PAYLOAD", "Pontos request_id objektum szükséges.")
        id_, session_id = request_token(body["request_id"]), request_token(session_id)
        previous = self.operations.exit_request(id_) if action == "VERIFY_EXIT" else self.operations.request(id_)
        if previous:
            if previous["session_request_id"] != session_id or action != "VERIFY_EXIT" and previous["action"] != action:
                raise FirmwareError("ID_CONFLICT", "Eltérő művelet/session kérésazonosító.", 409)
            return exit_result(previous) if action == "VERIFY_EXIT" else action_result(previous)
        row = self.sessions.request(session_id)
        if not row or not row["active"] or row["state"] != "ADMITTED":
            raise FirmwareError("SESSION_UNBOUND", "Aktív, megőrzött natív session szükséges.", 409)
        if row["connection_key"] != self.rover.connection_key:
            raise FirmwareError("ENDPOINT_CHANGED", "A megőrzött roverkapcsolat megváltozott.", 409)
        if not self.rover.activity_lock.acquire(blocking=False):
            raise FirmwareError("BUSY", "Másik vezérlési/frissítési művelet folyamatban van.", 409)
        audited = False
        try:
            if action == "VERIFY_EXIT":
                proof = self.normal_proof(row)
                checked_at = self.rover.clock()
                def check():
                    if proof["source_age_ms"] + max(0, math.ceil((self.rover.clock()-checked_at)*1000)) > 1500:
                        raise FirmwareError("PROOF_EXPIRED", "A normál állapot igazolása a HC-mentés előtt elavult.", 409)
                # Invalidate all old executable/process-local control objects before release.
                self.rover.commands = None
                self.rover._sample = None
                return exit_result(self.operations.close(id_, session_id, proof, check=check))
            if any(item["action"] == action for item in self.operations.history(session_id)):
                raise FirmwareError("ACTION_RECORDED", "Már naplózott művelet; csak GET-egyeztetés engedélyezett.", 409)
            image, metadata = None, None
            if action == "IMAGE":
                if not self.preflight.preflight_lock.acquire(blocking=False):
                    raise FirmwareError("PREFLIGHT_BUSY", "Másik firmware-ellenőrzés folyamatban van.", 429)
                audited = True
                stored = self.staging.store.job(row["hc_job_id"])
                image, elf = self.staging.store.artifact(stored["artifact_id"])
                envelope = struct.pack("<I", len(image)) + image + elf
                if hashlib.sha256(envelope).hexdigest() != stored["artifact_id"]:
                    raise FirmwareError("ARTIFACT_CORRUPT", "A megőrzött firmware-fájlpár lenyomata eltér.", 409)
                metadata = self.preflight.preflight(envelope, stored["release_id"])["metadata"]
                if metadata["profile_crc"] != row["profile_crc"]:
                    raise FirmwareError("PROFILE_MISMATCH", "Eltérő kiadási profil.", 409)
            current = self.read(row)
            checked_at = self.rover.clock()
            if not current[{"IMAGE": "upload_available", "ABORT": "abort_available", "FINISH": "finish_available"}[action]]:
                raise FirmwareError("UPDATE_NOT_READY", "Nincs friss, kötött natív engedély erre a műveletre.", 409)
            op, send = self.operations.reserve(id_, session_id, action, current["observation"]["stm_service_boot"])
            if not send:
                return action_result(op)
            if current["freshness"]["effective_age_ms"] + max(0, math.ceil((self.rover.clock()-checked_at)*1000)) > 2000:
                return action_result(self.operations.complete(id_, "REJECTED", "PROOF_EXPIRED"))
            state, code = "UNKNOWN", "REPLY_LOST"
            try:
                status, reply = self.rover.update_mutation(action, row["update_id"], image, metadata)
                require(type(reply) is dict and reply.get("v") == 3)
                require("update_id" not in reply or reply["update_id"] == row["update_id"])
                if status == 202:
                    state, code = "ADMITTED", "ADMITTED"
                elif status in (400, 401, 403, 404, 409, 413, 422, 423, 501):
                    remote = reply.get("code")
                    state, code = "REJECTED", remote if type(remote) is str and re.fullmatch(r"[A-Z_0-9]{1,32}", remote) else f"HTTP_{status}"
            except RoverReadError:
                pass
            return action_result(self.operations.complete(id_, state, code))
        except RoverReadError as error:
            raise FirmwareError(error.code, str(error), 409) from None
        finally:
            if audited:
                self.preflight.preflight_lock.release()
            self.rover.activity_lock.release()

    def normal_proof(self, row):
        finish = next((op for op in self.operations.history(row["request_id"]) if op["action"] == "FINISH"), None)
        if not finish or finish["state"] == "REJECTED":
            raise FirmwareError("EXIT_NOT_AUTHORIZED", "Explicit megőrzött FINISH-szándék szükséges.", 409)
        identity, current, _ = self.observe()
        require(identity["esp_boot"] == row["esp_boot"] and identity["profile_crc"] == row["profile_crc"]
                and vg_identity(identity) and identity["compatible"] and not identity["update_locked"]
                and current["phase"] == "IDLE" and not current["locked"] and current["error"] == "NONE"
                and current["update_id"] in (None, row["update_id"]))
        started = self.rover.clock()
        status, payload = self.rover.request("GET", "/api/v3/state")
        require(status == 200)
        state = validate_state(payload, identity)
        age = state["source_age_ms"] + max(0, math.ceil((self.rover.clock()-started)*1000)) if state["source_age_ms"] is not None else None
        require(state["source_valid"] and age is not None and age <= 1500
                and state["stm_boot"] != finish["service_boot"] and state["stm_boot"] != row.get("initial_stm_boot") and state["armed"] is False
                and state["store"] == "EMPTY" and state["mission_id"] is None and state["revision"] in (None, 0)
                and state["crc32"] in (None, "00000000") and state["segment_index"] == 0 and state["segment_count"] == 0
                and state["manual_lease_id"] in (None, 0) and state["manual_input_seq"] in (None, 0)
                and not state["ready_for_start"] and not state["ready_for_resume"])
        require(state["state"] == "DISARMED" and state["fault_mask"] == 0 and state["safety_active_mask"] == 0
                or state["state"] == "FAULT" and state["fault_mask"] != 0 and state["fault_mask"] & ~7 == 0
                and state["fault_mask"] == state["safety_active_mask"])
        # HTTP STATE does not expose motor targets. Native unlocked IDLE attests
        # its separately measured zero-target restart barrier (§17.8); do not invent fields.
        return {"esp_boot": identity["esp_boot"], "stm_boot": state["stm_boot"], "profile_crc": identity["profile_crc"],
                "control_epoch": state["control_epoch"], "state": state["state"], "store": "EMPTY",
                "fault_mask": state["fault_mask"], "source_age_ms": age, "zero_targets_authority": "NATIVE_IDLE_RESTART_BARRIER"}


def operation_descriptor(row):
    return {key: row[key] for key in ("request_id", "session_request_id", "action", "state", "code", "service_boot")} | {
        "persisted": True, "created_at": row["created_at"].isoformat(), "updated_at": row["updated_at"].isoformat()}


def action_result(row):
    return {"ok": True, "scope": "HC_UPDATE_ACTION", "found": True, "operation": operation_descriptor(row), "exit": None}


def exit_result(row):
    return {"ok": True, "scope": "HC_UPDATE_ACTION", "found": True, "operation": None,
            "exit": {"request_id": row["request_id"], "session_request_id": row["session_request_id"], "persisted": True,
                     "created_at": row["created_at"].isoformat(), "proof": row["proof"]}}
