import json
import os
import signal
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import paho.mqtt.client as mqtt
import psycopg2
from psycopg2 import OperationalError
from psycopg2.extras import execute_values


# ====== CONFIG ======
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

PG_HOST = os.getenv("PG_HOST", "pgbouncer")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB = os.getenv("PG_DB", "homecontrol")
PG_USER = os.getenv("PG_USER", "hc")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")

PG_DSN = f"host={PG_HOST} port={PG_PORT} dbname={PG_DB} user={PG_USER} password={PG_PASSWORD}"

MQTT_ROOT = "zigbee"
MQTT_SUBSCRIPTIONS = [
    "zigbee/#",
    "homecontrol/tele/tuya/#",
    "homecontrol/tele/growatt/#",
    "homecontrol/tele/irrigation/+/pump_metrics",
    "homecontrol/tele/irrigation/+/solar",
    "homecontrol/stat/irrigation/+/availability",
    "homecontrol/xiaomi_x10/#",
    "homecontrol/gree_climate/#",
]

OFFLINE_AFTER_MINUTES = 20
SWEEP_EVERY_SECONDS = 60

TOPIC_CACHE_TTL_SEC = 60
RULES_CACHE_TTL_SEC = 60
METRIC_CACHE_TTL_SEC = 300

ERROR_LOG_TTL_SEC = 300
HEARTBEAT_FILE = "/tmp/hc_ingest_heartbeat"

MEASUREMENT_BATCH_SIZE = 100
MEASUREMENT_FLUSH_EVERY_SECONDS = 2.0
MQTT_RETRY_SECONDS = 5
X10_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
X10_HC_WEEKLY_TASK_IDS = set(range(11, 18))
X10_HC_TASK_ID_BY_DAY_INDEX = [12, 13, 14, 17, 15, 16, 11]
X10_HC_DAY_INDEX_BY_TASK_ID = {task_id: index for index, task_id in enumerate(X10_HC_TASK_ID_BY_DAY_INDEX)}
X10_HC_DAY_INDEX_BY_ROBOT_MASK_INDEX = [6, 0, 1, 2, 3, 4, 5]

STATE_CHANGE_KEYS = {
    "switch_state",
    "contact",
    "occupancy",
    "motion",
    "presence",
    "pump_running",
    "valve_state",
    "valve_code_text",
    "manual_valve_state",
    "liquid_state",
    "water_leak",
    "battery_low",
    "x10_bridge_online",
    "x10_bridge_status",
    "x10_robot_state",
    "x10_robot_state_text",
    "x10_charge_status",
    "x10_task_state",
    "x10_clean_mode",
    "x10_mop_attached",
    "x10_suction",
    "x10_water_level",
    "x10_command_result",
    "x10_error",
    "x10_room_clean_status",
    "climate_power",
    "climate_mode",
    "climate_target_temperature",
    "climate_fan_speed",
    "climate_error",
}


# ====== TYPES ======
@dataclass
class Rule:
    store_mode: str
    deadband: Optional[float]
    min_i: Optional[int]
    max_i: Optional[int]
    enabled: bool


@dataclass
class MetricMeta:
    value_type: str
    min_num: Optional[float]
    max_num: Optional[float]
    enforce_validation: bool


# ====== GLOBAL STATE / CACHES ======
running = True
mqtt_connected = False
mqtt_started_once = False

topic_to_entity: Dict[str, Tuple[Optional[int], float]] = {}
entity_rules: Dict[int, Tuple[Dict[str, Rule], float]] = {}
metric_meta_cache: Dict[str, Tuple[Optional[MetricMeta], float]] = {}

last_saved: Dict[Tuple[int, str], Tuple[Any, float]] = {}
error_log_last: Dict[str, float] = {}

pending_measurements: List[Tuple[int, str, Optional[float], Optional[bool], Optional[str], Optional[str], str]] = []
# tuple: (entity_id, key, v_num, v_bool, v_text, v_json_jsonstr, meta_jsonstr)


# ====== SIGNALS ======
def handle_signal(signum, frame):
    global running
    print(f"[SYS] signal received: {signum}, shutting down...")
    running = False


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


# ====== HELPERS ======
def now() -> float:
    return time.time()


def touch_heartbeat():
    try:
        with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))
    except Exception:
        pass


def log_limited(key: str, message: str):
    t = now()
    last = error_log_last.get(key, 0)
    if t - last >= ERROR_LOG_TTL_SEC:
        print(message)
        error_log_last[key] = t


def topic_base_of(topic: str) -> Optional[str]:
    parts = topic.split("/")
    if len(parts) >= 2 and parts[0] == MQTT_ROOT:
        return f"{parts[0]}/{parts[1]}"
    if len(parts) >= 2 and parts[0] == "homecontrol" and parts[1] == "xiaomi_x10":
        return "homecontrol/xiaomi_x10"
    if len(parts) >= 2 and parts[0] == "homecontrol" and parts[1] == "gree_climate":
        return "homecontrol/gree_climate"
    if len(parts) >= 5 and parts[0] == "homecontrol" and parts[1] == "tele" and parts[2] == "tuya":
        markers = {"availability", "error", "state", "m"}
        for i in range(3, len(parts)):
            if parts[i] in markers:
                if i == 4 and parts[3] == "poller":
                    return None
                return "/".join(parts[:i])
        return None
    if len(parts) >= 4 and parts[0] == "homecontrol" and parts[1] == "tele" and parts[2] == "growatt":
        return "/".join(parts[:4])
    if len(parts) >= 4 and parts[0] == "homecontrol" and parts[1] == "tele" and parts[2] == "irrigation":
        return "/".join(parts[:4])
    if len(parts) >= 4 and parts[0] == "homecontrol" and parts[1] == "stat" and parts[2] == "irrigation":
        return "homecontrol/tele/irrigation/" + parts[3]
    return None


