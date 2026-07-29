#!/usr/bin/env python3
import ast
import json
import re
import time
import subprocess
import base64
import threading
from pathlib import Path
from datetime import datetime, timedelta

import paho.mqtt.client as mqtt

import config


CONFIG = {
    "mqtt_host": config.MQTT_HOST,
    "mqtt_port": config.MQTT_PORT,
    "base_topic": config.BASE_TOPIC,

    "robot_ip": config.ROBOT_IP,
    "robot_token": config.ROBOT_TOKEN,

    "poll_idle_sec": config.POLL_IDLE_SEC,
    "poll_cleaning_sec": config.POLL_CLEANING_SEC,
    "map_check_cleaning_sec": config.MAP_CHECK_CLEANING_SEC,
    "scheduler_watch_sec": config.SCHEDULER_WATCH_SEC,

    "map_script": str(config.MAP_SCRIPT),
    "maps_index": str(config.MAPS_INDEX),
    "capture_dir": str(config.CAPTURE_DIR),
    "capture_status_sec": config.CAPTURE_STATUS_SEC,
    "capture_map_sec": config.CAPTURE_MAP_SEC,
    "capture_scheduler_sec": config.CAPTURE_SCHEDULER_SEC,

    "room_clean_task_id": config.ROOM_CLEAN_TASK_ID,
    "room_clean_delay_min": config.ROOM_CLEAN_DELAY_MIN,
    "room_clean_suction": config.ROOM_CLEAN_SUCTION,
    "room_clean_param": config.ROOM_CLEAN_PARAM,
    "set_map_siid": config.SET_MAP_SIID,
    "set_map_aiid": config.SET_MAP_AIID,
}

STATE_TEXT = {
    1: "cleaning_or_room_cleaning",
    2: "moved_or_remote_active",
    5: "returning_or_relocating",
    6: "idle_docked",
    12: "cleaning",
    13: "charging",
}

last_state = {}
last_map_md5 = None
last_status_poll = 0
last_map_poll = 0
last_scheduler_watch = 0
active_room_clean = None
capture_session = None
last_capture_status = 0
last_capture_map = 0
last_capture_scheduler = 0
WEEKLY_TASK_IDS = [12, 13, 14, 17, 15, 16, 11]
ROBOT_DAY_MASK_INDEX_BY_HC_DAY = [1, 2, 3, 4, 5, 6, 0]

client = mqtt.Client()
command_lock = threading.Lock()


def topic(name):
    return f"{CONFIG['base_topic']}/{name}"


def publish(name, value, retain=True, force=False):
    if isinstance(value, (dict, list)):
        payload = json.dumps(value, ensure_ascii=False)
    else:
        payload = str(value)

    if force or last_state.get(name) != payload:
        client.publish(topic(name), payload, retain=retain)
        last_state[name] = payload
        print(f"MQTT publish {topic(name)} = {payload}")


def publish_command_result(command, ok=True, message="", extra=None):
    data = {
        "command": command,
        "ok": ok,
        "message": message,
        "ts": int(time.time()),
    }
    if extra is not None:
        data["extra"] = extra
    publish("command_result", data, retain=False, force=True)


