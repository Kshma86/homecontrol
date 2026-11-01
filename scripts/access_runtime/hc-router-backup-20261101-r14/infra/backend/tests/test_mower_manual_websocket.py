"""Loopback-only WebSocket integration; never imports the production app."""
import json
import queue
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import websocket
from flask import Flask, request
from werkzeug.serving import make_server, WSGIRequestHandler
from werkzeug.security import generate_password_hash
from mower_manual_service import ManualRelay, browser_socket, connect_rover
from mower_operator_auth import COOKIE_NAME, MowerOperatorAuth
from mower_v3_routes import register_mower_v3_controls
from mower_v3_service import MowerV3Service, MANUAL_PROTOCOL
from tests.test_mower_v3_service import Transport
from tests.test_mower_manual_service import claim, claimed, drive


class QuietHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass


class Upstream:
    def __init__(self):
        self.sent = []
        self.responses = queue.Queue()
        self.released = threading.Event()

    def send(self, raw):
        frame = json.loads(raw)
        self.sent.append(frame)
        if frame["type"] == "claim":
            self.responses.put(json.dumps(claimed()))
        elif frame["type"] == "drive":
            self.responses.put(json.dumps({"type": "observed", "lease_id": 7, "last_input_seq": frame["seq"],
                                           "state": "MANUAL", "stopped": not frame["deadman"]}))
        elif frame["type"] == "release":
            self.released.set()

    def recv(self):
        try:
            return self.responses.get(timeout=.05)
        except queue.Empty:
            raise TimeoutError() from None

    def shutdown(self):
        pass


class ManualWebSocketTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        transport = Transport()
        transport.state.update(state="IDLE", armed=True, stopped=True)
        self.rover = MowerV3Service(transport=transport)
        self.auth = MowerOperatorAuth(password_hash=generate_password_hash("test-only", method="pbkdf2:sha256:1000"), secret="ab" * 32)
        self.cookie = self.auth.login("test-only")[0]
        self.upstream = Upstream()
        self.relay = ManualRelay(self.rover, connector=lambda: self.upstream)
        register_mower_v3_controls(self.app, rover=self.rover, auth=self.auth, relay=self.relay)

        @self.app.route("/fake-native", websocket=True)
        def fake_native():
            # Test the *outgoing* backend transport with synthetic credentials.
            self.assertEqual(request.headers.get("Authorization"), "Bearer " + "cd" * 32)
            socket = browser_socket(request.environ)
            socket.send("x" * 600)
            socket.close()
            return ""

        self.server = make_server("127.0.0.1", 0, self.app, threaded=True, request_handler=QuietHandler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def connect(self, authenticated=True, protocol=MANUAL_PROTOCOL):
        client = websocket.create_connection(f"ws://127.0.0.1:{self.port}/api/mower/v3/manual", timeout=2,
            subprotocols=[protocol], origin=f"http://127.0.0.1:{self.port}", http_no_proxy=["*"],
            cookie=f"{COOKIE_NAME}={self.cookie}" if authenticated else None)
        self.clients.append(client)
        return client

    def activate(self):
        client = self.connect()
        self.assertEqual(client.subprotocol, MANUAL_PROTOCOL)
        client.send(json.dumps(claim()))
        self.assertEqual(json.loads(client.recv()), claimed())
        return client

    def test_auth_and_protocol_reject_before_upgrade_or_native_contact(self):
        with self.assertRaises(websocket.WebSocketBadStatusException) as error:
            self.connect(authenticated=False)
        self.assertEqual(error.exception.status_code, 401)
        with self.assertRaises(websocket.WebSocketBadStatusException) as error:
            self.connect(protocol="legacy-manual")
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(self.upstream.sent, [])

    def test_real_upgrade_timestamped_drive_zero_and_matching_disconnect_release(self):
        client = self.activate()
        client.send(json.dumps(drive()))
        self.assertEqual(json.loads(client.recv())["last_input_seq"], 1)
        client.send(json.dumps(drive(2, False)))
        observed = json.loads(client.recv())
        self.assertTrue(observed["stopped"])
        self.assertEqual(observed["last_input_seq"], 2)
        client.close()
        self.assertTrue(self.upstream.released.wait(timeout=2))
        self.assertEqual([frame["type"] for frame in self.upstream.sent], ["claim", "drive", "drive", "release"])

    def test_logout_revocation_closes_existing_socket_without_global_stop(self):
        client = self.activate()
        self.auth.logout(SimpleNamespace(cookies={COOKIE_NAME: self.cookie}))
        self.assertTrue(self.upstream.released.wait(timeout=2))
        self.assertEqual([frame["type"] for frame in self.upstream.sent], ["claim", "release"])

    def test_only_one_authenticated_browser_can_own_manual_relay(self):
        first = self.activate()
        second = self.connect()
        self.assertEqual(json.loads(second.recv())["code"], "BUSY")
        self.assertEqual([frame["type"] for frame in self.upstream.sent], ["claim"])
        first.close()
        self.assertTrue(self.upstream.released.wait(timeout=2))

    def test_binary_input_cannot_become_motion(self):
        client = self.activate()
        client.send_binary(json.dumps(drive()).encode("ascii"))
        try:
            client.recv()
        except websocket.WebSocketException:
            pass
        self.assertTrue(self.upstream.released.wait(timeout=2))
        self.assertFalse(any(frame["type"] == "drive" for frame in self.upstream.sent))

    def test_backend_transport_rejects_oversized_upstream_before_json_decode(self):
        client = connect_rover(f"ws://127.0.0.1:{self.port}/fake-native", "cd" * 32)
        self.clients.append(client)
        with self.assertRaises(websocket.WebSocketProtocolException):
            client.recv()


if __name__ == "__main__":
    unittest.main()
