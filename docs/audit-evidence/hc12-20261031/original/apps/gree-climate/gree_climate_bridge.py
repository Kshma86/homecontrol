from mqtt_credentials import configure_mqtt_auth
import asyncio
import json
import os
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

import paho.mqtt.client as mqtt
from greeclimate.device import Device, FanSpeed, Mode, TemperatureUnits
from greeclimate.deviceinfo import DeviceInfo


MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
BASE_TOPIC = os.environ.get("CLIMATE_BASE_TOPIC", "homecontrol/gree_climate").rstrip("/")
DEVICE_IP = os.environ.get("GREE_CLIMATE_IP", "192.168.1.72")
DEVICE_PORT = int(os.environ.get("GREE_CLIMATE_PORT", "7000"))
DEVICE_MAC = os.environ.get("GREE_CLIMATE_MAC", "9424b8ba43f7")
DEVICE_NAME = os.environ.get("GREE_CLIMATE_NAME", "Gree klíma")
POLL_SECONDS = int(os.environ.get("GREE_CLIMATE_POLL_SECONDS", "20"))
COMMAND_TIMEOUT = float(os.environ.get("GREE_COMMAND_TIMEOUT", "8"))
BUZZER_SETTINGS_PATH = Path(os.environ.get("GREE_BUZZER_SETTINGS_PATH", "/data/buzzer.json"))


def read_buzzer() -> bool:
    try:
        value = json.loads(BUZZER_SETTINGS_PATH.read_text())["buzzer"]
    except FileNotFoundError:
        return False
    if not isinstance(value, bool):
        raise ValueError("saved buzzer setting must be boolean")
    return value


def save_buzzer(value: bool):
    BUZZER_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = BUZZER_SETTINGS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps({"buzzer": value}))
    temporary.replace(BUZZER_SETTINGS_PATH)


MODE_MAP = {
    "auto": Mode.Auto,
    "cool": Mode.Cool,
    "dry": Mode.Dry,
    "fan": Mode.Fan,
    "heat": Mode.Heat,
}

FAN_MAP = {
    "auto": FanSpeed.Auto,
    "low": FanSpeed.Low,
    "mediumlow": FanSpeed.MediumLow,
    "medium": FanSpeed.Medium,
    "mediumhigh": FanSpeed.MediumHigh,
    "high": FanSpeed.High,
}

FAN_EXTRA_MAP = {
    "quiet": "quiet",
    "turbo": "turbo",
}

MODE_NAME_MAP = {value: key for key, value in MODE_MAP.items()}
FAN_NAME_MAP = {value: key for key, value in FAN_MAP.items()}


def enum_name(value: Any, names: Dict[Any, str]) -> str:
    if value is None:
        return "unknown"
    return names.get(value, str(value))


