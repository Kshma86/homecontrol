#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tuya multi-connector poller + MQTT publisher

- Párhuzamosan pollol több Tuya konnektort (tinytuya)
- Konzolra táblázatot ír (opcionális)
- Fájlba snapshot logot ír (opcionális)
- MQTT-re publisholja az adatokat (opcionális)

Config: multi_connector_config.json (alapból a script workdirjében keresi),
       felülírható: TUYA_CFG env var
"""

import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Optional, Tuple, Any, List

import tinytuya

# MQTT (opcionális)
try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None

# ------------------ config ------------------
CFG_PATH = os.environ.get("TUYA_CFG", "multi_connector_config.json")
with open(CFG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

POLL_SECONDS = float(cfg.get("poll_seconds", 5))
LOG_DIR = os.path.expanduser(cfg.get("log_dir", "~/hc_logs/tuya"))
os.makedirs(LOG_DIR, exist_ok=True)

SINKS = cfg.get("sinks", {})
SINK_CONSOLE = bool(SINKS.get("console", True))
SINK_FILE = bool(SINKS.get("file", True))
SINK_MQTT = bool(SINKS.get("mqtt", False))

DEFAULT_VERSION = float(cfg.get("version", 3.3))

DEFAULT_SCALES = (cfg.get("scales", {}) or {})
DEFAULT_POWER_DIV = float(DEFAULT_SCALES.get("power_div", 10.0))
DEFAULT_VOLTAGE_DIV = float(DEFAULT_SCALES.get("voltage_div", 10.0))
DEFAULT_CURRENT_DIV = float(DEFAULT_SCALES.get("current_div", 1000.0))
DEFAULT_ENERGY_DIV = float(DEFAULT_SCALES.get("energy_div", 100.0))

DEVICES_CFG = cfg.get("devices", []) or []
if not DEVICES_CFG:
    raise SystemExit(f"{CFG_PATH}: 'devices' lista üres")

# --- performance / resilience tuning (config felülírhatja) ---
MAX_WORKERS = int(cfg.get("max_workers", min(16, max(1, len(DEVICES_CFG)))))
FAST_TIMEOUT = float(cfg.get("fast_timeout", 1.0))
SLOW_TIMEOUT = float(cfg.get("slow_timeout", 2.5))
RETRY_DELAY_SEC = float(cfg.get("retry_delay_sec", 0.08))
FALLBACK_DELAY_SEC = float(cfg.get("fallback_delay_sec", 0.05))

COOLDOWN_CONNECT_SEC = int(cfg.get("cooldown_connect_sec", 30))  # Err 901
COOLDOWN_KEYVER_SEC = int(cfg.get("cooldown_keyver_sec", 10))    # Err 914
COOLDOWN_GENERIC_SEC = int(cfg.get("cooldown_generic_sec", 5))

REBUILD_AFTER_FAILS = int(cfg.get("rebuild_after_fails", 3))
KIND_LOCK_AFTER_SUCCESSES = int(cfg.get("kind_lock_after_successes", 2))

# ------------------ MQTT config ------------------
MQTT_CFG = (cfg.get("mqtt", {}) or {})
MQTT_HOST = str(MQTT_CFG.get("host", "127.0.0.1"))
MQTT_PORT = int(MQTT_CFG.get("port", 1883))
MQTT_USER = MQTT_CFG.get("username")
MQTT_PASS = MQTT_CFG.get("password")
MQTT_CLIENT_ID = str(MQTT_CFG.get("client_id", f"hc-tuya-poller-{socket.gethostname()}"))
MQTT_BASE_TOPIC = str(MQTT_CFG.get("base_topic", "homecontrol/tele/tuya")).rstrip("/")
MQTT_QOS = int(MQTT_CFG.get("qos", 0))
MQTT_RETAIN_STATE = bool(MQTT_CFG.get("retain_state", False))
MQTT_RETAIN_METRICS = bool(MQTT_CFG.get("retain_metrics", False))
MQTT_KEEPALIVE = int(MQTT_CFG.get("keepalive", 30))
MQTT_PUBLISH_ERRORS = bool(MQTT_CFG.get("publish_errors", True))
MQTT_COMMAND_TOPIC = str(MQTT_CFG.get("command_topic", "homecontrol/cmd/tuya")).rstrip("/")


# ------------------ helpers ------------------
def get_logfile_for_today() -> str:
    return os.path.join(LOG_DIR, f"tuya_multi_connectors_{date.today().isoformat()}.log")


def fmt(v, fmtstr: str, na="—"):
    if v is None:
        return na
    try:
        return format(v, fmtstr)
    except Exception:
        return str(v)


def short(obj: Any, n: int = 260) -> str:
    s = repr(obj)
    return s if len(s) <= n else s[:n] + "...<truncated>"


def extract_dps(status: Any) -> dict:
    if isinstance(status, dict):
        if isinstance(status.get("dps"), dict):
            return status["dps"]
        data = status.get("data")
        if isinstance(data, dict) and isinstance(data.get("dps"), dict):
            return data["dps"]
    return {}


def get_fresh_status(dev):
    """
    FIX: egyes tinytuya verziókban updatedps/update_dps/refresh visszatérhet None-nal.
    Ilyenkor essünk vissza dev.status()-ra.
    """
    for fn in ("updatedps", "update_dps", "refresh"):
        if hasattr(dev, fn):
            try:
                r = getattr(dev, fn)()
                if r is not None:
                    return r
            except TypeError:
                pass
            except Exception:
                continue
    return dev.status()


def extract_src_timestamp(resp: dict) -> Tuple[Optional[int], Optional[str]]:
    if not isinstance(resp, dict):
        return None, None

    t = resp.get("t")
    if isinstance(t, (int, float)):
        return int(t), "t"
    if isinstance(t, str) and t.isdigit():
        return int(t), "t"

    data = resp.get("data")
    if isinstance(data, dict):
        t2 = data.get("t") or data.get("time") or data.get("timestamp")
        if isinstance(t2, (int, float)):
            return int(t2), "data.*"
        if isinstance(t2, str) and t2.isdigit():
            return int(t2), "data.*"

    for k in ("time", "timestamp", "eventTime", "lastUpdateTime", "update_time"):
        v = resp.get(k)
        if isinstance(v, (int, float)):
            vv = int(v)
            if vv > 10_000_000_000:
                vv //= 1000
            return vv, k
        if isinstance(v, str) and v.isdigit():
            vv = int(v)
            if vv > 10_000_000_000:
                vv //= 1000
            return vv, k

    return None, None


def safe_lag(recv_ts: int, src_ts: Optional[int]) -> Optional[int]:
    if not src_ts:
        return None
    lag = recv_ts - src_ts
    if lag < 0:
        return None
    return lag


def pick_first_present(dps: dict, candidates: List[int]) -> Optional[int]:
    for k in candidates:
        if str(k) in dps and dps.get(str(k)) is not None:
            return k
    return None


def is_boolish_switch_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return value in (0, 1)
    if isinstance(value, str):
        return value.strip().lower() in {"0", "1", "true", "false", "on", "off"}
    return False


def pick_switch_dp(dps: dict, candidates: List[int]) -> Optional[int]:
    for k in candidates:
        if str(k) in dps and is_boolish_switch_value(dps.get(str(k))):
            return k
    return None


def resolve_dp(dp_map: dict, name: str, dps: dict) -> Optional[int]:
    if dp_map and name in dp_map:
        try:
            return int(dp_map[name])
        except Exception:
            return None

    if name == "switch":
        return pick_switch_dp(dps, [1, 16, 20])

    candidates = {
        "power": [19, 5],
        "voltage": [20],
        "current": [18],
        "energy_forward": [17, 109, 6],
    }.get(name, [])

    return pick_first_present(dps, candidates) if candidates else None


def classify_error(err: str) -> str:
    s = err or ""
    if "Err': '901" in s or "Unable to Connect" in s or "Network Error" in s:
        return "connect"
    if "Err': '914" in s or "device key or version" in s or "Check device key or version" in s:
        return "keyver"
    return "generic"


def cooldown_for(err: str) -> int:
    k = classify_error(err)
    if k == "connect":
        return COOLDOWN_CONNECT_SEC
    if k == "keyver":
        return COOLDOWN_KEYVER_SEC
    return COOLDOWN_GENERIC_SEC


# ------------------ device model ------------------
@dataclass
class DevRuntime:
    device_id: str
    name: str
    ip: str
    local_key: str
    version: float
    port: int
    dp_map: dict
    power_div: float
    voltage_div: float
    current_div: float
    energy_div: float
    location: str = ""
    availability_grace_sec: int = 0

    dev: Optional[Any] = None
    dev_kind: str = "Device"  # "Device" vagy "OutletDevice"
    last_state: dict = field(default_factory=dict)
    last_error: Optional[str] = None

    consec_fail: int = 0
    last_raw: Optional[str] = None
    next_poll_ts: int = 0

    kind_locked: bool = False
    success_count: int = 0

    ecalc_kwh: float = 0.0
    _last_ecalc_ts: Optional[int] = None
    lock: Lock = field(default_factory=Lock)

    def build_device(self, kind: Optional[str] = None, timeout: float = 2.0):
        if kind:
            self.dev_kind = kind

        if self.dev_kind == "OutletDevice" and hasattr(tinytuya, "OutletDevice"):
            d = tinytuya.OutletDevice(
                self.device_id,
                self.ip,
                self.local_key,
                connection_timeout=timeout,
                persist=False,
                connection_retry_limit=1,
                connection_retry_delay=0.2,
                port=self.port,
            )
        else:
            d = tinytuya.Device(
                self.device_id,
                self.ip,
                self.local_key,
                connection_timeout=timeout,
                persist=False,
                connection_retry_limit=1,
                connection_retry_delay=0.2,
                port=self.port,
            )
            self.dev_kind = "Device"

        d.set_version(self.version)
        d.set_socketPersistent(False)
        d.set_socketTimeout(timeout)
        self.dev = d

    def note_energy_calc(self, now_ts: int, power_w: Optional[float]):
        if self._last_ecalc_ts is None:
            self._last_ecalc_ts = now_ts
            return
        dt = now_ts - self._last_ecalc_ts
        self._last_ecalc_ts = now_ts
        if dt <= 0 or power_w is None:
            return
        self.ecalc_kwh += (power_w * dt) / 3_600_000.0


def parse_partial(dr: DevRuntime, dps: dict, recv_ts: int, src_ts: Optional[int], src_field: Optional[str]) -> dict:
    def has(k: Optional[int]) -> bool:
        return k is not None and str(k) in dps and dps.get(str(k)) is not None

    def gi(k: int) -> int:
        return int(dps[str(k)])

    def gb(k: int) -> bool:
        return bool(dps[str(k)])

    out = {
        "ts": recv_ts,
        "device_id": dr.device_id,
        "device_name": dr.name,
        "location": dr.location or None,
        "ip": dr.ip,
        "recv_ts": recv_ts,
        "src_ts": src_ts,
        "src_field": src_field,
        "lag_sec": safe_lag(recv_ts, src_ts),
        "energy_calc_kwh": dr.ecalc_kwh,
        "dev_kind": dr.dev_kind,
        "tuya_raw_dps": dps,
    }

    dp_sw = resolve_dp(dr.dp_map, "switch", dps)
    dp_p  = resolve_dp(dr.dp_map, "power", dps)
    dp_u  = resolve_dp(dr.dp_map, "voltage", dps)
    dp_i  = resolve_dp(dr.dp_map, "current", dps)
    dp_e  = resolve_dp(dr.dp_map, "energy_forward", dps)

    if has(dp_sw): out["switch"] = gb(dp_sw)
    if has(dp_p):  out["power_w"] = gi(dp_p) / dr.power_div
    if has(dp_u):  out["voltage_v"] = gi(dp_u) / dr.voltage_div
    if has(dp_i):  out["current_a"] = gi(dp_i) / dr.current_div
    if has(dp_e):  out["energy_forward_kwh"] = gi(dp_e) / dr.energy_div

    return out


# ------------------ MQTT output ------------------
mqtt_client: Optional["mqtt.Client"] = None
mqtt_connected: bool = False
mqtt_last_conn_err: Optional[str] = None
command_queue: "Queue[tuple[str, dict]]" = Queue()


def _mqtt_topic_join(*parts: str) -> str:
    cleaned = []
    for p in parts:
        if p is None:
            continue
        s = str(p).strip("/")
        if s:
            cleaned.append(s)
    return "/".join(cleaned)


def mqtt_on_connect(client, userdata, flags, rc, properties=None):
    global mqtt_connected, mqtt_last_conn_err
    mqtt_connected = (rc == 0)
    mqtt_last_conn_err = None if mqtt_connected else f"connect_rc={rc}"
    if mqtt_connected:
        client.subscribe(_mqtt_topic_join(MQTT_COMMAND_TOPIC, "+", "switch"), qos=MQTT_QOS)


def mqtt_on_disconnect(client, userdata, rc, properties=None):
    global mqtt_connected
    mqtt_connected = False


def mqtt_on_message(client, userdata, msg):
    prefix = _mqtt_topic_join(MQTT_COMMAND_TOPIC, "")
    parts = msg.topic.split("/")
    prefix_parts = prefix.split("/")
    if len(parts) != len(prefix_parts) + 2 or parts[:len(prefix_parts)] != prefix_parts or parts[-1] != "switch":
        return
    device_name = parts[-2]
    raw_payload = msg.payload.decode("utf-8", errors="replace").strip()
    try:
        payload = json.loads(raw_payload) if raw_payload else {}
    except Exception:
        payload = {"value": raw_payload}
    if not isinstance(payload, dict):
        payload = {"value": payload}
    command_queue.put((device_name, payload))


def init_mqtt():
    global mqtt_client, mqtt_last_conn_err
    if not SINK_MQTT:
        return
    if mqtt is None:
        raise SystemExit("SINK_MQTT=true, de a paho-mqtt nincs telepítve (pip install paho-mqtt)")

    c = mqtt.Client(client_id=MQTT_CLIENT_ID, clean_session=True)
    c.on_connect = mqtt_on_connect
    c.on_disconnect = mqtt_on_disconnect
    c.on_message = mqtt_on_message

    if MQTT_USER:
        c.username_pw_set(MQTT_USER, MQTT_PASS)

    c.will_set(_mqtt_topic_join(MQTT_BASE_TOPIC, "poller", "availability"),
               payload="offline", qos=1, retain=True)

    try:
        c.connect(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
        c.loop_start()
        mqtt_client = c
    except Exception as e:
        mqtt_last_conn_err = repr(e)
        mqtt_client = c
        try:
            c.loop_start()
        except Exception:
            pass


def mqtt_publish(topic: str, payload: Any, qos: int = MQTT_QOS, retain: bool = False):
    if not SINK_MQTT or mqtt_client is None:
        return

    global mqtt_connected, mqtt_last_conn_err

    if not mqtt_connected:
        try:
            mqtt_client.reconnect()
            mqtt_connected = True
            mqtt_last_conn_err = None
        except Exception as e:
            mqtt_last_conn_err = repr(e)
            return

    if isinstance(payload, (dict, list)):
        data = json.dumps(payload, ensure_ascii=False)
    else:
        data = str(payload)

    mqtt_client.publish(topic, data, qos=qos, retain=retain)


def mqtt_publish_device(dr: DevRuntime, st: dict, err: Optional[str]):
    loc = (dr.location or "").strip()
    dev = dr.name
    base = _mqtt_topic_join(MQTT_BASE_TOPIC, loc, dev) if loc else _mqtt_topic_join(MQTT_BASE_TOPIC, dev)

    availability = "online" if not err else "degraded"
    if err and dr.availability_grace_sec > 0 and classify_error(err) == "connect":
        last_ts = st.get("ts") if isinstance(st, dict) else None
        try:
            last_age = int(time.time()) - int(last_ts)
        except Exception:
            last_age = None
        if last_age is not None and 0 <= last_age <= dr.availability_grace_sec:
            availability = "online"

    mqtt_publish(_mqtt_topic_join(base, "availability"),
                 availability, qos=1, retain=True)
    mqtt_publish(_mqtt_topic_join(base, "error"),
                 "" if not err else err, qos=1, retain=True)

    mqtt_publish(_mqtt_topic_join(base, "state"), st, qos=MQTT_QOS, retain=MQTT_RETAIN_STATE)

    metrics = {
        "switch": st.get("switch"),
        "power_w": st.get("power_w"),
        "voltage_v": st.get("voltage_v"),
        "current_a": st.get("current_a"),
        "energy_forward_kwh": st.get("energy_forward_kwh"),
        "energy_calc_kwh": st.get("energy_calc_kwh"),
        "tuya_raw_dps": st.get("tuya_raw_dps"),
        "lag_sec": st.get("lag_sec"),
        "recv_ts": st.get("recv_ts"),
        "src_ts": st.get("src_ts"),
    }
    for k, v in metrics.items():
        if v is None:
            continue
        mqtt_publish(_mqtt_topic_join(base, "m", k), v, qos=MQTT_QOS, retain=MQTT_RETAIN_METRICS)


def command_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "on", "yes", "open"}:
        return True
    if text in {"0", "false", "off", "no", "close"}:
        return False
    return None


def publish_command_result(device_name: str, ok: bool, message: str, extra: Optional[dict] = None):
    payload = {
        "ok": bool(ok),
        "device_name": device_name,
        "message": message,
        "ts": int(time.time()),
    }
    if extra:
        payload.update(extra)
    mqtt_publish(_mqtt_topic_join(MQTT_BASE_TOPIC, device_name, "command_result"), payload, qos=1, retain=False)


def handle_switch_command(device_name: str, payload: dict) -> bool:
    target = next((dr for dr in runtimes if dr.name == device_name or dr.device_id == device_name), None)
    value = command_bool(payload.get("value", payload.get("state", payload.get("switch"))))
    if target is None:
        publish_command_result(device_name, False, "unknown device")
        return False
    if value is None:
        publish_command_result(device_name, False, "invalid switch value", {"payload": payload})
        return False

    switch_dp = int(target.dp_map.get("switch", 1) or 1)
    try:
        with target.lock:
            if target.dev is None:
                target.build_device(kind=target.dev_kind, timeout=SLOW_TIMEOUT)
            target.dev.set_socketTimeout(SLOW_TIMEOUT)
            result = target.dev.set_status(value, switch_dp)
        target.next_poll_ts = 0
        target.last_error = None
        target.last_state = dict(target.last_state or {})
        target.last_state.update({
            "ts": int(time.time()),
            "device_id": target.device_id,
            "device_name": target.name,
            "location": target.location or None,
            "ip": target.ip,
            "switch": value,
            "dev_kind": target.dev_kind,
        })
        publish_command_result(target.name, True, "switch command sent", {"value": value, "dp": switch_dp, "result": result})
        return True
    except Exception as exc:
        target.last_error = repr(exc)
        target.next_poll_ts = int(time.time()) + cooldown_for(target.last_error)
        publish_command_result(target.name, False, "switch command failed", {"value": value, "dp": switch_dp, "error": repr(exc)})
        return False


def drain_commands(max_items: int = 20):
    handled = 0
    while handled < max_items:
        try:
            device_name, payload = command_queue.get_nowait()
        except Empty:
            return
        handle_switch_command(device_name, payload)
        handled += 1


def command_worker():
    while True:
        try:
            device_name, payload = command_queue.get(timeout=1.0)
        except Empty:
            continue
        handle_switch_command(device_name, payload)


# ------------------ polling with fast/slow retry + fallback ------------------
def poll_one(dr: DevRuntime) -> Tuple[Optional[dict], Optional[str]]:
    now = int(time.time())
    if dr.next_poll_ts and now < dr.next_poll_ts:
        return (dr.last_state if dr.last_state else None), dr.last_error

    def attempt(timeout: float) -> Tuple[Optional[dict], Optional[str], Any]:
        with dr.lock:
            if dr.dev is None:
                dr.build_device(kind=dr.dev_kind, timeout=timeout)

            dr.dev.set_socketTimeout(timeout)
            status = get_fresh_status(dr.dev)
        dps = extract_dps(status)
        src_ts, src_field = extract_src_timestamp(status if isinstance(status, dict) else {})

        if not dps:
            return None, f"unexpected_response kind={dr.dev_kind} status={short(status)}", status

        recv_ts = int(time.time())
        partial = parse_partial(dr, dps, recv_ts=recv_ts, src_ts=src_ts, src_field=src_field)

        dr.note_energy_calc(recv_ts, partial.get("power_w"))
        partial["energy_calc_kwh"] = dr.ecalc_kwh

        merged = dict(dr.last_state) if dr.last_state else {}
        merged.update(partial)
        dr.last_state = merged

        dr.success_count += 1
        if dr.success_count >= KIND_LOCK_AFTER_SUCCESSES:
            dr.kind_locked = True

        return merged, None, status

    # 1) fast
    try:
        st, err, raw = attempt(FAST_TIMEOUT)
        if not err:
            dr.last_error = None
            dr.next_poll_ts = 0
            return st, None
        dr.last_raw = short(raw)
    except Exception as e1:
        err = repr(e1)

    # 2) rebuild + slow
    try:
        with dr.lock:
            dr.build_device(kind=dr.dev_kind, timeout=SLOW_TIMEOUT)
        time.sleep(RETRY_DELAY_SEC)
        st2, err2, raw2 = attempt(SLOW_TIMEOUT)
        if not err2:
            dr.last_error = None
            dr.next_poll_ts = 0
            return st2, None
        dr.last_raw = short(raw2)
        err = err2
    except Exception as e2:
        err = repr(e2)

    # 3) fallback kind (if not locked)
    if not dr.kind_locked:
        other_kind = "OutletDevice" if dr.dev_kind != "OutletDevice" else "Device"
        try:
            with dr.lock:
                dr.build_device(kind=other_kind, timeout=SLOW_TIMEOUT)
            time.sleep(FALLBACK_DELAY_SEC)
            st3, err3, raw3 = attempt(SLOW_TIMEOUT)
            if not err3:
                dr.last_error = None
                dr.next_poll_ts = 0
                return st3, None
            dr.last_raw = short(raw3)
            err = err3
        except Exception as e3:
            err = f"fallback_build_failed({other_kind}): {repr(e3)}"

    dr.last_error = err
    dr.next_poll_ts = int(time.time()) + cooldown_for(err)
    return (dr.last_state if dr.last_state else None), err


# ------------------ output ------------------
def print_table(states: List[dict], errors: dict):
    headers = ["NAME              ", "IP             ", "SW", "P(W)    ", "U(V) ", "I(A)", "Ef(kWh) ", "Ecalc(kWh)", "LAG(s)", "SRC   ", "KIND"]
    line = " | ".join(headers)
    print(line)
    print("-" * len(line))

    for st in states:
        sw = st.get("switch")
        sw_s = "—" if sw is None else ("1" if sw else "0")

        lag = st.get("lag_sec")
        lag_s = "—" if lag is None else str(int(lag))

        print(
            f'{st.get("device_name","—"):<18} | '
            f'{st.get("ip","—"):<15} | '
            f'{sw_s:>2} | '
            f'{fmt(st.get("power_w"), "7.1f"):>7} | '
            f'{fmt(st.get("voltage_v"), "5.1f"):>5} | '
            f'{fmt(st.get("current_a"), "5.3f"):>5} | '
            f'{fmt(st.get("energy_forward_kwh"), "8.2f"):>8} | '
            f'{fmt(st.get("energy_calc_kwh"), "10.4f"):>10} | '
            f'{lag_s:>6} | '
            f'{(st.get("src_field") or "—"):<5} | '
            f'{(st.get("dev_kind") or "—"):<11}'
        )

    bad = [(k, v) for k, v in errors.items() if v]
    if bad:
        print()
        for dev_name, err in bad:
            print(f"ERR {dev_name}: {err}")


def sink_file_snapshot(states: List[dict], errors: dict):
    if not SINK_FILE:
        return
    logfile = get_logfile_for_today()
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        for st in states:
            f.write(json.dumps(st, ensure_ascii=False) + "\n")
        for dev_name, err in errors.items():
            if err:
                f.write(f"ERR {dev_name}: {err}\n")


# ------------------ init runtimes ------------------
runtimes: List[DevRuntime] = []
for dc in DEVICES_CFG:
    did = dc["device_id"]
    name = dc.get("name", did)
    ip = dc["device_ip"]
    lk = dc["local_key"]
    location = str(dc.get("location", "") or "")
    port = int(dc.get("port", 6668))

    ver = float(dc.get("version", DEFAULT_VERSION))
    dp_map = dc.get("dp_map", {}) or {}

    scales = dc.get("scales", {}) or {}
    power_div = float(scales.get("power_div", DEFAULT_POWER_DIV))
    voltage_div = float(scales.get("voltage_div", DEFAULT_VOLTAGE_DIV))
    current_div = float(scales.get("current_div", DEFAULT_CURRENT_DIV))
    energy_div = float(scales.get("energy_div", DEFAULT_ENERGY_DIV))
    availability_grace_sec = int(dc.get("availability_grace_sec", cfg.get("availability_grace_sec", 0)) or 0)

    dr = DevRuntime(
        device_id=did,
        name=name,
        ip=ip,
        local_key=lk,
        version=ver,
        port=port,
        dp_map=dp_map,
        power_div=power_div,
        voltage_div=voltage_div,
        current_div=current_div,
        energy_div=energy_div,
        location=location,
        availability_grace_sec=availability_grace_sec,
    )
    dr.build_device(kind="Device", timeout=SLOW_TIMEOUT)
    runtimes.append(dr)

# ------------------ startup ------------------
if SINK_MQTT:
    init_mqtt()
    Thread(target=command_worker, name="tuya-command-worker", daemon=True).start()
    mqtt_publish(_mqtt_topic_join(MQTT_BASE_TOPIC, "poller", "availability"), "online", qos=1, retain=True)
    mqtt_publish(_mqtt_topic_join(MQTT_BASE_TOPIC, "poller", "info"), {
        "client_id": MQTT_CLIENT_ID,
        "host": MQTT_HOST,
        "port": MQTT_PORT,
        "ts": int(time.time()),
        "devices": len(runtimes),
    }, qos=1, retain=True)

print("Tuya multi-connector poller starting...")
print(f"Config: {CFG_PATH}")
print(f"Devices: {len(runtimes)}  poll={POLL_SECONDS}s  workers={MAX_WORKERS}  logdir={LOG_DIR}")
print(f"Timeouts: fast={FAST_TIMEOUT}s slow={SLOW_TIMEOUT}s  cooldowns: 901={COOLDOWN_CONNECT_SEC}s 914={COOLDOWN_KEYVER_SEC}s")
print(f"Kind lock after successes: {KIND_LOCK_AFTER_SUCCESSES}")
if SINK_MQTT:
    print(f"MQTT: {MQTT_HOST}:{MQTT_PORT} base_topic={MQTT_BASE_TOPIC} qos={MQTT_QOS} retain_state={MQTT_RETAIN_STATE} retain_metrics={MQTT_RETAIN_METRICS}")
print()

# ------------------ main loop ------------------
polls = 0
ok = 0
errors = 0

executor = ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(runtimes)))

try:
    while True:
        drain_commands()
        polls += 1
        states_out: List[dict] = []
        err_out: dict = {}

        fut_map = {executor.submit(poll_one, dr): dr for dr in runtimes}

        for fut in as_completed(fut_map):
            dr = fut_map[fut]
            try:
                st, err = fut.result()
            except Exception as e:
                st, err = (dr.last_state if dr.last_state else None), repr(e)

            if err:
                errors += 1
                dr.consec_fail += 1
                dr.last_error = err
                err_out[dr.name] = err

                if dr.consec_fail >= REBUILD_AFTER_FAILS:
                    dr.build_device(kind=dr.dev_kind, timeout=SLOW_TIMEOUT)
                    dr.consec_fail = 0
            else:
                ok += 1
                dr.consec_fail = 0
                dr.last_error = None
                err_out[dr.name] = None

            if st:
                states_out.append(st)
            else:
                states_out.append({
                    "device_name": dr.name,
                    "device_id": dr.device_id,
                    "location": dr.location or None,
                    "ip": dr.ip,
                    "energy_calc_kwh": dr.ecalc_kwh,
                    "dev_kind": dr.dev_kind,
                })

        states_out.sort(key=lambda x: x.get("device_name", ""))

        if SINK_MQTT:
            for st in states_out:
                dev_name = st.get("device_name", "")
                dr = next((x for x in runtimes if x.name == dev_name), None)
                if dr is None:
                    continue
                err = err_out.get(dr.name)

                if err and not MQTT_PUBLISH_ERRORS:
                    continue

                mqtt_publish_device(dr, st, err)

            mqtt_publish(_mqtt_topic_join(MQTT_BASE_TOPIC, "poller", "stats"), {
                "ts": int(time.time()),
                "polls": polls,
                "ok": ok,
                "errors": errors,
                "mqtt_connected": bool(mqtt_connected),
                "mqtt_last_error": mqtt_last_conn_err,
            }, qos=1, retain=True)

        if SINK_CONSOLE:
            os.system("clear")
            print_table(states_out, err_out)
            print()
            last_err = next((v for v in err_out.values() if v), None)
            print(f"polls={polls} ok={ok} errors={errors} last_error={last_err} mqtt_connected={mqtt_connected}")

        sink_file_snapshot(states_out, err_out)
        time.sleep(POLL_SECONDS)

finally:
    try:
        if SINK_MQTT and mqtt_client is not None:
            mqtt_publish(_mqtt_topic_join(MQTT_BASE_TOPIC, "poller", "availability"), "offline", qos=1, retain=True)
            try:
                mqtt_client.loop_stop()
            except Exception:
                pass
            try:
                mqtt_client.disconnect()
            except Exception:
                pass
    except Exception:
        pass

    executor.shutdown(wait=False)