def map_key(raw_key: str, raw_value: Any, topic: str = "") -> str:
    if topic.endswith("/solar"):
        solar_keys = {
            "battery_voltage": "solar_battery_voltage_v",
            "charge_current": "solar_charge_current_a",
            "pv_voltage": "solar_pv_voltage_v",
            "pv_current": "solar_pv_current_a",
            "controller_temp": "solar_controller_temp_c",
        }
        if raw_key in solar_keys:
            return solar_keys[raw_key]
    if raw_key == "energy":
        return "energy_kwh"
    if raw_key == "energy_forward_kwh":
        return "energy_kwh"
    if raw_key == "state":
        return "switch_state"
    if raw_key == "switch":
        return "switch_state"
    if raw_key == "pump":
        return "pump_running"
    if raw_key == "current_a":
        return "pump_current_a"
    if raw_key == "voltage_12v":
        return "supply_voltage_12v"
    if raw_key == "temp_c":
        return "controller_temp_c"
    if raw_key == "valve":
        return "valve_state"
    if raw_key == "manual_valve":
        return "manual_valve_state"
    if raw_key == "voltage":
        fv = coerce_num(raw_value)
        if fv is not None and fv >= 1000:
            return "battery_voltage_mv"
        return "mains_voltage_v"
    return raw_key


def tuya_metric_items(topic: str, payload: Any) -> Optional[List[Tuple[str, Any, str]]]:
    prefix = "homecontrol/tele/tuya/"
    if not topic.startswith(prefix):
        return None

    if topic.endswith("/error"):
        return []

    parts = topic.split("/")
    if len(parts) >= 7 and parts[-2] == "m":
        return [(parts[-1], payload, parts[-1])]

    if topic.endswith("/state"):
        if not isinstance(payload, dict):
            return []
        allowed = {
            "switch",
            "power_w",
            "voltage_v",
            "current_a",
            "energy_forward_kwh",
            "energy_calc_kwh",
            "tuya_raw_dps",
            "lag_sec",
            "recv_ts",
            "src_ts",
        }
        return [(k, v, k) for k, v in payload.items() if k in allowed]

    return []


def growatt_metric_items(topic: str, payload: Any) -> Optional[List[Tuple[str, Any, str]]]:
    prefix = "homecontrol/tele/growatt/"
    if not topic.startswith(prefix):
        return None

    if not isinstance(payload, dict):
        return []

    values = payload.get("values")
    if not isinstance(values, dict):
        values = payload

    scale_map = {
        "pvpowerin": ("growatt_pv_power_in_w", 0.1),
        "pvpowerout": ("growatt_pv_power_out_w", 0.1),
        "pv1watt": ("growatt_pv1_power_w", 0.1),
        "pv2watt": ("growatt_pv2_power_w", 0.1),
        "pv3watt": ("growatt_pv3_power_w", 0.1),
        "pvgridpower": ("growatt_grid_power_l1_w", 0.1),
        "pvgridpower2": ("growatt_grid_power_l2_w", 0.1),
        "pvgridpower3": ("growatt_grid_power_l3_w", 0.1),
        "pv1voltage": ("growatt_pv1_voltage_v", 0.1),
        "pv2voltage": ("growatt_pv2_voltage_v", 0.1),
        "pv3voltage": ("growatt_pv3_voltage_v", 0.1),
        "pvgridvoltage": ("growatt_grid_voltage_l1_v", 0.1),
        "pvgridvoltage2": ("growatt_grid_voltage_l2_v", 0.1),
        "pvgridvoltage3": ("growatt_grid_voltage_l3_v", 0.1),
        "pv1current": ("growatt_pv1_current_a", 0.1),
        "pv2current": ("growatt_pv2_current_a", 0.1),
        "pv3current": ("growatt_pv3_current_a", 0.1),
        "pvgridcurrent": ("growatt_grid_current_l1_a", 0.1),
        "pvgridcurrent2": ("growatt_grid_current_l2_a", 0.1),
        "pvgridcurrent3": ("growatt_grid_current_l3_a", 0.1),
        "pvfrequentie": ("growatt_grid_frequency_hz", 0.01),
        "pvenergytoday": ("growatt_energy_today_kwh", 0.1),
        "pvenergytotal": ("growatt_energy_total_kwh", 0.1),
        "epv1today": ("growatt_pv1_energy_today_kwh", 0.1),
        "epv1total": ("growatt_pv1_energy_total_kwh", 0.1),
        "epv2today": ("growatt_pv2_energy_today_kwh", 0.1),
        "epv2total": ("growatt_pv2_energy_total_kwh", 0.1),
        "epvtotal": ("growatt_pv_energy_total_kwh", 0.1),
        "pvtemperature": ("growatt_inverter_temperature_c", 0.1),
        "pvipmtemperature": ("growatt_ipm_temperature_c", 0.1),
        "totworktime": ("growatt_total_work_time_s", 0.5),
        "pvstatus": ("growatt_status_code", 1),
    }

    if not any(raw_key in scale_map for raw_key in values.keys()):
        return None

    items: List[Tuple[str, Any, str]] = []
    for raw_key, raw_value in values.items():
        if raw_key not in scale_map or raw_value is None:
            continue
        metric_key, scale = scale_map[raw_key]
        numeric = coerce_num(raw_value)
        if numeric is None:
            continue
        items.append((metric_key, numeric * scale, raw_key))

    if payload.get("device") is not None:
        items.append(("growatt_device", payload.get("device"), "device"))
    if payload.get("time") is not None:
        items.append(("growatt_sample_time", payload.get("time"), "time"))
    if payload.get("buffered") is not None:
        items.append(("growatt_buffered", payload.get("buffered"), "buffered"))

    return items


