"""Native HC_BRINGUP diagnostics only; no operational admission or updater unlock."""
import math
import threading
import time

from mower_service_read import ServiceHttp
from mower_v3_service import (RoverReadError, STATE_TIMEOUT_MS, hex_id, integer,
                              require, validate_identity, validate_state)

PATHS = {"/api/v3/identity", "/api/v3/state", "/api/v3/update", "/api/v3/health"}


class BringupHttp(ServiceHttp):
    read_paths = PATHS


def bringup_identity(payload):
    result = validate_identity(payload)
    if (payload.get("mode") != "HC_BRINGUP" or payload.get("esp_fw") != "esp-hc-bringup-20261010"
            or payload.get("stm_fw") not in {None, "stm-hc-bringup-20261010"}):
        raise RoverReadError("INCOMPATIBLE_VERSION", "Nem a támogatott HC_BRINGUP firmware.")
    require((payload["stm_boot"] is None) == (payload["stm_fw"] is None))
    for key in ("conformant", "runtime_parameters", "stm_remote_update", "stm_reset_recovery",
                "motion_permitted", "commissioned", "profile_verified", "esp_ota_enabled"):
        require(payload.get(key) is False)
    require(payload["update_locked"] is True and payload["profile_crc"] == "00000000"
            and payload["stm_flash_layout"] == "H743_1M_STANDALONE"
            and payload["update_service_abi"] == 1 and payload["stm_image_max_bytes"] == 0
            and payload["stm_confirmed_slot"] is None and payload["stm_inactive_slot"] is None
            and payload["stm_bootloader_fw"] is None)
    return result | {key: payload[key] for key in
                     ("mode", "motion_permitted", "commissioned", "profile_verified", "esp_ota_enabled")}


def bringup_state(payload, identity):
    require(type(payload) is dict and type(payload.get("source_valid")) is bool)
    fault = payload.get("fault_mask")
    require(fault is None or hex_id(fault, 8))
    # Deliberately separate diagnostic schema: null safety evidence and hex fault
    # mask are NOT allowed to relax the ordinary, motion-admitting validator.
    normalized = dict(payload, source_valid=False, fault_mask=int(fault, 16) if fault is not None else None)
    result = validate_state(normalized, identity)
    require(payload.get("safety_source_valid") is False
            and payload.get("safety_installed_mask") is None and payload.get("safety_active_mask") is None
            and integer(payload.get("safety_source_seq")) and payload.get("safety_source_age_ms") is None)
    if payload["source_valid"]:
        require(identity["stm_boot"] is not None and integer(payload["source_seq"], 1)
                and integer(payload["source_age_ms"]) and integer(payload["state_seq"], 1)
                and integer(payload["control_epoch"], 1) and integer(payload["event_seq"])
                and payload["state"] == "DISARMED" and payload["armed"] is False
                and payload["phase"] == "NONE" and payload["store"] == "EMPTY"
                and payload["outcome"] == "NONE" and payload["reason"] is not None
                and payload["fault_mask"] is not None
                and payload["segment_index"] == 0 and payload["segment_count"] == 0
                and payload["mission_id"] is None and payload["revision"] is None and payload["crc32"] is None
                and payload["manual_lease_id"] is None and payload["manual_input_seq"] is None
                and payload["stopped"] is False
                and payload["ready_for_start"] is False and payload["ready_for_resume"] is False)
    return result | {key: payload[key] for key in ("source_valid", "fault_mask", "safety_source_valid",
                     "safety_source_seq", "safety_source_age_ms")}


def bringup_update(payload, identity):
    require(type(payload) is dict and type(payload.get("v")) is int and payload["v"] == 3
            and payload.get("esp_boot") == identity["esp_boot"])
    expected = {"locked": True, "phase": "ERROR", "error": "METADATA_ERROR",
                "detail": "AWAITING_SERVICE_STATUS", "source": "NONE", "source_valid": False,
                "image_bytes": 0, "http_received_bytes": 0, "stm_written_bytes": 0,
                "stop_evidence": "UNKNOWN", "can_retry": False, "can_finish": False,
                "update_id": None, "target": None, "stm_service_boot": None, "source_age_ms": None,
                "image_sha256": None, "fw_id": None, "confirmed_slot": None, "inactive_slot": None,
                "candidate_slot": None, "bootloader_fw": None, "can_active": None,
                "outputs_inhibited": None, "stop_evidence_age_ms": None}
    for key, value in expected.items():
        require(key in payload and type(payload[key]) is type(value) and payload[key] == value)
    require(integer(payload.get("last_phase_ms")))
    return {"v": 3, "esp_boot": payload["esp_boot"], "last_phase_ms": payload["last_phase_ms"]} | expected


