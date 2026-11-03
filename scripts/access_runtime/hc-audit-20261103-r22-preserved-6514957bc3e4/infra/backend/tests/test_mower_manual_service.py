import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mower_manual_service import ManualSession, ManualRelay, TimedBuffer, decode_frame
from mower_v3_service import MowerV3Service, MANUAL_PROTOCOL, RoverReadError
from tests.test_mower_v3_service import Transport


def claim():
    return {"type": "claim", "request_id": "claim-1", "esp_boot": "0123456789ABCDEF",
            "stm_boot": "FEDCBA9876543210", "control_epoch": 3}


def claimed():
    return {"type": "claimed", "lease_id": 7, "control_epoch": 4, "lease_ms": 350,
            "max_linear_mm_s": 500, "max_yaw_mdeg_s": 90000}


def drive(seq=1, held=True):
    return {"type": "drive", "lease_id": 7, "control_epoch": 4, "seq": seq,
            "linear_mm_s": 100 if held else 0, "yaw_mdeg_s": 0, "blade_rpm": 0, "deadman": held}


class ManualSessionTest(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.transport = Transport()
        self.transport.state.update(state="IDLE", armed=True, stopped=True)
        self.rover = MowerV3Service(transport=self.transport, clock=lambda: self.now)
        self.snapshot = self.rover.snapshot()
        self.session = ManualSession(self.snapshot, clock=lambda: self.now)

    def activate(self):
        self.session.client(claim(), self.now)
        self.session.server(claimed())

    def test_claim_requires_fresh_idle_stopped_source_and_exact_binding(self):
        for updates in ({"state": "AUTO"}, {"stopped": False}):
            with self.subTest(updates=updates):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot["state"].update(updates)
                with self.assertRaises(RoverReadError):
                    ManualSession(snapshot, clock=lambda: self.now).client(claim(), self.now)
        for updates in ({"control_epoch": True}, {"control_epoch": 2}, {"esp_boot": "wrong"}):
            with self.assertRaises(RoverReadError):
                self.session.client(claim() | updates, self.now)
        self.now += 1.6
        with self.assertRaises(RoverReadError):
            self.session.client(claim(), self.now)

    def test_admission_reads_may_delay_claim_but_not_motor_targets(self):
        self.now += .4
        self.session.client(claim(), 100.0)
        self.session.server(claimed())
        with self.assertRaises(RoverReadError):
            self.session.client(drive(),100.0)
        self.session.client(drive(held=False),self.now)
        self.now += .4
        self.session.client({'type':'release','lease_id':7,'control_epoch':4},100.0)
        self.assertEqual(self.session.phase,'RELEASED')

    def test_preclaim_observed_is_telemetry_and_never_a_lease(self):
        observed={'type':'observed','lease_id':0,'last_input_seq':0,'state':'IDLE','stopped':True}
        self.session.server(observed)
        self.assertEqual(self.session.phase,'NEW')
        self.assertIsNone(self.session.lease)
        self.session.client(claim(),self.now)
        self.session.server(observed)
        self.assertEqual(self.session.phase,'CLAIMING')
        self.assertIsNone(self.session.lease)
        with self.assertRaises(RoverReadError): self.session.client(drive(),self.now)
        self.session.server(claimed())
        self.assertEqual(self.session.phase,'ACTIVE')

    def test_native_idle_without_lease_ends_session_and_never_accepts_drive(self):
        self.activate()
        self.session.server({'type':'observed','lease_id':0,'last_input_seq':0,'state':'IDLE','stopped':True})
        self.assertEqual(self.session.phase,'ENDED')
        with self.assertRaises(RoverReadError): self.session.client(drive(),self.now)

    def test_claim_does_not_need_gnss_and_lease_is_exact(self):
        self.activate()
        self.assertEqual(self.session.phase, "ACTIVE")
        self.assertEqual(self.session.lease["lease_ms"], 350)
        for updates in ({"lease_ms": 400}, {"control_epoch": 3}, {"control_epoch": 2}, {"lease_id": True}):
            session = ManualSession(self.snapshot, clock=lambda: self.now)
            session.client(claim(), self.now)
            with self.assertRaises(RoverReadError):
                session.server(claimed() | updates)

    def test_drive_requires_full_frame_monotonic_sequence_and_zero_blade(self):
        self.activate()
        self.session.client(drive(), self.now)
        for frame in (drive(), drive(2) | {"lease_id": 8}, drive(2) | {"control_epoch": 3},
                      drive(2) | {"linear_mm_s": 501}, drive(2) | {"yaw_mdeg_s": 90001},
                      drive(2) | {"linear_mm_s": 1.2}, drive(2) | {"seq": True},
                      drive(2) | {"blade_rpm": 1}, drive(2) | {"extra": 0},
                      {key: value for key, value in drive(2).items() if key != "yaw_mdeg_s"}):
            with self.subTest(frame=frame), self.assertRaises(RoverReadError):
                self.session.client(frame, self.now)
        self.session.client(drive(2, False), self.now)

    def test_false_deadman_must_zero_both_axes_and_old_arrivals_reject(self):
        self.activate()
        with self.assertRaises(RoverReadError):
            self.session.client(drive() | {"deadman": False}, self.now)
        with self.assertRaises(RoverReadError):
            self.session.client(drive(), self.now - .101)

    def test_observed_requires_matching_lease_and_actually_sent_sequence(self):
        self.activate()
        self.session.client(drive(), self.now)
        observed = {"type": "observed", "lease_id": 7, "last_input_seq": 1, "state": "MANUAL", "stopped": False}
        with self.assertRaises(RoverReadError):
            self.session.server(observed)
        self.session.sent_seq = 1
        self.session.server(observed)
        self.session.server(observed | {"state": "IDLE", "stopped": True})
        self.assertEqual(self.session.phase, "ENDED")
        self.assertEqual(self.session.release_frame(), {"type": "release", "lease_id": 7, "control_epoch": 4})

    def test_release_ends_only_matching_lease_and_cannot_reclaim(self):
        self.activate()
        release = self.session.release_frame()
        self.session.client(release, self.now)
        self.assertIsNone(self.session.release_frame())
        with self.assertRaises(RoverReadError):
            self.session.client(claim(), self.now)

    def test_json_text_only_size_duplicate_and_nonfinite_limits(self):
        for raw in (b"{}", '[1]', '{"type":"claim","type":"drive"}', '{"x":NaN}', "é" * 257):
            with self.subTest(raw=raw), self.assertRaises(RoverReadError):
                decode_frame(raw)

    def test_receipt_buffer_stamps_arrival_and_bounds_queue_and_rate(self):
        from wsproto.utilities import LocalProtocolError
        buffer = TimedBuffer(clock=lambda: self.now)
        buffer.append("first")
        self.now += .2
        self.assertEqual(buffer.pop(0), (100.0, "first"))
        for _ in range(4):
            buffer.append("frame")
        with self.assertRaises(LocalProtocolError):
            buffer.append("overflow")
        buffer = TimedBuffer(clock=lambda: self.now)
        for _ in range(40):
            buffer.append("frame")
            buffer.pop(0)
        with self.assertRaises(LocalProtocolError):
            buffer.append("rate-overflow")

    def run_relay(self, frames):
        now = self.now
        class Browser:
            subprotocol = MANUAL_PROTOCOL
            def __init__(self):
                self.stage = 0
                self.queue = [(now, json.dumps(claim()))]
                self.outputs = []
                self.closed = False
            def receive(self, timeout):
                return self.queue.pop(0) if self.queue else None
            def send(self, raw):
                self.outputs.append(json.loads(raw))
                if self.outputs[-1]["type"] == "claimed":
                    self.queue = [(at, json.dumps(frame)) for at, frame in frames]
            def close(self):
                self.closed = True
        class Upstream:
            def __init__(self):
                self.sent = []
                self.reads = 0
            def send(self, raw):
                self.sent.append(json.loads(raw))
            def recv(self):
                self.reads += 1
                return json.dumps(claimed()) if self.reads == 1 else ""
            def shutdown(self):
                pass
        browser, upstream = Browser(), Upstream()
        relay = ManualRelay(self.rover, connector=lambda: upstream, clock=lambda: self.now)
        relay.run(browser, lambda: True)
        self.assertTrue(browser.closed)
        self.assertFalse(relay._owner.locked())
        return upstream.sent

    def test_relay_forwards_only_latest_fresh_unsent_drive_and_matching_release(self):
        frames = [(self.now - .2, drive()), (self.now, drive(2)), (self.now, drive(3))]
        sent = self.run_relay(frames)
        self.assertEqual([item["type"] for item in sent], ["claim", "drive", "release"])
        self.assertEqual(sent[1]["seq"], 3)
        self.assertTrue(all(item["type"] != "stop" for item in sent))

    def test_relay_false_deadman_discards_queued_motion_and_sends_full_zero(self):
        sent = self.run_relay([(self.now, drive()), (self.now, drive(2, False))])
        self.assertEqual([item["type"] for item in sent], ["claim", "drive", "release"])
        self.assertEqual(sent[1], drive(2, False))


if __name__ == "__main__":
    unittest.main()
