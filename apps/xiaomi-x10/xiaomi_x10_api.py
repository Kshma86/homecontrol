import json
import time
from flask import Blueprint, jsonify, request
import paho.mqtt.client as mqtt

import config

xiaomi_x10_bp = Blueprint("xiaomi_x10", __name__)

MQTT_HOST = config.MQTT_HOST
MQTT_PORT = config.MQTT_PORT
BASE_TOPIC = config.BASE_TOPIC

state_cache = {}
mqtt_client = mqtt.Client()


def parse_payload(payload):
    text = payload.decode("utf-8")

    try:
        return json.loads(text)
    except Exception:
        return text


def on_connect(client, userdata, flags, rc):
    print("X10 API MQTT connected:", rc)
    client.subscribe(f"{BASE_TOPIC}/#")


def on_message(client, userdata, msg):
    rel_topic = msg.topic.replace(f"{BASE_TOPIC}/", "", 1)
    state_cache[rel_topic] = {
        "value": parse_payload(msg.payload),
        "ts": int(time.time())
    }


def mqtt_publish_command(command, payload="1"):
    topic = f"{BASE_TOPIC}/command/{command}"

    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload, ensure_ascii=False)

    mqtt_client.publish(topic, str(payload), retain=False)


def start_xiaomi_x10_mqtt():
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_client.loop_start()


@xiaomi_x10_bp.route("/api/xiaomi_x10/status", methods=["GET"])
def get_status():
    return jsonify({
        "state": state_cache.get("state", {}).get("value"),
        "robot_state": state_cache.get("robot_state", {}).get("value"),
        "robot_state_text": state_cache.get("robot_state_text", {}).get("value"),
        "battery": state_cache.get("battery", {}).get("value"),
        "clean_mode": state_cache.get("clean_mode", {}).get("value"),
        "mop_attached": state_cache.get("mop_attached", {}).get("value"),
        "suction": state_cache.get("suction", {}).get("value"),
        "water_level": state_cache.get("water_level", {}).get("value"),
        "map_current_id": state_cache.get("map/current_id", {}).get("value"),
        "map_current_name": state_cache.get("map/current_name", {}).get("value"),
        "map_current_png": state_cache.get("map/current_png", {}).get("value"),
        "room_clean_status": state_cache.get("room_clean/status", {}).get("value"),
        "bridge_online": state_cache.get("bridge/online", {}).get("value"),
        "bridge_status": state_cache.get("bridge/status", {}).get("value"),
        "bridge_last_seen": state_cache.get("bridge/last_seen", {}).get("value"),
    })


@xiaomi_x10_bp.route("/api/xiaomi_x10/rooms", methods=["GET"])
def get_rooms():
    return jsonify({
        "map_id": state_cache.get("map/current_id", {}).get("value"),
        "map_name": state_cache.get("map/current_name", {}).get("value"),
        "rooms": state_cache.get("map/current_rooms_normalized", {}).get("value") or []
    })


@xiaomi_x10_bp.route("/api/xiaomi_x10/map", methods=["GET"])
def get_map():
    return jsonify({
        "current": state_cache.get("map/current", {}).get("value"),
        "current_id": state_cache.get("map/current_id", {}).get("value"),
        "current_name": state_cache.get("map/current_name", {}).get("value"),
        "current_png": state_cache.get("map/current_png", {}).get("value"),
        "object": state_cache.get("map/object", {}).get("value"),
        "md5": state_cache.get("map/md5", {}).get("value"),
    })


@xiaomi_x10_bp.route("/api/xiaomi_x10/command", methods=["POST"])
def send_command():
    data = request.get_json(force=True) or {}

    command = data.get("command")
    payload = data.get("payload", "1")

    allowed = {
        "status",
        "refresh_map",
        "check_map",
        "read_scheduler",
        "start",
        "stop",
        "home",
        "room_clean",
    }

    if command not in allowed:
        return jsonify({"ok": False, "error": f"unknown command: {command}"}), 400

    mqtt_publish_command(command, payload)

    return jsonify({
        "ok": True,
        "command": command,
        "payload": payload
    })


@xiaomi_x10_bp.route("/api/xiaomi_x10/cache", methods=["GET"])
def get_cache():
    return jsonify(state_cache)
