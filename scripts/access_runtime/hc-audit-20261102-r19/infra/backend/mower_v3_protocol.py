"""Pure rover wire contracts shared by transports and control services.

No I/O, ownership, retries or device actions belong in this module.
The former public import paths remain aliases for compatibility.
"""


import re

import rover_parameters as codec


CONTRACT = "3.1.0"
MANUAL_PROTOCOL = "homecontrol.mower.manual.v3"
STATES = {"DISARMED", "IDLE", "MANUAL", "AUTO", "PAUSED", "FAULT", "MAINTENANCE"}


class RoverReadError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class UnknownMutation(RoverReadError):
    def __init__(self):
        super().__init__("REPLY_LOST", "A művelet eredménye ismeretlen; csak olvasási egyeztetés végezhető.")


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


def request_id(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is not None


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
