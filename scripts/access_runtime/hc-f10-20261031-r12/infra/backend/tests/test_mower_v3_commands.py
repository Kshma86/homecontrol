import copy
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mower_v3_service import MowerV3Service, UnknownMutation
from mower_v3_commands import MowerV3Commands
from tests.test_mower_v3_service import Transport


def command(name="arm", id_="hc-test-1"):
    return {"v": 3, "request_id": id_, "esp_boot": "0123456789ABCDEF", "stm_boot": "FEDCBA9876543210",
            "control_epoch": 3, "command": name, "value": None}


def ack(name="arm", id_="hc-test-1"):
    return {"v": 3, "request_id": id_, "command": name, "result": "APPLIED", "code": "OK", "detail": 0,
            "stm_boot": "FEDCBA9876543210", "control_epoch": 4, "state_seq": 16, "state": "IDLE"}


class CommandTransport(Transport):
    def __init__(self):
        super().__init__()
        self.mutations = []
        self.responses = []

    def request(self, method, path, body=None):
        if method == "POST":
            self.mutations.append((method, path, copy.deepcopy(body)))
        else:
            self.calls.append(path)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class MowerV3CommandsTest(unittest.TestCase):
    def setUp(self):
        self.transport = CommandTransport()
        self.now = 100.0
        self.rover = MowerV3Service(transport=self.transport, clock=lambda: self.now)
        self.commands = MowerV3Commands(self.rover)

    def test_admission_is_pending_and_only_correlated_ack_is_applied(self):
        self.transport.responses = [(202, {"v": 3, "request_id": "hc-test-1"}), (200, ack())]
        result, code = self.commands.submit(command())
        self.assertEqual((code, result["result"]), (202, "PENDING"))
        self.assertEqual(self.commands.status("hc-test-1")[0]["result"], "APPLIED")
        self.assertEqual(len(self.transport.mutations), 1)

    def test_lost_mutation_exact_duplicate_and_readback_never_resend(self):
        self.transport.responses = [UnknownMutation(), (200, ack())]
        self.assertEqual(self.commands.submit(command())[0]["result"], "UNKNOWN")
        self.assertEqual(self.commands.submit(command())[0]["result"], "UNKNOWN")
        self.assertEqual(len(self.transport.mutations), 1)
        self.assertEqual(self.commands.status("hc-test-1")[0]["result"], "APPLIED")
        self.assertEqual(len(self.transport.mutations), 1)

    def test_same_id_different_body_conflicts_without_mutation(self):
        self.transport.responses = [(202, {"v": 3, "request_id": "hc-test-1"})]
        self.commands.submit(command())
        self.assertEqual(self.commands.submit(command("disarm"))[1], 409)
        self.assertEqual(len(self.transport.mutations), 1)

    def test_wrong_ack_request_command_or_boot_is_unknown(self):
        for updates in ({"request_id": "other"}, {"command": "start"}, {"stm_boot": "123456789ABCDEF0"}, {"state_seq": None}):
            with self.subTest(updates=updates):
                self.commands = MowerV3Commands(self.rover)
                self.transport.responses = [(200, {**ack(), **updates})]
                self.assertEqual(self.commands.submit(command())[0]["result"], "UNKNOWN")

    def test_pending_over_1500_ms_is_unknown_and_only_get_is_used(self):
        self.transport.responses = [(202, {"v": 3, "request_id": "hc-test-1"}), (202, {"v": 3, "request_id": "hc-test-1"})]
        self.commands.submit(command())
        self.now += 1.6
        self.assertEqual(self.commands.status("hc-test-1")[0]["result"], "UNKNOWN")
        self.assertEqual(len(self.transport.mutations), 1)

    def test_stale_epoch_profile_gate_and_locked_update_do_not_send(self):
        cases = [(command() | {"control_epoch": 2}, {}), (command(), {"profile_crc": "00000000"}), (command(), {"update_locked": True})]
        for body, updates in cases:
            with self.subTest(updates=updates):
                self.setUp()
                self.transport.identity.update(updates)
                self.assertEqual(self.commands.submit(body)[0]["result"], "REJECTED")
                self.assertEqual(self.transport.mutations, [])

    def test_stop_has_no_identity_epoch_profile_or_ordinary_state_requirement(self):
        self.transport.identity["update_locked"] = True
        self.transport.responses = [(200, ack("stop"))]
        body = {"v": 3, "request_id": "hc-test-1"}
        self.assertEqual(self.commands.submit(body, stop=True)[0]["result"], "APPLIED")
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.transport.mutations[0], ("POST", "/api/v3/stop", body))

    def test_503_not_ready_stop_is_not_applied_or_abort(self):
        self.transport.responses = [(503, {"v": 3, "code": "NOT_READY"})]
        result, _ = self.commands.submit({"v": 3, "request_id": "hc-test-1"}, stop=True)
        self.assertEqual((result["result"], result["code"]), ("REJECTED", "NOT_READY"))
        self.assertEqual(len(self.transport.mutations), 1)

    def test_payload_extra_fields_float_bool_and_legacy_commands_reject(self):
        invalid = [command() | {"extra": 1}, command() | {"control_epoch": True}, command("route_play"),
                   command("heading_set") | {"value": {"heading_mdeg": 90.0}},
                   command("heading_set") | {"value": {"heading_mdeg": True}},
                   command("start") | {"value": {"mission_id": "0" * 32, "revision": 1, "crc32": "ABCDEF01"}}]
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.commands.submit(body)[1], 400)
        self.assertEqual(self.transport.mutations, [])

    def test_unconfigured_stop_is_definitely_not_sent(self):
        result, code = MowerV3Commands(MowerV3Service()).submit({"v": 3, "request_id": "stop-1"}, stop=True)
        self.assertEqual((code, result["code"]), (503, "UNCONFIGURED"))

    def test_full_pending_ledger_does_not_block_stop_or_replay_retired_id(self):
        for index in range(128):
            id_ = f"ordinary-{index}"
            self.transport.responses.append((202, {"v": 3, "request_id": id_}))
            self.commands.submit(command(id_=id_))
        self.assertEqual(self.commands.submit(command(id_="overflow"))[1], 429)
        self.transport.responses.append((200, ack("stop", "priority-stop")))
        self.assertEqual(self.commands.submit({"v": 3, "request_id": "priority-stop"}, stop=True)[0]["result"], "APPLIED")
        before = len(self.transport.mutations)
        self.assertEqual(self.commands.submit(command(id_="ordinary-0"))[0]["code"], "HISTORY_EXPIRED")
        self.assertEqual(len(self.transport.mutations), before)

    def test_unknown_command_is_read_only_and_not_found(self):
        self.transport.responses = [(404, {"v": 3, "code": "NOT_FOUND"})]
        self.assertEqual(self.commands.status("not-local")[0]["code"], "NOT_FOUND")
        self.assertEqual(self.transport.mutations, [])

    def test_gateway_server_error_is_unknown_not_proof_of_rejection(self):
        self.transport.responses = [(502, {"v": 3, "code": "UPSTREAM_ERROR"})]
        result, code = self.commands.submit(command())
        self.assertEqual((result["result"], code), ("UNKNOWN", 202))

    def test_snapshot_network_lock_cannot_delay_stop_service(self):
        ready = threading.Event()
        self.rover._lock.acquire()
        worker = threading.Thread(target=lambda: (self.rover.command_service(), ready.set()), daemon=True)
        worker.start()
        try:
            self.assertTrue(ready.wait(timeout=.5))
        finally:
            self.rover._lock.release()
            worker.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
