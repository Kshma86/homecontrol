import ipaddress
import json
import math
import struct
import time
import uuid
import zlib
from typing import Any, Callable, Dict, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


CONTRACT_VERSION = "2.4.0"
CONTRACT_MAJOR = 2
MISSION_CONTRACT_MIN = (2, 4, 0)
MISSION_PREVIEW_CAPABILITY = "mission.upload_preview.v1"
MISSION_FULL_CAPABILITY = "mission.v1"
MISSION_FW_STALE_SECONDS = 120

COMMANDS = {
    "stop": "stop",
    "arm": "arm",
    "disarm": "disarm",
    "fault_clear": "fault_clear",
    "clear_estop": "clear_estop",
    "safety_reset": "safety_reset",
    "telemetry": "telemetry",
    "blade_stop": "blade_stop",
    "north_set": "heading/north_set",
    "heading_cancel": "heading/cancel",
    "auto_status": "auto/status",
    "route_record": "route/record",
    "route_clear": "route/clear",
    "route_play": "route/play",
    "route_stop": "route/stop",
}

VALUE_COMMANDS = {
    "blade_rpm": ("blade_rpm", 0.0, 25000.0, True),
    "heading_target": ("heading/target_deg", 0.0, 360.0, False),
    "heading_relative": ("heading/relative_deg", -360.0, 360.0, False),
}

REQUIRED_STATUS_TOPICS = (
    "availability",
    "status/fw",
    "status/link",
    "status/imu",
    "status/gnss",
    "status/route",
    "status/robot",
    "status/fault",
    "status/safety",
    "status/auto",
    "status/heading",
    "status/motor/1",
    "status/motor/2",
    "status/motor/3",
)

STATUS_STALE_SECONDS = {
    "status/link": 10,
    "status/imu": 2,
    "status/gnss": 3,
    "status/motor/1": 3,
    "status/motor/2": 3,
    "status/motor/3": 3,
}
DEFAULT_STATUS_STALE_SECONDS = 10

STATUS_REQUIRED_FIELDS = {
    "status/fw": {"esp": str, "stm": str, "contract": str},
    "status/link": {"wifi": bool, "stm_alive": bool, "can_alive": bool, "stm_age_ms": int, "can_age_ms": int, "manual_ws_claimed": bool},
    "status/imu": {"alive": bool, "compass_deg": (int, float), "north_valid": bool, "auto_north_active": bool, "auto_north_status": str, "age_ms": int},
    "status/gnss": {"alive": bool, "fix_quality": int, "fix_name": str, "sats": int, "hdop": (int, float), "speed_kmh": (int, float), "course_deg": (int, float), "correction_age_s": (int, float), "age_ms": int},
    "status/robot": {"state": str, "armed": bool, "estop": bool, "fault_mask": int, "auto": bool, "link_alive": bool},
    "status/fault": {"name": str, "active": bool, "mask": int},
    "status/safety": {"bumper": bool, "lift": bool, "tilt": bool, "imu_tilt": bool, "wire_lost": bool},
    "status/heading": {"north_valid": bool, "current_deg": (int, float), "assist": bool, "assist_active": bool, "target_active": bool},
    "status/motor/1": {"id": int, "seen": bool, "age_ms": int, "rpm": int},
    "status/motor/2": {"id": int, "seen": bool, "age_ms": int, "rpm": int},
    "status/motor/3": {"id": int, "seen": bool, "age_ms": int, "rpm": int},
    "status/auto": {"active": bool, "phase": str, "count": int, "index": int},
    "status/route": {"count": int, "playing": bool, "points": list},
}


