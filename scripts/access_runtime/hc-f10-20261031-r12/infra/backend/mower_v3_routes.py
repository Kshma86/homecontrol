"""Mower-only operator auth and command/WS routes; no legacy dependencies."""
import json

from flask import Response, jsonify, request

from mower_operator_auth import COOKIE_NAME, COOKIE_PATH, SESSION_SECONDS, same_origin
from mower_v3_service import MANUAL_PROTOCOL, unique_object, reject_constant


def strict_body(limit):
    if request.content_length is None or request.content_length > limit or request.mimetype != "application/json":
        raise ValueError("Invalid body")
    body = json.loads(request.get_data(cache=False), object_pairs_hook=unique_object, parse_constant=reject_constant)
    if type(body) is not dict:
        raise ValueError("Invalid body")
    return body


def register_mower_v3_controls(app, *, rover, auth, relay):
    def guard():
        if not same_origin(request):
            return jsonify({"ok": False, "code": "ORIGIN_REJECTED", "error": "Csak a HomeControl saját oldaláról engedélyezett."}), 403
        if not auth.authenticated(request):
            return jsonify({"ok": False, "code": "AUTH_REQUIRED", "error": "Kezelői bejelentkezés szükséges."}), 401
        return None

    @app.get("/api/mower/v3/operator")
    def mower_v3_operator():
        response = jsonify({"ok": True, **auth.status(request)})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/mower/v3/operator/login")
    def mower_v3_login():
        if not same_origin(request):
            return jsonify({"ok": False, "code": "ORIGIN_REJECTED"}), 403
        if getattr(auth, "superuser", False):
            return jsonify({"ok": True, **auth.status(request)})
        try:
            body = strict_body(1024)
            if set(body) != {"password"}:
                raise ValueError()
        except (ValueError, UnicodeError):
            return jsonify({"ok": False, "code": "INVALID_PAYLOAD"}), 400
        cookie, code, status = auth.login(body["password"])
        response = jsonify({"ok": cookie is not None, "code": code})
        response.headers["Cache-Control"] = "no-store"
        if cookie:
            response.set_cookie(COOKIE_NAME, cookie, max_age=SESSION_SECONDS, httponly=True,
                                samesite="Strict", secure=request.is_secure or request.headers.get("Origin", "").startswith("https://"), path=COOKIE_PATH)
        return response, status

    @app.post("/api/mower/v3/operator/logout")
    def mower_v3_logout():
        denied = guard()
        if denied:
            return denied
        auth.logout(request)
        response = jsonify({"ok": True})
        response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)
        return response

    def command_route(stop=False):
        denied = guard()
        if denied:
            return denied
        try:
            body = strict_body(1024)
        except (ValueError, UnicodeError):
            return jsonify({"ok": False, "code": "INVALID_PAYLOAD", "error": "Hibás JSON parancs."}), 400
        payload, code = rover.command_service().submit(body, stop=stop)
        return jsonify(payload), code

    app.add_url_rule("/api/mower/v3/command", "mower_v3_command", lambda: command_route(), methods=["POST"])
    app.add_url_rule("/api/mower/v3/stop", "mower_v3_stop", lambda: command_route(True), methods=["POST"])

    @app.get("/api/mower/v3/command/<id_>")
    def mower_v3_command_result(id_):
        if not auth.authenticated(request):
            return jsonify({"ok": False, "code": "AUTH_REQUIRED"}), 401
        payload, code = rover.command_service().status(id_)
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store"
        return response, code

    @app.route("/api/mower/v3/manual", websocket=True)
    def mower_v3_manual():
        denied = guard()
        if denied:
            return denied
        if getattr(rover, "read_only", False) and not getattr(rover, "motor_test_enabled", False):
            return jsonify({"ok": False, "code": "READ_ONLY"}), 403
        if request.headers.get("Sec-WebSocket-Protocol") != MANUAL_PROTOCOL:
            return jsonify({"ok": False, "code": "INCOMPATIBLE_VERSION"}), 400
        from mower_manual_service import browser_socket
        browser = browser_socket(request.environ)
        # Snapshot the request; relay loop rechecks revocation/expiry each iteration.
        relay.run(browser, lambda: auth.authenticated(request))
        class WebSocketResponse(Response):
            def __call__(self, *args, **kwargs):
                if browser.mode == "gunicorn":
                    raise StopIteration()
                return super().__call__(*args, **kwargs)
        return WebSocketResponse()
