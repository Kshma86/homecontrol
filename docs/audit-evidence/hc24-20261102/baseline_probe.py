"""Reproduce the original parser hang with an alarm; no socket creation."""
import importlib.util
import json
from pathlib import Path
import signal
import struct
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('hc24_before', HERE/'original/infra/mdns/mdns_responder.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
class Deadline(Exception):
    pass

def expired(*args):
    raise Deadline()

records = []
with patch.object(module.socket, 'socket', side_effect=AssertionError('No LAN allowed')):
    signal.signal(signal.SIGALRM, expired)
    for packet in (b'\xc0\x00', b'\xc0\x02\xc0\x00'):
        signal.setitimer(signal.ITIMER_REAL, .1)
        try:
            module.read_name(packet, 0)
            records.append(dict(packet_hex=packet.hex(), timed_out=False))
        except Deadline:
            records.append(dict(packet_hex=packet.hex(), timed_out=True))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    queries = []
    for qtype in (1, 255):
        packet = struct.pack('!HHHHHH', 0x1234, 0, 1, 0, 0, 0)+module.encode_name('HC.local')+struct.pack('!HH', qtype, 1)
        queries.append(dict(query_hex=packet.hex(), parsed=module.parse_questions(packet),
            should_answer=module.should_answer(packet, 'hc.local'),
            response_hex=module.build_response(packet, 'hc.local', '192.0.2.23').hex()))
    announcement=module.build_announcement('hc.local', '192.0.2.23').hex()
result=dict(ok=all(r['timed_out'] for r in records), deadline_seconds=.1,
            original_cycles=records, valid_queries=queries, announcement_hex=announcement, lan_packets_sent=0)
(HERE/'baseline-parser.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(ok=result['ok'], cycles_reproduced=len(records), valid_queries=len(queries), lan_packets_sent=0)))
assert result['ok']
