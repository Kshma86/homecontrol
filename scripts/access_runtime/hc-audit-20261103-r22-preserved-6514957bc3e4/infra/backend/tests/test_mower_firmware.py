import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mower_firmware_service import BODY_LIMIT, ELF_LIMIT, FirmwareError, MowerFirmwareService, validate_catalog
from tests.mower_firmware_fixture import artifacts, envelope


class MowerFirmwareTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hc-firmware-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "approved.json"
        self.image, self.elf, self.release = artifacts()
        self.catalog([])
        self.service = MowerFirmwareService(self.path)

    def catalog(self, rows):
        self.path.write_text(json.dumps({"format": "HC_FIRMWARE_RELEASES_V1", "releases": rows}))

    def reject(self, image=None, elf=None, release=None):
        with self.assertRaises(FirmwareError):
            self.service.preflight(envelope(self.image if image is None else image, self.elf if elf is None else elf), release)

    def test_real_elf_reference_verification_without_release_never_grants_upload(self):
        result = self.service.preflight(envelope(self.image, self.elf))
        self.assertTrue(result["elf_verified"])
        self.assertFalse(result["release_verified"])
        self.assertEqual(result["metadata"]["image_sha256"], hashlib.sha256(self.image).hexdigest())
        for field in ("upload_available", "persisted", "hardware_qualified", "rover_contacted"):
            self.assertFalse(result[field])

    def test_selected_server_reviewed_release_requires_both_hashes_and_embedded_metadata(self):
        self.catalog([self.release])
        result = self.service.preflight(envelope(self.image, self.elf), self.release["release_id"])
        self.assertTrue(result["release_verified"])
        self.assertFalse(result["upload_available"])
        for key, value in (("image_sha256", "0"*64), ("elf_sha256", "0"*64), ("firmware_id", "other"), ("profile_crc", "11223344"), ("image_bytes", 1568)):
            with self.subTest(key=key):
                self.catalog([self.release | {key: value}]); self.reject(release=self.release["release_id"])

    def test_caller_cannot_approve_unknown_release_or_send_metadata_instead_of_elf(self):
        self.reject(release="not-approved")
        self.reject(release="../bad")
        self.reject(elf=json.dumps(self.release).encode())

    def test_catalog_fail_closed_for_missing_file_duplicate_keys_and_invalid_shape(self):
        for raw in ("[]", '{"format":"x","format":"HC_FIRMWARE_RELEASES_V1","releases":[]}', '{"format":"HC_FIRMWARE_RELEASES_V1","releases":NaN}', '{"format":"HC_FIRMWARE_RELEASES_V1","releases":[],"approved":true}'):
            with self.subTest(raw=raw), self.assertRaises(FirmwareError): validate_catalog(raw)
        self.service.catalog_path = Path(self.temp.name) / "private-missing"
        with self.assertRaises(FirmwareError) as caught: self.service.releases()
        self.assertNotIn("private-missing", str(caught.exception))

    def test_catalog_rejects_noncanonical_or_invented_release_fields(self):
        for change in ({"image_bytes": True}, {"layout": "H743_1M_QSPI2"}, {"slot": "A"}, {"profile_crc": "00000000"}, {"image_sha256": "A"*64}, {"commissioned": True}):
            with self.subTest(change=change), self.assertRaises(FirmwareError):
                validate_catalog(json.dumps({"format":"HC_FIRMWARE_RELEASES_V1","releases":[self.release | change]}))
        with self.assertRaises(FirmwareError): validate_catalog(json.dumps({"format":"HC_FIRMWARE_RELEASES_V1","releases":[self.release,self.release]}))

    def test_reference_header_reserved_vector_and_trial_entry_gates(self):
        for offset in (0, 4, 768, 772, 774, 776, 780, 784, 788, 792, 796, 1024, 1028, 1030, 1032, 1048, 1052, 1056, 1060, 1064, 1066, 1068, 1070, 1124, 1279):
            wrong = bytearray(self.image); wrong[offset] ^= 1
            with self.subTest(offset=offset): self.reject(image=bytes(wrong))
        wrong = bytearray(self.image); struct.pack_into("<I", wrong, 1072, 0)
        self.reject(image=bytes(wrong))

    def test_no_padding_relocation_rfu1_or_installer_cross_acceptance(self):
        self.reject(image=self.image[:-1])
        self.reject(image=self.image+b"\xff"*32)
        for magic in (b"RFU1", b"RFI2"):
            wrong = bytearray(self.image); wrong[1024:1028] = magic; self.reject(image=bytes(wrong))

    def test_actual_elf_bin_ff_padding_ram_proof_and_irq_order_are_checked(self):
        # Valid header but altered executable bytes cannot bypass ELF equality.
        for offset in (1280, 1304, 1320, 1364, 1414, 1420, 1440, 1535):
            wrong = bytearray(self.image); wrong[offset] ^= 1
            with self.subTest(image_offset=offset): self.reject(image=bytes(wrong))
        # Also mutate ELF and image identically: startup proof must still reject.
        for offset in (1304, 1320, 1364, 1414, 1420, 1440):
            wrong_image, wrong_elf = bytearray(self.image), bytearray(self.elf)
            wrong_image[offset] ^= 1; wrong_elf[180 + offset] ^= 1
            with self.subTest(proof_offset=offset): self.reject(image=bytes(wrong_image), elf=bytes(wrong_elf))

    def test_bounded_elf_rejects_truncated_extended_compressed_and_excessive_tables(self):
        self.reject(elf=b"\x7fELF")
        for offset, format_, value in ((4,"B",2),(5,"B",2),(28,"I",0xFFFFFFF0),(32,"I",0xFFFFFFF0),(44,"H",65),(48,"H",0),(48,"H",257)):
            wrong = bytearray(self.elf); struct.pack_into("<"+format_, wrong, offset, value)
            with self.subTest(offset=offset, value=value): self.reject(elf=bytes(wrong))
        wrong = bytearray(self.elf); shoff = struct.unpack_from("<I", wrong, 32)[0]
        struct.pack_into("<I", wrong, shoff + 40 + 8, 0x802)
        self.reject(elf=bytes(wrong))
        self.reject(elf=b"\x7fELF" + bytes(ELF_LIMIT))

    def test_body_length_missing_elf_and_reference_failure_sanitize(self):
        for body in (b"", bytes(4), struct.pack("<I",1536)+self.image, bytes(BODY_LIMIT+1)):
            with self.assertRaises(FirmwareError): self.service.preflight(body)
        with patch("mower_firmware_service.qspi.verify_elf", side_effect=ValueError("private-path-and-data")):
            with self.assertRaises(FirmwareError) as caught: self.service.preflight(envelope(self.image,self.elf))
            self.assertNotIn("private", str(caught.exception))

    def test_vendored_reference_sources_still_match_handoff_manifest(self):
        root = Path(__file__).resolve().parents[3]
        with zipfile.ZipFile(root / "hc-v31-qspi-handoff-20261009-rcp1-foundation.zip") as archive:
            manifest = {row["path"]: row for row in json.loads(archive.read("MANIFEST.json"))["files"]}
            for name in ("rover_qspi_image.py", "rover_image.py", "rover_profile.py", "rover_ram_audit.py"):
                raw = Path(__file__).resolve().parents[1].joinpath(name).read_bytes()
                self.assertEqual(raw, archive.read("tools/" + name))
                self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest["tools/"+name]["sha256"])


if __name__ == "__main__": unittest.main()
