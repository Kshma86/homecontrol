"""Separate HC-only preflight/staging and explicit native session endpoints."""
from flask import Blueprint, jsonify, request
import psycopg
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from mower_firmware_service import BODY_LIMIT, FirmwareError
from mower_operator_auth import same_origin


def register_mower_firmware_routes(app, *, service, staging=None, auth=None, updates=None):
    blueprint = Blueprint("mower_firmware", __name__, url_prefix="/api/mower/v3/firmware")

    @blueprint.after_request
    def uncached(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @blueprint.errorhandler(FirmwareError)
    def invalid(error):
        data = {"ok": False, "code": error.code, "error": str(error), "upload_available": False}
        if request.endpoint in {"mower_firmware.create_session", "mower_firmware.session_action"}:
            # FirmwareError occurs only before mutation; transport uncertainty is durable.
            data["mutation_sent"] = False
        return jsonify(data), error.status

    @blueprint.errorhandler(psycopg.Error)
    def unavailable(error):
        uncertain = request.method == "POST"
        session = request.endpoint in {"mower_firmware.create_session", "mower_firmware.session_action"}
        native = session or request.endpoint in {"mower_firmware.current_session", "mower_firmware.session_request", "mower_firmware.action_request"}
        return jsonify({"ok": False, "code": "SESSION_UNKNOWN" if session else "SAVE_UNKNOWN" if uncertain else "STORAGE_UNAVAILABLE",
                        "error": "A HC-mentés eredménye ismeretlen; csak visszaolvasással egyeztethető." if uncertain else "A HC firmware-tároló nem érhető el.",
                        "upload_available": False, "rover_contacted": None if native else False}), 503

    def operator_guard():
        if auth is None or not auth.authenticated(request):
            raise FirmwareError("AUTH_REQUIRED", "A HC firmware-tárolóhoz kezelői bejelentkezés szükséges.", 401)
        if staging is None:
            raise FirmwareError("STORAGE_UNAVAILABLE", "A HC firmware-tároló nem érhető el.", 503)

    @blueprint.get("/releases")
    def releases():
        return jsonify(service.releases())

    @blueprint.post("/preflight")
    def preflight():
        return binary_request(stage=False)

    @blueprint.post("/jobs")
    def save_job():
        return binary_request(stage=True)

    @blueprint.get("/jobs")
    def jobs():
        operator_guard()
        return jsonify(staging.history())

    @blueprint.get("/jobs/requests/<request_id>")
    def saved_request(request_id):
        operator_guard()
        return jsonify(staging.request_status(request_id))

    @blueprint.get("/jobs/<job_id>")
    def job(job_id):
        operator_guard()
        return jsonify(staging.job(job_id))

    def updater_guard():
        operator_guard()
        if updates is None:
            raise FirmwareError("UPDATE_UNAVAILABLE", "A natív session-kezelés nem érhető el.", 503)

    @blueprint.get("/session")
    def current_session():
        updater_guard()
        return jsonify(updates.current())

    @blueprint.get("/sessions/requests/<request_id>")
    def session_request(request_id):
        updater_guard()
        return jsonify(updates.request_status(request_id))

    @blueprint.post("/jobs/<job_id>/session")
    def create_session(job_id):
        if not same_origin(request):
            raise FirmwareError("ORIGIN_REJECTED", "Csak a HomeControl saját oldaláról engedélyezett.", 403)
        updater_guard()
        if request.headers.get("Content-Encoding") is not None or request.headers.get("Transfer-Encoding") is not None:
            raise FirmwareError("INVALID_PAYLOAD", "Pontos, tömörítetlen JSON session-kérés szükséges.")
        from mower_v3_routes import strict_body
        try:
            body = strict_body(1024)
        except (ValueError, UnicodeError, RecursionError):
            raise FirmwareError("INVALID_PAYLOAD", "Legfeljebb 1024 bájtos, pontos JSON session-kérés szükséges.") from None
        result = updates.create(job_id, body)
        return jsonify(result), 202 if result["attempt"]["state"] in ("CREATE_INTENT", "UNKNOWN") else 200

    @blueprint.get("/operations/requests/<request_id>")
    def action_request(request_id):
        updater_guard()
        return jsonify(updates.action_status(request_id))

    @blueprint.post("/sessions/requests/<session_id>/<action>")
    def session_action(session_id, action):
        if not same_origin(request):
            raise FirmwareError("ORIGIN_REJECTED", "Csak saját HC-origin engedélyezett.", 403)
        updater_guard()
        if action not in {"image", "abort", "finish", "verify-exit"}:
            raise FirmwareError("INVALID_PAYLOAD", "Nem támogatott frissítési művelet.")
        if request.headers.get("Content-Encoding") is not None or request.headers.get("Transfer-Encoding") is not None:
            raise FirmwareError("INVALID_PAYLOAD", "Pontos, tömörítetlen JSON szükséges.")
        from mower_v3_routes import strict_body
        try:
            body = strict_body(1024)
        except (ValueError, UnicodeError, RecursionError):
            raise FirmwareError("INVALID_PAYLOAD", "Legfeljebb 1024 bájtos, pontos JSON szükséges.") from None
        result = updates.action(session_id, action.upper().replace("-", "_"), body)
        return jsonify(result)

    def binary_request(*, stage):
        if not same_origin(request):
            raise FirmwareError("ORIGIN_REJECTED", "Csak a HomeControl saját oldaláról engedélyezett.", 403)
        if stage:
            operator_guard()
        if request.mimetype != "application/octet-stream" or request.headers.get("Content-Encoding") is not None:
            raise FirmwareError("BAD_CONTENT_TYPE", "Nyers, tömörítetlen HC előellenőrzési csomag szükséges.")
        length = request.content_length
        if length is None or not 4 < length <= BODY_LIMIT or request.headers.get("Transfer-Encoding") is not None:
            raise FirmwareError("BAD_LENGTH", "Pontos Content-Length és legfeljebb 16,5 MiB + 4 bájt szükséges.", 413)
        if not service.preflight_lock.acquire(blocking=False):
            raise FirmwareError("PREFLIGHT_BUSY", "Másik fájlpár ellenőrzése folyamatban; próbáld később.", 429)
        try:
            try:
                body = request.stream.read(length + 1)
            except (BadRequest, RequestEntityTooLarge):
                raise FirmwareError("BAD_LENGTH", "A feltöltési adat hiányos vagy túl nagy.", 400) from None
            if len(body) != length:
                raise FirmwareError("BAD_LENGTH", "A feltöltési adat hossza eltér a deklarálttól.")
            if stage:
                return jsonify(staging.stage(body, request.headers.get("X-HC-Request-ID"), request.headers.get("X-HC-Release")))
            return jsonify(service.preflight(body, request.headers.get("X-HC-Release")))
        finally:
            service.preflight_lock.release()

    app.register_blueprint(blueprint)
