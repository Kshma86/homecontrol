import os
import socket
import struct
import time


MDNS_GROUP = "224.0.0.251"
MDNS_PORT = 5353
DEFAULT_TTL = 120
MAX_NAME_BYTES = 255  # Expanded wire name, including label lengths and root.
MAX_POINTER_JUMPS = 128  # Local work limit, not a DNS wire-format limit.


def env_name() -> str:
    name = os.getenv("HC_MDNS_NAME", "hc.local").strip().strip(".").lower()
    if not name.endswith(".local"):
        name = f"{name}.local"
    return name


def local_ip() -> str:
    configured = os.getenv("HC_MDNS_IP", "").strip()
    if configured:
        return configured
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    finally:
        sock.close()


def encode_name(name: str) -> bytes:
    out = bytearray()
    for label in name.strip(".").split("."):
        raw = label.encode("ascii")
        out.append(len(raw))
        out.extend(raw)
    out.append(0)
    return bytes(out)


def read_name(packet: bytes, offset: int):
    """Decode one bounded name; end stays after the first on-wire pointer."""
    labels = []
    jumped = False
    end = offset
    visited = set()
    name_bytes = 1  # The terminating root label counts toward the wire limit.
    jumps = 0
    while True:
        if offset < 0 or offset >= len(packet) or offset in visited:
            raise ValueError("Truncated or cyclic DNS name")
        visited.add(offset)
        length = packet[offset]
        if length == 0:
            offset += 1
            if not jumped:
                end = offset
            return ".".join(labels).lower(), end
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise ValueError("Truncated DNS pointer")
            pointer = ((length & 0x3F) << 8) | packet[offset + 1]
            jumps += 1
            if pointer >= len(packet) or jumps > MAX_POINTER_JUMPS:
                raise ValueError("Invalid or excessive DNS pointer chain")
            if not jumped:
                end = offset + 2
            jumped = True
            offset = pointer
            continue
        if length & 0xC0:
            raise ValueError("Unsupported DNS label type")
        if offset + 1 + length > len(packet):
            raise ValueError("Truncated DNS label")
        name_bytes += 1 + length
        if name_bytes > MAX_NAME_BYTES:
            raise ValueError("DNS name exceeds wire length limit")
        offset += 1
        labels.append(packet[offset:offset + length].decode("ascii", errors="ignore"))
        offset += length
        if not jumped:
            end = offset


def parse_questions(packet: bytes):
    if len(packet) < 12:
        return []
    qdcount = struct.unpack("!H", packet[4:6])[0]
    # Even a root question needs one name byte and four type/class bytes.
    if qdcount > (len(packet) - 12) // 5:
        return []
    offset = 12
    questions = []
    for _ in range(qdcount):
        try:
            name, offset = read_name(packet, offset)
        except ValueError:
            return []
        if offset + 4 > len(packet):
            return []
        qtype, qclass = struct.unpack("!HH", packet[offset:offset + 4])
        offset += 4
        questions.append((name, qtype, qclass))
    return questions


def build_response(packet: bytes, name: str, ip: str) -> bytes:
    question_end = 12
    if len(packet) >= 12:
        qdcount = struct.unpack("!H", packet[4:6])[0]
        for _ in range(qdcount):
            _, question_end = read_name(packet, question_end)
            question_end += 4
    question = packet[12:question_end]
    header = packet[:2] + struct.pack("!HHHHH", 0x8400, 1, 1, 0, 0)
    answer = (
        b"\xc0\x0c"
        + struct.pack("!HHIH", 1, 0x8001, DEFAULT_TTL, 4)
        + socket.inet_aton(ip)
    )
    return header + question + answer


def build_announcement(name: str, ip: str) -> bytes:
    header = struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0)
    answer = (
        encode_name(name)
        + struct.pack("!HHIH", 1, 0x8001, DEFAULT_TTL, 4)
        + socket.inet_aton(ip)
    )
    return header + answer


def should_answer(packet: bytes, name: str) -> bool:
    if len(packet) < 12:
        return False
    flags = struct.unpack("!H", packet[2:4])[0]
    if flags & 0x8000:
        return False
    for qname, qtype, _qclass in parse_questions(packet):
        if qname == name and qtype in (1, 255):
            return True
    return False


def make_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except OSError:
        pass
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
    sock.bind(("", MDNS_PORT))
    membership = socket.inet_aton(MDNS_GROUP) + socket.inet_aton("0.0.0.0")
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    sock.settimeout(1.0)
    return sock


def main():
    name = env_name()
    ip = local_ip()
    sock = make_socket()
    last_announce = 0
    print(f"[MDNS] advertising {name} -> {ip}", flush=True)
    while True:
        try:
            packet, addr = sock.recvfrom(9000)
            if should_answer(packet, name):
                response = build_response(packet, name, ip)
                sock.sendto(response, (MDNS_GROUP, MDNS_PORT))
                sock.sendto(response, addr)
                print(f"[MDNS] answered {name} for {addr[0]}:{addr[1]}", flush=True)
        except socket.timeout:
            pass
        now = time.monotonic()
        if now - last_announce >= 60:
            sock.sendto(build_announcement(name, ip), (MDNS_GROUP, MDNS_PORT))
            last_announce = now


if __name__ == "__main__":
    main()
