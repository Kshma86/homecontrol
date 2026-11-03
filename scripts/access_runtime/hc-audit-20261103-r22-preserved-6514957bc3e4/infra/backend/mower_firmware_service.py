"""HC-only VG release preflight; no persistence, update session or rover transport."""
from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
import struct
import threading
from types import SimpleNamespace

import rover_qspi_image as qspi
from mower_v3_service import unique_object, reject_constant

ELF_LIMIT = 16 * 1024 * 1024
BODY_LIMIT = 4 + qspi.APP_BYTES + ELF_LIMIT
CATALOG_LIMIT = 65536
RELEASE_FIELDS = {"release_id", "firmware_id", "image_sha256", "elf_sha256", "profile_crc", "image_bytes", "layout", "slot"}


class FirmwareError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


class MemoryElf:
    """Path-like read-only adapter for the unchanged reference ELF auditor."""
    def __init__(self, data):
        self.data = data

    def stat(self):
        return SimpleNamespace(st_size=len(self.data))

    def open(self, mode):
        if mode != "rb":
            raise ValueError("Read-only ELF")
        return BytesIO(self.data)


def valid_token(value, length):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,%d}" % length, value) is not None


def bounded_elf(data):
    """Reject compressed/extended/excessive ELF tables before the reference parser."""
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise FirmwareError("ELF_INVALID", "32 bites little-endian ELF szükséges.")
    phoff, shoff = struct.unpack_from("<II", data, 28)
    ehsize, phsize, phcount, shsize, shcount, shstrings = struct.unpack_from("<6H", data, 40)
    if (ehsize != 52 or phsize != 32 or not 1 <= phcount <= 64 or shsize != 40
            or not 1 <= shcount <= 256 or not 0 < shstrings < shcount
            or phoff < 52 or phoff + phsize * phcount > len(data)
            or shoff < 52 or shoff + shsize * shcount > len(data)):
        raise FirmwareError("ELF_INVALID", "Az ELF táblái hibásak vagy túllépik az ellenőrzési korlátot.")
    sections = [struct.unpack_from("<10I", data, shoff + index * 40) for index in range(shcount)]
    names = sections[shstrings]
    if names[1] != 3 or names[4] > len(data) or names[5] > len(data) - names[4]:
        raise FirmwareError("ELF_INVALID", "Hibás ELF szakasznévtábla.")
    for section in sections:
        name = section[0]
        if name >= names[5] or data.find(b"\0", names[4] + name, names[4] + min(names[5], name + 129)) < 0:
            raise FirmwareError("ELF_INVALID", "Hibás vagy túl hosszú ELF szakasznév.")
        _, kind, flags, _, offset, size, link, _, _, entry = section
        if flags & 0x800 or kind != 8 and (offset > len(data) or size > len(data) - offset):
            raise FirmwareError("ELF_INVALID", "Tömörített vagy fájlon kívüli ELF szakasz nem engedélyezett.")
        if kind in (2, 11):
            if entry != 16 or size % 16 or size > 8192 * 16 or not 0 < link < shcount or sections[link][1] != 3:
                raise FirmwareError("ELF_INVALID", "Az ELF szimbólumtáblája hibás vagy túl nagy.")
            strings_offset, strings_size = sections[link][4:6]
            if strings_offset > len(data) or strings_size > len(data) - strings_offset:
                raise FirmwareError("ELF_INVALID", "Hibás ELF névtábla.")
            for position in range(offset, offset + size, 16):
                name = struct.unpack_from("<I", data, position)[0]
                if name >= strings_size or data.find(b"\0", strings_offset + name, strings_offset + min(strings_size, name + 257)) < 0:
                    raise FirmwareError("ELF_INVALID", "Hibás vagy túl hosszú ELF szimbólumnév.")


