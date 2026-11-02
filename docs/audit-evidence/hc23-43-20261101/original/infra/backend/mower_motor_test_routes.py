"""Operator-only supervised test writes; native reconciliation always GET."""
from flask import Blueprint, jsonify, request
from mower_operator_auth import same_origin
from mower_parameters_service import DraftError, parse_json
from mower_v3_service import RoverReadError


def register_motor_test_routes(app, *, service, auth):
    bp = Blueprint("mower_motor_test", __name__, url_prefix="/api/mower/v3/motor-test")

    @bp.after_request
    def uncached(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.errorhandler(DraftError)
    def draft_error(error):
        return jsonify({"ok": False, "code": error.code, "error": str(error), **error.data}), error.status

    @bp.errorhandler(RoverReadError)
    def rover_error(error):
        return jsonify(ok=False, code=error.code, error=str(error)), 409

    def guard(write=False):
        if write and not same_origin(request):
            raise DraftError("ORIGIN_REJECTED", "Csak a HC saját oldaláról engedélyezett.", 403)
        if not auth.authenticated(request):
            raise DraftError("AUTH_REQUIRED", "Kezelői bejelentkezés szükséges.", 401)

    @bp.get("/initial")
    def initial():
        return jsonify(service.initial())

    @bp.get("/config")
    def configuration():
        return jsonify(service.configuration())

    @bp.post("/config")
    def save_configuration():
        guard(True)
        if request.mimetype != "application/json" or request.content_length is None or request.content_length > 16384:
            raise DraftError("INVALID_PAYLOAD", "Legfeljebb 16 KiB JSON konfiguráció szükséges.")
        body = parse_json(request.get_data(cache=False))
        if set(body) != {"parameters"}:
            raise DraftError("INVALID_PAYLOAD", "Teljes konfiguráció szükséges.")
        return jsonify(service.save_configuration(body["parameters"]))

    @bp.get("/status")
    def status():
        guard()
        return jsonify(service.status())

    @bp.post("/apply")
    def apply():
        guard(True)
        if (request.mimetype != "application/json" or request.content_length is None or request.content_length > 2048
                or request.headers.get("Transfer-Encoding")):
            raise DraftError("INVALID_PAYLOAD", "Legfeljebb 2048 bájt JSON szükséges.")
        payload, code = service.apply(parse_json(request.get_data(cache=False)))
        return jsonify(payload), code

    @bp.get("/reconcile")
    def reconcile():
        guard()
        try:
            body = {key: request.args[key] for key in ("request_id", "esp_boot", "stm_boot", "parameters_crc")}
            revision = request.args["expected_revision"]
            if not revision.isascii() or not revision.isdecimal() or len(revision) > 10:
                raise ValueError()
            body["expected_revision"] = int(revision)
        except (KeyError, ValueError):
            raise DraftError("INVALID_PAYLOAD", "Hiányos Apply egyeztetés.") from None
        return jsonify(service.reconcile(body))

    app.register_blueprint(bp)
