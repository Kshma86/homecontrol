import unittest
import uuid
import json
import zlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mower_service import MowerService


class Monitor:
    def snapshot(self):
        topics = {
            "status/robot": {"json": {"state": "ARMED", "armed": True, "estop": False, "fault_mask": 0, "auto": False, "link_alive": True}, "age_sec": 1},
            "status/fault": {"json": {"name": "NONE", "active": False, "mask": 0}, "age_sec": 1},
            "status/safety": {"json": {"bumper": False, "lift": False, "tilt": False, "imu_tilt": False, "wire_lost": False}, "age_sec": 1},
            "status/auto": {"json": {"active": False, "phase": "IDLE", "count": 0, "index": 0}, "age_sec": 1},
            "status/heading": {"json": {"north_valid": True, "current_deg": 271.5, "assist": False, "assist_active": False, "target_active": False}, "age_sec": 1},
            "status/motor/1": {"json": {"id": 1, "seen": True, "age_ms": 10, "rpm": 1200}, "age_sec": 1},
            "status/motor/2": {"json": {"id": 2, "seen": True, "age_ms": 10, "rpm": 1200}, "age_sec": 1},
            "status/motor/3": {"json": {"id": 3, "seen": True, "age_ms": 10, "rpm": 6000}, "age_sec": 1},
        }
        topics.update({
                "availability": {"json": "online", "age_sec": 2},
                "status/fw": {"json": {"esp": "test", "stm": "test", "contract": "2.0.0"}, "age_sec": 1},
                "status/link": {"json": {"wifi": True, "stm_alive": True, "can_alive": True, "stm_age_ms": 10, "can_age_ms": 10, "manual_ws_claimed": False, "ip": "192.168.1.50"}, "age_sec": 1},
                "status/gnss": {"json": {"alive": True, "fix_quality": 4, "fix_name": "RTK FIX", "lat": 47.1, "lon": 19.2, "sats": 20, "hdop": 0.7, "speed_kmh": 0.2, "course_deg": 42.0, "correction_age_s": 0.5, "age_ms": 10}, "age_sec": 1},
                "status/imu": {"json": {"alive": True, "compass_deg": 271.5, "north_valid": True, "auto_north_active": False, "auto_north_status": "IDLE", "age_ms": 10}, "age_sec": 1},
                "status/route": {
                    "json": {
                        "count": 1,
                        "max": 10,
                        "playing": False,
                        "points": [{"lat": 47.1, "lon": 19.2}],
                    },
                    "age_sec": 1,
                },
            })
        return {
            "mqtt_connected": True,
            "last_error": "",
            "topics": topics,
            "raw": [],
        }


