"""HC-24 synthetic parser/loop fixtures; socket creation is always forbidden."""
from collections import deque
from contextlib import contextmanager
import random
import signal
import struct
import unittest
from unittest.mock import patch

import mdns_responder as mdns


def header(count=1, flags=0):
    return struct.pack('!HHHHHH', 0x1234, flags, count, 0, 0, 0)


def query(name='hc.local', qtype=1, qclass=1):
    return header() + mdns.encode_name(name) + struct.pack('!HH', qtype, qclass)


@contextmanager
def deadline(seconds=.5):
    def expired(*args):
        raise AssertionError('DNS parser did not terminate within fixture deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class MDNSParserTest(unittest.TestCase):
    def setUp(self):
        self.socket_guard = patch.object(mdns.socket, 'socket', side_effect=AssertionError('LAN sockets forbidden'))
        self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)

    def rejected(self, packet, offset=0):
        with deadline(), self.assertRaises(ValueError):
            mdns.read_name(packet, offset)

    def test_plain_root_case_and_end_offset(self):
        self.assertEqual(mdns.read_name(b'\0tail', 0), ('', 1))
        self.assertEqual(mdns.read_name(b'xx\x02HC\x05LOCAL\0tail', 2), ('hc.local', 12))

    def test_compressed_name_preserves_first_pointer_end(self):
        packet = mdns.encode_name('hc.local') + b'\xc0\x00' + b'\x03www\xc0\x00' + b'\xc0\x0a'
        self.assertEqual(mdns.read_name(packet, 10), ('hc.local', 12))
        self.assertEqual(mdns.read_name(packet, 12), ('www.hc.local', 18))
        self.assertEqual(mdns.read_name(packet, 18), ('hc.local', 20))

    def test_self_referencing_pointer_terminates(self):
        self.rejected(b'\xc0\x00')

    def test_two_pointer_cycle_terminates(self):
        self.rejected(b'\xc0\x02\xc0\x00')

    def test_label_then_pointer_cycle_terminates(self):
        self.rejected(b'\x01a\xc0\x00')

    def test_truncated_label_pointer_root_and_invalid_offsets(self):
        for packet, offset in ((b'', 0), (b'\xc0', 0), (b'\xc0\x02', 0),
                               (b'\xc0\xff', 0), (b'\x03ab', 0), (b'\x01a', 0),
                               (b'\0', -1), (b'\0', 1)):
            with self.subTest(packet=packet, offset=offset):
                self.rejected(packet, offset)

    def test_reserved_label_encodings_rejected(self):
        for packet in (b'\x40\0', b'\x80\0', b'\x7f' + b'a' * 127 + b'\0', b'\xbf' + b'a' * 191 + b'\0'):
            with self.subTest(prefix=packet[0]):
                self.rejected(packet)

    def test_maximum_label_and_expanded_name_boundary(self):
        labels = ['a' * 63, 'b' * 63, 'c' * 63, 'd' * 61]
        packet = mdns.encode_name('.'.join(labels))
        self.assertEqual(len(packet), 255)
        self.assertEqual(mdns.read_name(packet, 0), ('.'.join(labels), 255))
        self.rejected(mdns.encode_name('.'.join(labels[:-1] + ['d' * 62])))
        self.assertEqual(mdns.read_name(mdns.encode_name('a' * 63), 0), ('a' * 63, 65))

    def test_expanded_length_limit_also_applies_after_compression(self):
        name = '.'.join(['a' * 63] * 3 + ['b' * 61])
        packet = mdns.encode_name(name) + b'\x01x\xc0\x00'
        self.rejected(packet, 255)

    def test_pointer_chain_work_limit(self):
        packet = bytearray(b'\0')
        target = 0
        for _ in range(mdns.MAX_POINTER_JUMPS):
            current = len(packet)
            packet.extend(struct.pack('!H', 0xC000 | target))
            target = current
        self.assertEqual(mdns.read_name(bytes(packet), target), ('', len(packet)))
        packet.extend(struct.pack('!H', 0xC000 | target))
        self.rejected(bytes(packet), len(packet) - 2)

    def test_valid_compressed_multi_question_parsing(self):
        packet = header(2) + mdns.encode_name('hc.local') + struct.pack('!HH', 1, 1)
        packet += b'\xc0\x0c' + struct.pack('!HH', 255, 0x8001)
        self.assertEqual(mdns.parse_questions(packet), [('hc.local', 1, 1), ('hc.local', 255, 0x8001)])

    def test_truncated_header_and_impossible_question_count(self):
        for size in range(12):
            self.assertEqual(mdns.parse_questions(b'\0' * size), [])
        self.assertEqual(mdns.parse_questions(header(65535) + b'\0' * 20), [])
        self.assertEqual(mdns.parse_questions(header(0)), [])
        self.assertEqual(mdns.parse_questions(header() + b'\0' + struct.pack('!HH', 1, 1)), [('', 1, 1)])

    def test_bad_question_discards_whole_section_without_partial_answer(self):
        good = query()[12:]
        for bad in (b'\xc0\x0c', b'\x05x', b'\0\0\x01\0', b'\xc0\xff\0\x01\0\x01'):
            packet = header(2) + good + bad
            self.assertEqual(mdns.parse_questions(packet), [])
            self.assertFalse(mdns.should_answer(packet, 'hc.local'))

    def test_malformed_first_question_is_not_answered(self):
        for body in (b'\xc0\x0c\0\x01\0\x01', b'\x40\0\0\x01\0\x01', b'\x03ab'):
            packet = header() + body
            with deadline():
                self.assertEqual(mdns.parse_questions(packet), [])
                self.assertFalse(mdns.should_answer(packet, 'hc.local'))

    def test_existing_answer_selection_and_response_flag(self):
        for qtype in (1, 255):
            self.assertTrue(mdns.should_answer(query('HC.LOCAL', qtype, 0x8001), 'hc.local'))
        self.assertFalse(mdns.should_answer(query('other.local'), 'hc.local'))
        self.assertFalse(mdns.should_answer(query(qtype=28), 'hc.local'))
        response = bytearray(query()); response[2] |= 0x80
        self.assertFalse(mdns.should_answer(bytes(response), 'hc.local'))

    def test_single_question_response_bytes_match_original_fixtures(self):
        for qtype, question_tail in ((1, '00010001'), (255, '00ff0001')):
            expected = bytes.fromhex('123484000001000100000000024843056c6f63616c00' + question_tail
                                     + 'c00c00018001000000780004c0000217')
            self.assertEqual(mdns.build_response(query('HC.local', qtype), 'hc.local', '192.0.2.23'), expected)

    def test_announcement_bytes_match_original_fixture(self):
        expected = bytes.fromhex('000084000000000100000000026863056c6f63616c0000018001000000780004c0000217')
        self.assertEqual(mdns.build_announcement('hc.local', '192.0.2.23'), expected)

    def test_receive_loop_continues_after_bad_packets_with_fake_socket(self):
        class Finished(BaseException):
            pass
        packets = deque([header() + b'\xc0\x0c\0\x01\0\x01', header(2) + query()[12:] + b'\x05x', query()])
        sent = []
        class FakeSocket:
            def recvfrom(self, limit):
                if not packets:
                    raise Finished()
                return packets.popleft(), ('192.0.2.100', 5353)
            def sendto(self, payload, address):
                sent.append((payload, address))
        with patch.object(mdns, 'make_socket', return_value=FakeSocket()), \
             patch.object(mdns, 'env_name', return_value='hc.local'), \
             patch.object(mdns, 'local_ip', return_value='192.0.2.23'), \
             patch.object(mdns.time, 'monotonic', return_value=0), deadline(), self.assertRaises(Finished):
            mdns.main()
        self.assertEqual(len(sent), 2)
        self.assertEqual([address for _, address in sent], [(mdns.MDNS_GROUP, mdns.MDNS_PORT), ('192.0.2.100', 5353)])
        expected = mdns.build_response(query(), 'hc.local', '192.0.2.23')
        self.assertEqual([payload for payload, _ in sent], [expected, expected])

    def test_deterministic_random_and_generated_names_are_bounded(self):
        rng = random.Random(24)
        with deadline(3):
            for _ in range(3000):
                packet = rng.randbytes(rng.randrange(0, 400))
                offset = rng.randrange(-1, len(packet) + 2)
                try:
                    name, end = mdns.read_name(packet, offset)
                except ValueError:
                    pass
                else:
                    self.assertTrue(0 <= end <= len(packet))
                self.assertIsInstance(mdns.parse_questions(packet), list)
            for _ in range(200):
                labels = [''.join(rng.choices('abcXYZ', k=rng.randrange(1, 20))) for _ in range(rng.randrange(1, 6))]
                expected = '.'.join(labels)
                wire = mdns.encode_name(expected)
                self.assertEqual(mdns.read_name(wire, 0), (expected.lower(), len(wire)))


if __name__ == '__main__':
    unittest.main()