def bringup_health(payload, identity):
    require(type(payload) is dict and type(payload.get("v")) is int and payload["v"] == 3
            and payload.get("esp_boot") == identity["esp_boot"])
    result = {"v": 3, "esp_boot": payload["esp_boot"]}
    for key in ("runtime_ready", "network_source_valid", "wifi_connected", "stm_peer_alive", "uart_rx_closed"):
        require(type(payload.get(key)) is bool)
        result[key] = payload[key]
    for key in ("published_ms", "esp_internal_free_bytes", "esp_largest_internal_block", "uart_admission_drops",
                "uart_tx_expired", "uart_input_errors", "gnss_input_errors", "uart_rx_faults",
                "uart_rx_discarded_bytes", "uart_rx_generation", "imu_resets", "sensor_mailbox_drops", "deadline_misses"):
        require(integer(payload.get(key)))
        result[key] = payload[key]
    for key in ("rssi_dbm", "network_source_age_ms", "rtcm_age_ms", "stm_busy_permille", "stm_supervisor_wcet_us",
                "stm_nav_wcet_us", "uart_crc_errors", "uart_overflows", "can_tx_errors", "telemetry_drops"):
        require(key in payload)
        value = payload[key]
        require(value is None or integer(value, -127 if key == "rssi_dbm" else 0,
                                        0 if key == "rssi_dbm" else 1000 if key == "stm_busy_permille" else 0xFFFFFFFF))
        result[key] = value
    require(not payload["network_source_valid"] or payload["network_source_age_ms"] is not None)
    require(payload.get("ntrip_state") == "DISCONNECTED")
    result["ntrip_state"] = payload["ntrip_state"]
    cores = payload.get("esp_core_busy_permille")
    require(type(cores) is list and len(cores) == 2 and all(x is None or integer(x, 0, 1000) for x in cores))
    result["esp_core_busy_permille"] = cores[:]
    result["esp_stack_min_bytes"], result["task_service"] = {}, {}
    for key in ("bridge", "gnss", "imu", "network", "frontend"):
        stacks, tasks = payload.get("esp_stack_min_bytes"), payload.get("task_service")
        require(type(stacks) is dict and key in stacks and (stacks[key] is None or integer(stacks[key])))
        require(type(tasks) is dict and key in tasks)
        result["esp_stack_min_bytes"][key] = stacks[key]
        task = tasks[key]
        if task is not None:
            require(type(task) is dict)
            clean = {}
            for metric in ("age_ms", "cycles", "max_gap_us", "max_elapsed_us", "service_misses"):
                require(integer(task.get(metric)))
                clean[metric] = task[metric]
            result["task_service"][key] = clean
        else:
            result["task_service"][key] = None
    return result