def x10_metric_items(topic: str, payload: Any) -> Optional[List[Tuple[str, Any, str]]]:
    prefix = "homecontrol/xiaomi_x10/"
    if not topic.startswith(prefix):
        return None

    rel = topic.removeprefix(prefix)
    if rel.startswith("command/"):
        return []

    scalar_map = {
        "battery": "battery",
        "robot_state": "x10_robot_state",
        "robot_state_text": "x10_robot_state_text",
        "charge_status": "x10_charge_status",
        "task_state": "x10_task_state",
        "clean_mode": "x10_clean_mode",
        "mop_attached": "x10_mop_attached",
        "suction": "x10_suction",
        "water_level": "x10_water_level",
        "bridge/online": "x10_bridge_online",
        "bridge/status": "x10_bridge_status",
        "bridge/last_seen": "x10_bridge_last_seen",
        "map/count": "x10_map_count",
        "map/current_id": "x10_map_current_id",
        "map/current_id_from_index": "x10_map_current_id_from_index",
        "map/current_name": "x10_map_current_name",
        "map/current_png": "x10_map_current_png",
        "map/md5": "x10_map_md5",
        "map/object_name": "x10_map_object_name",
        "scheduler/last_read": "x10_scheduler_last_read",
        "scheduler/entries": "x10_scheduler_entries",
        "scheduler/raw": "x10_scheduler_raw",
        "scheduler/write_candidate": "x10_scheduler_write_candidate",
        "scheduler/write_result": "x10_scheduler_write_result",
    }

    json_topic_map = {
        "state": "x10_state",
        "map/current": "x10_map_current",
        "map/current_room_names": "x10_map_room_names",
        "map/current_rooms": "x10_map_rooms",
        "map/current_rooms_raw": "x10_map_rooms_raw",
        "map/current_rooms_normalized": "x10_map_rooms_normalized",
        "map/index": "x10_map_index",
        "map/object": "x10_map_object",
        "robot/header_raw": "x10_robot_header_raw",
        "robot/position": "x10_robot_position",
        "robot/position_px": "x10_robot_position_px",
        "dock/position": "x10_dock_position",
        "dock/position_px": "x10_dock_position_px",
        "room_clean/request": "x10_room_clean_request",
        "room_clean/status": "x10_room_clean_status",
        "room_clean/task": "x10_room_clean_task",
        "command_result": "x10_command_result",
        "error": "x10_error",
    }

    if rel == "state" and isinstance(payload, dict):
        return [
            ("x10_state", payload, rel),
            ("x10_robot_state", payload.get("state"), "state.state"),
            ("x10_robot_state_text", payload.get("state_text"), "state.state_text"),
            ("battery", payload.get("battery"), "state.battery"),
            ("x10_charge_status", payload.get("charge_status"), "state.charge_status"),
            ("x10_task_state", payload.get("task_state"), "state.task_state"),
            ("x10_clean_mode", payload.get("clean_mode"), "state.clean_mode"),
            ("x10_mop_attached", payload.get("mop_attached"), "state.mop_attached"),
            ("x10_suction", payload.get("suction"), "state.suction"),
            ("x10_water_level", payload.get("water_level"), "state.water_level"),
        ]

    if rel in scalar_map:
        return [(scalar_map[rel], payload, rel)]

    if rel in json_topic_map:
        return [(json_topic_map[rel], payload, rel)]

    return []


def gree_climate_metric_items(topic: str, payload: Any) -> Optional[List[Tuple[str, Any, str]]]:
    prefix = "homecontrol/gree_climate/"
    if not topic.startswith(prefix):
        return None

    rel = topic.removeprefix(prefix)
    if rel.startswith("command"):
        return []

    if rel == "state" and isinstance(payload, dict):
        items: List[Tuple[str, Any, str]] = [
            ("climate_ok", payload.get("ok"), "state.ok"),
            ("climate_power", payload.get("power"), "state.power"),
            ("climate_mode", payload.get("mode"), "state.mode"),
            ("climate_target_temperature", payload.get("target_temperature"), "state.target_temperature"),
            ("climate_current_temperature", payload.get("current_temperature"), "state.current_temperature"),
            ("climate_fan_speed", payload.get("fan_speed"), "state.fan_speed"),
        ]
        if payload.get("error"):
            items.append(("climate_error", payload.get("error"), "state.error"))
        return items

    if rel == "command_result":
        return [("climate_command_result", payload, rel)]

    return []


def coerce_num(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(" ", "")
        if "," in s and "." not in s:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None
    return None


def coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "on", "online", "yes"):
            return True
        if s in ("0", "false", "off", "offline", "no"):
            return False
    return None


def normalize_value(vtype: str, value: Any) -> Tuple[Optional[float], Optional[bool], Optional[str], Optional[Any]]:
    if vtype == "num":
        fv = coerce_num(value)
        if fv is None:
            raise ValueError(f"not_numeric: {value!r}")
        return fv, None, None, None

    if vtype == "bool":
        bv = coerce_bool(value)
        if bv is None:
            raise ValueError(f"not_boolean: {value!r}")
        return None, bv, None, None

    if vtype == "text":
        return None, None, str(value), None

    if vtype == "json":
        return None, None, None, value

    raise ValueError(f"unsupported_value_type: {vtype!r}")


