#!/usr/bin/env python3
from mqtt_credentials import configure_mqtt_auth
from worker_health import WorkerHealth

import json
import os
import signal
import socket
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt
import requests


HA_BASE_URL = os.getenv("HA_BASE_URL", "http://127.0.0.1:8123").rstrip("/")
HA_TOKEN = os.getenv("HA_TOKEN", "").strip()
POLL_SECONDS = float(os.getenv("HA_GROWATT_POLL_SECONDS", "60"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("HA_GROWATT_REQUEST_TIMEOUT_SECONDS", "15"))

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", f"hc-ha-growatt-{socket.gethostname()}")
BASE_TOPIC = os.getenv("HA_GROWATT_BASE_TOPIC", "homecontrol/tele/growatt/cloud").rstrip("/")
MQTT_QOS = int(os.getenv("MQTT_QOS", "0"))
MQTT_RETAIN = os.getenv("MQTT_RETAIN", "false").strip().lower() in {"1", "true", "yes", "on"}

DEFAULT_ENTITY_MAP = {
    "system_power_w": "sensor.pyl0chj016_system_power",
    "output_power_w": "sensor.pyl0chj016_output_power",
    "energy_today_kwh": "sensor.pyl0chj016_energy_today",
    "lifetime_energy_kwh": "sensor.pyl0chj016_lifetime_energy_output",
    "solar_energy_today_kwh": "sensor.pyl0chj016_solar_energy_today",
    "lifetime_solar_energy_kwh": "sensor.pyl0chj016_lifetime_total_solar_energy",
    "battery_soc_percent": "sensor.pyl0chj016_state_of_charge_soc",
    "local_load_power_w": "sensor.pyl0chj016_local_load_power",
    "import_power_w": "sensor.pyl0chj016_import_power",
    "export_power_w": "sensor.pyl0chj016_export_power",
    "load_consumption_today_kwh": "sensor.pyl0chj016_load_consumption_today",
    "lifetime_load_consumption_kwh": "sensor.pyl0chj016_lifetime_total_load_consumption",
    "export_to_grid_today_kwh": "sensor.pyl0chj016_export_to_grid_today",
    "lifetime_export_to_grid_kwh": "sensor.pyl0chj016_lifetime_total_export_to_grid",
    "import_from_grid_today_kwh": "sensor.pyl0chj016_import_from_grid_today",
    "lifetime_import_from_grid_kwh": "sensor.pyl0chj016_lifetime_import_from_grid",
    "self_consumption_today_kwh": "sensor.pyl0chj016_self_consumption_today",
    "lifetime_self_consumption_kwh": "sensor.pyl0chj016_lifetime_self_consumption",
    "input_1_wattage_w": "sensor.pyl0chj016_input_1_wattage",
    "input_2_wattage_w": "sensor.pyl0chj016_input_2_wattage",
    "input_1_voltage_v": "sensor.pyl0chj016_input_1_voltage",
    "input_2_voltage_v": "sensor.pyl0chj016_input_2_voltage",
    "input_1_current_a": "sensor.pyl0chj016_input_1_amperage",
    "input_2_current_a": "sensor.pyl0chj016_input_2_amperage",
    "plant_output_power_w": "sensor.8226_alsrs_balassi_blint_utca_3_total_output_power",
    "plant_energy_today_kwh": "sensor.8226_alsrs_balassi_blint_utca_3_total_energy_today",
    "plant_lifetime_energy_kwh": "sensor.8226_alsrs_balassi_blint_utca_3_total_lifetime_energy_output",
}

running = True


def handle_signal(signum, frame):
    global running
    print(f"[SYS] signal received: {signum}, shutting down...")
    running = False


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def load_entity_map() -> Dict[str, str]:
    raw = os.getenv("HA_GROWATT_ENTITY_MAP", "").strip()
    if not raw:
        return DEFAULT_ENTITY_MAP
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise SystemExit(f"HA_GROWATT_ENTITY_MAP must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise SystemExit("HA_GROWATT_ENTITY_MAP must be a non-empty JSON object")
    return {str(k): str(v) for k, v in parsed.items()}


def coerce_state(value: Any) -> Optional[Any]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"unknown", "unavailable", "none", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return text


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ha_get_states(session: requests.Session, entity_ids) -> Dict[str, Dict[str, Any]]:
    """One HA snapshot per cycle; keep only configured entity objects."""
    with session.get(f"{HA_BASE_URL}/api/states", timeout=REQUEST_TIMEOUT_SECONDS) as response:
        response.raise_for_status()
        states = response.json()
    if not isinstance(states, list):
        raise ValueError("HA states response must be a list")
    wanted = set(entity_ids)
    return {state["entity_id"]: state for state in states
            if isinstance(state, dict) and isinstance(state.get("entity_id"), str)
            and state["entity_id"] in wanted}


def ha_state_age(last_updated: Any, observed_at: datetime) -> Optional[float]:
    """HA state-update age, not the inverter's physical measurement age."""
    if not isinstance(last_updated, str):
        return None
    try:
        updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        if updated.tzinfo is None:
            return None
        age = (observed_at - updated).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return None
    return age if age >= 0 else None


def build_payload(states, entity_map, *, observed_at: datetime) -> Dict[str, Any]:
    observed = observed_at.isoformat()
    payload: Dict[str, Any] = {"source": "home_assistant", "sample_time": observed}
    meta = {}
    for key, entity_id in entity_map.items():
        state = states.get(entity_id)
        if not state:
            continue
        value = coerce_state(state.get("state"))
        if value is None:
            continue
        payload[key] = value
        attrs = state.get("attributes")
        attrs = attrs if isinstance(attrs, dict) else {}
        meta[key] = {
            "entity_id": entity_id,
            "unit": attrs.get("unit_of_measurement"),
            "friendly_name": attrs.get("friendly_name"),
            "last_updated": state.get("last_updated"),
            "observed_at": observed,
            "ha_state_age_seconds": ha_state_age(state.get("last_updated"), observed_at),
        }
    payload["entity_count"] = len(meta)
    payload["meta"] = meta
    return payload


def poll_payload(session: requests.Session, entity_map) -> Dict[str, Any]:
    try:
        states = ha_get_states(session, entity_map.values())
    except Exception as exc:
        # Do not replay a previous snapshot or fall back to N serial requests.
        print(f"[HA] snapshot fetch error: {type(exc).__name__}")
        states = {}
    return build_payload(states, entity_map, observed_at=datetime.now(timezone.utc))


def publish_json(client: mqtt.Client, topic: str, payload: Dict[str, Any], retain: bool = False):
    client.publish(topic, json.dumps(payload, ensure_ascii=False, sort_keys=True), qos=MQTT_QOS, retain=retain)


def main():
    if not HA_TOKEN:
        raise SystemExit("HA_TOKEN is required. Create a Home Assistant long-lived access token and set HA_GROWATT_TOKEN in infra/.env.")

    entity_map = load_entity_map()
    health = WorkerHealth(maximum=max(POLL_SECONDS * 3,
        (REQUEST_TIMEOUT_SECONDS + 1) * 3, 120))
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    })

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
    configure_mqtt_auth(client)
    def on_connect(client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            client.publish(f"{BASE_TOPIC}/availability", "online", qos=MQTT_QOS, retain=True)
    client.on_connect = on_connect
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    health.start(lambda: {'connected': client.is_connected()})

    print(f"[RUN] HA Growatt poller started: ha={HA_BASE_URL} mqtt={MQTT_HOST}:{MQTT_PORT} topic={BASE_TOPIC}")
    try:
        while running:
            started = time.monotonic()
            payload = poll_payload(session, entity_map)
            ok_count = payload["entity_count"]
            publish_json(client, BASE_TOPIC, payload, retain=MQTT_RETAIN)
            print(f"[MQTT] published {ok_count}/{len(entity_map)} Growatt states")
            health.progress(success=ok_count > 0)

            sleep_for = max(1.0, POLL_SECONDS - (time.monotonic() - started))
            end_at = time.monotonic() + sleep_for
            while running and time.monotonic() < end_at:
                time.sleep(min(1.0, max(0.0, end_at - time.monotonic())))
    finally:
        health.close()
        session.close()
        try:
            client.publish(f"{BASE_TOPIC}/availability", "offline", qos=MQTT_QOS, retain=True)
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