class MowerBringupRead:
    def __init__(self, *, origin="", token="", transport=None, clock=time.monotonic, activity_lock=None, guard=None):
        self.clock = clock
        self.lock = activity_lock if activity_lock is not None else threading.Lock()
        self.guard = guard or (lambda: None)
        self.transport, self.error, self.sample, self.health_sample = transport, None, None, None
        self.configuration = {"origin_configured": bool(origin), "token_configured": bool(token)}
        if transport is None:
            if not origin or not token:
                self.error = "A backendben rover LAN-cím és privát API-token szükséges."
            else:
                try:
                    self.transport = BringupHttp(origin, token)
                except ValueError:
                    self.error = "Hibás rover alapcím vagy tokenformátum."

    def snapshot(self):
        result = {"ok": True, "mode": "HC_BRINGUP", "read_only": True, "hardware_qualified": False,
                  "configured": self.error is None, "configuration": self.configuration.copy(),
                  "identity": None, "state": None, "update": None, "health": None,
                  "capabilities": {key: False for key in ("manual", "commands", "mission_upload", "runtime_parameters", "stm_update", "esp_update")},
                  "connection": {"status": "UNCONFIGURED", "detail": self.error},
                  "freshness": {"fresh": False, "effective_age_ms": None, "timeout_ms": STATE_TIMEOUT_MS},
                  "health_freshness": {"fresh": False, "effective_age_ms": None, "timeout_ms": 3000}}
        if self.error:
            return result
        if not self.lock.acquire(blocking=False):
            result["connection"] = {"status": "BUSY", "detail": "Egy roverlekérés vagy művelet már folyamatban van."}
            return result
        try:
            self.guard()
            identity = bringup_identity(self.transport.get("/api/v3/identity"))
            result["identity"] = identity
            started = self.clock()
            state = bringup_state(self.transport.get("/api/v3/state"), identity)
            update = bringup_update(self.transport.get("/api/v3/update"), identity)
            health_started = self.clock()
            health = bringup_health(self.transport.get("/api/v3/health"), identity)
            now = self.clock()
            age = state["source_age_ms"]
            if age is not None:
                age += max(0, math.ceil((now - started) * 1000))
            key = state["esp_boot"], state["stm_boot"], state["source_seq"]
            evidence = {k: v for k, v in state.items() if k not in ("published_ms", "source_age_ms", "source_valid")}
            fresh = state["source_valid"] and age is not None and age <= STATE_TIMEOUT_MS and identity["compatible"]
            if self.sample and self.sample["key"][:2] == key[:2]:
                delta = (key[2] - self.sample["key"][2]) & 0xFFFFFFFF
                if delta == 0:
                    require(not state["source_valid"] or self.sample["evidence"] == evidence)
                    age = max(age, self.sample["age"] + math.ceil((now - self.sample["at"]) * 1000)) if age is not None else None
                    fresh = fresh and age is not None and age <= STATE_TIMEOUT_MS
                elif delta >= 0x80000000:
                    fresh = False
                else:
                    if state["source_valid"]:
                        epoch_delta = (state["control_epoch"] - self.sample["evidence"]["control_epoch"]) & 0xFFFFFFFF
                        require(epoch_delta < 0x80000000)
                    self.sample = None
            else:
                self.sample = None
            if self.sample is None and state["source_valid"] and age is not None:
                self.sample = {"key": key, "age": age, "at": now, "evidence": evidence}
            health_age = health["network_source_age_ms"]
            if health_age is not None:
                health_age += max(0, math.ceil((now - health_started) * 1000))
            health_fresh = health["network_source_valid"] and health_age is not None and health_age <= 3000
            health_key = health["esp_boot"], health["published_ms"]
            if self.health_sample and self.health_sample["key"][0] == health_key[0]:
                delta = (health_key[1] - self.health_sample["key"][1]) & 0xFFFFFFFF
                if delta == 0:
                    health_age = max(health_age, self.health_sample["age"] + math.ceil((now - self.health_sample["at"]) * 1000)) if health_age is not None else None
                    health_fresh = health_fresh and health_age is not None and health_age <= 3000
                elif delta >= 0x80000000:
                    health_fresh = False
                else:
                    self.health_sample = None
            else:
                self.health_sample = None
            if self.health_sample is None and health["network_source_valid"] and health_age is not None:
                self.health_sample = {"key": health_key, "age": health_age, "at": now}
            result.update(state=state, update=update, health=health,
                          freshness={"fresh": bool(fresh), "effective_age_ms": age, "timeout_ms": STATE_TIMEOUT_MS},
                          health_freshness={"fresh": bool(health_fresh),
                                            "effective_age_ms": health_age, "timeout_ms": 3000})
            result["connection"] = {"status": "BRINGUP_CONNECTED" if fresh else "STALE",
                                    "detail": "HC kapcsolat működik — csak olvasó, nem üzembe helyezett." if fresh
                                    else "Az ESP elérhető; az STM-állapot hiányzik vagy elavult."}
        except RoverReadError as error:
            result["connection"] = {"status": error.code, "detail": str(error)}
        finally:
            self.lock.release()
        return result


def register_mower_bringup_read(app, *, service):
    from flask import jsonify

    @app.get("/api/mower/v3/bringup/snapshot")
    def mower_bringup_snapshot():
        response = jsonify(service.snapshot())
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