def comparable_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    fv = coerce_num(value)
    if fv is not None:
        return fv
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    if value is None:
        return None
    return str(value)


def metric_in_range(meta: MetricMeta, value: Any) -> Tuple[bool, str]:
    if meta.value_type != "num":
        return True, "ok"

    if not meta.enforce_validation:
        return True, "ok"

    fv = coerce_num(value)
    if fv is None:
        return False, "not_numeric"

    if meta.min_num is not None and fv < float(meta.min_num):
        return False, f"below_min({fv}<{meta.min_num})"

    if meta.max_num is not None and fv > float(meta.max_num):
        return False, f"above_max({fv}>{meta.max_num})"

    return True, "ok"


def should_store_measurement(rule: Rule) -> bool:
    return rule.store_mode in ("both", "measurement", "history")


def should_store_state(rule: Rule) -> bool:
    return rule.store_mode in ("both", "state", "latest")


# ====== DB LOOKUPS ======
def load_entity_id_by_topic(cur, tb: str) -> Optional[int]:
    cur.execute("select id from hc.entity where topic_base=%s and is_active=true", (tb,))
    row = cur.fetchone()
    return row[0] if row else None


def load_rules(cur, entity_id: int) -> Dict[str, Rule]:
    cur.execute("""
        select metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled
        from hc.entity_metric
        where entity_id=%s
    """, (entity_id,))
    rules = {}
    for (k, sm, db, mi, ma, en) in cur.fetchall():
        rules[k] = Rule(sm, db, mi, ma, en)
    return rules


def load_metric_meta(cur, metric_key: str) -> Optional[MetricMeta]:
    cur.execute("""
        select value_type, min_num, max_num, enforce_validation
        from hc.metric
        where key=%s and is_active=true
    """, (metric_key,))
    row = cur.fetchone()
    if not row:
        return None
    return MetricMeta(
        value_type=row[0],
        min_num=row[1],
        max_num=row[2],
        enforce_validation=row[3],
    )


def cached_entity_id(cur, tb: str) -> Optional[int]:
    t = now()
    hit = topic_to_entity.get(tb)
    if hit and hit[1] > t:
        return hit[0]
    eid = load_entity_id_by_topic(cur, tb)
    topic_to_entity[tb] = (eid, t + TOPIC_CACHE_TTL_SEC)
    return eid


def cached_rules(cur, entity_id: int) -> Dict[str, Rule]:
    t = now()
    hit = entity_rules.get(entity_id)
    if hit and hit[1] > t:
        return hit[0]
    rules = load_rules(cur, entity_id)
    entity_rules[entity_id] = (rules, t + RULES_CACHE_TTL_SEC)
    return rules


def cached_metric_meta(cur, metric_key: str) -> Optional[MetricMeta]:
    t = now()
    hit = metric_meta_cache.get(metric_key)
    if hit and hit[1] > t:
        return hit[0]
    meta = load_metric_meta(cur, metric_key)
    metric_meta_cache[metric_key] = (meta, t + METRIC_CACHE_TTL_SEC)
    return meta


# ====== DECISION CACHE ======
def should_write(entity_id: int, metric_key: str, value: Any, rule: Rule, tnow: float) -> Tuple[bool, str]:
    if not rule.enabled:
        return False, "disabled"

    key = (entity_id, metric_key)
    prev = last_saved.get(key)
    if prev is None:
        return True, "first"

    prev_v, prev_ts = prev
    age = tnow - prev_ts

    if metric_key in STATE_CHANGE_KEYS and comparable_value(value) != prev_v:
        return True, "state_changed"

    if rule.min_i is not None and age < rule.min_i:
        return False, f"min_interval({age:.1f}s<{rule.min_i}s)"

    if rule.max_i is not None and age >= rule.max_i:
        return True, f"max_interval({age:.1f}s>={rule.max_i}s)"

    if rule.deadband is not None:
        try:
            v = float(value)
            pv = float(prev_v) if prev_v is not None else v
            if abs(v - pv) >= rule.deadband:
                return True, f"deadband(|{v:.3f}-{pv:.3f}|>={rule.deadband})"
            return False, f"deadband(|{v:.3f}-{pv:.3f}|<{rule.deadband})"
        except Exception:
            return True, "non_numeric_deadband_fallback"

    return False, "no_condition_met"


def update_last(entity_id: int, metric_key: str, value: Any, tnow: float):
    last_saved[(entity_id, metric_key)] = (comparable_value(value), tnow)


def warm_last_saved_from_entity_state(cur):
    cur.execute("""
        select entity_id, key, v_num, v_bool, v_text, v_json::text, extract(epoch from ts)
        from hc.entity_state
    """)
    loaded = 0
    for entity_id, key, v_num, v_bool, v_text, v_json, ts_epoch in cur.fetchall():
        if v_num is not None:
            value = float(v_num)
        elif v_bool is not None:
            value = bool(v_bool)
        elif v_text is not None:
            value = str(v_text)
        else:
            value = v_json
        last_saved[(entity_id, key)] = (comparable_value(value), float(ts_epoch))
        loaded += 1
    print(f"[CACHE] warmed last_saved from entity_state: {loaded} rows")


# ====== DB WRITES ======
def upsert_presence(cur, entity_id: int, status: str):
    cur.execute("""
        insert into hc.entity_presence (entity_id, last_seen_ts, status, updated_at)
        values (%s, now(), %s, now())
        on conflict (entity_id) do update set
          last_seen_ts = excluded.last_seen_ts,
          status = excluded.status,
          updated_at = excluded.updated_at
    """, (entity_id, status))


