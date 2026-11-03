#!/usr/bin/env python3
"""Validate/canonicalize the immutable v3.1 profile and generate C/C++ data."""
import argparse
import json
from pathlib import Path
import re
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config/rover_profile.template.json"


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name}: expected integer {low}..{high}, got {value!r}")


def validate(p):
    expected = set(json.loads(TEMPLATE.read_text(encoding="utf-8")))
    if type(p) is not dict or set(p) != expected:
        raise ValueError("Profile must contain exactly the specified fields")
    if p["profile_version"] != 1 or type(p["profile_version"]) is not int:
        raise ValueError("profile_version must be 1")
    if not isinstance(p["robot_id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", p["robot_id"]):
        raise ValueError("robot_id must match [A-Za-z0-9_-]{1,32}")
    for key in ("commissioned", "blade_enabled"):
        if type(p[key]) is not bool:
            raise ValueError(f"{key}: expected boolean")
    ranges = {
        "wheel_track_mm": (100, 1500), "blade_pole_pairs": (1, 100),
        "body_radius_mm": (100, 1000), "blade_erpm_limit": (1, 25000),
        "blade_rpm_limit": (1, 25000), "stop_deceleration_mm_s2": (1, 0xffffffff),
        "max_slope_mdeg": (0, 15000), "max_linear_mm_s": (50, 500),
        "max_yaw_mdeg_s": (5000, 45000), "accel_mm_s2": (50, 500),
        "yaw_accel_mdeg_s2": (5000, 90000), "gnss_hacc_limit_mm": (20, 100),
        "heading_accuracy_limit_mdeg": (1000, 15000), "tilt_limit_mdeg": (10000, 30000),
        "safety_installed_mask": (8, 15), "stop_test_max_ms": (1, 2000),
    }
    for key, bounds in ranges.items():
        integer(p[key], *bounds, key)
    arrays = {
        "wheel_circumference_mm": (2, 100, 2000), "wheel_motor_pole_pairs": (2, 1, 100),
        "wheel_gear_ratio_milli": (2, 1000, 1000000), "wheel_direction": (2, -1, 1),
        "antenna_body_mm": (3, -2000, 2000), "imu_mount_q_ppm": (4, -1000000, 1000000),
        "wheel_erpm_limit": (2, 1, 6000), "wheel_brake_ma": (2, 0, 0x7fffffff),
    }
    for key, (length, low, high) in arrays.items():
        if type(p[key]) is not list or len(p[key]) != length:
            raise ValueError(f"{key}: expected {length} integers")
        for i, item in enumerate(p[key]):
            integer(item, low, high, f"{key}[{i}]")
    integer(p["blade_direction"], -1, 1, "blade_direction")
    if not p["blade_direction"] or 0 in p["wheel_direction"]:
        raise ValueError("Motor directions must be -1 or +1")
    norm2 = sum(x*x for x in p["imu_mount_q_ppm"])
    if not 999000**2 <= norm2 <= 1001000**2:
        raise ValueError("imu_mount_q_ppm: norm must be within 0.1% of 1000000")
    if p["blade_rpm_limit"] * p["blade_pole_pairs"] > p["blade_erpm_limit"]:
        raise ValueError("blade_rpm_limit * blade_pole_pairs exceeds electrical limit")
    pins = p["safety_inputs"]
    if type(pins) is not dict or set(pins) != {"estop", "lift", "bumper"}:
        raise ValueError("safety_inputs must contain estop/lift/bumper")
    mask, used = 8, set()
    for index, name in enumerate(("estop", "lift", "bumper")):
        pin = pins[name]
        if type(pin) is not dict or set(pin) != {"present", "port", "pin", "active_level"} or type(pin["present"]) is not bool:
            raise ValueError(f"safety_inputs.{name}: incomplete pin definition")
        integer(pin["pin"], 0, 15, name + ".pin")
        integer(pin["active_level"], 0, 1, name + ".active_level")
        if pin["present"]:
            if not isinstance(pin["port"], str) or not re.fullmatch("[A-K]", pin["port"]):
                raise ValueError(f"{name}: present input requires port A..K")
            key = (pin["port"], pin["pin"])
            if key in used:
                raise ValueError("Safety inputs cannot share one pin")
            used.add(key)
            mask |= 1 << index
        elif pin["port"] != "NONE" or pin["pin"] != 0:
            raise ValueError(f"{name}: absent input requires port NONE/pin 0")
    if mask != p["safety_installed_mask"]:
        raise ValueError("safety_installed_mask disagrees with pin availability")
    if p["commissioned"] and not pins["estop"]["present"]:
        raise ValueError("Commissioned operation requires an installed physical ESTOP")
    firmware = p["vesc_firmware"]
    if type(firmware) is not list or len(firmware) != 3 or any(
        not isinstance(s, str) or not 1 <= len(s) <= 40 or any(ord(c) < 32 or ord(c) > 126 for c in s)
        for s in firmware
    ):
        raise ValueError("vesc_firmware: exactly three nonempty ASCII identifiers required")
    return p


def canonical(p):
    return json.dumps(validate(p), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def checksum(p):
    return zlib.crc32(canonical(p).encode("utf-8")) & 0xffffffff


def header(p):
    canonical_json = canonical(p)
    crc = checksum(p)
    fields = [str(crc) + "U", "1", str(int(p["commissioned"])), str(int(p["blade_enabled"])), json.dumps(p["robot_id"])]
    order = ["wheel_track_mm", "wheel_circumference_mm", "wheel_motor_pole_pairs", "wheel_gear_ratio_milli",
             "wheel_direction", "blade_direction", "blade_pole_pairs", "body_radius_mm", "antenna_body_mm",
             "imu_mount_q_ppm", "wheel_erpm_limit", "blade_erpm_limit", "blade_rpm_limit", "wheel_brake_ma",
             "stop_deceleration_mm_s2", "stop_test_max_ms", "max_slope_mdeg", "max_linear_mm_s",
             "max_yaw_mdeg_s", "accel_mm_s2", "yaw_accel_mdeg_s2", "gnss_hacc_limit_mm",
             "heading_accuracy_limit_mdeg", "tilt_limit_mdeg", "safety_installed_mask"]
    for key in order:
        value = p[key]
        fields.append("{" + ",".join(str(x) for x in value) + "}" if isinstance(value, list) else str(value) + ("U" if value >= 0 else ""))
    pins = []
    for name in ("estop", "lift", "bumper"):
        pin = p["safety_inputs"][name]
        port = ord(pin["port"]) - ord("A") if pin["present"] else 0
        pins.append("{" + ",".join(map(str, [int(pin["present"]), port, pin["pin"], pin["active_level"]])) + "}")
    fields.append("{" + ",".join(pins) + "}")
    fields.append("{" + ",".join(json.dumps(x) for x in p["vesc_firmware"]) + "}")
    return ('#ifndef ROVER_INSTALLED_PROFILE_H\n#define ROVER_INSTALLED_PROFILE_H\n#include "rover_profile.h"\n'
            f'#define R3_PROFILE_CRC_TEXT "{crc:08X}"\n#define R3_PROFILE_CRC_U32 {crc}U\n#define R3_PROFILE_JSON {json.dumps(canonical_json)}\n'
            'static const R3Profile r3_installed_profile = {\n    ' + ',\n    '.join(fields) + '\n};\n#endif\n')


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("check", "canonical", "install"))
    parser.add_argument("profile", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "shared/rover_installed_profile.h")
    args = parser.parse_args()
    try:
        p = json.loads(args.profile.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
        output = canonical(p)
        if args.operation == "canonical":
            print(output, end="")
        elif args.operation == "install":
            args.output.write_text(header(p), encoding="ascii")
            print(f"Installed profile {checksum(p):08X}; commissioned={p['commissioned']}. Rebuild BOTH firmwares.")
        else:
            print(f"Valid profile; CRC32={checksum(p):08X}; commissioned={p['commissioned']}")
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
