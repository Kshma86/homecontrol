from typing import Any, Dict


def normalized_segment_list(value: Any):
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").split(",")
    result = []
    for item in items:
        try:
            number = int(str(item).strip())
        except Exception:
            continue
        if number:
            result.append(number)
    return result


def normalize_x10_scalar(value: Any):
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"none", "null", "undefined", "unknown_none", "unknown_null"}:
        return None
    return text if text != "" else None


def normalize_x10_int_text(value: Any):
    text = normalize_x10_scalar(value)
    if text is None:
        return None
    try:
        return str(int(float(text)))
    except Exception:
        return text


def x10_command_expected(command_payload: Dict[str, Any]):
    return {
        "start_time": normalize_x10_scalar(command_payload.get("start_time") or command_payload.get("time")),
        "days": normalize_x10_scalar(command_payload.get("days")),
        "enabled": normalize_x10_int_text(command_payload.get("enabled")),
        "map_id": normalize_x10_int_text(command_payload.get("map_id")),
        "mode": normalize_x10_int_text(command_payload.get("mode") or command_payload.get("clean_mode")),
        "suction": normalize_x10_int_text(command_payload.get("suction")),
        "water_level": normalize_x10_int_text(command_payload.get("water_level") or command_payload.get("clean_param")),
        "segments": normalized_segment_list(command_payload.get("segments")),
    }


def x10_entry_observed(entry: Dict[str, Any]):
    return {
        "task_id": normalize_x10_scalar(entry.get("task_id")),
        "start_time": normalize_x10_scalar(entry.get("time") or entry.get("start_time")),
        "days": normalize_x10_scalar(entry.get("days")),
        "enabled": normalize_x10_int_text(entry.get("enabled")),
        "map_id": normalize_x10_int_text(entry.get("map_id")),
        "mode": normalize_x10_int_text(entry.get("clean_mode") or entry.get("flag")),
        "suction": normalize_x10_int_text(entry.get("suction")),
        "water_level": normalize_x10_int_text(entry.get("water_level") or entry.get("clean_param")),
        "segments": normalized_segment_list(entry.get("segments")),
        "raw": entry.get("raw"),
    }


def x10_entry_matches_command(entry: Dict[str, Any], expected: Dict[str, Any]):
    observed = x10_entry_observed(entry)
    checks = {
        "start_time": observed["start_time"] == expected["start_time"],
        "days": not expected["days"] or observed["days"] == expected["days"],
        "enabled": not expected["enabled"] or observed["enabled"] == expected["enabled"],
        "map_id": not expected["map_id"] or observed["map_id"] == expected["map_id"],
        "mode": not expected["mode"] or observed["mode"] == expected["mode"],
        "suction": not expected["suction"] or observed["suction"] == expected["suction"],
        "water_level": not expected["water_level"] or observed["water_level"] == expected["water_level"],
        "segments": not expected["segments"] or observed["segments"] == expected["segments"],
    }
    return all(checks.values()), checks, observed