def upsert_entity_state(cur, entity_id: int, key: str, vtype: str, value: Any, meta: dict):
    v_num, v_bool, v_text, v_json_raw = normalize_value(vtype, value)
    v_json = json.dumps(v_json_raw) if v_json_raw is not None else None

    cur.execute("""
        insert into hc.entity_state (entity_id, key, ts, v_num, v_bool, v_text, v_json, meta)
        values (%s, %s, now(), %s, %s, %s, %s::jsonb, %s::jsonb)
        on conflict (entity_id, key) do update set
          ts = excluded.ts,
          v_num = excluded.v_num,
          v_bool = excluded.v_bool,
          v_text = excluded.v_text,
          v_json = excluded.v_json,
          meta = excluded.meta
    """, (entity_id, key, v_num, v_bool, v_text, v_json, json.dumps(meta)))


def delete_entity_state(cur, entity_id: int, key: str):
    cur.execute(
        """
        delete from hc.entity_state
        where entity_id = %s and key = %s
        """,
        (entity_id, key),
    )


def parse_segments(value: Any) -> List[int]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").split(",")

    segments = []
    for item in raw_items:
        try:
            number = int(str(item).strip())
        except Exception:
            continue
        if number:
            segments.append(number)
    return segments


def int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def sync_x10_current_map(cur, entity_id: int, payload: Any):
    if not isinstance(payload, dict):
        return

    map_id = int_or_none(payload.get("header", {}).get("map_id") or payload.get("map_id") or payload.get("id"))
    if map_id is None:
        return

    name = payload.get("name") or f"Map {map_id}"
    png = payload.get("png")

    cur.execute("""
        insert into hc.x10_map (entity_id, map_id, name, png, is_current, has_room_data, source, updated_at)
        values (%s, %s, %s, %s, true, false, 'robot', now())
        on conflict (entity_id, map_id) do update set
          name = excluded.name,
          png = coalesce(excluded.png, hc.x10_map.png),
          is_current = true,
          source = 'robot',
          updated_at = now()
    """, (entity_id, map_id, name, png))

    cur.execute(
        "update hc.x10_map set is_current=false where entity_id=%s and map_id<>%s",
        (entity_id, map_id),
    )


def sync_x10_current_rooms(cur, entity_id: int, payload: Any):
    if not isinstance(payload, list):
        return

    payload_rooms = []
    payload_segment_ids = []
    for room in payload:
        if not isinstance(room, dict):
            continue
        segment_id = int_or_none(room.get("segment_id"))
        if segment_id is None:
            continue
        payload_segment_ids.append(segment_id)
        payload_rooms.append({
            "segment_id": segment_id,
            "name": str(room.get("name") or f"room_{segment_id}"),
            "room_id": str(room.get("room_id") or "") if room.get("room_id") is not None else "",
        })

    if not payload_rooms:
        return

    cur.execute("""
        select v_num::integer
        from hc.entity_state
        where entity_id=%s and key='x10_map_current_id'
    """, (entity_id,))
    row = cur.fetchone()
    map_id = row[0] if row else 3

    cur.execute("""
        select map_id, segment_id, name, coalesce(room_id, '') as room_id
        from hc.x10_room
        where entity_id=%s and is_active=true
    """, (entity_id,))
    known_rooms = cur.fetchall()
    scores = {}
    for known_map_id, known_segment_id, known_name, known_room_id in known_rooms:
        score = 0
        for room in payload_rooms:
            if known_room_id and room["room_id"] and known_room_id == room["room_id"]:
                score += 4
            if int_or_none(known_segment_id) == room["segment_id"] and str(known_name or "") == room["name"]:
                score += 2
            elif int_or_none(known_segment_id) == room["segment_id"]:
                score += 1
        scores[known_map_id] = scores.get(known_map_id, 0) + score

    if scores:
        best_map_id, best_score = max(scores.items(), key=lambda item: item[1])
        current_score = scores.get(map_id, 0)
        if best_map_id != map_id and best_score >= max(4, current_score + 4):
            log_limited(
                f"x10_room_map_reassign:{entity_id}",
                f"[X10_ROOM_MAP_REASSIGN] current_map={map_id} matched_map={best_map_id} "
                f"current_score={current_score} matched_score={best_score} segments={payload_segment_ids}"
            )
            map_id = best_map_id

    cur.execute("""
        insert into hc.x10_map (entity_id, map_id, name, has_room_data, source, updated_at)
        values (%s, %s, %s, true, 'robot', now())
        on conflict (entity_id, map_id) do update set
          has_room_data = true,
          updated_at = now()
    """, (entity_id, map_id, f"Map {map_id}"))

    seen_segments = []
    for room in payload:
        if not isinstance(room, dict):
            continue
        segment_id = int_or_none(room.get("segment_id"))
        if segment_id is None:
            continue
        seen_segments.append(segment_id)
        cur.execute("""
            insert into hc.x10_room (
              entity_id, map_id, segment_id, name, room_id, room_type,
              neighbors, is_active, source, updated_at
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb, true, 'robot', now())
            on conflict (entity_id, map_id, segment_id) do update set
              name = excluded.name,
              room_id = excluded.room_id,
              room_type = excluded.room_type,
              neighbors = excluded.neighbors,
              is_active = true,
              source = 'robot',
              updated_at = now()
        """, (
            entity_id,
            map_id,
            segment_id,
            room.get("name") or f"room_{segment_id}",
            room.get("room_id"),
            int_or_none(room.get("type")),
            json.dumps(room.get("neighbors") or []),
        ))

    if seen_segments:
        cur.execute(
            """
            update hc.x10_room
            set is_active=false, updated_at=now()
            where entity_id=%s and map_id=%s and not (segment_id = any(%s))
            """,
            (entity_id, map_id, seen_segments),
        )


