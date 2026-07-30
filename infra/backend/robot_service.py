import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional


class RobotService:
    ALLOWED_COMMANDS = {
        "status",
        "refresh_map",
        "check_map",
        "select_map",
        "read_scheduler",
        "start",
        "stop",
        "home",
        "room_clean",
        "schedule_clean",
        "schedule_clean_week",
        "capture_start",
        "capture_stop",
        "set_clean_mode",
        "set_suction",
        "set_water_level",
    }

    def __init__(
        self,
        fetch_all: Callable[..., Any],
        normalize_text: Callable[..., str],
        publish_mqtt: Callable[..., Any],
        invalidate_context: Callable[..., Any],
        context_meta: Callable[..., Dict[str, Any]],
        monitor: Any,
        base_topic: str,
        map_dir: Optional[Path] = None,
    ):
        self.fetch_all = fetch_all
        self.normalize_text = normalize_text
        self.publish_mqtt = publish_mqtt
        self.invalidate_context = invalidate_context
        self.context_meta = context_meta
        self.monitor = monitor
        self.base_topic = base_topic.rstrip("/")
        self.map_dir = Path(map_dir) if map_dir else None

    def map_url(self, value: Any) -> Optional[str]:
        if not value:
            return None
        filename = Path(str(value)).name
        if not filename:
            return None
        return f"/api/xiaomi-x10/maps/{filename}"

    @staticmethod
    def clean_value(value: Any):
        if isinstance(value, str):
            text = value.strip()
            if text.lower() in {"", "none", "null", "undefined", "unknown_none", "unknown_null"}:
                return None
            return value
        return value

    @classmethod
    def clean_state(cls, state: Any):
        if not isinstance(state, dict):
            return {}
        cleaned = {}
        for key, value in state.items():
            cleaned[key] = cls.clean_value(value)
        return cleaned

    @classmethod
    def first_value(cls, *values: Any):
        for value in values:
            clean = cls.clean_value(value)
            if clean is not None:
                return clean
        return None

    @classmethod
    def has_telemetry(cls, state: Dict[str, Any]):
        if not isinstance(state, dict):
            return False
        return any(
            cls.clean_value(state.get(key)) is not None
            for key in ("state", "state_text", "battery", "charge_status", "task_state", "clean_mode", "suction", "water_level")
        )

    def latest_capture_status(self):
        capture_dir = self.map_dir / "captures" if self.map_dir else None
        if not capture_dir or not capture_dir.exists():
            return None
        for path in sorted(capture_dir.glob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("kind") != "status":
                    continue
                data = self.clean_state(event.get("data"))
                if not self.has_telemetry(data):
                    continue
                return {
                    "source": "capture",
                    "file": str(path),
                    "event_ts": event.get("ts"),
                    "event_iso": event.get("iso"),
                    "label": event.get("label"),
                    "map_id": event.get("map_id"),
                    "state": data,
                }
        return None

    def catalog_payload(self):
        maps = self.fetch_all(
            """
            select map_id, name, png, md5, is_current, has_room_data
            from hc.x10_map
            order by map_id
            """
        )
        rooms = self.fetch_all(
            """
            select map_id, segment_id, name, room_id, room_type, neighbors, is_active
            from hc.x10_room
            where is_active=true
            order by map_id, name
            """
        )
        rooms_by_map: Dict[str, list] = {}
        for room in rooms:
            key = str(room["map_id"])
            rooms_by_map.setdefault(key, []).append(dict(room))
        return {
            "maps": [dict(item) for item in maps],
            "rooms_by_map": rooms_by_map,
        }

    def state_payload(self):
        topics = self.monitor.snapshot()
        state = self.clean_state(self.monitor.value("state") or {})
        telemetry_source = "mqtt"
        last_known_telemetry = None
        if not self.has_telemetry(state):
            last_known_telemetry = self.latest_capture_status()
            if last_known_telemetry:
                state = last_known_telemetry["state"]
                telemetry_source = "capture"
        map_png = self.monitor.value("map/current_png")
        robot_state = self.first_value(self.monitor.value("robot_state"), state.get("state"))
        robot_state_text = self.first_value(self.monitor.value("robot_state_text"), state.get("state_text"))
        battery = self.first_value(self.monitor.value("battery"), state.get("battery"))
        charge_status = self.first_value(self.monitor.value("charge_status"), state.get("charge_status"))
        task_state = self.first_value(self.monitor.value("task_state"), state.get("task_state"))
        clean_mode = self.first_value(self.monitor.value("clean_mode"), state.get("clean_mode"))
        mop_attached = self.first_value(self.monitor.value("mop_attached"), state.get("mop_attached"))
        suction = self.first_value(self.monitor.value("suction"), state.get("suction"))
        water_level = self.first_value(self.monitor.value("water_level"), state.get("water_level"))
        telemetry_fields = {
            "robot_state": robot_state,
            "robot_state_text": robot_state_text,
            "battery": battery,
            "charge_status": charge_status,
            "task_state": task_state,
            "clean_mode": clean_mode,
            "suction": suction,
            "water_level": water_level,
        }
        missing_telemetry_fields = [key for key, value in telemetry_fields.items() if value is None]
        return {
            "mqtt_connected": topics["mqtt_connected"],
            "last_error": topics["last_error"],
            "broker": topics["broker"],
            "base_topic": topics["base_topic"],
            "bridge_online": self.clean_value(self.monitor.value("bridge/online")),
            "bridge_status": self.clean_value(self.monitor.value("bridge/status")),
            "bridge_last_seen": self.clean_value(self.monitor.value("bridge/last_seen")),
            "telemetry_available": len(missing_telemetry_fields) < len(telemetry_fields),
            "missing_telemetry_fields": missing_telemetry_fields,
            "telemetry_source": telemetry_source,
            "last_known_telemetry": last_known_telemetry,
            "state": state,
            "robot_state": robot_state,
            "robot_state_text": robot_state_text,
            "battery": battery,
            "charge_status": charge_status,
            "task_state": task_state,
            "clean_mode": clean_mode,
            "mop_attached": mop_attached,
            "suction": suction,
            "water_level": water_level,
            "map": {
                "current": self.monitor.value("map/current"),
                "current_id": self.monitor.value("map/current_id"),
                "current_name": self.monitor.value("map/current_name"),
                "current_png": map_png,
                "current_png_url": self.map_url(map_png),
                "rooms": self.monitor.value("map/current_rooms_normalized") or [],
                "object": self.monitor.value("map/object"),
                "md5": self.monitor.value("map/md5"),
            },
            "robot_position": self.monitor.value("robot/position"),
            "robot_position_px": self.monitor.value("robot/position_px"),
            "dock_position": self.monitor.value("dock/position"),
            "dock_position_px": self.monitor.value("dock/position_px"),
            "room_clean_status": self.monitor.value("room_clean/status"),
            "capture_status": self.monitor.value("capture/status"),
            "scheduler_entries": self.monitor.value("scheduler/entries") or [],
            "catalog": self.catalog_payload(),
            "command_result": self.monitor.value("command_result"),
            "error": self.monitor.value("error"),
            "topics": topics["topics"],
            "raw": topics["raw"],
        }

    def rooms_payload(self):
        return {
            "map_id": self.monitor.value("map/current_id"),
            "map_name": self.monitor.value("map/current_name"),
            "rooms": self.monitor.value("map/current_rooms_normalized") or [],
        }

    def map_payload(self):
        map_png = self.monitor.value("map/current_png")
        return {
            "current": self.monitor.value("map/current"),
            "current_id": self.monitor.value("map/current_id"),
            "current_name": self.monitor.value("map/current_name"),
            "current_png": map_png,
            "current_png_url": self.map_url(map_png),
            "object": self.monitor.value("map/object"),
            "md5": self.monitor.value("map/md5"),
        }

    def command(self, data: Dict[str, Any]):
        command = self.normalize_text(data.get("command") or data.get("name"))
        payload = data.get("payload", "1")
        if command not in self.ALLOWED_COMMANDS:
            raise ValueError("unknown command")
        ok, message = self.publish_mqtt(f"{self.base_topic}/command/{command}", payload)
        self.invalidate_context("robot")
        return {"ok": ok, "message": message, "command": command, "context": self.context_meta("robot")}
