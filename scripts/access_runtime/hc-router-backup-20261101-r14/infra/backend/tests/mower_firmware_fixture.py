"""Synthetic format/audit fixture. NOT a deployable firmware or qualification."""
import hashlib
import struct


def artifacts():
    base = 0x08100000
    image = bytearray(b"\xff" * 1536)
    reset, probe, runtime = base + 1281, base + 1297, 0x24000101
    struct.pack_into("<II", image, 0, 0x24080000, reset)
    struct.pack_into("<4sHH6I", image, 768, b"RTE2", 1, 32, 2, base, reset, probe, runtime, 0x52544532)
    image[1024:1280] = bytes(256)
    struct.pack_into("<4sHH16sIIIIHHHHI48s", image, 1024, b"RFU2", 256, 2, b"STM32H743VG", 2, 1, base, 1536, 3, 1, 2, 0, 0xAABBCCDD, b"synthetic-test-only")
    begin, publish, end, fatal, ready = 1298, 1364, 1412, 1414, 1420
    copy_start, copy_end, zero_start, zero_end = 0x24000100, 0x24000104, 0x24000104, 0x24000114
    struct.pack_into("<H", image, 1280, 0xB672)
    struct.pack_into("<H", image, ready, 0xB662)
    struct.pack_into("<HH", image, fatal, 0xB672, 0xE7FE)
    fixed = {6:0x4291,8:0xD207,10:0xF850,12:0x3B04,14:0xF851,16:0x4B04,
             18:0x42A3,24:0xE7F5,30:0x4291,32:0xD205,34:0xF851,36:0x3B04,
             38:0x2B00,44:0xE7F7,52:0x1A89,58:0x1AD2,62:0xEA6F,64:0x0403,
             66:0x6041,68:0x6082,70:0x60C4,72:0xF3BF,74:0x8F4F,76:0x6003,
             78:0xF3BF,80:0x8F4F,82:0x6845,84:0x428D,90:0x6885,92:0x4295,
             98:0x68C5,100:0x42A5,106:0x6805,108:0x429D}
    for offset, instruction in fixed.items():
        struct.pack_into("<H", image, begin + offset, instruction)
    for offset in (20, 40, 86, 94, 102, 110):
        struct.pack_into("<HH", image, begin + offset, 0xF040, 0x8000 | ((fatal - (begin + offset + 4)) // 2))
    literals = [(0,0,base+1528),(2,1,copy_start),(4,2,copy_end),(26,1,zero_start),(28,2,zero_end),
                (46,0,zero_start),(48,1,copy_end),(50,2,copy_start),(54,2,zero_end),(56,3,zero_start),(60,3,0x52414D31)]
    for index, (offset, register, value) in enumerate(literals):
        literal = 1440 + index * 4
        displacement = (literal - ((begin + offset + 4) & ~3)) // 4
        struct.pack_into("<H", image, begin + offset, 0x4800 | (register << 8) | displacement)
        struct.pack_into("<I", image, literal, value)

    # Four load segments: flash, RAM copy, RAM zero, preserved boot capsule.
    blob_offset = 52 + 4 * 32
    elf = bytearray(bytes(blob_offset) + image)
    names = ["", ".isr_vector", ".rover_trial_entry", ".rover_firmware_header", ".text", ".data", ".bss", ".trial_handoff", ".symtab", ".strtab", ".shstrtab"]
    symbol_values = {
        "__rfu_image_bytes": (1536, 0, 0x10, 0xFFF1), "_estack": (0x24080000, 0, 0x10, 0xFFF1),
        "Reset_Handler": (reset, 248, 0x12, 4), "rover_app_entry_probe": (probe, 2, 0x12, 4),
        "rover_app_early_start": (runtime, 4, 0x12, 5), "rover_app_irq_ready": (base+ready, 0, 0x10, 4),
        "_sdata": (copy_start, 0, 0x10, 5), "_edata": (copy_end, 0, 0x10, 5),
        "_sidata": (base+1528, 0, 0x10, 0xFFF1), "_sbss": (zero_start, 0, 0x10, 6), "_ebss": (zero_end, 0, 0x10, 6),
        "_ram_start": (copy_start, 0, 0x10, 5), "_ram_end": (copy_end, 0, 0x10, 5),
        "_bss_start": (zero_start, 0, 0x10, 6), "_bss_end": (zero_end, 0, 0x10, 6),
        "rover_app_ram_fatal": (base+fatal+1, 4, 0x12, 4),
        "rover_ram_verify_begin": (base+begin, 0, 0x10, 4), "rover_ram_proof_publish": (base+publish, 0, 0x10, 4),
        "rover_ram_verify_end": (base+end, 0, 0x10, 4), "rover_ram_init_proof": (zero_start, 16, 0x11, 6),
    }
    strings, symbols = bytearray(b"\0"), bytearray(bytes(16))
    for name, (value, size, info, section) in symbol_values.items():
        position = len(strings); strings += name.encode() + b"\0"
        symbols += struct.pack("<IIIBBH", position, value, size, info, 0, section)
    symbols_offset = len(elf); elf += symbols
    strings_offset = len(elf); elf += strings
    section_strings, positions = bytearray(), []
    for name in names:
        positions.append(len(section_strings)); section_strings += name.encode() + b"\0"
    section_strings_offset = len(elf); elf += section_strings
    while len(elf) % 4:
        elf += b"\0"
    section_table = len(elf)
    sections = [
        (0,0,0,0,0,0,0,0,0), (1,2,base,blob_offset,8,0,0,4,0),
        (1,2,base+768,blob_offset+768,32,0,0,4,0), (1,2,base+1024,blob_offset+1024,256,0,0,4,0),
        (1,6,base+1280,blob_offset+1280,248,0,0,2,0), (1,3,copy_start,blob_offset+1528,4,0,0,4,0),
        (8,3,zero_start,blob_offset+1532,16,0,0,4,0), (8,3,0x38000000,blob_offset+1532,16384,0,0,4,0),
        (2,0,0,symbols_offset,len(symbols),9,1,4,16), (3,0,0,strings_offset,len(strings),0,0,1,0),
        (3,0,0,section_strings_offset,len(section_strings),0,0,1,0),
    ]
    for index, section in enumerate(sections):
        elf += struct.pack("<10I", positions[index], *section)
    identity = b"\x7fELF\x01\x01\x01" + bytes(9)
    struct.pack_into("<16sHHIIIIIHHHHHH", elf, 0, identity, 2, 40, 1, reset, 52, section_table, 0, 52, 32, 4, 40, len(sections), 10)
    for index, values in enumerate([
        (1,blob_offset,base,base,1528,1528,5,4),
        (1,blob_offset+1528,copy_start,base+1528,4,4,6,4),
        (1,blob_offset+1532,zero_start,zero_start,0,16,6,4),
        (1,blob_offset+1532,0x38000000,0x38000000,0,16384,6,4),
    ]):
        struct.pack_into("<8I", elf, 52 + index * 32, *values)
    image, elf = bytes(image), bytes(elf)
    release = {"release_id": "synthetic-test-only", "firmware_id": "synthetic-test-only",
               "image_sha256": hashlib.sha256(image).hexdigest(), "elf_sha256": hashlib.sha256(elf).hexdigest(),
               "profile_crc": "AABBCCDD", "image_bytes": len(image), "layout": "H743_1M_QSPI_REC2", "slot": "APP"}
    return image, elf, release


def envelope(image, elf):
    return struct.pack("<I", len(image)) + image + elf
