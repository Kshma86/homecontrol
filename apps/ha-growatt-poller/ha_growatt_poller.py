#!/usr/bin/env python3

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


def ha_get_state(session: requests.Session, entity_id: str) -> Optional[Dict[str, Any]]:
    url = f"{HA_BASE_URL}/api/states/{entity_id}"
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code == 404:
        print(f"[HA] missing entity: {entity_id}")
        return None
    response.raise_for_status()
    return response.json()


def publish_json(client: mqtt.Client, topic: str, payload: Dict[str, Any], retain: bool = False):
    client.publish(topic, json.dumps(payload, ensure_ascii=False, sort_keys=True), qos=MQTT_QOS, retain=retain)


def main():
    if not HA_TOKEN:
        raise SystemExit("HA_TOKEN is required. Create a Home Assistant long-lived access token and set HA_GROWATT_TOKEN in infra/.env.")

    entity_map = load_entity_map()
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    })

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    client.publish(f"{BASE_TOPIC}/availability", "online", qos=MQTT_QOS, retain=True)

    print(f"[RUN] HA Growatt poller started: ha={HA_BASE_URL} mqtt={MQTT_HOST}:{MQTT_PORT} topic={BASE_TOPIC}")
    try:
        while running:
            started = time.time()
            payload: Dict[str, Any] = {
                "source": "home_assistant",
                "sample_time": now_iso(),
            }
            meta: Dict[str, Dict[str, Any]] = {}

            ok_count = 0
            for key, entity_id in entity_map.items():
                try:
                    state = ha_get_state(session, entity_id)
                except Exception as exc:
                    print(f"[HA] fetch error entity={entity_id}: {exc}")
                    continue
                if not state:
                    continue
                value = coerce_state(state.get("state"))
                if value is None:
                    continue
                payload[key] = value
                attrs = state.get("attributes") or {}
                meta[key] = {
                    "entity_id": entity_id,
                    "unit": attrs.get("unit_of_measurement"),
                    "friendly_name": attrs.get("friendly_name"),
                    "last_updated": state.get("last_updated"),
                }
                ok_count += 1

            payload["entity_count"] = ok_count
            payload["meta"] = meta
            publish_json(client, BASE_TOPIC, payload, retain=MQTT_RETAIN)
            print(f"[MQTT] published {ok_count}/{len(entity_map)} Growatt states")

            sleep_for = max(1.0, POLL_SECONDS - (time.time() - started))
            end_at = time.time() + sleep_for
            while running and time.time() < end_at:
                time.sleep(min(1.0, end_at - time.time()))
    finally:
        try:
            client.publish(f"{BASE_TOPIC}/availability", "offline", qos=MQTT_QOS, retain=True)
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
