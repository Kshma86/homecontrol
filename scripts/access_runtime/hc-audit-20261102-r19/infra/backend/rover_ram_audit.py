"""Check the exact reset-only RAM verification macro in a native ARM ELF."""
import struct


def audit_ram_init(elf, copy_start, copy_end, load, zero_start, zero_end,
                   reset, reset_end, fatal):
    table = elf.get_section_by_name(".symtab")

    def symbol(name):
        found = table.get_symbol_by_name(name) if table else None
        if not found or len(found) != 1:
            raise ValueError("RAM initialization: missing/ambiguous " + name)
        return found[0]

    def data(address, size):
        for section in elf.iter_sections():
            if (section["sh_flags"] & 2 and section["sh_type"] != "SHT_NOBITS" and
                    section["sh_addr"] <= address < address+size <= section["sh_addr"]+section["sh_size"]):
                offset = address-section["sh_addr"]
                return section.data()[offset:offset+size]
        raise ValueError("RAM initialization: code/literal outside allocated bytes")

    begin, publish, end = (symbol(name)["st_value"] for name in
                          ("rover_ram_verify_begin", "rover_ram_proof_publish", "rover_ram_verify_end"))
    proof = symbol("rover_ram_init_proof")
    address = proof["st_value"]
    if (not all(value % 4 == 0 for value in (copy_start, copy_end, load, zero_start, zero_end, address)) or
            not 0x24000000 <= copy_start < copy_end <= zero_start < zero_end <= 0x24080000 or
            not 0x08000000 <= load < load+copy_end-copy_start <= 0x08200000 or
            proof["st_info"]["type"] != "STT_OBJECT" or proof["st_size"] != 16 or
            not isinstance(proof["st_shndx"], int) or
            elf.get_section(proof["st_shndx"])["sh_type"] != "SHT_NOBITS" or
            not zero_start <= address < address+16 <= zero_end or
            not reset < begin < publish < end < fatal < reset_end or
            publish-begin != 66 or end-begin != 114):
        raise ValueError("RAM initialization: span/proof/reset boundary")
    code = data(begin, 114)

    def half(offset):
        return struct.unpack_from("<H", code, offset)[0]

    fixed = {6:0x4291,8:0xD207,10:0xF850,12:0x3B04,14:0xF851,16:0x4B04,
             18:0x42A3,24:0xE7F5,30:0x4291,32:0xD205,34:0xF851,36:0x3B04,
             38:0x2B00,44:0xE7F7,52:0x1A89,58:0x1AD2,62:0xEA6F,64:0x0403,
             66:0x6041,68:0x6082,70:0x60C4,72:0xF3BF,74:0x8F4F,76:0x6003,
             78:0xF3BF,80:0x8F4F,82:0x6845,84:0x428D,90:0x6885,92:0x4295,
             98:0x68C5,100:0x42A5,106:0x6805,108:0x429D}
    for offset, expected in fixed.items():
        if half(offset) != expected:
            raise ValueError("RAM initialization: compare/publication instructions")
    for offset in (20,40,86,94,102,110):
        # Pinned BNE.W T3 displacements are positive and below 4096.
        first, second = half(offset), half(offset+2)
        if first != 0xF040 or second & 0xF800 != 0x8000 or begin+offset+4+(second & 2047)*2 != fatal:
            raise ValueError("RAM initialization: failure branch")
    for offset, register, expected in (
            (0,0,load),(2,1,copy_start),(4,2,copy_end),(26,1,zero_start),(28,2,zero_end),
            (46,0,address),(48,1,copy_end),(50,2,copy_start),(54,2,zero_end),
            (56,3,zero_start),(60,3,0x52414D31)):
        instruction = half(offset)
        if instruction & 0xFF00 != 0x4800+(register << 8):
            raise ValueError("RAM initialization: linker literal instruction")
        literal = ((begin+offset+4) & ~3)+(instruction & 255)*4
        if struct.unpack("<I", data(literal,4))[0] != expected:
            raise ValueError("RAM initialization: linker literal value")
    if data(fatal,2) != b"\x72\xb6":
        raise ValueError("RAM initialization: failure interrupt mask")
    if data(fatal+2,2) != b"\xfe\xe7" and data(fatal+2,4) != b"\xff\xf7\xfd\xbf":
        raise ValueError("RAM initialization: failure halt loop")
    return begin, end, address