def json_safe(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        return str(value)


def capture_public_status():
    if not capture_session:
        return {
            "active": False,
            "ts": int(time.time()),
            "capture_dir": CONFIG["capture_dir"],
        }

    return {
        "active": True,
        "session_id": capture_session["session_id"],
        "label": capture_session.get("label"),
        "map_id": capture_session.get("map_id"),
        "started_ts": capture_session["started_ts"],
        "sample_count": capture_session.get("sample_count", 0),
        "last_sample_ts": capture_session.get("last_sample_ts"),
        "file": capture_session["file"],
        "ts": int(time.time()),
    }


def publish_capture_status(force=True):
    publish("capture/status", capture_public_status(), retain=True, force=force)


def append_capture_event(kind, data=None, error=None):
    if not capture_session:
        return

    event = {
        "ts": int(time.time()),
        "iso": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "session_id": capture_session["session_id"],
        "label": capture_session.get("label"),
        "map_id": capture_session.get("map_id"),
    }
    if data is not None:
        event["data"] = json_safe(data)
    if error is not None:
        event["error"] = str(error)

    path = Path(capture_session["file"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    capture_session["sample_count"] = capture_session.get("sample_count", 0) + 1
    capture_session["last_sample_ts"] = event["ts"]
    publish_capture_status(force=True)


def decode_possible_base64(value):
    if not isinstance(value, str):
        return value

    try:
        decoded = base64.b64decode(value).decode("utf-8")
        if decoded and all(ord(c) >= 32 for c in decoded):
            return decoded
    except Exception:
        pass

    return value


def miio_cmd(args):
    cmd = [
        str(config.MIIOCLI),
        "dreamevacuum",
        "--ip", CONFIG["robot_ip"],
        "--token", CONFIG["robot_token"],
    ] + args

    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=20,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    output = result.stdout.strip()
    error_text = result.stderr.strip()
    combined = "\n".join(part for part in (output, error_text) if part)
    if re.search(r"(^|\n)\s*(Error:|ERROR:)", combined):
        raise RuntimeError(combined)

    return output


def get_property(siid, piid):
    out = miio_cmd(["get_property_by", str(siid), str(piid)])

    for line in reversed(out.splitlines()):
        line = line.strip()

        if line.startswith("[") and line.endswith("]"):
            data = ast.literal_eval(line)

            if isinstance(data, list) and data:
                value = data[0].get("value")

                if isinstance(value, str):
                    try:
                        return json.loads(value)
                    except Exception:
                        return value

                return value

    return None


def set_property(siid, piid, value):
    return miio_cmd(["set_property_by", str(siid), str(piid), str(value)])


def ensure_miio_success(result, context):
    codes = [int(code) for code in re.findall(r"'code':\s*(-?\d+)|\"code\":\s*(-?\d+)", str(result)) for code in code if code]
    if codes and any(code != 0 for code in codes):
        raise RuntimeError(f"{context} rejected by robot: {result}")
    return result


def call_action(siid, aiid):
    return miio_cmd(["call_action_by", str(siid), str(aiid)])


def call_action_with_params(siid, aiid, params):
    if not isinstance(params, list):
        params = [params]
    return miio_cmd([
        "call_action_by",
        str(siid),
        str(aiid),
        json.dumps(params, separators=(",", ":")),
    ])


def get_map_object():
    obj = get_property(6, 8)

    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            return None

    if not isinstance(obj, dict):
        return None

    publish("map/object", obj)

    if obj.get("object_name"):
        publish("map/object_name", obj["object_name"])

    if obj.get("md5"):
        publish("map/md5", obj["md5"])

    return obj


def find_first_existing_key(data, keys):
    if not isinstance(data, dict):
        return None

    for key in keys:
        if key in data:
            return data.get(key)

    return None


def get_maps_list(index):
    maps = find_first_existing_key(index, ["maps", "map_list", "saved_maps"])
    return maps if isinstance(maps, list) else []


def get_map_id(map_item):
    if not isinstance(map_item, dict):
        return None

    header = map_item.get("header")
    if isinstance(header, dict) and header.get("map_id") is not None:
        return header.get("map_id")

    return find_first_existing_key(map_item, ["map_id", "id", "mapId", "id_from_json"])


def get_saved_map_id(map_item):
    if not isinstance(map_item, dict):
        return None
    return find_first_existing_key(map_item, ["id_from_json", "saved_map_id", "savedMapId", "id"])


def resolve_select_map_id(requested_map_id):
    index_path = Path(CONFIG["maps_index"])
    if not index_path.exists():
        return requested_map_id, None

    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return requested_map_id, None

    for map_item in get_maps_list(index):
        header_map_id = get_map_id(map_item)
        saved_map_id = get_saved_map_id(map_item)
        if str(header_map_id) == str(requested_map_id):
            return int(saved_map_id) if saved_map_id is not None else requested_map_id, map_item
        if saved_map_id is not None and str(saved_map_id) == str(requested_map_id):
            return requested_map_id, map_item

    return requested_map_id, None


def get_map_name(map_item):
    name = find_first_existing_key(map_item, ["name", "map_name", "mapName"])

    if name:
        return decode_possible_base64(name)

    return f"map_{get_map_id(map_item)}"


def get_map_rooms(map_item):
    rooms = find_first_existing_key(map_item, ["rooms", "room_list", "segments"])
    return rooms if isinstance(rooms, list) else []


def get_room_id(room_item):
    return find_first_existing_key(room_item, ["room_id", "roomID", "id"])


def get_segment_id(room_item):
    return find_first_existing_key(room_item, ["segment_id", "segmentId", "segment"])


def get_room_name(room_item):
    name = find_first_existing_key(room_item, ["name", "room_name", "roomName"])

    if name:
        return decode_possible_base64(name)

    room_id = get_room_id(room_item)
    segment_id = get_segment_id(room_item)

    if room_id:
        return f"room_{room_id}"

    return f"room_{segment_id}"


def normalize_room(room_item):
    return {
        "segment_id": get_segment_id(room_item),
        "room_id": get_room_id(room_item),
        "name": get_room_name(room_item),
        "type": room_item.get("type") if isinstance(room_item, dict) else None,
        "neighbors": room_item.get("neighbors", []) if isinstance(room_item, dict) else [],
    }


def normalize_rooms(rooms):
    return [normalize_room(room) for room in rooms if isinstance(room, dict)]


def get_map_png(map_item):
    return find_first_existing_key(
        map_item,
        ["png", "image", "image_file", "filename", "file", "path"]
    )


def map_world_to_px(header, x, y):
    if not isinstance(header, dict):
        return None

    left = header.get("left")
    top = header.get("top")
    grid_size = header.get("grid_size")

    if left is None or top is None or not grid_size:
        return None

    return {
        "x": round((x - left) / grid_size, 2),
        "y": round((y - top) / grid_size, 2),
    }


def publish_robot_and_dock_position(active_map):
    if not isinstance(active_map, dict):
        return

    header = active_map.get("header")
    if not isinstance(header, dict):
        return

    map_id = get_map_id(active_map)
    map_name = get_map_name(active_map)

    robot_x = header.get("robot_x")
    robot_y = header.get("robot_y")
    robot_angle = header.get("robot_angle")

    dock_x = header.get("dock_x")
    dock_y = header.get("dock_y")
    dock_angle = header.get("dock_angle")

    robot_valid = (
        robot_x is not None and
        robot_y is not None and
        not (robot_x == 0 and robot_y == 0)
    )
    publish("robot/header_raw", {
        "map_id": map_id,
        "map_name": map_name,
        "robot_x": robot_x,
        "robot_y": robot_y,
        "robot_angle": robot_angle,
        "dock_x": dock_x,
        "dock_y": dock_y,
        "dock_angle": dock_angle,
        "left": header.get("left"),
        "top": header.get("top"),
        "grid_size": header.get("grid_size"),
        "width": header.get("width"),
        "height": header.get("height"),
        "ts": int(time.time()),
    })

    dock_valid = (
        dock_x is not None and
        dock_y is not None and
        dock_x != 32767 and
        dock_y != 32767
    )

    if robot_valid:
        robot_position = {
            "map_id": map_id,
            "map_name": map_name,
            "x": robot_x,
            "y": robot_y,
            "angle": robot_angle,
            "ts": int(time.time()),
        }
        publish("robot/position", robot_position)

        robot_px = map_world_to_px(header, robot_x, robot_y)
        if robot_px:
            publish("robot/position_px", {
                "map_id": map_id,
                "map_name": map_name,
                "x": robot_px["x"],
                "y": robot_px["y"],
                "angle": robot_angle,
                "ts": int(time.time()),
            })

    if dock_valid:
        dock_position = {
            "map_id": map_id,
            "map_name": map_name,
            "x": dock_x,
            "y": dock_y,
            "angle": dock_angle,
            "ts": int(time.time()),
        }
        publish("dock/position", dock_position)

        dock_px = map_world_to_px(header, dock_x, dock_y)
        if dock_px:
            publish("dock/position_px", {
                "map_id": map_id,
                "map_name": map_name,
                "x": dock_px["x"],
                "y": dock_px["y"],
                "angle": dock_angle,
                "ts": int(time.time()),
            })


def publish_map_info(index):
    if not isinstance(index, dict):
        return

    curr_id = find_first_existing_key(
        index,
        ["curr_id", "current_id", "currentMapId", "current_map_id"]
    )

    maps = get_maps_list(index)

    publish("map/index", index)
    publish("map/count", len(maps))

    if curr_id is not None:
        publish("map/current_id_from_index", curr_id)

    active_map = None

    for map_item in maps:
        if str(get_map_id(map_item)) == str(curr_id):
            active_map = map_item
            break

    if not active_map and maps:
        active_map = maps[0]

    if not active_map:
        return

    rooms_raw = get_map_rooms(active_map)
    rooms_normalized = normalize_rooms(rooms_raw)
    active_png = get_map_png(active_map)

    publish("map/current", active_map)
    publish("map/current_id", get_map_id(active_map))
    publish("map/current_name", get_map_name(active_map))
    publish("map/current_rooms_raw", rooms_raw)
    publish("map/current_rooms_normalized", rooms_normalized)
    publish("map/current_room_names", [room["name"] for room in rooms_normalized])

    if active_png:
        publish("map/current_png", active_png)

    publish_robot_and_dock_position(active_map)


def refresh_maps():
    print("Map refresh indul...")

    subprocess.run(
        ["python3", CONFIG["map_script"]],
        text=True,
        timeout=120,
        check=True,
    )

    index_path = Path(CONFIG["maps_index"])

    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        publish_map_info(index)
        return index

    publish("error", {"source": "refresh_maps", "error": "maps_index.json not found"}, retain=False)
    return None


def read_scheduler():
    scheduler = get_property(8, 2)
    publish("scheduler/raw", scheduler)
    publish("scheduler/entries", parse_scheduler_entries_payload(scheduler))
    publish("scheduler/last_read", int(time.time()))
    return scheduler


def start_capture(payload):
    global capture_session, last_capture_status, last_capture_map, last_capture_scheduler

    data = parse_command_payload(payload)
    if not isinstance(data, dict):
        data = {}

    label = str(data.get("label") or data.get("name") or "x10_capture")
    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "x10_capture"
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{session_id}_{safe_label}.jsonl"
    path = Path(CONFIG["capture_dir"]) / filename

    capture_session = {
        "session_id": session_id,
        "label": label,
        "map_id": data.get("map_id"),
        "started_ts": int(time.time()),
        "file": str(path),
        "sample_count": 0,
        "last_sample_ts": None,
    }
    last_capture_status = 0
    last_capture_map = 0
    last_capture_scheduler = 0

    append_capture_event("capture_start", {"request": data, "config": {
        "status_sec": CONFIG["capture_status_sec"],
        "map_sec": CONFIG["capture_map_sec"],
        "scheduler_sec": CONFIG["capture_scheduler_sec"],
    }})
    publish_command_result("capture_start", True, "capture started", capture_public_status())


def stop_capture():
    global capture_session

    status = capture_public_status()
    if capture_session:
        append_capture_event("capture_stop", status)
    capture_session = None
    publish_capture_status(force=True)
    publish_command_result("capture_stop", True, "capture stopped", status)


def capture_tick():
    global last_capture_status, last_capture_map, last_capture_scheduler

    if not capture_session:
        return

    now = time.time()

    if now - last_capture_status >= CONFIG["capture_status_sec"]:
        try:
            append_capture_event("status", read_status())
        except Exception as e:
            append_capture_event("status_error", error=e)
        last_capture_status = now

    if now - last_capture_map >= CONFIG["capture_map_sec"]:
        try:
            append_capture_event("map_refresh", refresh_maps())
        except Exception as e:
            append_capture_event("map_refresh_error", error=e)
        last_capture_map = now

    if now - last_capture_scheduler >= CONFIG["capture_scheduler_sec"]:
        try:
            scheduler = read_scheduler()
            append_capture_event("scheduler", {
                "raw": scheduler,
                "entries": parse_scheduler_entries_payload(scheduler),
            })
        except Exception as e:
            append_capture_event("scheduler_error", error=e)
        last_capture_scheduler = now


def parse_scheduler_entries(raw):
    if not raw:
        return []
    return [entry for entry in str(raw).split(";") if entry.strip()]


def normalize_days(days):
    raw = str(days or "").ljust(7, "0")[:7]
    return "".join("1" if char == "1" else "0" for char in raw)


def parse_scheduler_entry(entry):
    parts = entry.split("-")

    if len(parts) < 9:
        return None

    return {
        "task_id": parts[0],
        "enabled": parts[1],
        "time": parts[2],
        "days": parts[3],
        "flag": parts[4],
        "clean_mode": parts[4],
        "map_id": parts[5],
        "suction": parts[6],
        "clean_param": parts[7],
        "water_level": parts[7],
        "segments": parts[8],
        "raw": entry,
    }


def parse_scheduler_entries_payload(raw):
    return [parsed for parsed in (parse_scheduler_entry(entry) for entry in parse_scheduler_entries(raw)) if parsed]


def find_scheduler_task(raw, task_id):
    for entry in parse_scheduler_entries(raw):
        parsed = parse_scheduler_entry(entry)

        if parsed and parsed["task_id"] == str(task_id):
            return parsed

    return None


def build_schedule_entry(map_id, segments, start_time, enabled=1, days="0000000", task_id=None, clean_mode=0, suction=None, clean_param=None):
    task_id = task_id if task_id is not None else CONFIG["room_clean_task_id"]
    suction = suction if suction is not None else CONFIG["room_clean_suction"]
    clean_param = clean_param if clean_param is not None else CONFIG["room_clean_param"]
    clean_mode = 0 if clean_mode is None else clean_mode
    hhmm = str(start_time or "06:00")[:5]
    enabled = "1" if str(enabled).lower() in ("1", "true", "yes", "on") else "0"
    days = str(days or "0000000")

    segment_text = ",".join(str(x) for x in segments) if isinstance(segments, list) else str(segments)

    return f"{task_id}-{enabled}-{hhmm}-{days}-{clean_mode}-{map_id}-{suction}-{clean_param}-{segment_text}"


def build_room_clean_entry(map_id, segments, delay_min=None, task_id=None, clean_mode=0, suction=None, clean_param=None):
    delay_min = delay_min if delay_min is not None else CONFIG["room_clean_delay_min"]
    run_at = datetime.now() + timedelta(minutes=int(delay_min))
    return build_schedule_entry(
        map_id=map_id,
        segments=segments,
        start_time=run_at.strftime("%H:%M"),
        enabled=1,
        days="0000000",
        task_id=task_id,
        clean_mode=clean_mode,
        suction=suction,
        clean_param=clean_param,
    )


def set_room_clean_schedule(map_id, segments, delay_min=None, clean_mode=0, suction=None, clean_param=None):
    current = read_scheduler()
    entries = parse_scheduler_entries(current)

    task_id = CONFIG["room_clean_task_id"]

    new_entry = build_room_clean_entry(
        map_id=map_id,
        segments=segments,
        delay_min=delay_min,
        task_id=task_id,
        clean_mode=clean_mode,
        suction=suction,
        clean_param=clean_param,
    )

    kept_entries = []

    for entry in entries:
        parsed = parse_scheduler_entry(entry)

        if parsed and parsed["task_id"] == str(task_id):
            continue

        kept_entries.append(entry)

    kept_entries.append(new_entry)

    new_scheduler = ";".join(kept_entries)

    publish("scheduler/write_candidate", new_scheduler, retain=False, force=True)

    result = set_property(8, 2, new_scheduler)

    publish("scheduler/write_result", result, retain=False, force=True)

    time.sleep(1)
    read_scheduler()

    return {
        "new_entry": new_entry,
        "new_scheduler": new_scheduler,
        "result": result,
    }


def set_clean_schedule(map_id, segments, start_time, enabled=1, days="1111111", clean_mode=0, suction=None, clean_param=None):
    current = read_scheduler()
    entries = parse_scheduler_entries(current)

    task_id = CONFIG["room_clean_task_id"]
    new_entry = build_schedule_entry(
        map_id=map_id,
        segments=segments,
        start_time=start_time,
        enabled=enabled,
        days=days,
        clean_mode=clean_mode,
        task_id=task_id,
        suction=suction,
        clean_param=clean_param,
    )

    kept_entries = []

    for entry in entries:
        parsed = parse_scheduler_entry(entry)

        if parsed and parsed["task_id"] == str(task_id):
            continue

        kept_entries.append(entry)

    kept_entries.append(new_entry)
    new_scheduler = ";".join(kept_entries)

    publish("scheduler/write_candidate", new_scheduler, retain=False, force=True)
    result = set_property(8, 2, new_scheduler)
    publish("scheduler/write_result", result, retain=False, force=True)

    time.sleep(1)
    read_scheduler()

    return {
        "new_entry": new_entry,
        "new_scheduler": new_scheduler,
        "result": result,
    }


def one_hot_day(index):
    chars = ["0"] * 7
    robot_index = ROBOT_DAY_MASK_INDEX_BY_HC_DAY[int(index)]
    chars[robot_index] = "1"
    return "".join(chars)


def set_weekly_clean_schedules(map_id, schedules):
    new_entries = []
    for item in schedules:
        day_index = int(item.get("day_index", 0))
        if day_index < 0 or day_index > 6:
            continue

        segments = item.get("segments") or item.get("segment_id") or item.get("segment")
        if segments is None:
            segments = []
        if not isinstance(segments, list):
            segments = [segments]
        segments = [segment for segment in segments if str(segment).strip()]
        if not segments:
            segments = [0]
            item["enabled"] = 0

        task_id = WEEKLY_TASK_IDS[day_index]
        entry = build_schedule_entry(
            map_id=item.get("map_id", map_id),
            segments=segments,
            start_time=item.get("start_time") or item.get("time") or "06:00",
            enabled=item.get("enabled", 1),
            days=one_hot_day(day_index),
            task_id=task_id,
            clean_mode=item.get("mode", item.get("clean_mode", 0)),
            suction=item.get("suction", CONFIG["room_clean_suction"]),
            clean_param=item.get("clean_param", item.get("water_level", CONFIG["room_clean_param"])),
        )
        new_entries.append(entry)

    new_scheduler = ";".join(new_entries)

    publish("scheduler/write_candidate", new_scheduler, retain=False, force=True)
    result = ensure_miio_success(set_property(8, 2, new_scheduler), "weekly scheduler")
    publish("scheduler/write_result", result, retain=False, force=True)

    time.sleep(1)
    read_scheduler()

    return {
        "new_entries": new_entries,
        "new_scheduler": new_scheduler,
        "result": result,
    }


def publish_room_clean_status(status, extra=None):
    data = {
        "status": status,
        "ts": int(time.time()),
    }

    if extra is not None:
        data.update(extra)

    publish("room_clean/status", data, retain=True, force=True)


def watch_room_clean():
    global active_room_clean

    if not active_room_clean:
        return

    raw = read_scheduler()
    task = find_scheduler_task(raw, active_room_clean["task_id"])

    if not task:
        publish_room_clean_status("missing_task", {"active": active_room_clean})
        active_room_clean = None
        return

    publish("room_clean/task", task)

    if task["enabled"] == "0":
        publish_room_clean_status(
            "finished_or_cancelled",
            {
                "task": task,
                "active": active_room_clean,
            },
        )
        active_room_clean = None
    else:
        publish_room_clean_status(
            "active",
            {
                "task": task,
                "active": active_room_clean,
            },
        )


def read_status():
    robot_state = get_property(2, 1)
    battery = get_property(3, 1)
    charge_status = get_property(3, 2)
    task_state = get_property(4, 1)
    clean_mode = get_property(4, 23)
    mop_attached = get_property(4, 6)
    suction = get_property(4, 4)
    water_level = get_property(4, 5)

    status = {
        "state": robot_state,
        "state_text": STATE_TEXT.get(robot_state, f"unknown_{robot_state}"),
        "battery": battery,
        "charge_status": charge_status,
        "task_state": task_state,
        "clean_mode": clean_mode,
        "mop_attached": mop_attached,
        "suction": suction,
        "water_level": water_level,
        "ts": int(time.time()),
    }

    publish("state", status)
    publish("battery", battery)
    publish("robot_state", robot_state)
    publish("robot_state_text", status["state_text"])
    publish("charge_status", charge_status)
    publish("task_state", task_state)
    publish("clean_mode", clean_mode)
    publish("mop_attached", mop_attached)
    publish("suction", suction)
    publish("water_level", water_level)
    publish("bridge/last_seen", int(time.time()))

    get_map_object()

    return status


def check_map_update():
    global last_map_md5

    obj = get_map_object()

    if not obj:
        return

    md5 = obj.get("md5")

    if not md5:
        return

    if md5 != last_map_md5:
        print(f"Map md5 változott: {last_map_md5} -> {md5}")
        last_map_md5 = md5

        try:
            refresh_maps()
        except Exception as e:
            publish("error", {"source": "map_refresh", "error": str(e)}, retain=False)


def handle_room_clean(payload):
    global active_room_clean

    try:
        data = json.loads(payload) if payload else {}
    except Exception:
        data = {"segments": payload}

    map_id = data.get("map_id", 3)
    segments = data.get("segments") or data.get("segment_id") or data.get("segment")

    if segments is None:
        publish_command_result(
            "room_clean",
            ok=False,
            message='missing segments. Example: {"map_id":3,"segments":[4]}',
            extra=data,
        )
        return

    if not isinstance(segments, list):
        segments = [segments]

    delay_min = data.get("delay_min", CONFIG["room_clean_delay_min"])
    mode = data.get("mode", data.get("clean_mode", 0))
    suction = data.get("suction", CONFIG["room_clean_suction"])
    clean_param = data.get("clean_param", CONFIG["room_clean_param"])

    result = set_room_clean_schedule(
        map_id=map_id,
        segments=segments,
        delay_min=delay_min,
        clean_mode=mode,
        suction=suction,
        clean_param=clean_param,
    )

    active_room_clean = {
        "task_id": CONFIG["room_clean_task_id"],
        "map_id": map_id,
        "segments": segments,
        "delay_min": delay_min,
        "mode": mode,
        "clean_mode": mode,
        "suction": suction,
        "clean_param": clean_param,
        "water_level": clean_param,
        "created_ts": int(time.time()),
    }

    publish("room_clean/request", data, retain=False, force=True)
    publish_room_clean_status(
        "scheduled",
        {
            "active": active_room_clean,
            "result": result,
        },
    )
    publish_command_result("room_clean", True, "room clean schedule written", result)


def handle_schedule_clean(payload):
    try:
        data = json.loads(payload) if payload else {}
    except Exception:
        data = {}

    map_id = data.get("map_id", 3)
    segments = data.get("segments") or data.get("segment_id") or data.get("segment")

    if segments is None:
        publish_command_result(
            "schedule_clean",
            ok=False,
            message='missing segments. Example: {"map_id":3,"segments":[4],"start_time":"06:30"}',
            extra=data,
        )
        return

    if not isinstance(segments, list):
        segments = [segments]

    start_time = data.get("start_time") or data.get("time") or "06:00"
    days = data.get("days", "1111111")
    enabled = data.get("enabled", 1)
    suction = data.get("suction", CONFIG["room_clean_suction"])
    clean_param = data.get("clean_param", data.get("water_level", CONFIG["room_clean_param"]))
    mode = data.get("mode", data.get("clean_mode", 0))

    result = set_clean_schedule(
        map_id=map_id,
        segments=segments,
        start_time=start_time,
        enabled=enabled,
        days=days,
        clean_mode=mode if mode is not None else 0,
        suction=suction,
        clean_param=clean_param,
    )

    request = {
        "task_id": CONFIG["room_clean_task_id"],
        "map_id": map_id,
        "segments": segments,
        "start_time": start_time,
        "days": days,
        "enabled": enabled,
        "mode": mode,
        "suction": suction,
        "clean_param": clean_param,
        "water_level": clean_param,
        "created_ts": int(time.time()),
    }

    publish("room_clean/request", request, retain=False, force=True)
    publish_room_clean_status("scheduled", {"active": request, "result": result})
    publish_command_result("schedule_clean", True, "clean schedule written", result)


def handle_schedule_clean_week(payload):
    try:
        data = json.loads(payload) if payload else {}
    except Exception:
        data = {}

    map_id = data.get("map_id", 3)
    schedules = data.get("schedules") or []

    if not isinstance(schedules, list) or not schedules:
        publish_command_result(
            "schedule_clean_week",
            ok=False,
            message='missing schedules. Example: {"map_id":3,"schedules":[{"day_index":0,"start_time":"06:00","segments":[4]}]}',
            extra=data,
        )
        return

    result = set_weekly_clean_schedules(map_id, schedules)

    publish("room_clean/request", data, retain=False, force=True)
    publish_room_clean_status(
        "weekly_schedule_saved",
        {
            "active": {
                "map_id": map_id,
                "schedules": schedules,
                "created_ts": int(time.time()),
            },
            "result": result,
        },
    )
    publish_command_result("schedule_clean_week", True, "weekly clean schedule written", result)


def parse_command_payload(payload):
    try:
        return json.loads(payload) if payload else {}
    except Exception:
        return {"value": payload}


def command_value(payload, key="value"):
    data = parse_command_payload(payload)
    if isinstance(data, dict):
        return data.get(key, data.get("value"))
    return data


def command_int(payload, key="value"):
    value = command_value(payload, key)
    if value is None or value == "":
        raise ValueError(f"missing {key}")
    return int(value)


def handle_select_map(payload):
    requested_map_id = command_int(payload, "map_id")
    saved_map_id, map_item = resolve_select_map_id(requested_map_id)
    header_map_id = get_map_id(map_item) if map_item else None
    activation_map_id = header_map_id if header_map_id is not None else requested_map_id
    action_payload = json.dumps({"sm": {}, "mapid": activation_map_id}, separators=(",", ":"))
    previous_map_obj = get_map_object()
    previous_md5 = previous_map_obj.get("md5") if isinstance(previous_map_obj, dict) else None
    result = ensure_miio_success(
        call_action_with_params(
            CONFIG["set_map_siid"],
            CONFIG["set_map_aiid"],
            [{"piid": 4, "value": action_payload}],
        ),
        "select map",
    )
    publish("map/selected_request", {
        "map_id": requested_map_id,
        "saved_map_id": saved_map_id,
        "activation_map_id": activation_map_id,
        "action_payload": action_payload,
        "map_name": get_map_name(map_item) if map_item else None,
        "ts": int(time.time()),
    }, retain=False, force=True)
    publish_command_result(
        "select_map",
        True,
        "map activation sent",
        {
            "map_id": requested_map_id,
            "saved_map_id": saved_map_id,
            "activation_map_id": activation_map_id,
            "action_payload": action_payload,
            "map_name": get_map_name(map_item) if map_item else None,
            "siid": CONFIG["set_map_siid"],
            "aiid": CONFIG["set_map_aiid"],
            "result": result,
        },
    )
    switched_obj = wait_for_map_object_change(previous_md5, activation_map_id)
    if switched_obj:
        publish("map/selected_confirmed", {
            "map_id": requested_map_id,
            "activation_map_id": activation_map_id,
            "previous_md5": previous_md5,
            "md5": switched_obj.get("md5"),
            "ts": int(time.time()),
        }, retain=False, force=True)
    else:
        publish("map/selected_confirmed", {
            "map_id": requested_map_id,
            "activation_map_id": activation_map_id,
            "previous_md5": previous_md5,
            "md5": None,
            "timeout": True,
            "ts": int(time.time()),
        }, retain=False, force=True)
    refresh_maps()
    read_status()


def wait_for_map_object_change(previous_md5, activation_map_id, timeout_sec=20):
    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        time.sleep(2)
        obj = get_map_object()
        if not isinstance(obj, dict):
            continue

        md5 = obj.get("md5")
        if previous_md5 and md5 and md5 != previous_md5:
            return obj

        if not previous_md5 and md5:
            return obj

    return None


def handle_command(command, payload):
    print(f"Command: {command} payload={payload}")

    if command == "start":
        call_action(2, 1)
        publish_command_result(command, True, "start sent")

    elif command == "stop":
        call_action(2, 2)
        publish_command_result(command, True, "stop sent")

    elif command == "home":
        call_action(3, 1)
        publish_command_result(command, True, "home sent")

    elif command == "refresh_map":
        refresh_maps()
        publish_command_result(command, True, "map refreshed")

    elif command == "status":
        read_status()
        publish_command_result(command, True, "status refreshed")

    elif command == "check_map":
        check_map_update()
        publish_command_result(command, True, "map checked")

    elif command == "read_scheduler":
        scheduler = read_scheduler()
        publish_command_result(command, True, "scheduler read", scheduler)

    elif command == "select_map":
        handle_select_map(payload)
        return

    elif command == "set_clean_mode":
        value = command_int(payload)
        result = set_property(4, 23, value)
        publish("clean_mode", value)
        publish_command_result(command, True, "clean mode set", {"value": value, "result": result})

    elif command == "set_suction":
        value = command_int(payload)
        result = set_property(4, 4, value)
        publish("suction", value)
        publish_command_result(command, True, "suction set", {"value": value, "result": result})

    elif command == "set_water_level":
        value = command_int(payload)
        result = set_property(4, 5, value)
        publish("water_level", value)
        publish_command_result(command, True, "water level set", {"value": value, "result": result})

    elif command == "room_clean":
        handle_room_clean(payload)
        time.sleep(2)
        read_status()
        return

    elif command == "schedule_clean":
        handle_schedule_clean(payload)
        time.sleep(2)
        read_status()
        return

    elif command == "schedule_clean_week":
        handle_schedule_clean_week(payload)
        time.sleep(2)
        read_status()
        return

    elif command == "capture_start":
        start_capture(payload)
        return

    elif command == "capture_stop":
        stop_capture()
        return

    else:
        publish("error", {"source": "command", "error": f"unknown command: {command}"}, retain=False)
        publish_command_result(command, False, "unknown command")
        return

    time.sleep(2)
    read_status()


def on_connect(client, userdata, flags, rc):
    print("MQTT connected:", rc)
    client.subscribe(topic("command/#"))
    publish("bridge/online", 1)
    publish("bridge/status", "online")
    publish("bridge/last_seen", int(time.time()))


def on_message(client, userdata, msg):
    command = "unknown"
    try:
        if msg.retain:
            print(f"Ignored retained command: {msg.topic}")
            return

        prefix = topic("command/")

        if not msg.topic.startswith(prefix):
            return

        command = msg.topic.replace(prefix, "", 1)
        payload = msg.payload.decode("utf-8").strip()

        threading.Thread(
            target=run_command_worker,
            args=(command, payload),
            name=f"x10-command-{command}",
            daemon=True,
        ).start()

    except Exception as e:
        publish("error", {"source": "mqtt_message", "error": str(e)}, retain=False)
        publish_command_result(command, False, str(e))


def run_command_worker(command, payload):
    try:
        with command_lock:
            handle_command(command, payload)
    except Exception as e:
        publish("error", {"source": "command_worker", "command": command, "error": str(e)}, retain=False)
        publish_command_result(command, False, str(e))


def main():
    global last_status_poll, last_map_poll, last_scheduler_watch

    client.on_connect = on_connect
    client.on_message = on_message
    client.will_set(topic("bridge/online"), "0", retain=True)

    client.connect(CONFIG["mqtt_host"], CONFIG["mqtt_port"], 60)
    client.loop_start()

    publish("bridge/online", 1)
    publish("bridge/status", "online")
    publish("bridge/last_seen", int(time.time()))
    publish_capture_status(force=True)

    if not CONFIG["robot_ip"] or not CONFIG["robot_token"]:
        publish("bridge/status", "config_missing", force=True)
        publish(
            "error",
            {
                "source": "config",
                "error": "X10_ROBOT_IP and X10_ROBOT_TOKEN are required",
            },
            retain=True,
            force=True,
        )
        while True:
            publish("bridge/status", "config_missing", force=True)
            publish("bridge/last_seen", int(time.time()), force=True)
            time.sleep(60)

    publish("error", {}, retain=True, force=True)

    while True:
        try:
            now = time.time()

            current_state = last_state.get("robot_state")
            is_cleaning = current_state in ("1", "5","12")

            poll_sec = CONFIG["poll_cleaning_sec"] if is_cleaning else CONFIG["poll_idle_sec"]

            if now - last_status_poll >= poll_sec:
                status = read_status()
                last_status_poll = now
                is_cleaning = status["state"] in (1, 5, 12)

            if is_cleaning and now - last_map_poll >= CONFIG["map_check_cleaning_sec"]:
                check_map_update()
                last_map_poll = now

            if active_room_clean and now - last_scheduler_watch >= CONFIG["scheduler_watch_sec"]:
                watch_room_clean()
                last_scheduler_watch = now

            capture_tick()

            time.sleep(1)

        except Exception as e:
            publish("error", {"source": "main_loop", "error": str(e)}, retain=False)
            time.sleep(10)


if __name__ == "__main__":
    main()