def x10_days_for_rows(days: str) -> List[int]:
    normalized = str(days or "0000000").ljust(7, "0")[:7]
    indexes = [
        X10_HC_DAY_INDEX_BY_ROBOT_MASK_INDEX[index]
        for index, char in enumerate(normalized)
        if char == "1"
    ]
    return indexes if indexes else []


def sync_x10_schedules(cur, entity_id: int, entries: Any):
    if not isinstance(entries, list):
        return

    seen_task_ids = []
    seen_hc_day_indexes = set()
    cur.execute("delete from hc.x10_schedule_day where entity_id=%s", (entity_id,))
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        task_id = int_or_none(entry.get("task_id"))
        if task_id is None:
            continue

        days = str(entry.get("days") or "0000000").ljust(7, "0")[:7]
        segments = parse_segments(entry.get("segments"))
        is_enabled = str(entry.get("enabled")) == "1"
        start_time = str(entry.get("time") or "00:00")[:5]
        clean_mode = int_or_none(entry.get("clean_mode", entry.get("flag")))
        map_id = int_or_none(entry.get("map_id"))
        suction = int_or_none(entry.get("suction"))
        water_level = int_or_none(entry.get("water_level", entry.get("clean_param")))
        is_hc_owned = task_id in X10_HC_WEEKLY_TASK_IDS
        seen_task_ids.append(task_id)

        cur.execute("""
            insert into hc.x10_schedule (
              entity_id, task_id, is_enabled, start_time, days,
              clean_mode, map_id, suction, water_level, segments,
              raw, is_weekly, is_hc_owned, updated_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, now())
            on conflict (entity_id, task_id) do update set
              is_enabled = excluded.is_enabled,
              start_time = excluded.start_time,
              days = excluded.days,
              clean_mode = excluded.clean_mode,
              map_id = excluded.map_id,
              suction = excluded.suction,
              water_level = excluded.water_level,
              segments = excluded.segments,
              raw = excluded.raw,
              is_weekly = excluded.is_weekly,
              is_hc_owned = excluded.is_hc_owned,
              updated_at = excluded.updated_at
        """, (
            entity_id,
            task_id,
            is_enabled,
            start_time,
            days,
            clean_mode,
            map_id,
            suction,
            water_level,
            json.dumps(segments),
            entry.get("raw"),
            days != "0000000",
            is_hc_owned,
        ))

        if not is_hc_owned:
            continue

        day_indexes = [X10_HC_DAY_INDEX_BY_TASK_ID.get(task_id, task_id - 11)]
        for day_index in day_indexes:
            if day_index < 0 or day_index > 6:
                continue
            seen_hc_day_indexes.add(day_index)
            cur.execute("""
                insert into hc.x10_schedule_day (
                  entity_id, task_id, day_index, day_name, is_enabled,
                  start_time, clean_mode, map_id, suction, water_level,
                  segments, raw, is_hc_owned, updated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, now())
                on conflict (entity_id, task_id, day_index) do update set
                  day_name = excluded.day_name,
                  is_enabled = excluded.is_enabled,
                  start_time = excluded.start_time,
                  clean_mode = excluded.clean_mode,
                  map_id = excluded.map_id,
                  suction = excluded.suction,
                  water_level = excluded.water_level,
                  segments = excluded.segments,
                  raw = excluded.raw,
                  is_hc_owned = excluded.is_hc_owned,
                  updated_at = excluded.updated_at
            """, (
                entity_id,
                task_id,
                day_index,
                X10_DAY_NAMES[day_index],
                is_enabled,
                start_time,
                clean_mode,
                map_id,
                suction,
                water_level,
                json.dumps(segments),
                entry.get("raw"),
                True,
            ))

    for day_index in range(7):
        if day_index in seen_hc_day_indexes:
            continue
        cur.execute("""
            insert into hc.x10_schedule_day (
              entity_id, task_id, day_index, day_name, is_enabled,
              start_time, clean_mode, map_id, suction, water_level,
              segments, raw, is_hc_owned, updated_at
            )
            values (%s, %s, %s, %s, false, '06:00', null, null, null, null, '[]'::jsonb, null, true, now())
            on conflict (entity_id, task_id, day_index) do update set
              day_name = excluded.day_name,
              is_enabled = excluded.is_enabled,
              start_time = excluded.start_time,
              clean_mode = excluded.clean_mode,
              map_id = excluded.map_id,
              suction = excluded.suction,
              water_level = excluded.water_level,
              segments = excluded.segments,
              raw = excluded.raw,
              is_hc_owned = excluded.is_hc_owned,
              updated_at = excluded.updated_at
        """, (
            entity_id,
            X10_HC_TASK_ID_BY_DAY_INDEX[day_index],
            day_index,
            X10_DAY_NAMES[day_index],
        ))

    if seen_task_ids:
        cur.execute(
            "delete from hc.x10_schedule where entity_id=%s and not (task_id = any(%s))",
            (entity_id, seen_task_ids),
        )


def queue_measurement(entity_id: int, key: str, vtype: str, value: Any, meta: dict):
    v_num, v_bool, v_text, v_json_raw = normalize_value(vtype, value)
    v_json = json.dumps(v_json_raw) if v_json_raw is not None else None
    pending_measurements.append(
        (entity_id, key, v_num, v_bool, v_text, v_json, json.dumps(meta))
    )