def error_text(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return f"timed out talking to {DEVICE_IP}:{DEVICE_PORT}"
    return str(error) or error.__class__.__name__


async def update_state_and_wait(device: Device, timeout: float = COMMAND_TIMEOUT):
    device._valid_state.clear()
    await device.update_state()
    await asyncio.wait_for(device._valid_state.wait(), timeout=timeout)


async def connect_device() -> Device:
    info = DeviceInfo(DEVICE_IP, DEVICE_PORT, DEVICE_MAC, DEVICE_MAC)
    device = Device(info)
    # Apply the saved preference to every HC command, including scheduled ones.
    device.buzzer = read_buzzer()
    await device.bind()
    await update_state_and_wait(device)
    return device


def state_payload(device: Device) -> Dict[str, Any]:
    fan_speed = enum_name(device.fan_speed, FAN_NAME_MAP)
    if bool(device.quiet):
        fan_speed = "quiet"
    elif bool(device.turbo):
        fan_speed = "turbo"
    return {
        "ok": True,
        "name": getattr(device.device_info, "name", None) or DEVICE_NAME,
        "ip": getattr(device.device_info, "ip", DEVICE_IP),
        "port": getattr(device.device_info, "port", DEVICE_PORT),
        "mac": getattr(device.device_info, "mac", DEVICE_MAC),
        "power": "on" if bool(device.power) else "off",
        "mode": enum_name(device.mode, MODE_NAME_MAP),
        "target_temperature": device.target_temperature,
        "current_temperature": device.current_temperature,
        "fan_speed": fan_speed,
        "quiet": "on" if bool(device.quiet) else "off",
        "turbo": "on" if bool(device.turbo) else "off",
        "sleep": "on" if bool(device.sleep) else "off",
        "xfan": "on" if bool(device.xfan) else "off",
        "power_save": "on" if bool(device.power_save) else "off",
        "current_humidity": device.current_humidity,
        "target_humidity": device.target_humidity,
        "light": "on" if bool(device.light) else "off",
        "buzzer": "on" if device.buzzer else "off",
        "raw_properties": device.raw_properties,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


async def read_state() -> Dict[str, Any]:
    sampled_at = time.time()
    device = await connect_device()
    return {**state_payload(device), "sampled_at": sampled_at}


async def apply_command(command: Dict[str, Any]) -> Dict[str, Any]:
    sampled_at = time.time()
    device = await connect_device()
    changed = False
    if "buzzer" in command:
        if command["buzzer"] not in {"on", "off"}:
            raise ValueError("buzzer must be on or off")
        device.buzzer = command["buzzer"] == "on"

    power = str(command.get("power") or "").strip().lower()
    if power:
        if power not in {"on", "off"}:
            raise ValueError("power must be on or off")
        device.power = power == "on"
        changed = True

    mode = str(command.get("mode") or "").strip().lower()
    if mode:
        if mode not in MODE_MAP:
            raise ValueError("unknown mode")
        device.mode = MODE_MAP[mode]
        changed = True

    if command.get("target_temperature") is not None:
        target_temperature = int(command.get("target_temperature"))
        if target_temperature < 8 or target_temperature > 30:
            raise ValueError("target_temperature must be between 8 and 30")
        device.temperature_units = TemperatureUnits.C
        device.target_temperature = target_temperature
        changed = True

    fan = str(command.get("fan_speed") or "").strip().lower()
    if fan:
        if fan in FAN_EXTRA_MAP:
            device.quiet = fan == "quiet"
            device.turbo = fan == "turbo"
        elif fan in FAN_MAP:
            device.fan_speed = FAN_MAP[fan]
            device.quiet = False
            device.turbo = False
        else:
            raise ValueError("unknown fan_speed")
        changed = True

    for field in ("quiet", "turbo", "sleep", "xfan", "power_save"):
        value = str(command.get(field) or "").strip().lower()
        if value:
            if value not in {"on", "off"}:
                raise ValueError(f"{field} must be on or off")
            setattr(device, field, value == "on")
            changed = True

    light = str(command.get("light") or "").strip().lower()
    if light:
        if light not in {"on", "off"}:
            raise ValueError("light must be on or off")
        device.light = light == "on"
        changed = True

    if "buzzer" in command:
        save_buzzer(device.buzzer)

    if changed:
        await asyncio.wait_for(device.push_state_update(), timeout=COMMAND_TIMEOUT)
        await asyncio.sleep(2)
        sampled_at = time.time()
        await update_state_and_wait(device)

    payload = state_payload(device)
    payload["sampled_at"] = sampled_at
    payload["changed"] = changed
    return payload


class Bridge:
    def __init__(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="homecontrol-gree-climate")
        configure_mqtt_auth(self.client)
        self.client.will_set(f"{BASE_TOPIC}/availability", "offline", retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.lock = threading.Lock()

    def publish_json(self, topic: str, payload: Dict[str, Any], retain: bool = True):
        if topic == f"{BASE_TOPIC}/command_result":
            payload = {**payload, "reported_at": time.time()}
        self.client.publish(topic, json.dumps(payload, ensure_ascii=False), retain=retain)

    def publish_state(self, payload: Dict[str, Any]):
        self.publish_json(f"{BASE_TOPIC}/state", payload, retain=True)

    def publish_error(self, error: Exception):
        payload = {
            "ok": False,
            "name": DEVICE_NAME,
            "ip": DEVICE_IP,
            "port": DEVICE_PORT,
            "mac": DEVICE_MAC,
            "error": error_text(error),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.publish_state(payload)

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.publish(f"{BASE_TOPIC}/availability", "online", retain=True)
            client.subscribe(f"{BASE_TOPIC}/command", qos=0)
            threading.Thread(target=self.refresh_once, name="gree-initial-refresh", daemon=True).start()

    def on_message(self, client, userdata, msg):
        try:
            command = json.loads(msg.payload.decode("utf-8"))
            if not isinstance(command, dict):
                raise ValueError("command payload must be an object")
        except Exception as exc:
            self.publish_json(
                f"{BASE_TOPIC}/command_result",
                {"ok": False, "error": str(exc), "updated_at": datetime.now().isoformat(timespec="seconds")},
                retain=True,
            )
            return
        threading.Thread(target=self.handle_command, args=(command,), name="gree-command", daemon=True).start()

    def refresh_once(self):
        with self.lock:
            try:
                payload = asyncio.run(read_state())
                self.publish_state(payload)
            except Exception as exc:
                self.publish_error(exc)

    def handle_command(self, command: Dict[str, Any]):
        with self.lock:
            try:
                payload = asyncio.run(apply_command(command))
                self.publish_state(payload)
                self.publish_json(
                    f"{BASE_TOPIC}/command_result",
                    {"ok": True, "command": command, "state": payload, "updated_at": datetime.now().isoformat(timespec="seconds")},
                    retain=True,
                )
            except Exception as exc:
                self.publish_error(exc)
                self.publish_json(
                    f"{BASE_TOPIC}/command_result",
                    {"ok": False, "command": command, "error": error_text(exc), "updated_at": datetime.now().isoformat(timespec="seconds")},
                    retain=True,
                )

    def poll_loop(self):
        while True:
            self.refresh_once()
            time.sleep(max(5, POLL_SECONDS))

    def run(self):
        self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.client.loop_start()
        threading.Thread(target=self.poll_loop, name="gree-poll", daemon=True).start()
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    Bridge().run()