class MowerServiceTest(unittest.TestCase):
    def setUp(self):
        self.published = []
        self.service = MowerService(
            monitor=Monitor(),
            publish_mqtt=lambda *args, **kwargs: self._publish(*args, **kwargs),
            base_topic="homecontrol/mower",
            remote_url="http://mower-remote.local/",
        )

    def _publish(self, *args, **kwargs):
        self.published.append((args, kwargs))
        return True, ""

    def test_state_maps_status_and_motor_topics(self):
        payload = self.service.state_payload()
        self.assertTrue(payload["online"])
        self.assertTrue(payload["status"]["link"]["stm_alive"])
        self.assertEqual(payload["motors"]["1"]["rpm"], 1200)
        self.assertTrue(payload["rtk_pose"]["valid"])
        self.assertTrue(payload["rtk_pose"]["rtk_fixed"])
        self.assertEqual(payload["rtk_pose"]["heading_deg"], 271.5)
        self.assertEqual(payload["rtk_pose"]["heading_source"], "imu")
        self.assertTrue(payload["integration"]["healthy"])
        self.assertEqual(payload["integration"]["missing_topics"], [])
        self.assertEqual(payload["integration"]["invalid_topics"], [])
        self.assertTrue(payload["manual_control"]["implemented_in_esp"])
        self.assertEqual(payload["manual_control"]["deadman_timeout_ms"], 700)
        self.assertTrue(payload["integration"]["contract_compatible"])
        self.assertEqual(payload["integration"]["contract_reported"], "2.0.0")
        self.assertFalse(payload["integration"]["mission_supported"])
        self.assertEqual(self.published, [])

    def test_context_read_never_publishes_telemetry(self):
        self.service.state_payload()
        self.service.state_payload()
        self.assertEqual(self.published, [])

    def test_integration_reports_missing_and_stale_topics(self):
        monitor = Monitor()
        snapshot = monitor.snapshot()
        del snapshot["topics"]["status/motor/3"]
        snapshot["topics"]["status/imu"]["age_sec"] = 3
        monitor.snapshot = lambda: snapshot
        service = MowerService(monitor=monitor, publish_mqtt=self.service.publish_mqtt, base_topic="homecontrol/mower", remote_url="http://mower-remote.local/")
        integration = service.state_payload()["integration"]
        self.assertFalse(integration["healthy"])
        self.assertIn("status/motor/3", integration["missing_topics"])
        self.assertIn("status/imu", integration["stale_topics"])

    def test_retained_status_is_never_fresh(self):
        monitor = Monitor()
        snapshot = monitor.snapshot()
        snapshot["topics"]["status/gnss"]["retain"] = True
        monitor.snapshot = lambda: snapshot
        service = MowerService(monitor=monitor, publish_mqtt=self.service.publish_mqtt, base_topic="homecontrol/mower", remote_url="http://mower-remote.local/")
        payload = service.state_payload()
        self.assertFalse(payload["rtk_pose"]["valid"])
        self.assertIn("status/gnss", payload["integration"]["stale_topics"])

    def test_invalid_required_field_is_reported(self):
        monitor = Monitor()
        snapshot = monitor.snapshot()
        snapshot["topics"]["status/link"]["json"]["can_alive"] = 1
        monitor.snapshot = lambda: snapshot
        service = MowerService(monitor=monitor, publish_mqtt=self.service.publish_mqtt, base_topic="homecontrol/mower", remote_url="http://mower-remote.local/")
        integration = service.state_payload()["integration"]
        self.assertFalse(integration["healthy"])
        self.assertIn("status/link", integration["invalid_topics"])

    def test_mission_requires_v24_and_capability(self):
        monitor = Monitor()
        snapshot = monitor.snapshot()
        snapshot["topics"]["status/fw"]["json"].update({"contract": "2.4.0", "capabilities": ["mission.v1"]})
        monitor.snapshot = lambda: snapshot
        service = MowerService(monitor=monitor, publish_mqtt=self.service.publish_mqtt, base_topic="homecontrol/mower", remote_url="http://mower-remote.local/")
        integration = service.state_payload()["integration"]
        self.assertTrue(integration["mission_supported"])
        self.assertTrue(integration["mission_controls_enabled"])

    def test_preview_capability_allows_upload_but_not_controls(self):
        monitor = Monitor()
        snapshot = monitor.snapshot()
        snapshot["topics"]["status/fw"]["json"].update({"contract": "2.4.0", "capabilities": ["mission.upload_preview.v1"]})
        monitor.snapshot = lambda: snapshot
        service = MowerService(monitor=monitor, publish_mqtt=self.service.publish_mqtt, base_topic="homecontrol/mower", remote_url="http://mower-remote.local/")
        integration = service.state_payload()["integration"]
        self.assertTrue(integration["mission_upload_enabled"])
        self.assertFalse(integration["mission_controls_enabled"])
        self.assertEqual(integration["mission_mode"], "preview")

    def test_mission_firmware_heartbeat_allows_normal_publish_interval(self):
        monitor = Monitor()
        snapshot = monitor.snapshot()
        snapshot["topics"]["status/fw"].update({"age_sec": 60, "retain": False})
        snapshot["topics"]["status/fw"]["json"].update({"contract": "2.4.0", "capabilities": ["mission.upload_preview.v1"]})
        monitor.snapshot = lambda: snapshot
        service = MowerService(monitor=monitor, publish_mqtt=self.service.publish_mqtt, base_topic="homecontrol/mower", remote_url="http://mower-remote.local/")
        integration = service.state_payload()["integration"]
        self.assertTrue(integration["mission_fw_fresh"])
        self.assertTrue(integration["mission_upload_enabled"])

    def _mission_deploy_service(self, capability):
        monitor = Monitor()
        snapshot = monitor.snapshot()
        snapshot["topics"]["status/fw"]["json"].update({"contract": "2.4.0", "capabilities": [capability]})
        monitor.snapshot = lambda: snapshot
        service = MowerService(monitor=monitor, publish_mqtt=self.service.publish_mqtt, base_topic="homecontrol/mower", remote_url="http://mower-remote.local/")
        service.compile_mission = lambda mission: (b"HCM1-test", {"mission_id": "550e8400-e29b-41d4-a716-446655440000", "revision": 7, "bytes": 9, "payload_crc32": "12345678", "file_crc32": "89ABCDEF", "operation_count": 4})
        return service

    def test_full_mission_deploy_carries_session_id_and_requires_stm_validation(self):
        service = self._mission_deploy_service("mission.v1")
        calls = []
        responses = [
            (200, json.dumps({"ok": True, "contract": "2.4.0", "capabilities": ["mission.v1"], "storage": {"max_alloc_heap": 1024}}).encode()),
            (200, json.dumps({"ok": True, "stage": "PREPARE", "session_id": "session-123"}).encode()),
            (200, json.dumps({"ok": True, "stage": "UPLOAD", "received_bytes": 9}).encode()),
            (200, json.dumps({"ok": True, "stage": "STM_VALIDATE", "stm_validated": True}).encode()),
            (200, json.dumps({"ok": True, "stage": "ACTIVATE", "state": "ACTIVE_IDLE"}).encode()),
        ]
        def request(path, **kwargs):
            calls.append((path, kwargs))
            return responses.pop(0)
        service._esp_request = request
        payload, status = service.mission_deploy({})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "full")
        self.assertIn("session_id=session-123", calls[2][0])
        self.assertIn("session_id=session-123", calls[3][0])
        self.assertIn("session_id=session-123", calls[4][0])
        self.assertEqual(calls[2][1]["headers"]["Content-Length"], "9")

    def test_preview_deploy_stops_before_activate(self):
        service = self._mission_deploy_service("mission.upload_preview.v1")
        calls = []
        responses = [
            (200, json.dumps({"ok": True, "contract": "2.4.0", "capabilities": ["mission.upload_preview.v1"]}).encode()),
            (200, json.dumps({"ok": True, "stage": "PREPARE", "session_id": "preview-123"}).encode()),
            (200, json.dumps({"ok": True, "stage": "UPLOAD", "received_bytes": 9}).encode()),
            (200, json.dumps({"ok": True, "stage": "ESP_VALIDATE", "preview_validated": True, "stm_validated": False}).encode()),
        ]
        def request(path, **kwargs):
            calls.append(path)
            return responses.pop(0)
        service._esp_request = request
        payload, status = service.mission_deploy({})
        self.assertEqual(status, 200)
        self.assertEqual(payload["mode"], "preview")
        self.assertFalse(any("/activate" in path for path in calls))

    def test_compile_hcm1_mission_uses_116_byte_header(self):
        mission = {
            "schema": "hc.mower.mission.v1", "mission_id": "550e8400-e29b-41d4-a716-446655440000", "revision": 7,
            "origin": {"lat_e7": 469894200, "lon_e7": 179729900},
            "geometry": {"drive_type": "differential_tank", "pivot_turn": True, "rover_width_mm": 550, "rover_length_mm": 700, "pivot_safety_radius_mm": 470, "cut_width_mm": 420, "antenna_forward_mm": 0, "antenna_left_mm": 0, "boundary_clearance_mm": 250},
            "limits": {"drive_speed_mm_s": 350, "connector_speed_mm_s": 200, "turn_speed_mdeg_s": 30000, "start_tolerance_mm": 250, "waypoint_tolerance_mm": 120, "max_cross_track_mm": 250, "max_heading_error_mdeg": 45000, "max_rtk_age_ms": 1500, "max_correction_age_ms": 3000},
            "boundary": [{"east_mm": 0, "north_mm": 0}, {"east_mm": 1000, "north_mm": 0}, {"east_mm": 0, "north_mm": 1000}],
            "exclusions": [],
            "operations": [{"type": "PATH_START", "east_mm": 100, "north_mm": 100, "tolerance_mm": 250}, {"type": "BLADE_ON", "target_rpm": 6000}, {"type": "BLADE_OFF"}, {"type": "STOP"}],
        }
        binary, metadata = self.service.compile_mission(mission)
        self.assertEqual(binary[:4], b"HCM1")
        self.assertEqual(int.from_bytes(binary[8:12], "little"), len(binary))
        self.assertEqual(len(binary), 116 + 3 * 8 + 4 * 24)
        self.assertEqual(metadata["operation_count"], 4)
        self.assertEqual(metadata["payload_crc32"], "5C182252")
        self.assertEqual(metadata["file_crc32"], "FF821923")
        self.assertEqual(int.from_bytes(binary[12:16], "little"), zlib.crc32(binary[116:]) & 0xFFFFFFFF)

    def test_compile_mission_requires_path_start_and_stop(self):
        mission = {
            "schema": "hc.mower.mission.v1", "mission_id": str(uuid.uuid4()), "revision": 1,
            "origin": {"lat_e7": 0, "lon_e7": 0},
            "geometry": {"drive_type": "differential_tank", "pivot_turn": True, "rover_width_mm": 550, "rover_length_mm": 700, "pivot_safety_radius_mm": 470, "cut_width_mm": 420, "antenna_forward_mm": 0, "antenna_left_mm": 0, "boundary_clearance_mm": 250},
            "limits": {"drive_speed_mm_s": 350, "connector_speed_mm_s": 200, "turn_speed_mdeg_s": 30000, "start_tolerance_mm": 250, "waypoint_tolerance_mm": 120, "max_cross_track_mm": 250, "max_heading_error_mdeg": 45000, "max_rtk_age_ms": 1500, "max_correction_age_ms": 3000},
            "boundary": [{"east_mm": 0, "north_mm": 0}, {"east_mm": 1000, "north_mm": 0}, {"east_mm": 0, "north_mm": 1000}], "exclusions": [],
            "operations": [{"type": "BLADE_OFF"}, {"type": "BLADE_ON", "target_rpm": 6000}, {"type": "BLADE_OFF"}, {"type": "STOP"}],
        }
        with self.assertRaisesRegex(ValueError, "PATH_START"):
            self.service.compile_mission(mission)

    def test_pose_falls_back_to_gnss_course(self):
        monitor = Monitor()
        snapshot = monitor.snapshot()
        snapshot["topics"]["status/imu"] = {"json": {}, "age_sec": 1}
        snapshot["topics"]["status/gnss"]["json"]["course_deg"] = 42
        monitor.snapshot = lambda: snapshot
        service = MowerService(monitor=monitor, publish_mqtt=self.service.publish_mqtt, base_topic="homecontrol/mower", remote_url="http://mower-remote.local/")
        self.assertEqual(service.state_payload()["rtk_pose"]["heading_source"], "gnss_course")

    def test_stop_is_non_retained(self):
        payload, status = self.service.command({"command": "stop"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.published[0][0][0], "homecontrol/mower/cmd/stop")
        self.assertFalse(self.published[0][1]["retain"])
        self.assertIsNone(self.published[0][0][1]["value"])
        self.assertEqual(self.published[0][0][1]["request_id"], payload["request_id"])

    def test_web_ui_boolean_is_non_retained(self):
        payload, status = self.service.command({"command": "web_ui", "value": False})
        self.assertEqual(status, 200)
        self.assertIs(payload["payload"]["value"], False)
        self.assertEqual(self.published[0][0][0], "homecontrol/mower/cmd/web_ui")
        self.assertFalse(self.published[0][1]["retain"])

    def test_diagnostics_boolean_is_lowercase_and_non_retained(self):
        payload, status = self.service.command({"command": "diagnostics", "value": True})
        self.assertEqual(status, 200)
        self.assertIs(payload["payload"]["value"], True)
        self.assertEqual(self.published[0][0][0], "homecontrol/mower/cmd/diagnostics")
        self.assertFalse(self.published[0][1]["retain"])

    def test_auto_north_uses_start_value_and_is_non_retained(self):
        payload, status = self.service.command({"command": "auto_north"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["payload"]["value"], "start")
        self.assertEqual(self.published[0][0][0], "homecontrol/mower/cmd/heading/auto_north")
        self.assertFalse(self.published[0][1]["retain"])

    def test_rejects_out_of_range_blade_rpm(self):
        payload, status = self.service.command({"command": "blade_rpm", "value": 30000})
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(self.published, [])

    def test_rejects_fractional_blade_rpm(self):
        payload, status = self.service.command({"command": "blade_rpm", "value": 6000.5})
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_rejects_heading_target_360(self):
        payload, status = self.service.command({"command": "heading_target", "value": 360})
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_incompatible_contract_blocks_arm_but_allows_stop(self):
        monitor = Monitor()
        snapshot = monitor.snapshot()
        snapshot["topics"]["status/fw"]["json"]["contract"] = "1.9.0"
        monitor.snapshot = lambda: snapshot
        service = MowerService(monitor=monitor, publish_mqtt=self.service.publish_mqtt, base_topic="homecontrol/mower", remote_url="http://mower-remote.local/")
        rejected, rejected_status = service.command({"command": "arm"})
        self.assertEqual(rejected_status, 409)
        self.assertEqual(rejected["code"], "INCOMPATIBLE_VERSION")
        stopped, stopped_status = service.command({"command": "stop"})
        self.assertEqual(stopped_status, 200)
        self.assertTrue(stopped["ok"])

    def test_offline_blocks_even_stop(self):
        monitor = Monitor()
        snapshot = monitor.snapshot()
        snapshot["topics"]["availability"]["json"] = "offline"
        monitor.snapshot = lambda: snapshot
        service = MowerService(monitor=monitor, publish_mqtt=self.service.publish_mqtt, base_topic="homecontrol/mower", remote_url="http://mower-remote.local/")
        payload, status = service.command({"command": "stop"})
        self.assertEqual(status, 503)
        self.assertEqual(payload["code"], "MOWER_OFFLINE")

    def test_rejects_non_bin_firmware(self):
        payload, status = self.service.firmware_upload("notes.txt", b"firmware")
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_rejects_oversized_firmware(self):
        payload, status = self.service.firmware_upload("mower.bin", b"x" * (2 * 1024 * 1024 + 1))
        self.assertEqual(status, 413)
        self.assertFalse(payload["ok"])

    def test_rejects_unknown_route_action(self):
        payload, status = self.service.route_action("teleport")
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_route_status_comes_from_mqtt(self):
        payload, status = self.service.route_status()
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["transport"], "mqtt")
        self.assertEqual(payload["points"][0]["lat"], 47.1)

    def test_route_record_is_non_retained_mqtt(self):
        payload, status = self.service.route_action("record")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(self.published[0][0][0], "homecontrol/mower/cmd/route/record")
        self.assertFalse(self.published[0][1]["retain"])


if __name__ == "__main__":
    unittest.main()
