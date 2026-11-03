"""Mower-only operator sessions; rover credentials never authenticate a browser."""
import re
import secrets
import threading
import time
from collections import deque
from urllib.parse import urlsplit

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

COOKIE_NAME = "hc_mower_operator"
COOKIE_PATH = "/api/mower/v3"
SESSION_SECONDS = 3600


def same_origin(request):
    try:
        parsed = urlsplit(request.headers.get("Origin", ""))
        return (parsed.scheme in ("http", "https") and parsed.netloc == request.host
                and not parsed.username and not parsed.password and parsed.path in ("", "/")
                and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


class MowerOperatorAuth:
    def __init__(self, *, password_hash="", secret="", clock=time.monotonic, superuser=False):
        self.superuser = superuser
        self._password_hash = password_hash
        self._clock = clock
        self._lock = threading.Lock()
        self._attempts = deque(maxlen=5)
        self._sessions = {}
        self._signer = None
        if (password_hash.startswith(("scrypt:", "pbkdf2:sha256:"))
                and re.fullmatch(r"[a-fA-F0-9]{64}", secret)):
            self._signer = URLSafeTimedSerializer(secret, salt="hc-mower-v3-operator")

    @property
    def available(self):
        return self.superuser or self._signer is not None

    def authenticated(self, request):
        if self.superuser:
            return True
        if not self.available:
            return False
        try:
            data = self._signer.loads(request.cookies.get(COOKIE_NAME, ""), max_age=SESSION_SECONDS)
            nonce = data.get("nonce") if type(data) is dict else None
            with self._lock:
                expiry = self._sessions.get(nonce) if type(nonce) is str else None
                return expiry is not None and expiry > self._clock()
        except (BadSignature, SignatureExpired):
            return False

    def login(self, password):
        if self.superuser:
            return None, "AUTH_NOT_REQUIRED", 200
        if not self.available:
            return None, "AUTH_UNCONFIGURED", 503
        if type(password) is not str or not 1 <= len(password) <= 256:
            return None, "INVALID_PAYLOAD", 400
        now = self._clock()
        with self._lock:
            while self._attempts and now - self._attempts[0] >= 60:
                self._attempts.popleft()
            if len(self._attempts) >= 5:
                return None, "RATE_LIMITED", 429
            self._attempts.append(now)
        try:
            valid = check_password_hash(self._password_hash, password)
        except ValueError:
            valid = False
        if not valid:
            return None, "AUTH_FAILED", 401
        with self._lock:
            self._sessions = {key: expiry for key, expiry in self._sessions.items() if expiry > now}
            if len(self._sessions) >= 32:
                return None, "RATE_LIMITED", 429
            nonce = secrets.token_hex(16)
            self._sessions[nonce] = now + SESSION_SECONDS
        return self._signer.dumps({"nonce": nonce}), "OK", 200

    def logout(self, request):
        if self.superuser:
            return
        if not self.available:
            return
        try:
            data = self._signer.loads(request.cookies.get(COOKIE_NAME, ""), max_age=SESSION_SECONDS)
            with self._lock:
                if type(data) is dict and type(data.get("nonce")) is str:
                    self._sessions.pop(data["nonce"], None)
        except (BadSignature, SignatureExpired):
            pass

    def status(self, request):
        if self.superuser:
            return {"configured": True, "authenticated": True, "superuser": True, "session_seconds": None}
        return {"configured": self.available, "authenticated": self.authenticated(request),
                "session_seconds": SESSION_SECONDS}