def insert_measurement_one(cur, row):
    entity_id, key, v_num, v_bool, v_text, v_json, meta = row
    cur.execute("""
        insert into hc.measurement (ts, entity_id, key, v_num, v_bool, v_text, v_json, meta)
        values (now(), %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
    """, (entity_id, key, v_num, v_bool, v_text, v_json, meta))


def flush_measurements(cur):
    if not pending_measurements:
        return 0

    rows = pending_measurements[:]
    pending_measurements.clear()

    sql = """
        insert into hc.measurement (ts, entity_id, key, v_num, v_bool, v_text, v_json, meta)
        values %s
    """
    template = "(now(), %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)"

    try:
        execute_values(cur, sql, rows, template=template, page_size=MEASUREMENT_BATCH_SIZE)
        return len(rows)

    except Exception as e:
        log_limited("batch_insert_error", f"[BATCH_ERR] execute_values failed, falling back row-by-row: {e}")

        inserted = 0
        for row in rows:
            try:
                insert_measurement_one(cur, row)
                inserted += 1
            except Exception as row_e:
                log_limited(
                    f"row_insert:{row[0]}:{row[1]}",
                    f"[ROW_ERR] entity={row[0]} key={row[1]} error={row_e}"
                )
                continue
        return inserted


# ====== MAIN ======
def main():
    global mqtt_connected, mqtt_started_once

    print("[CFG] PG_HOST env =", os.getenv("PG_HOST"))
    print("[CFG] PG_DSN =", PG_DSN.replace(PG_PASSWORD, "***") if PG_PASSWORD else PG_DSN)
    print("[CFG] MQTT =", MQTT_HOST, MQTT_PORT)

    def connect_db():
        while running:
            try:
                conn = psycopg2.connect(PG_DSN)
                conn.autocommit = True
                print("[DB] connected")
                return conn
            except Exception as e:
                print("[DB] connect failed, retrying in 5s:", e)
                time.sleep(5)
        raise RuntimeError("stopped while connecting DB")

    def connect_or_reconnect_mqtt(client):
        nonlocal next_mqtt_retry
        global mqtt_started_once

        while running:
            try:
                if not mqtt_started_once:
                    client.connect(MQTT_HOST, MQTT_PORT, 60)
                    mqtt_started_once = True
                    print("[MQTT] connect initiated")
                else:
                    client.reconnect()
                    print("[MQTT] reconnect initiated")
                next_mqtt_retry = now() + MQTT_RETRY_SECONDS
                return
            except Exception as e:
                print("[MQTT] connect failed, retrying in 5s:", e)
                next_mqtt_retry = now() + MQTT_RETRY_SECONDS
                time.sleep(5)

    def reconnect_db():
        nonlocal conn, cur, last_flush_at
        try:
            conn.rollback()
        except Exception:
            pass
        conn = connect_db()
        cur = conn.cursor()
        warm_last_saved_from_entity_state(cur)
        last_flush_at = now()

    def safe_flush_measurements():
        nonlocal last_flush_at
        if not pending_measurements:
            return

        try:
            inserted = flush_measurements(cur)
            if inserted:
                last_flush_at = now()
        except OperationalError as e:
            print("[DB] lost during batch flush, reconnecting:", e)
            reconnect_db()

    def on_connect(client, userdata, flags, reason_code, properties=None):
        global mqtt_connected
        mqtt_connected = True
        print("[MQTT] connected rc=", reason_code)
        for sub in MQTT_SUBSCRIPTIONS:
            client.subscribe(sub)
            print("[MQTT] subscribed:", sub)

    def on_disconnect(client, userdata, disconnect_flags=None, reason_code=None, properties=None):
        global mqtt_connected
        mqtt_connected = False
        print("[MQTT] disconnected rc=", reason_code)

    def sweep_presence():
        try:
            cur.execute(f"""
               update hc.entity_presence
               set status='offline', updated_at=now()
               where last_seen_ts < now() - interval '{OFFLINE_AFTER_MINUTES} minutes'
                 and status <> 'offline'
            """)
        except OperationalError as e:
            print("[DB] lost during presence sweep, reconnecting:", e)
            reconnect_db()

    def on_message(client, userdata, msg):
        tnow = now()
        topic = msg.topic
        tb = topic_base_of(topic)
        if not tb:
            return

        try:
            eid = cached_entity_id(cur, tb)
            if not eid:
                log_limited(f"unk_topic:{tb}", f"[UNK_TOPIC] {tb}")
                return

            is_retained = bool(getattr(msg, "retain", False))

            if topic.endswith("/availability"):
                raw = msg.payload.decode("utf-8", errors="replace").strip().lower()
                if raw in ("online", "offline", "degraded") and not is_retained:
                    upsert_presence(cur, eid, raw)
                touch_heartbeat()
                return

            if topic.startswith("homecontrol/tele/tuya/") and topic.endswith("/error"):
                touch_heartbeat()
                return

            if not is_retained and not topic.startswith("homecontrol/tele/tuya/"):
                upsert_presence(cur, eid, "online")

            raw_payload = msg.payload.decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw_payload)
            except Exception:
                if tb == "homecontrol/xiaomi_x10" or (topic.startswith("homecontrol/tele/tuya/") and "/m/" in topic):
                    payload = raw_payload.strip()
                else:
                    log_limited(f"json:{tb}", f"[BAD_JSON] topic={topic} payload={raw_payload!r}")
                    touch_heartbeat()
                    return

            if topic == "homecontrol/xiaomi_x10/error" and payload == {}:
                delete_entity_state(cur, eid, "x10_error")
                update_last(eid, "x10_error", {}, tnow)
                touch_heartbeat()
                return

            rules = cached_rules(cur, eid)

            metric_items = x10_metric_items(topic, payload)
            if metric_items is None:
                metric_items = gree_climate_metric_items(topic, payload)
            if metric_items is None:
                metric_items = tuya_metric_items(topic, payload)
            if metric_items is None:
                metric_items = growatt_metric_items(topic, payload)
            if metric_items is None:
                if not isinstance(payload, dict):
                    log_limited(f"json_obj:{tb}", f"[BAD_JSON_OBJECT] topic={topic} payload={raw_payload!r}")
                    touch_heartbeat()
                    return
                metric_items = [(raw_k, raw_v, raw_k) for raw_k, raw_v in payload.items()]

            relay = payload.get("state") if isinstance(payload, dict) else None
            relay_bool: Optional[bool] = None
            if isinstance(relay, str):
                relay_bool = True if relay.upper() == "ON" else False if relay.upper() == "OFF" else None

            for raw_k, raw_v, raw_src in metric_items:
                if raw_v is None:
                    continue
                metric_key = map_key(raw_k, raw_v, topic)

                if metric_key in (
                    "battery_state",
                    "water_warning",
                    "valve_open_raw",
                    "valve_close_raw",
                    "manual_valve_open_raw",
                    "manual_valve_close_raw",
                    "last_tele_sec_ago",
                ):
                    continue

                mmeta = cached_metric_meta(cur, metric_key)
                if not mmeta:
                    log_limited(f"unk_metric:{metric_key}", f"[UNK_METRIC] entity={eid} metric={metric_key} topic={topic}")
                    continue

                vtype = mmeta.value_type

                ok_range, why_range = metric_in_range(mmeta, raw_v)
                if not ok_range:
                    log_limited(
                        f"range:{eid}:{metric_key}",
                        f"[SKIP_RANGE] entity={eid} key={metric_key} value={raw_v} topic={topic} reason={why_range}"
                    )
                    continue

                rule = rules.get(metric_key)
                if not rule:
                    continue

                if topic == "homecontrol/xiaomi_x10/scheduler/entries" and metric_key == "x10_scheduler_entries":
                    sync_x10_schedules(cur, eid, raw_v)
                elif topic == "homecontrol/xiaomi_x10/map/current" and metric_key == "x10_map_current":
                    sync_x10_current_map(cur, eid, raw_v)
                elif topic == "homecontrol/xiaomi_x10/map/current_rooms_normalized" and metric_key == "x10_map_rooms_normalized":
                    sync_x10_current_rooms(cur, eid, raw_v)

                ok, _reason = should_write(eid, metric_key, raw_v, rule, tnow)
                if not ok:
                    continue

                meta = {
                    "src": "mqtt",
                    "topic": topic,
                    "topic_base": tb,
                    "raw_key": raw_src,
                    "recv_ts": int(tnow),
                    "retained": is_retained,
                }

                try:
                    if should_store_measurement(rule):
                        queue_measurement(eid, metric_key, vtype, raw_v, meta)

                    if should_store_state(rule):
                        upsert_entity_state(cur, eid, metric_key, vtype, raw_v, meta)

                    update_last(eid, metric_key, raw_v, tnow)

                except OperationalError as e:
                    print(
                        f"[DB] lost during write, reconnecting: "
                        f"entity={eid} key={metric_key} value={raw_v} topic={topic} err={e}"
                    )
                    reconnect_db()
                    continue

                except Exception as e:
                    log_limited(
                        f"write:{eid}:{metric_key}",
                        f"[ERR] entity={eid} key={metric_key} value={raw_v} topic={topic} error={e}"
                    )
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    continue

            touch_heartbeat()

        except OperationalError as e:
            print(f"[DB] lost before processing topic={topic}, reconnecting: {e}")
            reconnect_db()
            return

    conn = connect_db()
    cur = conn.cursor()
    warm_last_saved_from_entity_state(cur)

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except Exception:
        client = mqtt.Client()

    client.reconnect_delay_set(min_delay=2, max_delay=30)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    next_mqtt_retry = now()
    last_flush_at = now()

    connect_or_reconnect_mqtt(client)

    print("[RUN] multi ingest started. CTRL+C to stop.")
    touch_heartbeat()

    try:
        while running:
            if not mqtt_connected and now() >= next_mqtt_retry:
                connect_or_reconnect_mqtt(client)

            rc = client.loop(timeout=1.0)
            if rc not in (mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_AGAIN):
                log_limited(f"mqtt_loop:{rc}", f"[MQTT] loop rc={rc}")

            if len(pending_measurements) >= MEASUREMENT_BATCH_SIZE:
                safe_flush_measurements()
            elif pending_measurements and (now() - last_flush_at) >= MEASUREMENT_FLUSH_EVERY_SECONDS:
                safe_flush_measurements()

            if now() >= (last_flush_at + SWEEP_EVERY_SECONDS):
                # this condition is not used for sweep timing; keep heartbeat alive even in low traffic periods
                pass

            touch_heartbeat()

            if 'next_sweep_at' not in locals():
                next_sweep_at = now() + SWEEP_EVERY_SECONDS

            if now() >= next_sweep_at:
                sweep_presence()
                next_sweep_at = now() + SWEEP_EVERY_SECONDS

    finally:
        try:
            safe_flush_measurements()
        except Exception:
            pass

        try:
            client.disconnect()
        except Exception:
            pass

        try:
            cur.close()
        except Exception:
            pass

        try:
            conn.close()
        except Exception:
            pass

        print("[SYS] shutdown complete")


if __name__ == "__main__":
    main()
