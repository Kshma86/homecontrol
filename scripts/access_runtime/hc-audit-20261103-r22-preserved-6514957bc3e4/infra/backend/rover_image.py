#!/usr/bin/env python3
"""Package/inspect/check already slot-linked RFU1 images; never relocate, flash or enable OTA."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import rover_profile as profile

MAX_BYTES = 786432
BASES = {"A": 0x08040000, "B": 0x08140000}
RAM = ((0x20000000, 0x20020000), (0x24000000, 0x24080000),
       (0x30000000, 0x30048000), (0x38000000, 0x38010000))


def inspect(data):
    if not 1280 <= len(data) <= MAX_BYTES or len(data) % 32:
        raise ValueError("BAD_LENGTH: exact padded RFU1 image length required")
    h = data[1024:1280]
    u16 = lambda offset: struct.unpack_from("<H", h, offset)[0]
    u32 = lambda offset: struct.unpack_from("<I", h, offset)[0]
    if h[:4] != b"RFU1" or (u16(4), u16(6), u32(24), u16(46)) != (256, 1, 1, 0) or any(h[100:]):
        raise ValueError("BAD_HEADER: RFU1 format/layout/reserved fields")
    if h[8:24] != b"STM32H743VI\0\0\0\0\0":
        raise ValueError("WRONG_TARGET: verified STM32H743VI layout only")
    slot = {1: "A", 2: "B"}.get(u32(28))
    if not slot or u32(32) != BASES[slot]:
        raise ValueError("WRONG_SLOT: image must already be linked for its declared slot")
    if u32(36) != len(data):
        raise ValueError("BAD_LENGTH: binary/header length mismatch")
    if (u16(40), u16(42), u16(44)) != (3, 1, 1):
        raise ValueError("ABI_MISMATCH: this package policy requires operational 3.1 / service ABI 1")
    raw_fw = h[52:100]
    nul = raw_fw.find(b"\0")
    if nul >= 0:
        if any(raw_fw[nul:]):
            raise ValueError("BAD_HEADER: firmware ID must be NUL padded")
        raw_fw = raw_fw[:nul]
    if not re.fullmatch(rb"[A-Za-z0-9_.-]{1,48}", raw_fw):
        raise ValueError("BAD_HEADER: invalid firmware ID")
    stack, reset = struct.unpack_from("<II", data)
    if stack % 8 or not any(low < stack <= high for low, high in RAM):
        raise ValueError("BAD_HEADER: initial MSP is outside permitted RAM/alignment")
    if not reset & 1 or not BASES[slot] <= (reset & ~1) < BASES[slot] + len(data):
        raise ValueError("BAD_HEADER: reset vector is not a Thumb address in this image")
    return dict(target="STM32H743VI", layout="H743_2M_AB1", slot=slot, link_address=f"{BASES[slot]:08X}",
                image_bytes=len(data), contract="3.1.0", service_abi=1, profile_crc=f"{u32(48):08X}",
                fw_id=raw_fw.decode("ascii"), image_sha256=hashlib.sha256(data).hexdigest())


def check(data, slot, firmware_id, sha256, installed_profile):
    metadata = inspect(data)
    profile.validate(installed_profile)
    if slot not in BASES or metadata["slot"] != slot:
        raise ValueError("WRONG_SLOT: package/header disagreement")
    if not isinstance(firmware_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,48}", firmware_id) or metadata["fw_id"] != firmware_id:
        raise ValueError("BAD_HEADER: package/header firmware ID disagreement")
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256) or metadata["image_sha256"] != sha256:
        raise ValueError("BAD_HASH: exact lowercase external SHA-256 required")
    if metadata["profile_crc"] != f"{profile.checksum(installed_profile):08X}":
        raise ValueError("PROFILE_MISMATCH: package differs from installed profile")
    return metadata


def package(data, slot, firmware_id):
    if not 1280 <= len(data) <= MAX_BYTES:
        raise ValueError("BAD_LENGTH: bounded slot-linked input required")
    expected = struct.unpack_from("<I", data, 1024 + 36)[0]
    if expected != (len(data) + 31) // 32 * 32:
        raise ValueError("BAD_LENGTH: linker header must declare exact 32-byte padded length")
    padded = bytes(data).ljust(expected, b"\xff")
    metadata = inspect(padded)
    if metadata["slot"] != slot:
        raise ValueError("WRONG_SLOT: package/header disagreement")
    if metadata["fw_id"] != firmware_id:
        raise ValueError("BAD_HEADER: package/header firmware ID disagreement")
    metadata["conformant"] = False
    metadata["stm_remote_update"] = False
    return padded, metadata


def verify_elf(path, data):
    try:
        from elftools.elf.elffile import ELFFile
    except ImportError as error:
        raise ValueError("ELF verification requires pyelftools") from error
    metadata = inspect(data)
    base, end = BASES[metadata["slot"]], BASES[metadata["slot"]]+len(data)
    expected = bytearray(b"\xff"*len(data))
    ram = (*RAM,(0,0x10000))
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf.elfclass != 32 or not elf.little_endian or elf["e_machine"] != "EM_ARM" or elf["e_type"] != "ET_EXEC":
            raise ValueError("BAD_HEADER: executable little-endian ARM ELF required")
        if elf["e_entry"] != struct.unpack_from("<I",data,4)[0]:
            raise ValueError("BAD_HEADER: ELF entry/reset vector disagreement")
        vectors, header = elf.get_section_by_name(".isr_vector"), elf.get_section_by_name(".rover_firmware_header")
        if vectors is None or vectors["sh_addr"] != base or not 8 <= vectors["sh_size"] <= 1024:
            raise ValueError("BAD_HEADER: ELF vector placement/size")
        if header is None or header["sh_addr"] != base+1024 or header["sh_size"] != 256:
            raise ValueError("BAD_HEADER: ELF RFU1 placement/size")
        symbols = elf.get_section_by_name(".symtab")
        length_symbol = None if symbols is None else symbols.get_symbol_by_name("__rfu_image_bytes")
        if not length_symbol or len(length_symbol) != 1 or length_symbol[0]["st_value"] != len(data):
            raise ValueError("BAD_LENGTH: ELF padded-length symbol disagreement")
        reset_symbol = symbols.get_symbol_by_name("Reset_Handler")
        ready_symbol = symbols.get_symbol_by_name("rover_app_irq_ready")
        if not reset_symbol or len(reset_symbol)!=1 or not ready_symbol or len(ready_symbol)!=1:
            raise ValueError("BAD_HEADER: missing/ambiguous masked APP entry")
        reset = reset_symbol[0]["st_value"] & ~1
        ready = ready_symbol[0]["st_value"] & ~1
        reset_end = reset + reset_symbol[0]["st_size"]
        if (reset_symbol[0]["st_value"] != elf["e_entry"] or
                not base <= reset < ready < ready+2 <= reset_end <= end or
                struct.unpack_from("<H",data,reset-base)[0]!=0xB672 or
                struct.unpack_from("<H",data,ready-base)[0]!=0xB662):
            raise ValueError("BAD_HEADER: APP entry/IRQ-ready mask boundary")
        from rover_ram_audit import audit_ram_init
        def ram_symbol(name):
            found = symbols.get_symbol_by_name(name)
            if not found or len(found)!=1:
                raise ValueError("RAM initialization: missing/ambiguous " + name)
            return found[0]["st_value"]
        _,ram_end,_ = audit_ram_init(elf,ram_symbol("_sdata"),ram_symbol("_edata"),ram_symbol("_sidata"),
                                   ram_symbol("_sbss"),ram_symbol("_ebss"),reset,reset_end,
                                   ram_symbol("rover_app_ram_fatal") & ~1)
        if ram_end >= ready:
            raise ValueError("RAM initialization: verification after IRQ-ready")
        from rover_trial_audit import audit_trial_entry
        audit_trial_entry(elf,base,1 if metadata["slot"]=="A" else 2)
        segments = [s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
        for segment in segments:
            if segment["p_filesz"] and not base <= segment["p_paddr"] < segment["p_paddr"]+segment["p_filesz"] <= end:
                raise ValueError("WRONG_SLOT: ELF load bytes outside image slot")
        intervals = []
        for section in elf.iter_sections():
            if not section["sh_flags"] & 2 or not section["sh_size"]:
                continue
            address, size = section["sh_addr"], section["sh_size"]
            if not (base <= address < address+size <= base+MAX_BYTES or
                    any(low <= address < address+size <= high for low,high in ram)):
                raise ValueError("WRONG_SLOT: allocated ELF section outside slot/RAM")
            if section["sh_type"] == "SHT_NOBITS":
                continue
            owners = [s for s in segments if s.section_in_segment(section)]
            if len(owners) != 1:
                raise ValueError("BAD_HEADER: ELF section load ownership")
            load = owners[0]["p_paddr"]+address-owners[0]["p_vaddr"]
            if not base <= load < load+size <= end:
                raise ValueError("WRONG_SLOT: ELF section load outside image")
            if any(load < b and a < load+size for a,b in intervals):
                raise ValueError("BAD_HEADER: overlapping ELF load sections")
            intervals.append((load,load+size))
            expected[load-base:load-base+size] = section.data()
        if expected != data:
            raise ValueError("BAD_HASH: package bytes differ from ELF sections/FF padding")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    observe = sub.add_parser("inspect")
    observe.add_argument("image", type=Path)
    verify = sub.add_parser("check")
    verify.add_argument("image", type=Path)
    verify.add_argument("--slot", choices=("A", "B"), required=True)
    verify.add_argument("--firmware-id", required=True)
    verify.add_argument("--sha256", required=True)
    verify.add_argument("--profile", type=Path, required=True)
    prepare = sub.add_parser("package")
    prepare.add_argument("image", type=Path)
    prepare.add_argument("--slot", choices=("A", "B"), required=True)
    prepare.add_argument("--firmware-id", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--metadata", type=Path, required=True)
    prepare.add_argument("--elf", type=Path)
    args = parser.parse_args()
    try:
        with args.image.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if args.operation == "package":
            paths = [p.resolve() for p in (args.image,args.output,args.metadata)]
            if len(set(paths)) != 3:
                raise ValueError("Package input/output/metadata must be separate files")
            for i, a in enumerate(paths):
                for b in paths[i+1:]:
                    if a.exists() and b.exists() and a.samefile(b):
                        raise ValueError("Package paths cannot share a hard-linked file")
            data, metadata = package(data,args.slot,args.firmware_id)
            if args.elf is not None:
                verify_elf(args.elf,data)
            args.output.write_bytes(data)
            args.metadata.write_text(json.dumps(metadata,sort_keys=True,separators=(",", ":"))+"\n",encoding="ascii")
        elif args.operation == "check":
            p = json.loads(args.profile.read_text(encoding="utf-8"), object_pairs_hook=profile.reject_duplicate_keys)
            metadata = check(data, args.slot, args.firmware_id, args.sha256, p)
        else:
            metadata = inspect(data)
        print(json.dumps(metadata, sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
