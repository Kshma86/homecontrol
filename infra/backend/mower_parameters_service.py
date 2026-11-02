"""HC-only RCP1 drafts. No rover transport, commissioning or live-apply path."""
import hashlib
import json
import re

import rover_parameters as rcp1
from mower_v3_protocol import request_id, integer

LIMIT = 16384
MAX_REVISION = 0xFFFFFFFF


class DraftError(Exception):
    def __init__(self, code, message, status=400, **data):
        super().__init__(message)
        self.code, self.status, self.data = code, status, data


def rover_key(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value) is None:
        raise DraftError("INVALID_ROVER_KEY", "A HC roverazonosító 1–32 ASCII betű, szám, _ vagy - lehet.")
    return value


def template():
    return {key: 1 if key == "parameters_version" else None for key in sorted(rcp1.FIELDS)}


def canonical_draft(parameters):
    return json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def parse_json(raw):
    if type(raw) not in (bytes, str) or len(raw.encode("utf-8") if type(raw) is str else raw) > LIMIT:
        raise DraftError("INVALID_PAYLOAD", "A paraméteradat legfeljebb 16 KiB lehet.")
    try:
        text = raw.decode("utf-8") if type(raw) is bytes else raw
        depth, quoted, escaped = 0, False, False
        for character in text:
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character in "[{":
                depth += 1
                if depth > 6:
                    raise ValueError("Excessive JSON nesting")
            elif character in "]}":
                depth -= 1
        result = json.loads(text, object_pairs_hook=rcp1.reject_duplicates, parse_constant=rcp1.reject_constant)
        if type(result) is not dict:
            raise ValueError("Expected object")
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise DraftError("INVALID_PAYLOAD", "Hibás JSON: duplikált kulcs és nem véges szám sem engedélyezett.") from None


def validate_draft(parameters):
    if type(parameters) is dict and type(parameters.get("parameters_version")) is int and parameters["parameters_version"] == 2:
        if set(parameters) not in (rcp1.V2_FIELDS, rcp1.MINIMAL_FIELDS, rcp1.MINIMAL_FIELDS | rcp1.BLADE_FIELDS):
            raise DraftError("INVALID_PARAMETERS", "Teljes RCP2 vagy kompakt ERPM 10/13 mező szükséges.")
        errors = []
        try:
            rcp1.validate(parameters)
        except (ValueError, TypeError):
            errors = [{"field": "parameters", "message": "A teljes RCP2 paraméteradat érvénytelen."}]
        canonical = canonical_draft(parameters) if not errors else None
        return {"valid": not errors, "saveable": not errors, "missing": [], "errors": errors,
                "draft_sha256": hashlib.sha256(canonical.encode("ascii")).hexdigest() if canonical else None,
                "rcp1_crc32": f"{rcp1.checksum(parameters):08X}" if not errors else None,
                "parameters_crc": f"{rcp1.checksum(parameters):08X}" if not errors else None,
                "hardware_qualified": False, "applied_to_rover": False}
    if type(parameters) is not dict or set(parameters) != rcp1.FIELDS:
        raise DraftError("INVALID_PARAMETERS", "Pontosan az RCP1 27 mezője szükséges; board- és minősítési mező nem engedélyezett.")
    errors, missing = [], []

    def issue(field, message):
        errors.append({"field": field, "message": message})

    def number(field, value, low, high, direction=False):
        if value is None:
            missing.append(field)
        elif type(value) is not int or not low <= value <= high or direction and value not in (-1, 1):
            issue(field, "Csak -1 vagy +1 lehet." if direction else f"Egész szám szükséges: {low}…{high}.")

    number("parameters_version", parameters["parameters_version"], 1, 1)
    if parameters["parameters_version"] is None:
        issue("parameters_version", "Az adatverzió kötelezően 1.")
    if parameters["robot_id"] is None:
        missing.append("robot_id")
    elif type(parameters["robot_id"]) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,32}", parameters["robot_id"]) is None:
        issue("robot_id", "1–32 ASCII betű, szám, _ vagy - szükséges.")
    if parameters["blade_enabled"] is None:
        missing.append("blade_enabled")
    elif type(parameters["blade_enabled"]) is not bool:
        issue("blade_enabled", "Logikai érték szükséges; az ismeretlen nem jelent kikapcsoltat.")
    for field, (_, _, low, high) in rcp1.SCALARS.items():
        number(field, parameters[field], low, high, field == "blade_direction")
    for field, (_, _, count, low, high) in rcp1.ARRAYS.items():
        value = parameters[field]
        if value is None:
            missing.append(field)
        elif type(value) is not list or len(value) != count:
            issue(field, f"Pontosan {count} elemű tömb szükséges.")
        else:
            for index, item in enumerate(value):
                number(f"{field}[{index}]", item, low, high, field == "wheel_direction")
    if not errors:
        if all(parameters[field] is not None for field in ("blade_rpm_limit", "blade_pole_pairs", "blade_erpm_limit")):
            if parameters["blade_rpm_limit"] * parameters["blade_pole_pairs"] > parameters["blade_erpm_limit"]:
                issue("blade_rpm_limit", "A mechanikai fordulat × póluspár meghaladja az elektromos késlimitet.")
        q = parameters["imu_mount_q_ppm"]
        if q is not None and all(item is not None for item in q) and not 999000**2 <= sum(item*item for item in q) <= 1001000**2:
            issue("imu_mount_q_ppm", "A kvaternió normája 1 000 000 ±0,1% lehet.")
    valid = not errors and not missing
    if valid:
        # Reference validation is the final authority, never the partial draft checks.
        try:
            rcp1.validate(parameters)
        except ValueError:
            issue("parameters", "A teljes adat nem felel meg az RCP1 referenciának.")
            valid = False
    canonical = canonical_draft(parameters) if not errors else None
    return {"valid": valid, "saveable": not errors, "missing": missing, "errors": errors,
            "draft_sha256": hashlib.sha256(canonical.encode("ascii")).hexdigest() if canonical is not None else None,
            "rcp1_crc32": f"{rcp1.checksum(parameters):08X}" if valid else None,
            "hardware_qualified": False, "applied_to_rover": False}


