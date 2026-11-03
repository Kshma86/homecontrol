"""Side effect free probes: no lazy service creation, SQL or MQTT requests."""
from flask import jsonify

PROBE_PATHS = frozenset(('/health/live', '/health/ready', '/health/workers'))


def register_health_routes(app, existing_service):
    @app.get('/health/live')
    def health_live():
        service = existing_service()
        stopping = service is not None and service._stop.is_set()
        return jsonify({'ok': not stopping}), 503 if stopping else 200

    @app.get('/health/ready')
    def health_ready():
        service = existing_service()
        status = service.readiness() if service is not None else {'ok': False, 'reason': 'starting'}
        return jsonify(status), 200 if status['ok'] else 503

    @app.get('/health/workers')
    def health_workers():
        service = existing_service()
        status = service.liveness() if service is not None else {'ok': True, 'starting': True}
        return jsonify(status), 200 if status['ok'] else 503