class MowerService:
    def __init__(
        self,
        *,
        monitor: Any,
        publish_mqtt: Callable[..., Any],
        base_topic: str,
        remote_url: str,
    ):
        self.monitor = monitor
        self.publish_mqtt = publish_mqtt
        self.base_topic = base_topic.rstrip("/")
        self.remote_url = remote_url
        self.update_client_id = "homecontrol-stm-update"
        self.mission_client_id = "homecontrol-mission"
        self.mission_session_id = ""

    def _capabilities(self):
        fw = ((self.monitor.snapshot().get("topics", {}).get("status/fw") or {}).get("json") or {})
        values = fw.get("capabilities")
        return [item for item in values if isinstance(item, str)] if isinstance(values, list) else []

    @staticmethod
    def _mission_response(status: int, body: bytes, default_stage: str, default_message: str):
        text = body.decode("utf-8", errors="replace").strip() if body else ""
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {"message": text} if text else {}
        if not isinstance(payload, dict):
            payload = {"message": text or default_message}
        payload.setdefault("stage", default_stage)
        payload.setdefault("message", default_message if status >= 400 else "OK")
        payload["ok"] = status == 200 and payload.get("ok", True) is not False
        if not payload["ok"]:
            payload.setdefault("code", "REMOTE_ERROR")
            payload.setdefault("error", payload.get("message") or default_message)
        return payload

    def _mission_mqtt_access(self):
        snapshot = self.monitor.snapshot()
        fw_item = snapshot.get("topics", {}).get("status/fw") or {}
        fw = fw_item.get("json") or {}
        reported = str(fw.get("contract") or "").strip() if isinstance(fw, dict) else ""
        capabilities = self._capabilities()
        fresh = (
            fw_item.get("age_sec") is not None
            and fw_item["age_sec"] <= MISSION_FW_STALE_SECONDS
            and not bool(fw_item.get("retain"))
        )
        if not fresh:
            return None, "mission firmware status is missing, stale or retained"
        if not self._version_at_least(reported, MISSION_CONTRACT_MIN):
            return None, f"mission requires contract {CONTRACT_VERSION} or newer; rover reports {reported or 'missing'}"
        if MISSION_FULL_CAPABILITY in capabilities:
            return "full", ""
        if MISSION_PREVIEW_CAPABILITY in capabilities:
            return "preview", ""
        return None, "rover does not advertise mission.v1 or mission.upload_preview.v1"

    @staticmethod
    def _bounded_int(value, name, minimum, maximum):
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
        return value

    def compile_mission(self, mission: Dict[str, Any]):
        if not isinstance(mission, dict) or mission.get("schema") != "hc.mower.mission.v1":
            raise ValueError("unsupported mission schema")
        try:
            mission_uuid = uuid.UUID(str(mission.get("mission_id")))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("mission_id must be an RFC4122 UUID") from exc
        revision = self._bounded_int(mission.get("revision"), "revision", 1, 0xFFFFFFFF)
        origin = mission.get("origin") or {}
        origin_lat = self._bounded_int(origin.get("lat_e7"), "origin.lat_e7", -900000000, 900000000)
        origin_lon = self._bounded_int(origin.get("lon_e7"), "origin.lon_e7", -1800000000, 1800000000)
        geometry = mission.get("geometry") or {}
        if geometry.get("drive_type") != "differential_tank" or geometry.get("pivot_turn") is not True:
            raise ValueError("mission requires differential_tank with pivot_turn=true")
        geometry_names = ("rover_width_mm", "rover_length_mm", "pivot_safety_radius_mm", "cut_width_mm", "antenna_forward_mm", "antenna_left_mm", "boundary_clearance_mm")
        geometry_values = [self._bounded_int(geometry.get(name), f"geometry.{name}", -100000 if name.startswith("antenna_") else 0, 100000) for name in geometry_names]
        if any(value <= 0 for index, value in enumerate(geometry_values) if index not in (4, 5, 6)) or geometry_values[6] < 0:
            raise ValueError("invalid mission geometry")
        if geometry_values[2] < math.ceil(math.hypot(geometry_values[0], geometry_values[1]) / 2):
            raise ValueError("pivot_safety_radius_mm is smaller than the rover footprint")
        limits = mission.get("limits") or {}
        limit_names = ("drive_speed_mm_s", "connector_speed_mm_s", "turn_speed_mdeg_s", "start_tolerance_mm", "waypoint_tolerance_mm", "max_cross_track_mm", "max_heading_error_mdeg", "max_rtk_age_ms", "max_correction_age_ms")
        limit_values = [self._bounded_int(limits.get(name), f"limits.{name}", 1, 1000000) for name in limit_names]
        boundary = mission.get("boundary")
        exclusions = mission.get("exclusions") or []
        operations = mission.get("operations")
        if not isinstance(boundary, list) or not 3 <= len(boundary) <= 256:
            raise ValueError("boundary must contain 3..256 points")
        if not isinstance(exclusions, list) or len(exclusions) > 32:
            raise ValueError("exclusions must contain at most 32 polygons")
        if not isinstance(operations, list) or not 4 <= len(operations) <= 4096:
            raise ValueError("operations must contain 4..4096 items")

        def point_bytes(point, label):
            if not isinstance(point, dict):
                raise ValueError(f"{label} must be an object")
            east = self._bounded_int(point.get("east_mm"), f"{label}.east_mm", -2000000000, 2000000000)
            north = self._bounded_int(point.get("north_mm"), f"{label}.north_mm", -2000000000, 2000000000)
            return struct.pack("<ii", east, north)

        geometry_body = b"".join(point_bytes(point, f"boundary[{index}]") for index, point in enumerate(boundary))
        for zone_index, zone in enumerate(exclusions):
            if not isinstance(zone, list) or not 3 <= len(zone) <= 128:
                raise ValueError(f"exclusions[{zone_index}] must contain 3..128 points")
            geometry_body += struct.pack("<HH", len(zone), 0)
            geometry_body += b"".join(point_bytes(point, f"exclusions[{zone_index}][{index}]") for index, point in enumerate(zone))

        type_ids = {"TURN_IN_PLACE": 1, "DRIVE_LINE": 2, "BLADE_ON": 3, "BLADE_OFF": 4, "STOP": 5, "PATH_START": 6}
        operation_body = bytearray()
        for index, operation in enumerate(operations):
            if not isinstance(operation, dict) or operation.get("type") not in type_ids:
                raise ValueError(f"operations[{index}] has unknown type")
            kind = operation["type"]
            east = int(operation.get("east_mm", 0)); north = int(operation.get("north_mm", 0))
            flags = 1 if kind == "DRIVE_LINE" and operation.get("blade") is True else 0
            if kind == "TURN_IN_PLACE": arg0 = int(operation.get("heading_mdeg", 0))
            elif kind == "DRIVE_LINE": arg0 = int(operation.get("speed_mm_s", 0))
            elif kind == "BLADE_ON": arg0 = int(operation.get("target_rpm", 0))
            elif kind == "PATH_START": arg0 = int(operation.get("tolerance_mm", 0))
            else: arg0 = 0
            cell = int(operation.get("cell", 0)); lane = int(operation.get("lane", 0))
            for value, name in ((east, "east_mm"), (north, "north_mm"), (arg0, "arg0")):
                self._bounded_int(value, f"operations[{index}].{name}", -2000000000, 2000000000)
            self._bounded_int(cell, f"operations[{index}].cell", 0, 65535); self._bounded_int(lane, f"operations[{index}].lane", 0, 65535)
            operation_body.extend(struct.pack("<BBHiiiHHI", type_ids[kind], flags, 0, east, north, arg0, cell, lane, 0))
        if operations[0].get("type") != "PATH_START" or operations[-1].get("type") != "STOP":
            raise ValueError("mission must start with PATH_START and end with STOP")
        if operations[1].get("type") != "BLADE_ON" or operations[-2].get("type") != "BLADE_OFF":
            raise ValueError("mowing mission must switch the blade on once after PATH_START and off once before STOP")
        if any(operation.get("type") in ("BLADE_ON", "BLADE_OFF") for operation in operations[2:-2]):
            raise ValueError("intermediate blade switching is forbidden in mowing mission v1")
        if any(operation.get("type") == "DRIVE_LINE" and operation.get("blade") is not True for operation in operations):
            raise ValueError("every DRIVE_LINE must keep the blade enabled in mowing mission v1")
        body = geometry_body + bytes(operation_body)
        payload_crc = zlib.crc32(body) & 0xFFFFFFFF
        total_length = 116 + len(body)
        header = struct.pack("<4sHHII16sIiiHHI", b"HCM1", 1, 0, total_length, payload_crc, mission_uuid.bytes, revision, origin_lat, origin_lon, len(boundary), len(exclusions), len(operations))
        header += struct.pack("<7i", *geometry_values) + struct.pack("<9i", *limit_values)
        binary = header + body
        if len(binary) != total_length or total_length > 256 * 1024:
            raise ValueError("compiled mission exceeds the 256 KiB limit")
        return binary, {"mission_id": str(mission_uuid), "revision": revision, "bytes": total_length, "payload_crc32": f"{payload_crc:08X}", "file_crc32": f"{zlib.crc32(binary) & 0xFFFFFFFF:08X}", "operation_count": len(operations)}

    def _esp_origin(self) -> str:
        snapshot = self.monitor.snapshot()
        link = (snapshot.get("topics", {}).get("status/link") or {}).get("json") or {}
        ip = str(link.get("ip") or "").strip()
        if ip:
            try:
                address = ipaddress.ip_address(ip)
            except ValueError as exc:
                raise ValueError("invalid mower address") from exc
            if not (address.is_private or address.is_link_local):
                raise ValueError("mower address must be on the private network")
            return f"http://{address}"

        parsed = urlparse(self.remote_url)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("invalid mower remote URL")
        return f"http://{parsed.netloc}"

    def _esp_request(self, path: str, *, method: str = "GET", body: bytes = None, headers=None, timeout=10):
        url = f"{self._esp_origin()}{path}"
        request = Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.status, response.read()
        except HTTPError as exc:
            return exc.code, exc.read()
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"ESP remote unavailable: {exc}") from exc

    def firmware_status(self) -> Tuple[Dict[str, Any], int]:
        try:
            status, body = self._esp_request("/api/stm_update_status", timeout=3)
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc)}, 503
        payload["ok_response"] = status == 200
        payload["reachable"] = True
        payload["remote"] = self._esp_origin()
        return payload, 200 if status == 200 else status

    def firmware_upload(self, filename: str, firmware: bytes) -> Tuple[Dict[str, Any], int]:
        if not filename.lower().endswith(".bin"):
            return {"ok": False, "error": "STM firmware must be a .bin file"}, 400
        if not firmware:
            return {"ok": False, "error": "firmware file is empty"}, 400
        if len(firmware) > 2 * 1024 * 1024:
            return {"ok": False, "error": "firmware exceeds the 2 MiB STM flash limit"}, 413

        crc = zlib.crc32(firmware) & 0xFFFFFFFF
        query = urlencode({"client": self.update_client_id, "claim": 1, "size": len(firmware), "crc": crc})
        try:
            prep_status, prep_body = self._esp_request(
                f"/api/stm_update_prepare?{query}", method="POST", body=b"", timeout=55
            )
            if prep_status != 200:
                message = prep_body.decode("utf-8", errors="replace").strip()
                return {"ok": False, "error": message or "STM update prepare failed"}, prep_status

            boundary = f"----homecontrol-{uuid.uuid4().hex}"
            safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "")
            prefix = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="firmware"; filename="{safe_name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            upload_body = prefix + firmware + f"\r\n--{boundary}--\r\n".encode()
            upload_status, upload_response = self._esp_request(
                f"/api/stm_update?{query}",
                method="POST",
                body=upload_body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                timeout=590,
            )
        except (RuntimeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}, 503

        message = upload_response.decode("utf-8", errors="replace").strip()
        ok = upload_status == 200
        return {
            "ok": ok,
            "message": message,
            "filename": filename,
            "bytes": len(firmware),
            "crc32": crc,
            "staged": ok,
        }, 200 if ok else upload_status

    def firmware_action(self, action: str) -> Tuple[Dict[str, Any], int]:
        endpoints = {"activate": "/api/stm_activate", "reset": "/api/stm_reset"}
        if action not in endpoints:
            return {"ok": False, "error": "unsupported firmware action"}, 400
        allowed, reason = self._control_allowed()
        if not allowed:
            return {"ok": False, "error": reason, "code": "INCOMPATIBLE_VERSION"}, 409
        query = urlencode({"client": self.update_client_id, "claim": 1})
        try:
            status, body = self._esp_request(
                f"{endpoints[action]}?{query}", method="POST", body=b"", timeout=20
            )
        except (RuntimeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}, 503
        message = body.decode("utf-8", errors="replace").strip()
        return {"ok": status == 200, "action": action, "message": message}, status

    def mission_status(self) -> Tuple[Dict[str, Any], int]:
        try:
            status, body = self._esp_request("/api/mission/status", timeout=4)
            payload = self._mission_response(status, body, "STATUS", "mission status failed")
        except (RuntimeError, ValueError) as exc:
            return {"ok": False, "stage": "STATUS", "code": "REMOTE_UNAVAILABLE", "error": str(exc), "message": str(exc)}, 503
        return payload, status

    def mission_deploy(self, mission: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        allowed, reason = self._control_allowed()
        if not allowed:
            return {"ok": False, "error": reason, "code": "INCOMPATIBLE_VERSION"}, 409
        mode, reason = self._mission_mqtt_access()
        if not mode:
            return {"ok": False, "stage": "PREPARE", "error": reason, "message": reason, "code": "CAPABILITY_UNAVAILABLE"}, 409
        stage = "COMPILE"
        metadata = {}
        try:
            binary, metadata = self.compile_mission(mission)
            stage = "STATUS"
            status_code, status_body = self._esp_request("/api/mission/status", timeout=5)
            remote_status = self._mission_response(status_code, status_body, "STATUS", "mission status preflight failed")
            if status_code != 200:
                return remote_status, status_code
            snapshot = self.monitor.snapshot()
            mqtt_fw = ((snapshot.get("topics", {}).get("status/fw") or {}).get("json") or {})
            mqtt_contract = str(mqtt_fw.get("contract") or "")
            mqtt_capabilities = {item for item in mqtt_fw.get("capabilities", []) if isinstance(item, str)}
            remote_contract = str(remote_status.get("contract") or "")
            remote_capabilities = {item for item in remote_status.get("capabilities", []) if isinstance(item, str)}
            if remote_contract != mqtt_contract or remote_capabilities != mqtt_capabilities:
                return {"ok": False, "stage": "STATUS", "code": "STATUS_MISMATCH", "message": "HTTP mission status contract/capabilities differ from fresh MQTT status", "error": "HTTP mission status contract/capabilities differ from fresh MQTT status", "mqtt_contract": mqtt_contract, "http_contract": remote_contract, "mqtt_capabilities": sorted(mqtt_capabilities), "http_capabilities": sorted(remote_capabilities)}, 409
            max_alloc = remote_status.get("max_alloc_heap")
            storage = remote_status.get("storage") if isinstance(remote_status.get("storage"), dict) else {}
            max_alloc = storage.get("max_alloc_heap", max_alloc)
            if isinstance(max_alloc, int) and len(binary) > max_alloc:
                return {"ok": False, "stage": "PREPARE", "code": "INSUFFICIENT_STORAGE", "message": f"Mission requires {len(binary)} bytes but rover largest allocation is {max_alloc} bytes", "error": f"Mission requires {len(binary)} bytes but rover largest allocation is {max_alloc} bytes", **metadata}, 507

            stage = "PREPARE"
            query = urlencode({"client": self.mission_client_id, "size": len(binary), "crc": int(metadata["file_crc32"], 16), "mission_id": metadata["mission_id"], "revision": metadata["revision"]})
            prepare_status, prepare_body = self._esp_request(f"/api/mission/prepare?{query}", method="POST", body=b"", timeout=10)
            prepare = self._mission_response(prepare_status, prepare_body, "PREPARE", "mission prepare failed")
            if prepare_status != 200:
                return {**metadata, **prepare}, prepare_status
            session_id = str(prepare.get("session_id") or "").strip()
            if not session_id:
                return {"ok": False, "stage": "PREPARE", "code": "PROTOCOL_ERROR", "message": "Rover prepare response did not include session_id", "error": "Rover prepare response did not include session_id", **metadata}, 502
            self.mission_session_id = session_id
            session_query = urlencode({"client": self.mission_client_id, "session_id": session_id})

            stage = "UPLOAD"
            upload_status, upload_body = self._esp_request(f"/api/mission/upload?{session_query}", method="POST", body=binary, headers={"Content-Type": "application/octet-stream", "Content-Length": str(len(binary))}, timeout=120)
            upload = self._mission_response(upload_status, upload_body, "UPLOAD", "mission upload failed")
            if upload_status != 200:
                return {**metadata, **upload}, upload_status

            stage = "ESP_VALIDATE"
            validate_status, validate_body = self._esp_request(f"/api/mission/validate?{session_query}", method="POST", body=b"", timeout=180)
            validate = self._mission_response(validate_status, validate_body, "STM_VALIDATE", "mission validation failed")
            if validate_status != 200:
                return {**metadata, **validate}, validate_status
            if mode == "preview":
                return {**metadata, **validate, "ok": True, "mode": "preview", "stage": validate.get("stage") or "ESP_VALIDATE", "session_id": session_id, "message": validate.get("message") or "Mission uploaded and preview-validated; activation is disabled"}, 200
            if validate.get("stm_validated") is not True:
                return {"ok": False, "stage": "STM_VALIDATE", "code": "STM_REJECTED", "message": "Rover returned success without stm_validated=true", "error": "Rover returned success without stm_validated=true", "session_id": session_id, **metadata}, 422

            stage = "ACTIVATE"
            activate_query = urlencode({"client": self.mission_client_id, "session_id": session_id, "mission_id": metadata["mission_id"], "revision": metadata["revision"]})
            activate_status, activate_body = self._esp_request(f"/api/mission/activate?{activate_query}", method="POST", body=b"", timeout=20)
            activate = self._mission_response(activate_status, activate_body, "ACTIVATE", "mission activation failed")
            if activate_status != 200:
                return {**metadata, **activate}, activate_status
        except ValueError as exc:
            return {"ok": False, "stage": stage, "code": "INVALID_ARGUMENT", "error": str(exc), "message": str(exc), **metadata}, 400
        except RuntimeError as exc:
            return {"ok": False, "stage": stage, "code": "REMOTE_UNAVAILABLE", "error": str(exc), "message": str(exc), **metadata}, 503
        return {**metadata, **activate, "ok": True, "mode": "full", "stage": "ACTIVATE", "session_id": self.mission_session_id, "message": activate.get("message") or "Mission compiled, uploaded, STM-validated and activated"}, 200

    def mission_action(self, action: str) -> Tuple[Dict[str, Any], int]:
        if action not in ("start", "pause", "resume", "stop"):
            return {"ok": False, "error": "unsupported mission action"}, 400
        allowed, reason = self._control_allowed()
        if not allowed:
            return {"ok": False, "error": reason, "code": "INCOMPATIBLE_VERSION"}, 409
        mode, reason = self._mission_mqtt_access()
        if mode != "full":
            return {"ok": False, "error": "Rover firmware does not advertise mission.v1", "code": "CAPABILITY_UNAVAILABLE"}, 409
        try:
            status_code, status_body = self._esp_request("/api/mission/status", timeout=5)
            current = self._mission_response(status_code, status_body, "STATUS", "mission status reconciliation failed")
            if status_code != 200:
                return current, status_code
            session_id = str(current.get("session_id") or self.mission_session_id or "").strip()
            if not session_id:
                return {"ok": False, "stage": action.upper(), "code": "SESSION_MISMATCH", "message": "No active mission session_id is available", "error": "No active mission session_id is available"}, 409
            query = urlencode({"client": self.mission_client_id, "session_id": session_id})
            status, body = self._esp_request(f"/api/mission/{action}?{query}", method="POST", body=b"", timeout=20)
        except (RuntimeError, ValueError) as exc:
            return {"ok": False, "stage": action.upper(), "code": "REMOTE_UNAVAILABLE", "error": str(exc), "message": str(exc)}, 503
        payload = self._mission_response(status, body, action.upper(), f"mission {action} failed")
        payload["action"] = action
        return payload, status

    def _claim_remote_session(self) -> Tuple[bool, str, int]:
        query = urlencode({"client": self.update_client_id})
        status, body = self._esp_request(f"/api/session?{query}", timeout=4)
        message = body.decode("utf-8", errors="replace").strip()
        return status == 200, message, status

    def _mqtt_route_payload(self):
        snapshot = self.monitor.snapshot()
        item = snapshot.get("topics", {}).get("status/route") or {}
        payload = item.get("json")
        # The original status/route summary has no point list. Presence of the
        # points array identifies ESP firmware with MQTT route control support.
        if not isinstance(payload, dict) or not isinstance(payload.get("points"), list):
            return None, item
        return payload, item

    def route_status(self) -> Tuple[Dict[str, Any], int]:
        payload, item = self._mqtt_route_payload()
        if payload is not None:
            result = dict(payload)
            result.setdefault("count", len(result.get("points") or []))
            result.setdefault("playing", False)
            result.setdefault("stm_auto", False)
            result.setdefault("index", 0)
            result.setdefault("mode", "idle")
            result["age_sec"] = item.get("age_sec")
            result["transport"] = "mqtt"
            result["ok"] = True
            return result, 200

        try:
            status, body = self._esp_request("/api/route", timeout=3)
            result = json.loads(body.decode("utf-8", errors="replace"))
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc), "transport": "legacy_http"}, 503
        result["ok"] = status == 200
        result["transport"] = "legacy_http"
        return result, 200 if status == 200 else status

    def route_action(self, action: str) -> Tuple[Dict[str, Any], int]:
        commands = {
            "record": "route_record",
            "clear": "route_clear",
            "play": "route_play",
            "stop": "route_stop",
            "auto_status": "auto_status",
        }
        if action not in commands:
            return {"ok": False, "error": "unsupported route action"}, 400
        allowed, reason = self._control_allowed()
        if not allowed:
            return {"ok": False, "error": reason, "code": "INCOMPATIBLE_VERSION"}, 409
        mqtt_payload, _ = self._mqtt_route_payload()
        if mqtt_payload is not None:
            payload, status = self.command({"command": commands[action]})
            payload["action"] = action
            if payload.get("ok"):
                payload["message"] = f"RTK route {action} command sent over MQTT"
            return payload, status

        endpoints = {
            "record": "/api/route_add",
            "clear": "/api/route_clear",
            "play": "/api/route_play",
            "stop": "/api/route_stop",
            "auto_status": "/api/auto_status",
        }
        query = urlencode({"client": self.update_client_id, "claim": 1})
        try:
            claimed, claim_message, claim_status = self._claim_remote_session()
            if not claimed:
                return {"ok": False, "error": claim_message or "ESP remote session busy"}, claim_status
            status, body = self._esp_request(f"{endpoints[action]}?{query}", timeout=12)
        except (RuntimeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}, 503
        message = body.decode("utf-8", errors="replace").strip()
        return {"ok": status == 200, "action": action, "message": message, "transport": "legacy_http"}, status

    def state_payload(self) -> Dict[str, Any]:
        snapshot = self.monitor.snapshot()
        topics = snapshot.get("topics", {})

        def value(name: str, default=None):
            item = topics.get(name)
            return item.get("json", default) if item else default

        availability_item = topics.get("availability")
        availability = value("availability", "unknown")
        status_names = (
            "fw", "link", "imu", "gnss", "route", "robot", "fault", "safety",
            "stm_imu", "stm_gnss", "auto", "heading", "command",
        )
        status = {name: value(f"status/{name}", {}) for name in status_names}
        status["mission"] = value("status/mission", {})
        status["mission_storage"] = value("status/mission/storage", {})
        status["mission_validation"] = value("status/mission/validation", {})
        gnss = status.get("gnss") if isinstance(status.get("gnss"), dict) else {}
        imu = status.get("imu") if isinstance(status.get("imu"), dict) else {}
        lat = self._finite_number(gnss.get("lat"))
        lon = self._finite_number(gnss.get("lon"))
        heading = self._finite_number(imu.get("compass_deg"))
        heading_source = "imu"
        if heading is None:
            heading = self._finite_number(gnss.get("course_deg"))
            heading_source = "gnss_course" if heading is not None else None
        fix_quality = self._finite_number(gnss.get("fix_quality"))
        gnss_age = (topics.get("status/gnss") or {}).get("age_sec")
        gnss_fresh = gnss_age is not None and gnss_age <= STATUS_STALE_SECONDS["status/gnss"] and not bool((topics.get("status/gnss") or {}).get("retain"))
        pose = {
            "valid": lat is not None and lon is not None and bool(gnss.get("alive")) and bool(fix_quality and fix_quality > 0) and gnss_fresh,
            "lat": lat,
            "lon": lon,
            "heading_deg": heading % 360 if heading is not None else None,
            "heading_source": heading_source,
            "fix_quality": int(fix_quality) if fix_quality is not None else None,
            "fix_name": gnss.get("fix_name"),
            "rtk_fixed": fix_quality == 4,
            "correction_age_s": self._finite_number(gnss.get("correction_age_s")),
            "hdop": self._finite_number(gnss.get("hdop")),
            "north_valid": bool(imu.get("north_valid")),
            "source": "mqtt_status",
        }
        motors = {str(index): value(f"status/motor/{index}", {}) for index in range(1, 4)}
        link_item = topics.get("status/link") or {}
        link_fresh = (
            link_item.get("age_sec") is not None
            and link_item["age_sec"] <= STATUS_STALE_SECONDS["status/link"]
            and not bool(link_item.get("retain"))
        )
        online = bool(snapshot.get("mqtt_connected")) and availability == "online" and link_fresh
        mower_ip = str(status.get("link", {}).get("ip") or "").strip()
        missing_topics = [name for name in REQUIRED_STATUS_TOPICS if name not in topics]
        stale_topics = [
            name for name in REQUIRED_STATUS_TOPICS
            if name in topics
            and name != "availability"
            and (
                topics[name].get("age_sec") is None
                or topics[name]["age_sec"] > STATUS_STALE_SECONDS.get(name, DEFAULT_STATUS_STALE_SECONDS)
                or bool(topics[name].get("retain"))
            )
        ]
        invalid_topics = self._invalid_status_topics(topics)
        stm_alive = bool(status.get("link", {}).get("stm_alive"))
        can_alive = bool(status.get("link", {}).get("can_alive"))
        contract_version = str(status.get("fw", {}).get("contract") or "").strip()
        contract_major = self._version_major(contract_version)
        contract_compatible = contract_major == CONTRACT_MAJOR
        raw_capabilities = status.get("fw", {}).get("capabilities")
        capabilities = [item for item in raw_capabilities if isinstance(item, str)] if isinstance(raw_capabilities, list) else []
        fw_item = topics.get("status/fw") or {}
        mission_fw_fresh = (
            fw_item.get("age_sec") is not None
            and fw_item["age_sec"] <= MISSION_FW_STALE_SECONDS
            and not bool(fw_item.get("retain"))
        )
        mission_contract_compatible = self._version_at_least(contract_version, MISSION_CONTRACT_MIN)
        mission_full_supported = mission_fw_fresh and mission_contract_compatible and MISSION_FULL_CAPABILITY in capabilities
        mission_preview_supported = mission_fw_fresh and mission_contract_compatible and MISSION_PREVIEW_CAPABILITY in capabilities
        mission_upload_supported = mission_full_supported or mission_preview_supported
        command_ack = status.get("command") if isinstance(status.get("command"), dict) else {}
        return {
            "ok": True,
            "online": online,
            "availability": availability,
            "availability_age_sec": availability_item.get("age_sec") if availability_item else None,
            "mqtt_connected": bool(snapshot.get("mqtt_connected")),
            "mqtt_error": snapshot.get("last_error", ""),
            "base_topic": self.base_topic,
            "remote_url": self.remote_url,
            "manual_control": {
                "transport": "websocket",
                "url": f"ws://{mower_ip}/ws" if mower_ip else "",
                "protocol": "homecontrol.mower.manual.v1",
                "deadman_timeout_ms": 700,
                "implemented_in_esp": True,
                "enabled": online and contract_compatible,
            },
            "integration": {
                "architecture": "hc_mqtt_ws__esp_uart__stm_can__vesc",
                "gateway": "esp32_remote",
                "realtime_controller": "stm32",
                "status_transport": "mqtt",
                "manual_transport": "websocket",
                "command_retain": False,
                "contract_expected": CONTRACT_VERSION,
                "contract_reported": contract_version or None,
                "contract_compatible": contract_compatible,
                "capabilities": capabilities,
                "controls_enabled": online and contract_compatible,
                "stop_enabled": online,
                "mission_supported": mission_full_supported,
                "mission_full_supported": mission_full_supported,
                "mission_preview_supported": mission_preview_supported,
                "mission_upload_supported": mission_upload_supported,
                "mission_mode": "full" if mission_full_supported else "preview" if mission_preview_supported else "unavailable",
                "mission_fw_fresh": mission_fw_fresh,
                "mission_fw_age_sec": fw_item.get("age_sec"),
                "mission_fw_stale_after_sec": MISSION_FW_STALE_SECONDS,
                "mission_controls_enabled": online and mission_full_supported,
                "mission_upload_enabled": online and mission_upload_supported,
                "healthy": online and contract_compatible and stm_alive and can_alive and not missing_topics and not stale_topics and not invalid_topics,
                "stm_alive": stm_alive,
                "can_alive": can_alive,
                "required_topics": list(REQUIRED_STATUS_TOPICS),
                "missing_topics": missing_topics,
                "stale_topics": stale_topics,
                "invalid_topics": invalid_topics,
                "stale_after_seconds": dict(STATUS_STALE_SECONDS),
            },
            "command_ack": {
                "request_id": command_ack.get("request_id"),
                "command": command_ack.get("command"),
                "accepted": command_ack.get("accepted"),
                "code": command_ack.get("code"),
                "message": command_ack.get("message"),
                "received_at": (topics.get("status/command") or {}).get("timestamp"),
            },
            "status": status,
            "rtk_pose": pose,
            "motors": motors,
            "topics": topics,
            "raw": snapshot.get("raw", [])[:30],
            "updated_at": time.time(),
        }

    def _control_allowed(self) -> Tuple[bool, str]:
        snapshot = self.monitor.snapshot()
        topics = snapshot.get("topics", {})
        availability = (topics.get("availability") or {}).get("json")
        link_item = topics.get("status/link") or {}
        online = (
            bool(snapshot.get("mqtt_connected"))
            and availability == "online"
            and link_item.get("age_sec") is not None
            and link_item["age_sec"] <= STATUS_STALE_SECONDS["status/link"]
            and not bool(link_item.get("retain"))
        )
        if not online:
            return False, "mower is offline or link status is stale"
        fw = (topics.get("status/fw") or {}).get("json") or {}
        reported = str(fw.get("contract") or "").strip() if isinstance(fw, dict) else ""
        if self._version_major(reported) != CONTRACT_MAJOR:
            return False, f"mower contract {reported or 'missing'} is incompatible; expected {CONTRACT_VERSION}"
        return True, ""

    @staticmethod
    def _version_major(version):
        try:
            return int(str(version).split(".", 1)[0])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _version_at_least(version, minimum):
        try:
            parts = tuple(int(part) for part in str(version).split(".")[:3])
            parts = parts + (0,) * (3 - len(parts))
            return parts >= minimum
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _invalid_status_topics(topics):
        invalid = []
        for topic, fields in STATUS_REQUIRED_FIELDS.items():
            item = topics.get(topic)
            if not item:
                continue
            payload = item.get("json")
            if not isinstance(payload, dict):
                invalid.append(topic)
                continue
            bad = False
            for field, expected in fields.items():
                field_value = payload.get(field)
                if expected is bool:
                    valid = type(field_value) is bool
                elif expected is int:
                    valid = type(field_value) is int
                else:
                    valid = isinstance(field_value, expected) and not isinstance(field_value, bool)
                if not valid:
                    bad = True
                    break
            if topic == "status/gnss" and payload.get("alive") and int(payload.get("fix_quality") or 0) > 0:
                bad = bad or not isinstance(payload.get("lat"), (int, float)) or not isinstance(payload.get("lon"), (int, float))
            if topic == "status/route" and isinstance(payload.get("points"), list):
                bad = bad or any(
                    not isinstance(point, dict)
                    or not isinstance(point.get("lat"), (int, float))
                    or not isinstance(point.get("lon"), (int, float))
                    for point in payload["points"]
                )
            if topic.startswith("status/motor/") and isinstance(payload.get("id"), int):
                bad = bad or payload["id"] != int(topic.rsplit("/", 1)[1])
            if bad:
                invalid.append(topic)
        return invalid

    @staticmethod
    def _finite_number(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number

    def command(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        command = str(data.get("command") or "").strip().lower()
        value = None
        if command in COMMANDS:
            suffix = COMMANDS[command]
        elif command == "auto_north":
            suffix = "heading/auto_north"
            value = data.get("value", "start")
            if value not in ("start", "stop"):
                return {"ok": False, "error": "auto_north value must be start or stop"}, 400
        elif command in ("heading_assist", "web_ui", "diagnostics"):
            suffix = {
                "heading_assist": "heading/assist",
                "web_ui": "web_ui",
                "diagnostics": "diagnostics",
            }[command]
            value = data.get("value")
            if not isinstance(value, bool):
                return {"ok": False, "error": f"{command} value must be boolean"}, 400
        elif command in VALUE_COMMANDS:
            suffix, minimum, maximum, integer_required = VALUE_COMMANDS[command]
            try:
                number = float(data.get("value"))
            except (TypeError, ValueError):
                return {"ok": False, "error": f"{command} requires a numeric value"}, 400
            if number < minimum or number > maximum or (command == "heading_target" and number >= maximum):
                comparator = f">= {minimum:g} and < {maximum:g}" if command == "heading_target" else f"between {minimum:g} and {maximum:g}"
                return {"ok": False, "error": f"{command} must be {comparator}"}, 400
            if integer_required and not number.is_integer():
                return {"ok": False, "error": f"{command} requires an integer value"}, 400
            value = int(number) if integer_required else number
        elif command == "goto_point":
            suffix = "navigation/goto"
            raw_value = data.get("value")
            if not isinstance(raw_value, dict):
                return {"ok": False, "error": "goto_point value must be an object"}, 400
            lat = self._finite_number(raw_value.get("lat"))
            lon = self._finite_number(raw_value.get("lon"))
            speed_mps = self._finite_number(raw_value.get("speed_mps", 0.2))
            if lat is None or not -90 <= lat <= 90 or lon is None or not -180 <= lon <= 180:
                return {"ok": False, "error": "goto_point requires valid WGS84 lat/lon"}, 400
            if speed_mps is None or not 0.05 <= speed_mps <= 0.5:
                return {"ok": False, "error": "goto_point speed_mps must be between 0.05 and 0.5"}, 400
            capabilities = (((self.monitor.snapshot().get("topics", {}).get("status/fw") or {}).get("json") or {}).get("capabilities") or [])
            if "positioning.v1" not in capabilities:
                return {"ok": False, "error": "Rover firmware does not advertise positioning.v1", "code": "CAPABILITY_UNAVAILABLE"}, 409
            value = {"lat": lat, "lon": lon, "speed_mps": speed_mps, "blade": False}
        else:
            return {"ok": False, "error": "unsupported mower command"}, 400

        allowed, reason = self._control_allowed()
        if not allowed and command != "stop":
            return {"ok": False, "error": reason, "code": "INCOMPATIBLE_VERSION"}, 409
        if not allowed and "offline" in reason:
            return {"ok": False, "error": reason, "code": "MOWER_OFFLINE"}, 503

        request_id = f"hc-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:12]}"
        payload = {"request_id": request_id, "value": value}
        topic = f"{self.base_topic}/cmd/{suffix}"
        ok, detail = self.publish_mqtt(topic, payload, qos=0, retain=False)
        if not ok:
            return {"ok": False, "error": detail or "MQTT publish failed", "topic": topic}, 503
        return {
            "ok": True,
            "command": command,
            "topic": topic,
            "payload": payload,
            "request_id": request_id,
            "ack": "pending",
            "context": {"read_after": ["/api/context/mower"]},
        }, 200