def validate_catalog(raw):
    try:
        data = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
        if type(data) is not dict or set(data) != {"format", "releases"} or data["format"] != "HC_FIRMWARE_RELEASES_V1":
            raise ValueError()
        rows = data["releases"]
        if type(rows) is not list or len(rows) > 64:
            raise ValueError()
        ids = set()
        for row in rows:
            if type(row) is not dict or set(row) != RELEASE_FIELDS:
                raise ValueError()
            if not valid_token(row["release_id"], 64) or row["release_id"] in ids or not valid_token(row["firmware_id"], 48):
                raise ValueError()
            ids.add(row["release_id"])
            for key in ("image_sha256", "elf_sha256"):
                if type(row[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", row[key]) is None:
                    raise ValueError()
            if type(row["profile_crc"]) is not str or re.fullmatch(r"[0-9A-F]{8}", row["profile_crc"]) is None or row["profile_crc"] == "00000000":
                raise ValueError()
            length = row["image_bytes"]
            if type(length) is not int or not 1280 <= length <= qspi.APP_BYTES or length % 32:
                raise ValueError()
            if row["layout"] != qspi.LAYOUT or row["slot"] != "APP":
                raise ValueError()
        return rows
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise FirmwareError("RELEASE_CATALOG_INVALID", "A szerveroldali kiadási lista hibás; nincs kiadásjóváhagyás.", 503) from None


class MowerFirmwareService:
    def __init__(self, catalog_path):
        self.catalog_path = Path(catalog_path)
        self.preflight_lock = threading.Lock()

    def catalog(self):
        try:
            with self.catalog_path.open("rb") as stream:
                raw = stream.read(CATALOG_LIMIT + 1)
            if len(raw) > CATALOG_LIMIT:
                raise FirmwareError("RELEASE_CATALOG_INVALID", "A szerveroldali kiadási lista túl nagy.", 503)
            return validate_catalog(raw)
        except OSError:
            raise FirmwareError("RELEASE_CATALOG_UNAVAILABLE", "A szerveroldali kiadási lista nem érhető el.", 503) from None

    def releases(self):
        return {"ok": True, "releases": self.catalog(), "upload_available": False,
                "scope": "HC_LOCAL_PREFLIGHT", "image_max_bytes": qspi.APP_BYTES, "elf_max_bytes": ELF_LIMIT}

    def preflight(self, body, release_id=None):
        if type(body) is not bytes or len(body) > BODY_LIMIT or len(body) < 4:
            raise FirmwareError("BAD_LENGTH", "A HC előellenőrzési csomag mérete hibás.")
        length = struct.unpack_from("<I", body)[0]
        if not 1280 <= length <= qspi.APP_BYTES or length % 32 or len(body) <= 4 + length or len(body) - 4 - length > ELF_LIMIT:
            raise FirmwareError("BAD_LENGTH", "1280–524288 bájtos, 32-re igazított RFU2 és legfeljebb 16 MiB ELF szükséges.")
        image, elf = body[4:4 + length], body[4 + length:]
        if not elf.startswith(b"\x7fELF"):
            raise FirmwareError("ELF_INVALID", "A második fájl nem ELF; bináris vagy JSON metadata nem helyettesíti.")
        if release_id is not None and not valid_token(release_id, 64):
            raise FirmwareError("INVALID_RELEASE", "Hibás kiadásazonosító.")
        releases = self.catalog()
        release = next((row for row in releases if row["release_id"] == release_id), None)
        if release_id is not None and release is None:
            raise FirmwareError("RELEASE_NOT_APPROVED", "A kiadás nincs a szerveroldali jóváhagyási listában.")
        bounded_elf(elf)
        elf_hash = hashlib.sha256(elf).hexdigest()
        if release and elf_hash != release["elf_sha256"]:
            raise FirmwareError("ELF_HASH_MISMATCH", "Az ELF hash nem egyezik a jóváhagyott kiadással.")
        try:
            metadata = qspi.check(image, release["image_sha256"], release["profile_crc"], release["firmware_id"]) if release else qspi.inspect(image)
            qspi.entry_descriptor(image)
            if metadata["profile_crc"] == "00000000":
                raise FirmwareError("PROFILE_MISMATCH", "A firmware profil-CRC nem lehet nulla.")
            if release and metadata["image_bytes"] != release["image_bytes"]:
                raise FirmwareError("BAD_LENGTH", "A képméret nem egyezik a jóváhagyott kiadással.")
            qspi.verify_elf(MemoryElf(elf), image)
        except (ValueError, IndexError, TypeError, KeyError, OverflowError) as error:
            prefix = str(error).split(":", 1)[0]
            code = prefix if prefix in {"BAD_LENGTH", "BAD_HEADER", "WRONG_TARGET", "WRONG_SLOT", "ABI_MISMATCH", "BAD_HASH", "PROFILE_MISMATCH"} else "ELF_INVALID"
            raise FirmwareError(code, "Az RFU2/RTE2 kép vagy az ELF nem felel meg a referenciaellenőrzésnek.") from None
        except (ImportError, OSError):
            raise FirmwareError("AUDITOR_UNAVAILABLE", "Az ELF ellenőrző nem érhető el; nincs igazolt eredmény.", 503) from None
        return {"ok": True, "scope": "HC_LOCAL_PREFLIGHT", "metadata": metadata,
                "elf_sha256": elf_hash, "elf_verified": True, "release_verified": release is not None,
                "release_id": release_id, "upload_available": False, "persisted": False,
                "hardware_qualified": False, "rover_contacted": False,
                "warning": "Ez nem telepítés, roverprofil-egyezés vagy hardveres minősítés."
                           if release else "A fájlpár szerkezetileg ellenőrzött, de nincs jóváhagyott kiadáshoz rendelve."}
