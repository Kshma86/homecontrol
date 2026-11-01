"""Authenticated, timestamped latest-only manual relay. No generated motion frames."""
import json
import logging
import threading
import time
from collections import deque

from mower_v3_commands import request_id
from mower_v3_service import MANUAL_PROTOCOL, STATES, RoverReadError, integer, require, unique_object, reject_constant


def decode_frame(raw):
    require(type(raw) is str and len(raw.encode("utf-8")) <= 512)
    try:
        payload = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except ValueError:
        require(False)
    require(type(payload) is dict)
    return payload


def claim_ready(snapshot):
    identity, state = snapshot.get('identity') or {}, snapshot.get('state') or {}
    direct = identity.get('mode') == 'MOTOR_TEST' and identity.get('manual_claim_from_disarmed') is True and identity.get('test_manual_control') is True
    return bool(snapshot.get('capabilities', {}).get('manual')
                and (not identity.get('update_locked') or identity.get('mode') == 'MOTOR_TEST' and snapshot['capabilities'].get('manual_erpm') is True)
                and (state.get('state') in ('DISARMED', 'IDLE') if direct else state.get('state') == 'IDLE' and state.get('stopped') is True)
                and state.get('store') not in ('RECEIVING', 'VALIDATING'))


class ManualSession:
    def __init__(self, snapshot, *, clock=time.monotonic):
        self.clock = clock
        self.snapshot = snapshot
        self.at = clock()
        self.phase = "NEW"
        self.lease = None
        self.seq = 0
        self.sent_seq = 0
        self.claim_id = None

    def client(self, payload, received_at):
        kind = payload.get("type")
        if kind in ("drive", "drive_erpm"):
            require(self.clock() - received_at <= .1)
        elif kind == "claim":
            require(self.clock() - received_at <= 1.5)
        if kind == "claim":
            require(self.phase == "NEW" and set(payload) == {"type", "request_id", "esp_boot", "stm_boot", "control_epoch"})
            identity, state = self.snapshot.get("identity"), self.snapshot.get("state")
            require(identity is not None and state is not None and self.snapshot["freshness"]["fresh"]
                    and self.snapshot["freshness"]["effective_age_ms"] + (self.clock() - self.at) * 1000 <= 1500)
            require(claim_ready(self.snapshot))
            require(request_id(payload["request_id"]) and
                    integer(payload["control_epoch"], 1) and
                    (payload["esp_boot"], payload["stm_boot"], payload["control_epoch"]) ==
                    (identity["esp_boot"], identity["stm_boot"], state["control_epoch"]))
            self.phase, self.claim_id = "CLAIMING", payload["request_id"]
            return payload
        require(self.phase == "ACTIVE" and self.lease is not None)
        require(type(payload.get("lease_id")) is int and payload["lease_id"] == self.lease["lease_id"]
                and type(payload.get("control_epoch")) is int and payload["control_epoch"] == self.lease["control_epoch"])
        if kind == "release":
            require(set(payload) == {"type", "lease_id", "control_epoch"})
            self.phase = "RELEASED"
            self.lease = None
            return payload
        require(kind in ("drive", "drive_erpm", "stop") and integer(payload.get("seq"), 1) and payload["seq"] > self.seq)
        if kind == "stop":
            require(set(payload) == {"type", "lease_id", "control_epoch", "seq"})
        elif kind == "drive_erpm":
            require(self.lease.get("drive_mode") == "ERPM")
            require(set(payload) == {"type", "lease_id", "control_epoch", "seq", "left_erpm", "right_erpm", "third_erpm", "deadman"})
            targets = [payload[key] for key in ("left_erpm", "right_erpm", "third_erpm")]
            require(type(payload["deadman"]) is bool and all(integer(value, -limit, limit)
                    for value, limit in zip(targets, self.lease["motor_erpm_limits"])))
            require(payload["deadman"] or targets == [0, 0, 0])
        else:
            require(self.lease.get("drive_mode") != "ERPM")
            require(set(payload) == {"type", "lease_id", "control_epoch", "seq", "linear_mm_s", "yaw_mdeg_s", "blade_rpm", "deadman"})
            require(integer(payload["linear_mm_s"], -self.lease["max_linear_mm_s"], self.lease["max_linear_mm_s"]))
            require(integer(payload["yaw_mdeg_s"], -self.lease["max_yaw_mdeg_s"], self.lease["max_yaw_mdeg_s"]))
            # Cutter controls need a separately verified profile/feedback UI.
            require(type(payload["blade_rpm"]) is int and payload["blade_rpm"] == 0 and type(payload["deadman"]) is bool)
            require(payload["deadman"] or payload["linear_mm_s"] == payload["yaw_mdeg_s"] == 0)
        self.seq = payload["seq"]
        return payload

    def server(self, payload):
        kind = payload.get("type")
        if kind == "claimed":
            base = {"type", "lease_id", "control_epoch", "lease_ms", "max_linear_mm_s", "max_yaw_mdeg_s"}
            extended = set(payload) == base | {"drive_mode", "motor_erpm_limits"}
            erpm = extended and payload.get("drive_mode") == "ERPM"
            require(self.phase == "CLAIMING" and (set(payload) == base or extended))
            if extended:
                require(payload.get("drive_mode") in ("ERPM", "METRIC"))
            require(integer(payload["lease_id"], 1) and integer(payload["control_epoch"], 1)
                    and type(payload["lease_ms"]) is int and payload["lease_ms"] == 350)
            if erpm:
                p = None if self.snapshot.get("simple_control") else (self.snapshot.get("parameters") or {}).get("parameters")
                expected_limits = (p["wheel_erpm_limit"] + [p["blade_erpm_limit"] if p["blade_enabled"] else 0]) if p else [6000,6000,25000]
                require(payload["drive_mode"] == "ERPM" and type(payload["motor_erpm_limits"]) is list
                        and len(payload["motor_erpm_limits"]) == 3
                        and all(integer(limit, 0, cap) for limit, cap in zip(payload["motor_erpm_limits"], expected_limits))
                        and all(limit > 0 for limit in payload["motor_erpm_limits"][:2])
                        and integer(payload["max_linear_mm_s"], 0, 0) and integer(payload["max_yaw_mdeg_s"], 0, 0))
            else:
                require(integer(payload["max_linear_mm_s"], 1, 65535) and integer(payload["max_yaw_mdeg_s"], 1, 360000))
                if extended:
                    require(type(payload["motor_erpm_limits"]) is list and len(payload["motor_erpm_limits"]) == 3
                        and all(integer(value,0,cap) for value,cap in zip(payload["motor_erpm_limits"],[6000,6000,25000])))
            delta = (payload["control_epoch"] - self.snapshot["state"]["control_epoch"]) & 0xFFFFFFFF
            require(0 < delta < 0x80000000)
            self.lease, self.phase = payload.copy(), "ACTIVE"
        elif kind == "observed":
            require(set(payload) == {"type", "lease_id", "last_input_seq", "state", "stopped"})
            require(integer(payload["lease_id"]) and integer(payload["last_input_seq"])
                    and type(payload["state"]) is str and payload["state"] in STATES and type(payload["stopped"]) is bool)
            if self.lease is None:
                # Native idle telemetry can precede claim/claimed; it grants no authority.
                require(self.phase in ("NEW", "CLAIMING"))
            else:
                ended = payload["lease_id"] == 0 and payload["last_input_seq"] == 0 and payload["state"] != "MANUAL"
                require(ended or payload["lease_id"] == self.lease["lease_id"] and payload["last_input_seq"] <= self.sent_seq)
                if payload["state"] != "MANUAL":
                    self.phase = "ENDED"
        elif kind == "error":
            import re
            require(set(payload) == {"type", "code", "detail"} and type(payload["code"]) is str
                    and re.fullmatch(r"[A-Z_]{1,32}", payload["code"]) is not None and integer(payload["detail"]))
            self.phase = "ENDED"
        else:
            require(False)
        return payload

    def release_frame(self):
        return ({"type": "release", "lease_id": self.lease["lease_id"], "control_epoch": self.lease["control_epoch"]}
                if self.lease is not None else None)


