import copy
from datetime import datetime, timezone
import hashlib
import json
import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rover_parameters as rcp1
from mower_parameters_service import DraftError, MowerParametersService, parse_json, template, validate_draft


def fixture():
    # Exact handoff Python/C fixture. Synthetic TEST data, never robot defaults.
    return dict(parameters_version=1, robot_id="test_only", blade_enabled=False,
                wheel_track_mm=500, body_radius_mm=300, wheel_circumference_mm=[1000, 1100],
                wheel_motor_pole_pairs=[7, 9], wheel_gear_ratio_milli=[1000, 2000], wheel_direction=[1, -1],
                blade_direction=1, blade_pole_pairs=7, max_slope_mdeg=0, blade_erpm_limit=21000,
                blade_rpm_limit=3000, antenna_body_mm=[-1, 2, -3], imu_mount_q_ppm=[1000000, 0, 0, 0],
                wheel_erpm_limit=[5000, 6000], wheel_brake_ma=[900, 1000], stop_deceleration_mm_s2=250,
                stop_test_max_ms=2000, max_linear_mm_s=200, max_yaw_mdeg_s=15000, accel_mm_s2=100,
                gnss_hacc_limit_mm=50, heading_accuracy_limit_mdeg=5000, tilt_limit_mdeg=20000,
                yaw_accel_mdeg_s2=30000)


class MemoryStore:
    def __init__(self):
        self.rows = []

    def latest(self, key):
        rows = self.history(key)
        return rows[0] if rows else None

    def history(self, key):
        return [copy.deepcopy(row) for row in reversed(self.rows) if row["rover_key"] == key][:20]

    def revision(self, key, revision):
        return next((row for row in self.history(key) if row["revision"] == revision), None)

    def request(self, key, id_):
        return next((copy.deepcopy(row) for row in self.rows if row["rover_key"] == key and row["request_id"] == id_), None)

    def list_latest(self):
        return [self.latest(key) for key in sorted({row["rover_key"] for row in self.rows})]

    def save(self, key, id_, expected, parameters, sha):
        previous = self.request(key, id_)
        if previous:
            if (previous["expected_revision"], previous["parameters"]) != (expected, parameters):
                raise DraftError("ID_CONFLICT", "Conflict", 409)
            return previous, True
        latest = self.latest(key)
        current = latest["revision"] if latest else 0
        if expected != current:
            raise DraftError("REVISION_CONFLICT", "Conflict", 409, current_revision=current)
        row = dict(rover_key=key, revision=current + 1, expected_revision=current, request_id=id_,
                   parameters=copy.deepcopy(parameters), draft_sha256=sha, saved_at=datetime(2026, 10, 9, tzinfo=timezone.utc))
        self.rows.append(row)
        return copy.deepcopy(row), False


class MowerParametersTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.service = MowerParametersService(self.store)

    def save(self, parameters=None, id_="save-1", expected=0, key="hc-test"):
        return self.service.save(key, {"request_id": id_, "expected_revision": expected,
                                      "parameters": template() if parameters is None else parameters})

    def test_legacy_schema_has_exact_27_fields(self):
        result = self.service.schema()
        self.assertEqual(len(result["schema"]["properties"]), 27)
        self.assertEqual(set(result["template"]), rcp1.FIELDS)
        self.assertFalse(result["schema"]["additionalProperties"])
        frontend_fixture = Path(__file__).resolve().parents[2] / "frontend/tests/fixtures/mower-parameters-schema.json"
        self.assertEqual(json.loads(frontend_fixture.read_text()), result["schema"])

    def test_template_has_no_operational_defaults_and_can_save_incomplete(self):
        parameters = template()
        self.assertEqual(parameters["parameters_version"], 1)
        self.assertTrue(all(value is None for key, value in parameters.items() if key != "parameters_version"))
        report = validate_draft(parameters)
        self.assertTrue(report["saveable"])
        self.assertFalse(report["valid"])
        self.assertIsNone(report["rcp1_crc32"])
        saved = self.save()
        self.assertEqual(saved["draft_revision"], 1)
        self.assertEqual(self.service.latest("hc-test")["parameters"], parameters)
        self.assertFalse(saved["apply_available"])
        self.assertIsNone(saved["active_configuration"])
        self.assertFalse(saved["validation"]["hardware_qualified"])
        self.assertFalse(saved["validation"]["applied_to_rover"])

    def test_complete_matches_reference_crc_and_roundtrip_not_commissioning(self):
        parameters = fixture()
        saved = self.save(parameters)
        self.assertTrue(saved["validation"]["valid"])
        self.assertEqual(saved["validation"]["rcp1_crc32"], f"{rcp1.checksum(parameters):08X}")
        encoded = self.service.export("hc-test", 1, binary=True)
        self.assertEqual(encoded, rcp1.encode(parameters))
        self.assertEqual(len(encoded), 256)
        self.assertEqual(self.service.import_data(encoded, binary=True)["parameters"], parameters)
        self.assertEqual(json.loads(self.service.export("hc-test", 1)), parameters)
        self.assertFalse(saved["validation"]["hardware_qualified"])

    def test_missing_fields_and_hardware_or_commissioning_fields_are_forbidden(self):
        for field in ("commissioned", "installed", "profile_crc", "uid", "gpio", "safety_inputs", "vesc_firmware"):
            with self.subTest(field=field), self.assertRaises(DraftError):
                self.service.validate(fixture() | {field: True})
        with self.assertRaises(DraftError):
            self.service.validate({"robot_id": "test_only"})

    def test_all_scalar_and_array_ranges_bool_and_float_are_strict(self):
        for name, (_, _, low, high) in rcp1.SCALARS.items():
            for value in (low - 1, high + 1, True, float(low), float("inf")):
                report = validate_draft(fixture() | {name: value})
                with self.subTest(name=name, value=value):
                    self.assertFalse(report["saveable"])
                    self.assertIsNone(report["draft_sha256"])
        for name, (_, _, count, low, high) in rcp1.ARRAYS.items():
            for value in (low - 1, high + 1, False, float(low)):
                parameters = fixture()
                parameters[name][0] = value
                with self.subTest(name=name, value=value):
                    self.assertFalse(validate_draft(parameters)["saveable"])
            self.assertFalse(validate_draft(fixture() | {name: [0] * (count - 1)})["saveable"])

    def test_null_array_items_are_incomplete_not_defaults(self):
        parameters = template() | {"wheel_direction": [None, -1], "imu_mount_q_ppm": [None, 0, 0, 0]}
        report = validate_draft(parameters)
        self.assertTrue(report["saveable"])
        self.assertFalse(report["valid"])
        self.assertIn("wheel_direction[0]", report["missing"])

    def test_cross_checks_apply_even_with_other_missing_fields(self):
        for update in ({"blade_direction": 0}, {"wheel_direction": [0, 1]}, {"imu_mount_q_ppm": [0, 0, 0, 0]},
                       {"blade_rpm_limit": 3001, "blade_pole_pairs": 7, "blade_erpm_limit": 21000}):
            parameters = template() | update
            self.assertFalse(validate_draft(parameters)["saveable"])
        self.assertTrue(validate_draft(fixture() | {"imu_mount_q_ppm": [-1000000, 0, 0, 0]})["valid"])

    def test_identity_and_boolean_types_never_coerce(self):
        for updates in ({"robot_id": "á"}, {"robot_id": "a" * 33}, {"robot_id": "a.b"}, {"robot_id": 3},
                        {"blade_enabled": 1}, {"parameters_version": True}, {"parameters_version": None}):
            self.assertFalse(validate_draft(fixture() | updates)["saveable"])

    def test_strict_json_rejects_duplicate_nonfinite_oversize_and_deep_nesting(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', "x" * 16385, b"\xff", "[" * 1200 + "]" * 1200):
            with self.subTest(raw=raw[:30]), self.assertRaises(DraftError):
                parse_json(raw)
        # Finite JSON exponent overflows Python float; report invalid, never 500/hash.
        raw = json.dumps(fixture()).replace('"wheel_track_mm": 500', '"wheel_track_mm": 1e999')
        self.assertFalse(validate_draft(parse_json(raw))["saveable"])

    def test_request_and_revision_types_reject_before_storage(self):
        for update in ({"request_id": "a/b"}, {"expected_revision": True}, {"expected_revision": -1}, {"expected_revision": 0.0}, {"extra": True}):
            with self.assertRaises(DraftError):
                self.service.save("hc-test", {"request_id": "save-1", "expected_revision": 0, "parameters": template()} | update)
        self.assertEqual(self.store.rows, [])

    def test_replay_after_service_restart_is_durable_and_not_new_revision(self):
        result = self.save(fixture())
        self.service = MowerParametersService(self.store)
        repeated = self.save(fixture())
        self.assertEqual(repeated["draft_revision"], result["draft_revision"])
        self.assertTrue(repeated["replayed"])
        self.assertEqual(len(self.store.rows), 1)
        self.assertEqual(self.service.request_status("hc-test", "save-1")["draft_revision"], 1)

    def test_cas_conflict_and_id_conflict_preserve_old_revisions(self):
        self.save(fixture())
        with self.assertRaises(DraftError) as error:
            self.save(template(), "save-2", 0)
        self.assertEqual(error.exception.code, "REVISION_CONFLICT")
        with self.assertRaises(DraftError) as error:
            self.save(template(), "save-1", 0)
        self.assertEqual(error.exception.code, "ID_CONFLICT")
        self.save(template(), "save-2", 1)
        self.assertEqual([row["draft_revision"] for row in self.service.history("hc-test")["revisions"]], [2, 1])
        self.assertEqual(self.service.revision("hc-test", 1)["parameters"], fixture())

    def test_rover_keys_are_separate_from_parameter_robot_id_and_no_path_tricks(self):
        self.save(fixture(), key="hc-rover-A")
        self.save(template(), key="hc-rover-B")
        self.assertEqual(self.service.latest("hc-rover-A")["parameters"]["robot_id"], "test_only")
        self.assertEqual(self.service.latest("hc-rover-B")["draft_revision"], 1)
        for key in ("", "../rover", "x/y", "á", "a" * 33):
            with self.assertRaises(DraftError):
                self.service.latest(key)

    def test_unknown_request_and_revision_do_not_invent_success(self):
        self.assertEqual(self.service.latest("hc-empty")["draft_revision"], 0)
        for call in (lambda: self.service.request_status("hc-empty", "unknown"), lambda: self.service.revision("hc-empty", 1)):
            with self.assertRaises(DraftError) as error:
                call()
            self.assertEqual(error.exception.status, 404)

    def test_incomplete_json_export_allowed_but_binary_export_blocked(self):
        self.save()
        self.assertEqual(json.loads(self.service.export("hc-test", 1)), template())
        with self.assertRaises(DraftError) as error:
            self.service.export("hc-test", 1, binary=True)
        self.assertEqual(error.exception.code, "DRAFT_INCOMPLETE")

    def test_import_never_saves_and_crc_or_reserved_bytes_cannot_slip_through(self):
        original = rcp1.encode(fixture())
        self.assertTrue(self.service.import_data(original, True)["validation"]["valid"])
        self.assertEqual(self.store.rows, [])
        for index in range(256):
            data = bytearray(original); data[index] ^= 1
            with self.subTest(index=index), self.assertRaises(DraftError):
                self.service.import_data(bytes(data), True)
        for index in (9, 10, 11, 22, 44, 45, 46, 47, 71, *range(152, 252)):
            data = bytearray(original); data[index] = 1
            struct.pack_into("<I", data, 252, zlib.crc32(data[:252]) & 0xffffffff)
            with self.subTest(reserved=index), self.assertRaises(DraftError):
                self.service.import_data(bytes(data), True)
        self.assertEqual(self.store.rows, [])


if __name__ == "__main__":
    unittest.main()