def draft_result(key, row):
    if row is None:
        return {"rover_key": key, "draft_revision": 0, "parameters": template(), "saved_at": None,
                "source": "HC_DRAFT", "active_configuration": None, "apply_available": False,
                "validation": validate_draft(template())}
    parameters = row["parameters"]
    return {"rover_key": key, "draft_revision": row["revision"], "parameters": parameters,
            "saved_at": row["saved_at"].isoformat() if hasattr(row["saved_at"], "isoformat") else row["saved_at"],
            "request_id": row["request_id"], "source": "HC_DRAFT", "active_configuration": None,
            "apply_available": False, "validation": validate_draft(parameters)}


class MowerParametersService:
    def __init__(self, store):
        self.store = store

    def schema(self):
        return {"ok": True, "format": "RCP1", "bytes": 256, "schema": rcp1.schema(), "template": template(),
                "apply_available": False, "active_configuration": None}

    def latest(self, key):
        rover_key(key)
        return {"ok": True, **draft_result(key, self.store.latest(key))}

    def list_drafts(self):
        return {"ok": True, "drafts": [{"rover_key": row["rover_key"], "draft_revision": row["revision"],
                 "saved_at": row["saved_at"].isoformat(), "source": "HC_DRAFT"} for row in self.store.list_latest()],
                "apply_available": False}

    def history(self, key):
        rover_key(key)
        return {"ok": True, "revisions": [draft_result(key, row) for row in self.store.history(key)]}

    def request_status(self, key, id_):
        rover_key(key)
        if not request_id(id_):
            raise DraftError("INVALID_PAYLOAD", "Hibás mentésazonosító.")
        row = self.store.request(key, id_)
        if row is None:
            raise DraftError("NOT_FOUND", "A mentés még nem olvasható vissza; nincs igazolt siker.", 404)
        return {"ok": True, "saved": True, **draft_result(key, row)}

    def revision(self, key, revision):
        rover_key(key)
        if not integer(revision, 1):
            raise DraftError("INVALID_REVISION", "Hibás draftverzió.")
        row = self.store.revision(key, revision)
        if row is None:
            raise DraftError("NOT_FOUND", "A mentett draftverzió nem található.", 404)
        return {"ok": True, **draft_result(key, row)}

    def validate(self, parameters):
        report = validate_draft(parameters)
        return {"ok": True, "parameters": parameters, "validation": report,
                "canonical_rcp": rcp1.encode(parameters).hex() if report["valid"] else None, "apply_available": False}

    def import_data(self, raw, binary=False):
        try:
            parameters = rcp1.decode(raw) if binary else parse_json(raw)
        except ValueError:
            raise DraftError("INVALID_RCP1", "Hibás RCP1: méret, verzió, CRC, reserved byte vagy paraméteradat eltér.") from None
        report = validate_draft(parameters)
        if not report["saveable"]:
            raise DraftError("INVALID_PARAMETERS", "Az importált paraméteradat hibás.", validation=report)
        return {"ok": True, "parameters": parameters, "validation": report, "saved": False, "apply_available": False}

    def save(self, key, body):
        rover_key(key)
        if (type(body) is not dict or set(body) != {"request_id", "expected_revision", "parameters"}
                or not request_id(body["request_id"]) or not integer(body["expected_revision"])):
            raise DraftError("INVALID_PAYLOAD", "Teljes paraméteradat, request_id és expected_revision szükséges.")
        report = validate_draft(body["parameters"])
        if not report["saveable"]:
            raise DraftError("INVALID_PARAMETERS", "A draft hibás értéket tartalmaz; javítás előtt nem menthető.", validation=report)
        row, replayed = self.store.save(key, body["request_id"], body["expected_revision"], body["parameters"], report["draft_sha256"])
        return {"ok": True, "saved": True, "replayed": replayed, **draft_result(key, row)}

    def export(self, key, revision, binary=False):
        draft = self.revision(key, revision)
        if binary:
            if not draft["validation"]["valid"]:
                raise DraftError("DRAFT_INCOMPLETE", "RCP1 csak teljes és valid draftból exportálható.", 409)
            return rcp1.encode(draft["parameters"])
        return (json.dumps(draft["parameters"], sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
