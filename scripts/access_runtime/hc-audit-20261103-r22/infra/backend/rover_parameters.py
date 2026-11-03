#!/usr/bin/env python3
"""Strict HC draft/RCP1 codec. No firmware header generation or rover mutation.

This is a data contract, NOT an installed HTTP parameter setter. Hardware
certification, identity/boot binding and motion admission are separate checks.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
import zlib

VERSION = 1
BYTES = 256
# name: (offset, format, minimum, maximum). Units are encoded in field names.
SCALARS = {
    "wheel_track_mm": (48, "H", 100, 1500),
    "body_radius_mm": (50, "H", 100, 1000),
    "blade_direction": (70, "b", -1, 1),
    "blade_pole_pairs": (72, "H", 1, 100),
    "max_slope_mdeg": (74, "H", 0, 15000),
    "blade_erpm_limit": (76, "I", 1, 25000),
    "blade_rpm_limit": (80, "I", 1, 25000),
    "stop_deceleration_mm_s2": (128, "I", 1, 0xffffffff),
    "stop_test_max_ms": (132, "I", 1, 2000),
    "max_linear_mm_s": (136, "H", 50, 500),
    "max_yaw_mdeg_s": (138, "H", 5000, 45000),
    "accel_mm_s2": (140, "H", 50, 500),
    "gnss_hacc_limit_mm": (142, "H", 20, 100),
    "heading_accuracy_limit_mdeg": (144, "H", 1000, 15000),
    "tilt_limit_mdeg": (146, "H", 10000, 30000),
    "yaw_accel_mdeg_s2": (148, "I", 5000, 90000),
}
# name: (offset, format, length, minimum, maximum).
ARRAYS = {
    "wheel_circumference_mm": (52, "H", 2, 100, 2000),
    "wheel_motor_pole_pairs": (56, "H", 2, 1, 100),
    "wheel_gear_ratio_milli": (60, "I", 2, 1000, 1000000),
    "wheel_direction": (68, "b", 2, -1, 1),
    "antenna_body_mm": (84, "i", 3, -2000, 2000),
    "imu_mount_q_ppm": (96, "i", 4, -1000000, 1000000),
    "wheel_erpm_limit": (112, "I", 2, 1, 6000),
    "wheel_brake_ma": (120, "I", 2, 0, 0x7fffffff),
}
FIELDS = set(SCALARS) | set(ARRAYS) | {"parameters_version", "robot_id", "blade_enabled"}
V2_FIELDS = FIELDS | {"drive_mode", "wheel_electrical_ratio_milli", "motor_accel_erpm_s", "blade_brake_ma"}


MINIMAL_FIELDS = {"parameters_version", "robot_id", "drive_mode", "blade_enabled", "wheel_direction",
                  "wheel_erpm_limit", "wheel_brake_ma", "motor_accel_erpm_s", "imu_mount_q_ppm", "tilt_limit_mdeg"}
BLADE_FIELDS = {"blade_direction", "blade_erpm_limit", "blade_brake_ma"}


def expand(p):
    """Compact ERPM is a complete replacement; inactive fields become zero."""
    if type(p) is not dict or set(p) == V2_FIELDS or p.get("parameters_version") != 2:
        return p
    enabled = p.get("blade_enabled")
    if type(enabled) is not bool or set(p) != MINIMAL_FIELDS | (BLADE_FIELDS if enabled else set()) or p.get("drive_mode") != "ERPM":
        raise ValueError("Expected full RCP2 or exact compact ERPM 10/13 fields")
    acceleration = p.get("motor_accel_erpm_s")
    if type(acceleration) is not list or len(acceleration) != (3 if enabled else 2):
        raise ValueError("Invalid compact acceleration length")
    full = {name: 0 for name in SCALARS}
    full.update({name: [0] * count for name, (_, _, count, _, _) in ARRAYS.items()})
    full.update(wheel_electrical_ratio_milli=[0,0], blade_brake_ma=0)
    full.update(p)
    full['motor_accel_erpm_s'] = list(acceleration) + ([] if enabled else [0])
    return full


def necessary(p):
    p = validate(p)
    if p.get("drive_mode") != "ERPM":
        return None
    keys = MINIMAL_FIELDS | (BLADE_FIELDS if p['blade_enabled'] else set())
    result = {key: p[key] for key in sorted(keys)}
    result['motor_accel_erpm_s'] = p['motor_accel_erpm_s'][:3 if p['blade_enabled'] else 2]
    return result


def validate_v2(p):
    p = expand(p)
    if set(p) != V2_FIELDS:
        raise ValueError("RCP2 requires exactly its 31 fields")
    integer(p["parameters_version"], 2, 2, "parameters_version")
    if not isinstance(p["robot_id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", p["robot_id"]):
        raise ValueError("Invalid robot_id")
    if type(p["blade_enabled"]) is not bool or p["drive_mode"] not in ("ERPM", "CALIBRATED"):
        raise ValueError("Invalid enable/mode")
    for name, (_, _, low, high) in SCALARS.items():
        integer(p[name], low if name in ("tilt_limit_mdeg", "blade_direction") or p["blade_enabled"] and name == "blade_erpm_limit" else 0, high, name)
    for name, (_, _, count, low, high) in ARRAYS.items():
        if type(p[name]) is not list or len(p[name]) != count:
            raise ValueError(f"{name}: invalid array length")
        for value in p[name]:
            integer(value, low if name in ("wheel_direction", "antenna_body_mm", "imu_mount_q_ppm", "wheel_erpm_limit") else 0, high, name)
    for name, count, low, high in (("wheel_electrical_ratio_milli", 2, 0, 100000000), ("motor_accel_erpm_s", 3, 1, 100000)):
        if type(p[name]) is not list or len(p[name]) != count:
            raise ValueError(f"{name}: invalid array length")
        for index, value in enumerate(p[name]):
            integer(value, 0 if name == "motor_accel_erpm_s" and index == 2 and not p["blade_enabled"] else low, high, name)
    integer(p["blade_brake_ma"], 0, 0x7fffffff, "blade_brake_ma")
    if p["blade_enabled"] and not p["blade_direction"] or 0 in p["wheel_direction"] or not 999000**2 <= sum(q*q for q in p["imu_mount_q_ppm"]) <= 1001000**2:
        raise ValueError("Invalid direction/IMU quaternion")
    for name in ("wheel_track_mm", "body_radius_mm"):
        if p[name] and p[name] < SCALARS[name][2]:
            raise ValueError(f"{name}: nonzero value below range")
    if any(v and v < 100 for v in p["wheel_circumference_mm"]):
        raise ValueError("Invalid wheel circumference")
    if any(p["wheel_motor_pole_pairs"]) or any(p["wheel_gear_ratio_milli"]):
        raise ValueError("RCP2 uses measured combined ratio, not separate guessed poles/gearing")
    if p["drive_mode"] == "ERPM":
        unused = ("blade_pole_pairs", "blade_rpm_limit", "max_slope_mdeg", "stop_deceleration_mm_s2", "stop_test_max_ms",
                  "max_linear_mm_s", "max_yaw_mdeg_s", "accel_mm_s2", "yaw_accel_mdeg_s2", "gnss_hacc_limit_mm", "heading_accuracy_limit_mdeg")
        if any(p[k] for k in unused):
            raise ValueError("ERPM-only inactive metric fields must be zero (unavailable)")
    else:
        for name, (_, _, low, high) in SCALARS.items():
            if not p["blade_enabled"] and name in ("blade_pole_pairs", "blade_rpm_limit"):
                integer(p[name], 0, 0, name)
            else:
                integer(p[name], low, high, name)
        if not all(p["wheel_circumference_mm"]) or min(p["wheel_electrical_ratio_milli"]) < 1000:
            raise ValueError("Metric control requires measured wheel ratios/circumferences")
        if p["blade_rpm_limit"] * p["blade_pole_pairs"] > p["blade_erpm_limit"]:
            raise ValueError("Blade mechanical limit exceeds electrical limit")
    return p


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name}: expected integer {low}..{high}")


def validate(p):
    if type(p) is dict and type(p.get("parameters_version")) is int and p["parameters_version"] == 2:
        return validate_v2(p)
    if type(p) is not dict or set(p) != FIELDS:
        raise ValueError("Parameters must contain exactly the RCP1 fields; hardware/commissioning fields are forbidden")
    integer(p["parameters_version"], VERSION, VERSION, "parameters_version")
    if type(p["robot_id"]) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", p["robot_id"]):
        raise ValueError("robot_id: expected [A-Za-z0-9_-]{1,32}")
    if type(p["blade_enabled"]) is not bool:
        raise ValueError("blade_enabled: expected boolean")
    for name, (_, _, low, high) in SCALARS.items():
        integer(p[name], low, high, name)
    for name, (_, _, count, low, high) in ARRAYS.items():
        if type(p[name]) is not list or len(p[name]) != count:
            raise ValueError(f"{name}: expected an array of {count} integers")
        for index, item in enumerate(p[name]):
            integer(item, low, high, f"{name}[{index}]")
    if not p["blade_direction"] or 0 in p["wheel_direction"]:
        raise ValueError("Motor directions must be -1 or +1")
    if p["blade_rpm_limit"] * p["blade_pole_pairs"] > p["blade_erpm_limit"]:
        raise ValueError("blade_rpm_limit * blade_pole_pairs exceeds electrical limit")
    if not 999000**2 <= sum(q*q for q in p["imu_mount_q_ppm"]) <= 1001000**2:
        raise ValueError("imu_mount_q_ppm: norm must be within 0.1% of 1000000")
    return p


def reject_duplicates(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"Duplicate JSON key: {name}")
        result[name] = value
    return result


def reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def loads(text):
    return validate(json.loads(text, object_pairs_hook=reject_duplicates, parse_constant=reject_constant))


def canonical(p):
    return json.dumps(validate(p), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def encode(p):
    p = validate(p)
    b = bytearray(BYTES)
    v2 = p["parameters_version"] == 2
    struct.pack_into("<4sHHB", b, 0, b"RCP2" if v2 else b"RCP1", 2 if v2 else VERSION, BYTES, int(p["blade_enabled"]))
    robot = p["robot_id"].encode("ascii")
    b[12:12+len(robot)] = robot
    for name, (offset, fmt, _, _) in SCALARS.items():
        struct.pack_into("<"+fmt, b, offset, p[name])
    for name, (offset, fmt, count, _, _) in ARRAYS.items():
        struct.pack_into("<"+fmt*count, b, offset, *p[name])
    if v2:
        b[152] = 1 if p["drive_mode"] == "ERPM" else 2
        struct.pack_into("<II", b, 156, *p["wheel_electrical_ratio_milli"])
        struct.pack_into("<III", b, 164, *p["motor_accel_erpm_s"])
        struct.pack_into("<I", b, 176, p["blade_brake_ma"])
    struct.pack_into("<I", b, 252, zlib.crc32(b[:252]) & 0xffffffff)
    return bytes(b)


def checksum(p):
    """Integrity CRC, NOT a cryptographic identity or a commissioning grant."""
    return struct.unpack_from("<I", encode(p), 252)[0]


def decode(b):
    if type(b) is not bytes or len(b) != BYTES:
        raise ValueError("RCP1 must be exactly 256 bytes")
    header = struct.unpack_from("<4sHH", b)
    if header not in ((b"RCP1", VERSION, BYTES), (b"RCP2", 2, BYTES)):
        raise ValueError("Unsupported parameter header/version/length")
    if struct.unpack_from("<I", b, 252)[0] != zlib.crc32(b[:252]) & 0xffffffff:
        raise ValueError("RCP1 CRC mismatch")
    if b[8] not in (0, 1):
        raise ValueError("Invalid blade_enabled")
    try:
        robot = b[12:45].split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("Invalid robot_id encoding") from error
    p = dict(parameters_version=header[1], robot_id=robot, blade_enabled=bool(b[8]))
    for name, (offset, fmt, _, _) in SCALARS.items():
        p[name] = struct.unpack_from("<"+fmt, b, offset)[0]
    for name, (offset, fmt, count, _, _) in ARRAYS.items():
        p[name] = list(struct.unpack_from("<"+fmt*count, b, offset))
    if header[1] == 2:
        if b[152] not in (1, 2):
            raise ValueError("Invalid RCP2 control mode")
        p.update(drive_mode="ERPM" if b[152] == 1 else "CALIBRATED",
                 wheel_electrical_ratio_milli=list(struct.unpack_from("<II", b, 156)),
                 motor_accel_erpm_s=list(struct.unpack_from("<III", b, 164)),
                 blade_brake_ma=struct.unpack_from("<I", b, 176)[0])
    if encode(p) != b:
        raise ValueError("Noncanonical RCP1: reserved bytes or robot_id padding")
    return p


def schema():
    """Offline UI schema. Cross-field and physical validation remain mandatory."""
    properties = {
        "parameters_version": {"type": "integer", "const": VERSION},
        "robot_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,32}$"},
        "blade_enabled": {"type": "boolean"},
    }
    for name, (_, _, low, high) in SCALARS.items():
        properties[name] = {"type": "integer", "minimum": low, "maximum": high}
    properties["blade_direction"] = {"type": "integer", "enum": [-1, 1]}
    for name, (_, _, count, low, high) in ARRAYS.items():
        item = {"type": "integer", "minimum": low, "maximum": high}
        if name == "wheel_direction":
            item = {"type": "integer", "enum": [-1, 1]}
        properties[name] = {"type": "array", "minItems": count, "maxItems": count, "items": item}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Rover parameters RCP1 (draft, not admission)",
            "type": "object", "additionalProperties": False, "required": sorted(FIELDS), "properties": properties}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("check", "canonical", "encode", "decode", "schema"))
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.operation == "schema":
            if args.input or args.output:
                raise ValueError("schema takes no input/output path; emits JSON on stdout")
            print(json.dumps(schema(), indent=2, sort_keys=True))
            return 0
        if not args.input or (args.operation == "encode") != bool(args.output):
            raise ValueError("Input is required; only encode requires/allows --output")
        p = decode(args.input.read_bytes()) if args.operation == "decode" else loads(args.input.read_text(encoding="utf-8"))
        if args.operation in ("canonical", "decode"):
            print(canonical(p))
        elif args.operation == "encode":
            with args.output.open("xb") as stream:
                stream.write(encode(p))
            print(f"Encoded RCP1: 256 bytes, CRC32={checksum(p):08X}; NOT applied to a rover")
        else:
            print(f"Valid parameter draft: CRC32={checksum(p):08X}; NOT hardware-qualified or applied")
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
