#!/usr/bin/env python3
"""Package/check the separate single-APP RFU2 format. No flash/device operations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

from rover_image import RAM

LAYOUT = "H743_1M_QSPI_REC2"
TARGET = "STM32H743VG"
APP_BASE = 0x08100000
APP_BYTES = 524288
NOR_BYTES = 8388608


def layout():
    return {
        "layout": LAYOUT, "layout_id": 2, "service_abi": 2, "target": TARGET,
        "implementation": "transactional_core_and_native_ports", "conformant": False, "stm_remote_update": False,
        "internal_flash_bytes": 1048576, "qspi_bytes": NOR_BYTES,
        "internal": [
            {"name": "loader", "base": "08000000", "bytes": 491520, "remote_write": False},
            {"name": "factory", "base": "08078000", "bytes": 32768, "remote_write": False},
            {"name": "app", "base": "08100000", "bytes": APP_BYTES, "remote_write": False},
        ],
        "qspi": [
            {"name": "journal_0", "offset": "00000000", "bytes": 131072},
            {"name": "journal_1", "offset": "00020000", "bytes": 131072},
            *({"name": f"store_{index + 1}", "offset": f"{0x40000 + index * 0x100000:08X}",
               "bytes": 1048576, "max_image_bytes": APP_BYTES} for index in range(4)),
            {"name": "reserved", "offset": "00440000", "bytes": 3932160},
        ],
    }


def inspect(data):
    if not 1280 <= len(data) <= APP_BYTES or len(data) % 32:
        raise ValueError("BAD_LENGTH: padded RFU2 length must be 1280..524288 and a multiple of 32")
    header = data[1024:1280]
    u16 = lambda offset: struct.unpack_from("<H", header, offset)[0]
    u32 = lambda offset: struct.unpack_from("<I", header, offset)[0]
    if header[:4] != b"RFU2" or (u16(4), u16(6), u32(24), u16(46)) != (256, 2, 2, 0) or any(header[100:]):
        raise ValueError("BAD_HEADER: distinct RFU2 format/layout/reserved fields required")
    if header[8:24] != TARGET.encode("ascii").ljust(16, b"\0"):
        raise ValueError("WRONG_TARGET: STM32H743VG required")
    if (u32(28), u32(32)) != (1, APP_BASE):
        raise ValueError("WRONG_SLOT: one internal APP at 0x08100000; never relocate an A/B image")
    if u32(36) != len(data):
        raise ValueError("BAD_LENGTH: header and body disagree")
    if (u16(40), u16(42), u16(44)) != (3, 1, 2):
        raise ValueError("ABI_MISMATCH: operational 3.1 and proposed service ABI 2 required")
    raw_fw = header[52:100]
    terminator = raw_fw.find(b"\0")
    if terminator >= 0:
        if any(raw_fw[terminator:]):
            raise ValueError("BAD_HEADER: noncanonical firmware padding")
        raw_fw = raw_fw[:terminator]
    if not re.fullmatch(rb"[A-Za-z0-9_.-]{1,48}", raw_fw):
        raise ValueError("BAD_HEADER: invalid firmware ID")
    stack, reset = struct.unpack_from("<II", data)
    if stack % 8 or not any(low < stack <= high for low, high in RAM):
        raise ValueError("BAD_HEADER: invalid MSP")
    if not reset & 1 or not APP_BASE <= (reset & ~1) < APP_BASE + len(data):
        raise ValueError("BAD_HEADER: reset vector outside internal image")
    return {
        "layout": LAYOUT, "layout_id": 2, "target": TARGET, "slot": "APP", "link_address": f"{APP_BASE:08X}",
        "service_abi": 2, "image_bytes": len(data), "profile_crc": f"{u32(48):08X}",
        "fw_id": raw_fw.decode("ascii"), "image_sha256": hashlib.sha256(data).hexdigest(),
        "conformant": False, "stm_remote_update": False,
    }


def check(data, expected_hash, expected_profile, expected_firmware):
    metadata = inspect(data)
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or metadata["image_sha256"] != expected_hash:
        raise ValueError("BAD_HASH: exact lowercase external SHA-256 required")
    if not isinstance(expected_profile, str) or not re.fullmatch(r"[0-9A-F]{8}", expected_profile) or metadata["profile_crc"] != expected_profile:
        raise ValueError("PROFILE_MISMATCH: exact installed profile CRC required")
    if metadata["fw_id"] != expected_firmware:
        raise ValueError("BAD_HEADER: firmware ID disagreement")
    entry_descriptor(data)
    return metadata


def entry_descriptor(data):
    descriptor = data[768:800]
    if len(descriptor) != 32:
        raise ValueError("BAD_HEADER: missing RTE2 entry")
    magic, version, size, layout_id, base, reset, probe, runtime, token = struct.unpack("<4sHH6I", descriptor)
    if (magic, version, size, layout_id, base, reset, token) != (
            b"RTE2", 1, 32, 2, APP_BASE, struct.unpack_from("<I", data, 4)[0], 0x52544532):
        raise ValueError("BAD_HEADER: distinct RTE2 locked-entry ABI required")
    for index, code in enumerate((reset, probe, runtime)):
        if not code & 1 or not (APP_BASE + 1280 <= (code & ~1) < APP_BASE + len(data) or
                               index == 2 and 0x24000000 <= (code & ~1) < 0x2407C000):
            raise ValueError("BAD_HEADER: RTE2 entry address outside linked code")
    return reset, probe, runtime


def package(data, firmware_id):
    if not 1280 <= len(data) <= APP_BYTES:
        raise ValueError("BAD_LENGTH: bounded already APP-linked RFU2 input required")
    expected = struct.unpack_from("<I", data, 1060)[0]
    if expected != (len(data) + 31) // 32 * 32:
        raise ValueError("BAD_LENGTH: linker must declare exact padded size; header is never patched")
    padded = bytes(data).ljust(expected, b"\xff")
    metadata = inspect(padded)
    if metadata["fw_id"] != firmware_id:
        raise ValueError("BAD_HEADER: package/header firmware ID disagreement")
    entry_descriptor(padded)
    return padded, metadata


def verify_elf(path, data):
    from elftools.common.exceptions import ELFError
    try:
        _verify_elf(path, data)
    except (ELFError, struct.error) as error:
        raise ValueError("BAD_HEADER: malformed ELF") from error


def _verify_elf(path, data):
    from elftools.elf.elffile import ELFFile
    from rover_ram_audit import audit_ram_init
    inspect(data)
    reset, probe, runtime = entry_descriptor(data)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("BAD_LENGTH: ELF input exceeds audit budget")
    end = APP_BASE + len(data)
    reconstructed = bytearray(b"\xff" * len(data))
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if (elf.elfclass != 32 or not elf.little_endian or elf["e_machine"] != "EM_ARM" or
                elf["e_type"] != "ET_EXEC" or elf["e_entry"] != reset):
            raise ValueError("BAD_HEADER: executable ARM ELF / reset agreement required")
        sections = ((".isr_vector", APP_BASE, None), (".rover_trial_entry", APP_BASE + 768, 32),
                    (".rover_firmware_header", APP_BASE + 1024, 256))
        for name, address, size in sections:
            section = elf.get_section_by_name(name)
            if section is None or section["sh_addr"] != address or (size and section["sh_size"] != size):
                raise ValueError("BAD_HEADER: exact ELF placement required: " + name)
            if size is None and not 8 <= section["sh_size"] <= 768:
                raise ValueError("BAD_HEADER: vectors overlap RTE2")
        symbols = elf.get_section_by_name(".symtab")

        def symbol(name):
            found = None if symbols is None else symbols.get_symbol_by_name(name)
            if not found or len(found) != 1:
                raise ValueError("BAD_HEADER: missing/ambiguous ELF symbol: " + name)
            return found[0]

        if (symbol("__rfu_image_bytes")["st_value"] != len(data) or
                symbol("_estack")["st_value"] != struct.unpack_from("<I", data)[0] or
                symbol("Reset_Handler")["st_value"] != reset or
                symbol("rover_app_entry_probe")["st_value"] != probe or
                symbol("rover_app_early_start")["st_value"] != runtime):
            raise ValueError("BAD_HEADER: ELF/header/entry descriptor disagreement")
        first = reset & ~1
        last = first + symbol("Reset_Handler")["st_size"]
        ready = symbol("rover_app_irq_ready")["st_value"] & ~1
        if not APP_BASE + 1280 <= first < ready < last <= end:
            raise ValueError("BAD_HEADER: IRQ-ready outside reset initialization")
        _, checked_end, _ = audit_ram_init(elf, symbol("_sdata")["st_value"], symbol("_edata")["st_value"],
                                           symbol("_sidata")["st_value"], symbol("_sbss")["st_value"],
                                           symbol("_ebss")["st_value"], first, last,
                                           symbol("rover_app_ram_fatal")["st_value"] & ~1)
        if checked_end >= ready:
            raise ValueError("BAD_HEADER: IRQ enabled before RAM initialization proof")
        copy_start, copy_end, zero_start, zero_end, stack = (
            symbol(name)["st_value"] for name in ("_sdata", "_edata", "_sbss", "_ebss", "_estack"))
        if (symbol("_ram_start")["st_value"] != copy_start or symbol("_ram_end")["st_value"] != copy_end or
                symbol("_bss_start")["st_value"] != zero_start or symbol("_bss_end")["st_value"] != zero_end or
                stack != 0x24080000 or zero_end > stack - 16384):
            raise ValueError("BAD_HEADER: native RAM boundaries / stack reserve")
        capsule = elf.get_section_by_name(".trial_handoff")
        if (capsule is None or capsule["sh_type"] != "SHT_NOBITS" or
                capsule["sh_addr"] != 0x38000000 or capsule["sh_size"] != 16384 or
                not capsule["sh_flags"] & 2):
            raise ValueError("BAD_HEADER: preserved boot capsule RAM reservation required")
        segments = [segment for segment in elf.iter_segments() if segment["p_type"] == "PT_LOAD"]
        for segment in segments:
            if segment["p_filesz"] and not APP_BASE <= segment["p_paddr"] < segment["p_paddr"] + segment["p_filesz"] <= end:
                raise ValueError("WRONG_SLOT: ELF load outside single internal APP")
        spans, virtual_spans = [], []
        for section in elf.iter_sections():
            if not section["sh_flags"] & 2 or not section["sh_size"]:
                continue
            address, length = section["sh_addr"], section["sh_size"]
            if any(address < high and low < address + length for low, high in virtual_spans):
                raise ValueError("BAD_HEADER: overlapping allocated ELF sections")
            virtual_spans.append((address, address + length))
            if not (APP_BASE <= address < address + length <= APP_BASE + APP_BYTES or
                    any(low <= address < address + length <= high for low, high in (*RAM, (0, 0x10000)))):
                raise ValueError("WRONG_SLOT: ELF allocated section outside APP/RAM")
            parents = [segment for segment in segments if segment.section_in_segment(section)]
            if len(parents) != 1:
                raise ValueError("BAD_HEADER: ELF section load ownership")
            if section["sh_type"] == "SHT_NOBITS":
                if not (zero_start <= address < address + length <= zero_end or
                        section.name == ".trial_handoff" or
                        section.name == "._user_heap_stack" and zero_end <= address < address + length <= stack - 16384):
                    raise ValueError("BAD_HEADER: RAM outside verified zero span / reserved heap / capsule")
                continue
            if not (APP_BASE <= address < address + length <= end or
                    copy_start <= address < address + length <= copy_end):
                raise ValueError("BAD_HEADER: RAM load outside verified startup copy span")
            load = parents[0]["p_paddr"] + address - parents[0]["p_vaddr"]
            if not APP_BASE <= load < load + length <= end or any(load < high and low < load + length for low, high in spans):
                raise ValueError("WRONG_SLOT: overlapping/out-of-APP load bytes")
            spans.append((load, load + length))
            reconstructed[load - APP_BASE:load - APP_BASE + length] = section.data()
        if reconstructed != data:
            raise ValueError("BAD_HASH: RFU2 bytes differ from ELF sections / FF padding")
        if struct.unpack_from("<H", data, first - APP_BASE)[0] != 0xB672 or struct.unpack_from("<H", data, ready - APP_BASE)[0] != 0xB662:
            raise ValueError("BAD_HEADER: reset/IRQ mask boundary")


def read_image(path):
    with path.open("rb") as stream:
        data = stream.read(APP_BYTES + 1)
    if len(data) > APP_BYTES:
        raise ValueError("BAD_LENGTH: input exceeds internal APP capacity")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("layout")
    inspect_command = commands.add_parser("inspect")
    inspect_command.add_argument("image", type=Path)
    check_command = commands.add_parser("check")
    check_command.add_argument("image", type=Path)
    check_command.add_argument("--sha256", required=True)
    check_command.add_argument("--profile-crc", required=True)
    check_command.add_argument("--firmware-id", required=True)
    package_command = commands.add_parser("package")
    package_command.add_argument("image", type=Path)
    package_command.add_argument("--firmware-id", required=True)
    package_command.add_argument("--elf", required=True, type=Path)
    package_command.add_argument("--output", required=True, type=Path)
    package_command.add_argument("--metadata", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "layout":
            result = layout()
        elif args.command == "inspect":
            result = inspect(read_image(args.image))
        elif args.command == "package":
            if args.output.resolve() in (args.image.resolve(), args.elf.resolve(), args.metadata.resolve()) or args.metadata.resolve() in (args.image.resolve(), args.elf.resolve()):
                raise ValueError("BAD_REQUEST: output, metadata and inputs must be distinct")
            data, result = package(read_image(args.image), args.firmware_id)
            verify_elf(args.elf, data)
            result["elf_verified"] = True
            result["runtime_admitted"] = False
            args.output.write_bytes(data)
            args.metadata.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="ascii")
        else:
            result = check(read_image(args.image), args.sha256, args.profile_crc, args.firmware_id)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError, ImportError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