class TimedBuffer:
    """Timestamp at WS message receipt, not at delayed application dequeue."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._queue = deque()
        self._arrivals = deque()
        self._lock = threading.Lock()

    def append(self, raw):
        from wsproto.utilities import LocalProtocolError
        now = self.clock()
        with self._lock:
            while self._arrivals and now - self._arrivals[0] >= 1:
                self._arrivals.popleft()
            if len(self._queue) >= 4 or len(self._arrivals) >= 40 or not isinstance(raw, str) or len(raw.encode("utf-8")) > 512:
                raise LocalProtocolError("Mower WS input limit exceeded")
            self._arrivals.append(now)
            self._queue.append((now, raw))

    def pop(self, index):
        with self._lock:
            return self._queue.popleft()

    def __len__(self):
        with self._lock:
            return len(self._queue)


def browser_socket(environ):
    from simple_websocket import Server
    class TimestampedServer(Server):
        @property
        def input_buffer(self):
            return self._timed_buffer

        @input_buffer.setter
        def input_buffer(self, value):
            self._timed_buffer = TimedBuffer()
    return TimestampedServer.accept(environ, subprotocols=[MANUAL_PROTOCOL], max_message_size=512)


def connect_rover(url, token):
    import websocket
    from websocket._abnf import frame_buffer, continuous_frame
    class BoundedFrames(frame_buffer):
        def recv_length(self):
            super().recv_length()
            if self.length > 512:
                raise websocket.WebSocketProtocolException("Oversized rover frame")
    class BoundedMessage(continuous_frame):
        def add(self, frame):
            if len(frame.data) + (len(self.cont_data[1]) if self.cont_data else 0) > 512:
                raise websocket.WebSocketProtocolException("Oversized rover message")
            super().add(frame)
    class BoundedSocket(websocket.WebSocket):
        def recv_frame(self):
            frame = super().recv_frame()
            if frame.opcode == websocket.ABNF.OPCODE_CLOSE:
                import struct
                self.native_close_code = struct.unpack("!H", frame.data[:2])[0] if len(frame.data) >= 2 else 1005
            return frame
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.frame_buffer = BoundedFrames(self._recv, False)
            self.cont_frame = BoundedMessage(False, False)
    connection = websocket.create_connection(url, timeout=1.5, class_=BoundedSocket,
        subprotocols=[MANUAL_PROTOCOL], header={"Authorization": "Bearer " + token},
        suppress_origin=True, redirect_limit=0, http_no_proxy=["*"], enable_multithread=True)
    if connection.status != 101 or connection.subprotocol != MANUAL_PROTOCOL:
        connection.shutdown()
        raise RoverReadError("INCOMPATIBLE_VERSION", "A rover kézi protokollja eltér.")
    connection.settimeout(.05)
    return connection


class ManualRelay:
    def __init__(self, rover, *, connector=None, clock=time.monotonic):
        self.rover, self.connector, self.clock = rover, connector or rover.manual_socket, clock
        self._owner = threading.Lock()

    @property
    def active(self):
        return self._owner.locked()

    def run(self, browser, authorized):
        if not self._owner.acquire(blocking=False):
            browser.send(json.dumps({"type": "error", "code": "BUSY", "detail": 0}))
            browser.close()
            return
        upstream, session = None, None
        stage = "admission"
        try:
            if not authorized():
                raise RoverReadError("AUTH_REQUIRED", "")
            with self.rover.ordinary_operation():
                if not self.rover._lock.acquire(timeout=1.0):
                    raise RoverReadError("BUSY", "Állapotlekérdezés folyamatban van.")
                try:
                    snapshot = self.rover.snapshot()
                finally:
                    self.rover._lock.release()
                if not snapshot["freshness"]["fresh"] or not claim_ready(snapshot):
                    raise RoverReadError("CLAIM_NOT_READY", "A rover aktuális állapota nem enged kézi módot.")
                session = ManualSession(snapshot, clock=self.clock)
                stage = "native_handshake"
                upstream = self.connector()
            require(browser.subprotocol == MANUAL_PROTOCOL)
            deadline = self.clock() + 1.5
            while authorized():
                pending = None
                # Drain arrivals first: one latest unsent drive, no historical queue.
                for _ in range(20):
                    stage = "browser_receive"
                    item = browser.receive(timeout=0)
                    if item is None:
                        break
                    at, raw = item
                    stage = "browser_frame"
                    decoded = decode_frame(raw)
                    if decoded.get("type") in ("drive", "drive_erpm") and self.clock() - at > .1:
                        continue
                    try:
                        frame = session.client(decoded, at)
                    except RoverReadError:
                        logging.getLogger(__name__).warning("Manual browser frame rejected: phase=%s claim_epoch=%s frame_type=%s frame_epoch=%s", session.phase, session.snapshot['state']['control_epoch'], decoded.get('type'), decoded.get('control_epoch'))
                        raise
                    if frame["type"] in ("drive", "drive_erpm") and frame["deadman"]:
                        pending = at, frame
                    else:
                        pending = None
                        upstream.send(json.dumps(frame, separators=(",", ":")))
                        if "seq" in frame:
                            session.sent_seq = frame["seq"]
                if session.phase == "RELEASED":
                    break
                if pending and self.clock() - pending[0] <= .1:
                    upstream.send(json.dumps(pending[1], separators=(",", ":")))
                    session.sent_seq = pending[1]["seq"]
                if session.phase in ("NEW", "CLAIMING") and self.clock() > deadline:
                    raise RoverReadError("TIMEOUT", "")
                try:
                    stage = "native_receive"
                    raw = upstream.recv()
                except TimeoutError:
                    continue
                except Exception as error:
                    # websocket-client's timeout is not a built-in TimeoutError.
                    from websocket import WebSocketTimeoutException
                    if isinstance(error, WebSocketTimeoutException):
                        continue
                    raise
                if raw == "":
                    native_code = getattr(upstream, "native_close_code", 1005)
                    logging.getLogger(__name__).warning("Manual native socket closed: phase=%s close_code=%s sent_seq=%s", session.phase, native_code, session.sent_seq)
                    browser.send(json.dumps({"type":"error", "code":"ROVER_SOCKET_CLOSED", "detail":native_code}))
                    break
                stage = "native_decode"
                try:
                    decoded = decode_frame(raw)
                except RoverReadError:
                    logging.getLogger(__name__).warning("Manual native decode rejected: raw_type=%s length=%s", type(raw).__name__, len(raw) if isinstance(raw,(str,bytes)) else None)
                    raise
                stage = "native_frame"
                try:
                    payload = session.server(decoded)
                except RoverReadError:
                    diagnostic = {key: decoded[key] for key in ("type", "lease_id", "control_epoch", "lease_ms", "max_linear_mm_s", "max_yaw_mdeg_s", "drive_mode", "motor_erpm_limits", "last_input_seq", "state", "stopped", "code", "detail") if key in decoded}
                    logging.getLogger(__name__).warning("Manual native reply rejected: phase=%s claim_epoch=%s sent_seq=%s keys=%s frame=%s", session.phase, session.snapshot['state']['control_epoch'], session.sent_seq, sorted(decoded), json.dumps(diagnostic)[:1024])
                    raise RoverReadError("INVALID_ROVER_REPLY", "A natív kézi válasz nem illeszkedik a HC szerződéséhez.") from None
                browser.send(json.dumps(payload, separators=(",", ":")))
                if session.phase == "ENDED":
                    break
        except Exception as error:
            code = error.code if isinstance(error, RoverReadError) else "LINK_LOST"
            import re
            message = re.sub(r"[0-9a-fA-F]{64}", "[redacted]", str(error))[:256]
            logging.getLogger(__name__).warning("Manual relay ended: stage=%s phase=%s code=%s exception=%s message=%s", stage, session.phase if session else None, code, type(error).__name__, message)
            try:
                browser.send(json.dumps({"type": "error", "code": code, "detail": 0}))
            except Exception:
                pass
        finally:
            if upstream is not None:
                try:
                    frame = session.release_frame() if session else None
                    if frame:
                        upstream.send(json.dumps(frame, separators=(",", ":")))
                except Exception:
                    pass
                try:
                    upstream.shutdown()
                except Exception:
                    pass
            try:
                browser.close()
            except Exception:
                pass
            self._owner.release()
