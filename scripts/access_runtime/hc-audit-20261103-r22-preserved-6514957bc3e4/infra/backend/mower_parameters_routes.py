"""HC-local parameter editor routes. No native rover parameter endpoints."""
from flask import Blueprint, Response, jsonify, request
import psycopg

from mower_operator_auth import same_origin
from mower_parameters_service import DraftError, LIMIT, parse_json


def register_mower_parameter_routes(app, *, service, auth):
    blueprint = Blueprint("mower_parameters", __name__, url_prefix="/api/mower/v3/parameters")

    @blueprint.after_request
    def uncached(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @blueprint.errorhandler(DraftError)
    def invalid(error):
        return jsonify({"ok": False, "code": error.code, "error": str(error), **error.data}), error.status

    @blueprint.errorhandler(psycopg.Error)
    def unavailable(error):
        uncertain = request.method == "POST" and request.endpoint.endswith("save")
        return jsonify({"ok": False, "code": "SAVE_UNKNOWN" if uncertain else "STORAGE_UNAVAILABLE",
                        "error": "A mentés eredménye ismeretlen; csak visszaolvasással egyeztethető." if uncertain else "A HC drafttároló nem érhető el."}), 503

    def origin_guard(operator=False):
        if not same_origin(request):
            raise DraftError("ORIGIN_REJECTED", "Csak a HomeControl saját oldaláról engedélyezett.", 403)
        if operator and not auth.authenticated(request):
            raise DraftError("AUTH_REQUIRED", "A HC-adatbázisba mentéshez kezelői bejelentkezés szükséges.", 401)

    def raw_body():
        if request.content_length is None or request.content_length > LIMIT:
            raise DraftError("INVALID_PAYLOAD", "A paraméteradat legfeljebb 16 KiB lehet.")
        return request.get_data(cache=False)

    def json_body():
        if request.mimetype != "application/json":
            raise DraftError("INVALID_PAYLOAD", "JSON adat szükséges.")
        return parse_json(raw_body())

    @blueprint.get("/schema")
    def schema():
        return jsonify(service.schema())

    @blueprint.get("/drafts")
    def drafts():
        return jsonify(service.list_drafts())

    @blueprint.get("/drafts/<key>")
    def latest(key):
        return jsonify(service.latest(key))

    @blueprint.get("/drafts/<key>/history")
    def history(key):
        return jsonify(service.history(key))

    @blueprint.get("/drafts/<key>/requests/<id_>")
    def request_status(key, id_):
        return jsonify(service.request_status(key, id_))

    @blueprint.get("/drafts/<key>/revisions/<int:revision>")
    def revision(key, revision):
        return jsonify(service.revision(key, revision))

    @blueprint.post("/drafts/<key>")
    def save(key):
        origin_guard(operator=True)
        result = service.save(key, json_body())
        result["read_after"] = f"/api/mower/v3/parameters/drafts/{key}"
        return jsonify(result)

    @blueprint.post("/validate")
    def validate():
        origin_guard()
        return jsonify(service.validate(json_body()))

    @blueprint.post("/import")
    def import_data():
        origin_guard()
        if request.mimetype not in ("application/json", "application/octet-stream"):
            raise DraftError("INVALID_PAYLOAD", "JSON vagy 256 bájtos RCP1 adat szükséges.")
        return jsonify(service.import_data(raw_body(), binary=request.mimetype == "application/octet-stream"))

    @blueprint.get("/drafts/<key>/revisions/<int:revision>/export.<format_>")
    def export(key, revision, format_):
        if format_ not in ("json", "rcp1", "rcp2"):
            raise DraftError("INVALID_FORMAT", "Csak JSON, RCP1 és RCP2 export támogatott.")
        if format_ in ("rcp1", "rcp2"):
            draft = service.revision(key, revision)
            if draft["parameters"]["parameters_version"] != int(format_[-1]):
                raise DraftError("INVALID_FORMAT", "Az export formátuma nem egyezik a draft adatverziójával.")
        raw = service.export(key, revision, binary=format_ in ("rcp1", "rcp2"))
        return Response(raw, mimetype="application/octet-stream" if format_ in ("rcp1", "rcp2") else "application/json",
                        headers={"Content-Disposition": f'attachment; filename="{key}-hc-r{revision}.{format_}"',
                                 "X-HC-Parameter-Source": "HC_DRAFT_NOT_APPLIED"})

    app.register_blueprint(blueprint)
