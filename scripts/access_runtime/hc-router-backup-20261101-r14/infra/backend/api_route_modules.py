import subprocess
import threading
import time
import json
from typing import Any, Callable, Iterable

from context_payload_service import compact_context_payload
from flask import jsonify, request
from system_status_service import docker_socket_containers, docker_socket_request


ADMIN_RESTART_CONTAINERS = {
    "backend": "homecontrol-backend",
    "frontend": "homecontrol-frontend",
    "postgres": "homecontrol-postgres",
    "pgbouncer": "homecontrol-pgbouncer",
    "mqtt": "homecontrol-mqtt",
    "zigbee2mqtt": "zigbee2mqtt",
    "ingest": "homecontrol-ingest",
    "tuya": "homecontrol-tuya-poller",
    "x10": "homecontrol-xiaomi-x10",
    "climate": "homecontrol-gree-climate",
    "solar": "homecontrol-ha-growatt-poller",
    "ai": "homecontrol-ai-server",
    "proxy": "homecontrol-proxy",
    "mdns": "homecontrol-mdns",
}


def register_context_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_command_service: Callable[[], Any],
    parse_context_sections: Callable[[str], Any],
    json_ready: Callable[[Any], Any],
    default_context_sections: Iterable[str],
) -> None:
    @app.get("/api/context")
    def context_snapshot():
        sections = parse_context_sections(request.args.get("sections", ""))
        full = request.args.get("full", "").strip().lower() in {"1", "true", "yes", "on"}
        default_snapshot = sections is None and not full
        if sections is None and not full:
            sections = list(default_context_sections)
        force = request.args.get("force", "").strip().lower() in {"1", "true", "yes", "on"}
        payload = get_context_service().snapshot(sections=sections, force=force)
        if default_snapshot:
            payload = compact_context_payload(payload)
            all_sections = list(get_context_service().builders.keys())
            payload["default_sections"] = list(default_context_sections)
            payload["omitted_sections"] = [section for section in all_sections if section not in default_context_sections]
            payload["full_context_url"] = "/api/context?full=1"
        return jsonify(json_ready(payload)), 200 if payload.get("ok") else 207

    @app.get("/api/context/<section>")
    def context_section(section: str):
        force = request.args.get("force", "").strip().lower() in {"1", "true", "yes", "on"}
        payload = get_context_service().section(section, force=force)
        return jsonify(json_ready(payload)), 200 if payload.get("ok") else 404

    @app.get("/api/context/ai/summary")
    def context_ai_summary():
        force = request.args.get("force", "").strip().lower() in {"1", "true", "yes", "on"}
        payload = get_context_service().ai_summary(force=force)
        return jsonify(json_ready(payload)), 200 if payload.get("ok") else 207

    @app.post("/api/context/invalidate")
    def context_invalidate():
        body = request.get_json(force=True, silent=True) or {}
        section = str(body.get("section") or "").strip() or None
        return jsonify(get_context_service().invalidate(section)), 200

    @app.get("/api/context/events")
    def context_events():
        limit = request.args.get("limit")
        return jsonify({"ok": True, "events": get_command_service().recent_events(limit)}), 200


def register_mower_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_mower_service: Callable[[], Any],
    get_admin_service: Callable[[], Any],
    json_ready: Callable[[Any], Any],
    get_mower_v3_service: Callable[[], Any] = None,
) -> None:
    @app.get("/api/mower/v3/snapshot")
    def mower_v3_snapshot():
        if get_mower_v3_service is None:
            return jsonify({"ok": False, "error": "Mower v3 service unavailable"}), 503
        started = time.monotonic()
        response = jsonify(json_ready(get_mower_v3_service().snapshot()))
        response.headers["Server-Timing"] = f"rover;dur={(time.monotonic()-started)*1000:.3f}"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/mower/state")
    def mower_state():
        return jsonify(json_ready(get_context_service().section("mower")))

    @app.post("/api/mower/command")
    def mower_command():
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_mower_service().command(data)
        return jsonify(json_ready(payload)), status

    @app.get("/api/mower/mission/status")
    def mower_mission_status():
        payload, status = get_mower_service().mission_status()
        return jsonify(json_ready(payload)), status

    @app.post("/api/mower/mission/deploy")
    def mower_mission_deploy():
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_mower_service().mission_deploy(data)
        if status >= 400 or payload.get("ok") is False:
            app.logger.warning(
                "mower mission deploy failed status=%s stage=%s code=%s payload=%s",
                status,
                payload.get("stage"),
                payload.get("code"),
                json.dumps(payload, ensure_ascii=False, default=str)[:4000],
            )
        return jsonify(json_ready(payload)), status

    @app.post("/api/mower/mission/<action>")
    def mower_mission_action(action):
        payload, status = get_mower_service().mission_action(action)
        return jsonify(json_ready(payload)), status

    @app.get("/api/mower/firmware/status")
    def mower_firmware_status():
        payload, status = get_mower_service().firmware_status()
        return jsonify(json_ready(payload)), status

    @app.post("/api/mower/firmware/upload")
    def mower_firmware_upload():
        upload = request.files.get("firmware")
        if upload is None:
            return jsonify({"ok": False, "error": "missing firmware file"}), 400
        payload, status = get_mower_service().firmware_upload(upload.filename or "firmware.bin", upload.read())
        return jsonify(json_ready(payload)), status

    @app.post("/api/mower/firmware/<action>")
    def mower_firmware_action(action: str):
        payload, status = get_mower_service().firmware_action(action)
        return jsonify(json_ready(payload)), status

    @app.get("/api/mower/route")
    def mower_route_status():
        payload, status = get_mower_service().route_status()
        return jsonify(json_ready(payload)), status

    @app.post("/api/mower/route/<action>")
    def mower_route_action(action: str):
        payload, status = get_mower_service().route_action(action)
        return jsonify(json_ready(payload)), status

    @app.get("/api/mower/notes")
    def mower_notes_state():
        return jsonify({"ok": True, **get_admin_service().fetch_notes("mower")})

    @app.post("/api/mower/notes")
    def mower_notes_create():
        data = request.get_json(force=True, silent=True) or {}
        data["scope"] = "mower"
        try:
            result = get_admin_service().create_note(data)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(json_ready(result)), 201

    @app.put("/api/mower/notes/<int:note_id>")
    def mower_notes_update(note_id: int):
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_admin_service().update_note(note_id, data, "mower")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not result:
            return jsonify({"ok": False, "error": "mower note not found"}), 404
        return jsonify(json_ready(result))

    @app.delete("/api/mower/notes/<int:note_id>")
    def mower_notes_delete(note_id: int):
        result = get_admin_service().delete_note(note_id, "mower")
        if not result:
            return jsonify({"ok": False, "error": "mower note not found"}), 404
        return jsonify(json_ready(result))


def register_page_usage_routes(app, *, get_page_usage_service: Callable[[], Any]) -> None:
    @app.post("/api/page-usage/event")
    def page_usage_event():
        body = request.get_json(force=True, silent=True) or {}
        page_id = str(body.get("page_id") or "").strip()[:80]
        client_id = str(body.get("client_id") or "").strip()[:80]
        device_class = str(body.get("device_class") or "unknown").strip()[:20]
        if not page_id or not client_id:
            return jsonify({"ok": False, "error": "page_id and client_id are required"}), 400
        get_page_usage_service().record({
            "page_id": page_id,
            "client_id": client_id,
            "device_class": device_class,
            "viewport_width": body.get("viewport_width"),
            "viewport_height": body.get("viewport_height"),
            "standalone": body.get("standalone") is True,
            "user_agent": str(body.get("user_agent") or "")[:300],
        })
        return jsonify({"ok": True}), 201

    @app.get("/api/page-usage/summary")
    def page_usage_summary():
        return jsonify(get_page_usage_service().summary(request.args.get("days", 30))), 200


def register_ai_routes(
    app,
    *,
    get_ai_proxy_service: Callable[[], Any],
    get_ai_node_service: Callable[[], Any],
) -> None:
    @app.get("/api/ai/status")
    def ai_status():
        payload, status = get_ai_proxy_service().status()
        return jsonify(payload), status

    @app.post("/api/ai/restart")
    def ai_restart():
        service = get_ai_proxy_service()
        service.clear_knowledge_cache()
        service.clear_status_cache()
        try:
            response, _ = docker_socket_request("POST", "/containers/homecontrol-ai-server/restart?t=10", timeout=20)
        except RuntimeError as exc:
            return jsonify({"ok": False, "cache_cleared": True, "error": f"AI gateway restart failed: {exc}"}), 502

        receipt = json.loads(response)
        return jsonify({"ok": True, "cache_cleared": True, "ready": False, **receipt}), 202

    @app.get("/api/ai/node/status")
    def ai_node_status():
        return jsonify(get_ai_node_service().health()), 200

    @app.post("/api/ai/node/wake")
    def ai_node_wake():
        service = get_ai_node_service()
        body = request.get_json(silent=True) or {}
        try:
            payload, status = service.wake(body.get('backup_run_id'))
        except (ValueError, OSError):
            return jsonify({'ok': False, 'error': 'AI power guard is unavailable; wake was not dispatched'}), 503
        return jsonify(payload), status

    @app.post("/api/ai/node/command")
    def ai_node_command():
        body = request.get_json(force=True, silent=True) or {}
        action = str(body.get("action") or "").strip()
        schedule_power_off_on_failure = bool(body.get("schedule_power_off_on_failure"))
        power_off_delay_sec = body.get("power_off_delay_sec")
        service = get_ai_node_service()
        if action == 'shutdown':
            # A caller cannot bypass the coordinated backup guard. Backup-held
            # completion callbacks enqueue and execute only after lock release.
            payload, status = service.shutdown_request(power_off_delay_sec, schedule_power_off_on_failure, body.get('backup_run_id'))
            return jsonify(payload), status
        try:
            result = service.remote_command(action)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except subprocess.TimeoutExpired:
            result = {"ok": False, "error": f"AI node SSH command timed out after {service.ssh_timeout:g}s", "action": action}
            return jsonify(result), 504
        except OSError as exc:
            result = {"ok": False, "error": f"AI node SSH command failed: {exc}", "action": action}
            return jsonify(result), 502
        return jsonify(result), 200 if result.get("ok") else 502

    @app.post("/api/ai/chat")
    def ai_chat():
        if request.content_length and request.content_length > 17 * 1024 * 1024:
            return jsonify({"ok": False, "error": "A kérés legfeljebb 17 MiB lehet."}), 413
        raw = request.stream.read(17 * 1024 * 1024 + 1)
        if len(raw) > 17 * 1024 * 1024:
            return jsonify({"ok": False, "error": "A kérés legfeljebb 17 MiB lehet."}), 413
        try:
            body = json.loads(raw or b"{}")
        except (ValueError, UnicodeDecodeError):
            return jsonify({"ok": False, "error": "Hibás JSON kérés."}), 400
        if not isinstance(body, dict):
            return jsonify({"ok": False, "error": "A kérés JSON objektum legyen."}), 400
        payload, status = get_ai_proxy_service().chat(body)
        return jsonify(payload), status

    @app.get("/api/ai/config")
    def ai_config():
        payload, status = get_ai_proxy_service().config()
        return jsonify(payload), status

    @app.post("/api/ai/config")
    def ai_config_save():
        body = request.get_json(force=True, silent=True) or {}
        payload, status = get_ai_proxy_service().save_config(body)
        return jsonify(payload), status

    @app.get("/api/ai/models")
    def ai_models():
        payload, status = get_ai_proxy_service().models()
        return jsonify(payload), status

    @app.post("/api/ai/models/pull")
    def ai_model_pull():
        body = request.get_json(force=True, silent=True) or {}
        payload, status = get_ai_proxy_service().pull_model(body)
        return jsonify(payload), status

    @app.get("/api/ai/models/pull/status")
    def ai_model_pull_status():
        payload, status = get_ai_proxy_service().pull_status()
        return jsonify(payload), status


def register_sql_lab_routes(
    app,
    *,
    get_sql_lab_service: Callable[[], Any],
    json_ready: Callable[[Any], Any],
) -> None:
    from sql_lab_database import SqlLabUnavailable

    @app.get("/api/sql-lab/schema")
    def sql_lab_schema():
        try:
            return jsonify(json_ready(get_sql_lab_service().schema())), 200
        except SqlLabUnavailable as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503

    @app.post("/api/sql-lab/query")
    def sql_lab_query():
        body = request.get_json(force=True, silent=True) or {}
        payload, status = get_sql_lab_service().run(body)
        return jsonify(json_ready(payload)), status

    @app.get("/api/sql-lab/preview")
    def sql_lab_preview():
        try:
            payload, status = get_sql_lab_service().preview(
                request.args.get("schema", ""),
                request.args.get("table", ""),
                request.args.get("limit", 25),
            )
            return jsonify(json_ready(payload)), status
        except SqlLabUnavailable as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503


def register_backup_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_backup_service: Callable[[], Any],
    invalidate_context_sections: Callable[..., Any],
    context_command_meta: Callable[..., Any],
    json_ready: Callable[[Any], Any],
) -> None:
    @app.post("/api/backup/restore/recover")
    def api_backup_restore_recover():
        try:
            payload, status = get_backup_service().recover_restore_payload(request.get_json(silent=True) or {})
            return jsonify(payload), status
        except (ValueError, OSError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.get("/api/backup")
    def backup_state():
        return jsonify(json_ready(get_context_service().section("backup")))

    @app.put("/api/backup/settings")
    def update_backup_settings():
        data = request.get_json(force=True, silent=True) or {}
        try:
            payload, status = get_backup_service().update_settings_payload(data, context_command_meta)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        invalidate_context_sections("backup")
        return jsonify(payload), status

    @app.post("/api/backup/create")
    def create_backup_now():
        try:
            payload, status = get_backup_service().create_payload(context_command_meta)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        invalidate_context_sections("backup")
        return jsonify(payload), status

    @app.post("/api/backup/full-ai")
    def request_full_ai_backup():
        try:
            payload, status = get_backup_service().full_ai_backup_payload(context_command_meta)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        invalidate_context_sections("backup")
        return jsonify(payload), status

    @app.post("/api/backup/gitea/status")
    def gitea_config_status():
        try:
            payload, status = get_backup_service().gitea_status_payload()
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        return jsonify(payload), status

    @app.post("/api/backup/gitea/commit")
    def gitea_config_commit():
        data = request.get_json(force=True, silent=True) or {}
        try:
            payload, status = get_backup_service().gitea_commit_payload(data, context_command_meta)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        invalidate_context_sections("backup")
        return jsonify(payload), status

    @app.post("/api/backup/gitea/restore")
    def gitea_config_restore():
        data = request.get_json(force=True, silent=True) or {}
        try:
            payload, status = get_backup_service().gitea_restore_payload(data)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        return jsonify(payload), status

    @app.get("/api/backup/<path:backup_name>/contents")
    def get_backup_contents(backup_name: str):
        try:
            payload, status = get_backup_service().contents_payload(backup_name, request.args.get("limit") or 500)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(payload), status

    @app.get("/api/backup/<path:backup_name>/compare")
    def compare_backup_member(backup_name: str):
        try:
            payload, status = get_backup_service().compare_payload(backup_name, request.args.get("path"))
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(payload), status

    @app.post("/api/backup/restore")
    def restore_backup():
        data = request.get_json(force=True, silent=True) or {}
        try:
            payload, status = get_backup_service().restore_payload(data, context_command_meta)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        invalidate_context_sections("backup")
        return jsonify(payload), status


def register_climate_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_climate_service: Callable[[], Any],
    fetch_climate_schedule_rules: Callable[[], Any],
    json_ready: Callable[[Any], Any],
) -> None:
    @app.get("/api/climate/gree/state")
    def gree_climate_state():
        return jsonify(json_ready(get_context_service().section("climate")))

    @app.post("/api/climate/gree/window-guard")
    def climate_window_guard_config():
        service = get_climate_service()
        try:
            result = service.window_guard().save_config(request.get_json(force=True, silent=True) or {})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        service.invalidate_context("climate")
        return jsonify(json_ready({"ok": True, "window_guard": result}))

    @app.get("/api/climate/gree/power-history")
    def gree_climate_power_history():
        return jsonify(json_ready(get_context_service().section("climate_power_history")))

    @app.get("/api/climate/gree/parameter-history")
    def gree_climate_parameter_history():
        return jsonify(json_ready(get_context_service().section("climate_history")))

    @app.post("/api/climate/gree/command")
    def gree_climate_command():
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_climate_service().queue_command(data)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(result), 200 if result["ok"] else 502

    @app.get("/api/climate/gree/schedules")
    def gree_climate_schedules():
        try:
            schedules = fetch_climate_schedule_rules(request.args.get("profile"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "schedules": schedules})

    @app.post("/api/climate/gree/schedules")
    def gree_climate_schedule_create():
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_climate_service().create_schedule(data, fetch_climate_schedule_rules)
        except (TypeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(result), 201

    @app.put("/api/climate/gree/schedules/<int:schedule_id>")
    def gree_climate_schedule_update(schedule_id: int):
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_climate_service().update_schedule(schedule_id, data, fetch_climate_schedule_rules)
        except (TypeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not result:
            return jsonify({"ok": False, "error": "schedule not found"}), 404
        return jsonify(result)

    @app.delete("/api/climate/gree/schedules/<int:schedule_id>")
    def gree_climate_schedule_delete(schedule_id: int):
        result = get_climate_service().delete_schedule(schedule_id, fetch_climate_schedule_rules)
        if not result:
            return jsonify({"ok": False, "error": "schedule not found"}), 404
        return jsonify(result)


def register_scheduler_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_scheduler_service: Callable[[], Any],
    invalidate_context_sections: Callable[..., Any],
    context_command_meta: Callable[..., Any],
    json_ready: Callable[[Any], Any],
) -> None:
    @app.get("/api/scheduler/state")
    def scheduler_state():
        return jsonify(json_ready(get_context_service().section("scheduler")))

    @app.put("/api/scheduler/config")
    def scheduler_config_update():
        data = request.get_json(force=True, silent=True) or {}
        try:
            row = get_scheduler_service().update_config(
                mode=data.get("mode"),
                updated_by=data.get("updated_by") or "react-admin",
                notes=data.get("notes") or "",
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        invalidate_context_sections("scheduler")
        return jsonify({"ok": True, "config": row, "state": get_scheduler_service().state_payload(), "context": context_command_meta("scheduler")})

    @app.post("/api/v2/simulate/scheduler")
    def v2_simulate_scheduler():
        data = request.get_json(force=True, silent=True) or {}
        try:
            return jsonify(get_scheduler_service().simulate_v2_scheduler_chain(data))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400


def register_combustion_safety_routes(app, *, get_combustion_safety_service: Callable[[], Any], json_ready: Callable[[Any], Any]) -> None:
    @app.get("/api/combustion-safety/state")
    def combustion_safety_state():
        return jsonify(json_ready(get_combustion_safety_service().state_payload()))

    @app.put("/api/combustion-safety/config")
    def combustion_safety_config():
        data = request.get_json(force=True, silent=True) or {}
        try:
            config = get_combustion_safety_service().update_config(data, data.get("updated_by") or "api")
        except (TypeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "config": json_ready(config), "state": json_ready(get_combustion_safety_service().state_payload())})

    @app.post("/api/combustion-safety/acknowledge")
    def combustion_safety_acknowledge():
        try:
            return jsonify(json_ready(get_combustion_safety_service().acknowledge()))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409

    @app.post("/api/combustion-safety/preview-light")
    def combustion_safety_preview_light():
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_combustion_safety_service().preview_indicator(str(data.get("pattern") or ""))
        except (TypeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(result)

def register_robot_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_robot_service: Callable[[], Any],
    x10_monitor: Any,
    x10_map_dir: Any,
    json_ready: Callable[[Any], Any],
    send_from_directory: Callable[..., Any],
    path_cls: Callable[[str], Any],
) -> None:
    @app.get("/api/xiaomi-x10/state")
    def xiaomi_x10_state():
        return jsonify(json_ready(get_context_service().section("robot")))

    @app.get("/api/xiaomi-x10/rooms")
    def xiaomi_x10_rooms():
        return jsonify(get_robot_service().rooms_payload())

    @app.get("/api/xiaomi-x10/map")
    def xiaomi_x10_map():
        return jsonify(get_robot_service().map_payload())

    @app.post("/api/xiaomi-x10/command")
    def xiaomi_x10_command():
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_robot_service().command(data)
        except ValueError:
            return jsonify({"ok": False, "error": "unknown command"}), 400
        return jsonify(result), 200 if result["ok"] else 502

    @app.get("/api/xiaomi-x10/cache")
    def xiaomi_x10_cache():
        return jsonify(x10_monitor.snapshot())

    @app.get("/api/xiaomi-x10/maps/<path:filename>")
    def xiaomi_x10_map_file(filename):
        response = send_from_directory(x10_map_dir, path_cls(filename).name)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response


def register_energy_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_power_wall_service: Callable[[], Any],
    invalidate_context_sections: Callable[..., Any],
    context_command_meta: Callable[..., Any],
    normalize_text: Callable[..., str],
    json_ready: Callable[[Any], Any],
) -> None:
    @app.get("/api/tuya/state")
    def tuya_state():
        return jsonify(json_ready(get_context_service().section("tuya")))

    @app.get("/api/solar/state")
    def solar_state():
        return jsonify(json_ready(get_context_service().section("solar")))

    @app.post("/api/tuya/command")
    def tuya_command():
        data = request.get_json(force=True, silent=True) or {}
        entity_id = data.get("entity_id")
        entity_name = normalize_text(data.get("entity_name") or data.get("device_name"))
        value = get_power_wall_service().bool_from_request_value(data.get("value"))
        if value is None:
            return jsonify({"ok": False, "error": "value must be true/false"}), 400

        row, result = get_power_wall_service().tuya_switch_command(entity_id, entity_name, value)
        if not row:
            return jsonify({"ok": False, "error": "active Tuya entity not found"}), 404

        invalidate_context_sections("tuya", "power_wall")
        return jsonify({**result, "context": context_command_meta("tuya", "power_wall")}), 200 if result["ok"] else 502

    @app.get("/api/power-wall/state")
    def power_wall_state():
        return jsonify(json_ready(get_context_service().section("power_wall")))

    @app.get("/api/power-wall/history")
    def power_wall_history():
        try:
            entity_id = int(request.args.get("entity_id") or "0")
        except ValueError:
            return jsonify({"ok": False, "error": "entity_id must be numeric"}), 400
        if entity_id <= 0:
            return jsonify({"ok": False, "error": "entity_id is required"}), 400
        payload = get_power_wall_service().history_payload(entity_id)
        if not payload:
            return jsonify({"ok": False, "error": "power wall entity not found"}), 404
        return jsonify(payload)

    @app.post("/api/power-wall/policy")
    def power_wall_policy():
        data = request.get_json(force=True, silent=True) or {}
        entity_id = data.get("entity_id")
        has_always_on = "always_on" in data
        has_auto_climate = "auto_climate" in data
        if not entity_id:
            return jsonify({"ok": False, "error": "entity_id is required"}), 400
        try:
            row, policy = get_power_wall_service().set_policy(
                entity_id,
                always_on_marker=data.get("always_on") if has_always_on else None,
                auto_climate_marker=data.get("auto_climate") if has_auto_climate else None,
                delay_minutes=data.get("auto_climate_delay_minutes"),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not row:
            return jsonify({"ok": False, "error": "active power wall entity not found"}), 404
        invalidate_context_sections("power_wall")
        return jsonify({"ok": True, "policy": json_ready(policy), "platform": row["platform"], "context": context_command_meta("power_wall")})

    @app.put("/api/power-wall/display-name")
    def power_wall_display_name():
        data = request.get_json(force=True, silent=True) or {}
        entity_id = data.get("entity_id")
        display_name = normalize_text(data.get("display_name"))
        if not entity_id:
            return jsonify({"ok": False, "error": "entity_id is required"}), 400
        try:
            row, policy = get_power_wall_service().set_display_name(entity_id, display_name)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not row:
            return jsonify({"ok": False, "error": "active power wall entity not found"}), 404
        invalidate_context_sections("power_wall")
        return jsonify({"ok": True, "policy": json_ready(policy), "platform": row["platform"], "context": context_command_meta("power_wall")})

    @app.put("/api/power-wall/scheduler")
    def power_wall_scheduler_policy():
        data = request.get_json(force=True, silent=True) or {}
        entity_id = data.get("entity_id")
        if not entity_id:
            return jsonify({"ok": False, "error": "entity_id is required"}), 400
        try:
            row, policy = get_power_wall_service().set_scheduler_policy(entity_id, data)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not row:
            return jsonify({"ok": False, "error": "active power wall entity not found"}), 404
        invalidate_context_sections("power_wall")
        return jsonify({"ok": True, "policy": json_ready(policy), "platform": row["platform"], "context": context_command_meta("power_wall")})

    @app.get("/api/power-wall/scheduler/sessions")
    def power_wall_scheduler_sessions():
        try:
            entity_id = int(request.args.get("entity_id") or "0")
            limit = int(request.args.get("limit") or "40")
        except ValueError:
            return jsonify({"ok": False, "error": "entity_id and limit must be numeric"}), 400
        if entity_id <= 0:
            return jsonify({"ok": False, "error": "entity_id is required"}), 400
        row, rows = get_power_wall_service().scheduler_sessions(entity_id, limit)
        if not row:
            return jsonify({"ok": False, "error": "active power wall entity not found"}), 404
        return jsonify({"ok": True, "entity": row, "sessions": rows})

    @app.post("/api/power-wall/command")
    def power_wall_command():
        data = request.get_json(force=True, silent=True) or {}
        entity_id = data.get("entity_id")
        value = get_power_wall_service().bool_from_request_value(data.get("value"))
        if value is None:
            return jsonify({"ok": False, "error": "value must be true/false"}), 400
        if not entity_id:
            return jsonify({"ok": False, "error": "entity_id is required"}), 400

        row, result = get_power_wall_service().switch_command(entity_id, value)
        if not row:
            return jsonify({"ok": False, "error": "active power wall entity not found"}), 404
        if not result["topic"]:
            return jsonify({"ok": False, "error": result["message"]}), 400
        invalidate_context_sections("power_wall")
        return jsonify({**result, "platform": row["platform"], "context": context_command_meta("power_wall")}), 200 if result["ok"] else 502


def register_admin_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_admin_service: Callable[[], Any],
    get_process_binding_service: Callable[[], Any],
    get_season_profile_service: Callable[[], Any],
    json_ready: Callable[[Any], Any],
) -> None:
    @app.get("/api/admin/bootstrap")
    def admin_bootstrap():
        return jsonify(get_admin_service().bootstrap_payload())

    @app.get("/api/admin/season-profiles")
    def admin_season_profiles():
        return jsonify(json_ready(get_season_profile_service().payload()))

    @app.put("/api/admin/season-profiles/<domain>/<profile>")
    def admin_update_season_profile(domain: str, profile: str):
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_season_profile_service().update_profile(domain, profile, data)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(json_ready(result))

    @app.post("/api/admin/season-profiles/<domain>/activate")
    def admin_activate_season_profile(domain: str):
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_season_profile_service().activate(domain, str(data.get("profile") or ""))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(json_ready(result))

    @app.get("/api/admin/parameters")
    def admin_parameters():
        return jsonify(json_ready(get_admin_service().parameters_payload()))

    @app.get("/api/admin/containers")
    def admin_containers():
        try:
            by_name = {item["name"]: item for item in (docker_socket_containers() or [])}
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc), "containers": []}), 503
        containers = []
        for key, name in ADMIN_RESTART_CONTAINERS.items():
            current = by_name.get(name) or {}
            containers.append({
                "key": key,
                "name": name,
                "state": current.get("state") or "not found",
                "status": current.get("status") or "",
            })
        return jsonify({"ok": True, "containers": containers})

    @app.post("/api/admin/containers/<container_key>/restart")
    def admin_container_restart(container_key: str):
        container_name = ADMIN_RESTART_CONTAINERS.get(container_key)
        if not container_name:
            return jsonify({"ok": False, "error": "container is not allowed"}), 404

        try:
            response, _ = docker_socket_request("POST", f"/containers/{container_name}/restart?t=10", timeout=20)
            receipt = json.loads(response)
        except (RuntimeError, TimeoutError) as exc:
            return jsonify({"ok": False, "error": str(exc), "container": container_name}), 502
        return jsonify({"ok": True, "container": container_name, **receipt}), 202


    @app.get("/api/admin/host-jobs/<job_id>")
    def host_operation_job(job_id):
        from host_operations_client import HostOperationsClient
        try:
            job = HostOperationsClient().call('job', job_id=job_id, timeout=3)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503
        return jsonify({"ok": True, "job": job})

    @app.get("/api/process-bindings")
    def process_bindings():
        return jsonify(json_ready(get_process_binding_service().payload()))

    @app.put("/api/process-bindings/<process_key>")
    def update_process_binding(process_key: str):
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_process_binding_service().set_binding(process_key, data.get("entity_id"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(json_ready(result))

    @app.get("/api/notes")
    def notes_state():
        notes = get_context_service().section("notes")
        return jsonify(json_ready({"ok": notes.get("ok", True), "notes": {"issues": notes.get("issues", []), "requests": notes.get("requests", [])}}))

    @app.post("/api/notes")
    def notes_create():
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_admin_service().create_note(data)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(result), 201

    @app.put("/api/notes/<int:note_id>")
    def notes_update(note_id: int):
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_admin_service().update_note(note_id, data)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not result:
            return jsonify({"ok": False, "error": "note not found"}), 404
        return jsonify(result)

    @app.delete("/api/notes/<int:note_id>")
    def notes_delete(note_id: int):
        result = get_admin_service().delete_note(note_id)
        if not result:
            return jsonify({"ok": False, "error": "note not found"}), 404
        return jsonify(result)

    @app.post("/api/admin/metrics")
    def create_metric():
        data = request.get_json(force=True, silent=True) or {}
        try:
            return jsonify(get_admin_service().create_metric(data))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/admin/devices")
    def create_device_with_entity():
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = get_admin_service().create_device_with_entity(data)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(result)

    @app.put("/api/admin/devices/<int:device_id>")
    def update_device_with_entity(device_id: int):
        data = request.get_json(force=True, silent=True) or {}
        try:
            result, status = get_admin_service().update_device_with_entity(device_id, data)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(result), status


def register_irrigation_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_irrigation_service: Callable[[], Any],
    json_ready: Callable[[Any], Any],
) -> None:
    @app.post("/api/irrigation/manual/start")
    def start_irrigation_manual():
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_irrigation_service().start_manual(data)
        return jsonify(payload), status

    @app.post("/api/irrigation/command")
    def irrigation_command():
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_irrigation_service().command(data)
        return jsonify(payload), status

    @app.post("/api/irrigation/nano-config")
    def irrigation_nano_config():
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_irrigation_service().nano_config(data)
        return jsonify(payload), status

    @app.put("/api/irrigation/solar-pump/config")
    def update_irrigation_solar_pump_config():
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_irrigation_service().update_solar_pump_config(data)
        return jsonify(payload), status

    @app.put("/api/irrigation/schedules/<int:schedule_id>")
    def update_irrigation_schedule(schedule_id: int):
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_irrigation_service().update_schedule(schedule_id, data)
        return jsonify(payload), status

    @app.post("/api/irrigation/schedules")
    def create_irrigation_schedule():
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_irrigation_service().create_schedule(data)
        return jsonify(payload), status

    @app.delete("/api/irrigation/schedules/<int:schedule_id>")
    def delete_irrigation_schedule(schedule_id: int):
        payload, status = get_irrigation_service().delete_schedule(schedule_id)
        return jsonify(payload), status

    @app.post("/api/irrigation/manual/stop")
    def stop_irrigation_manual():
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_irrigation_service().stop_manual(data)
        return jsonify(payload), status

    @app.get("/api/irrigation/pilot")
    def irrigation_pilot_state():
        return jsonify(json_ready(get_context_service().section("irrigation_pilot")))

    @app.put("/api/irrigation/pilot/config")
    def update_irrigation_pilot_config():
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_irrigation_service().update_pilot_config(data)
        return jsonify(payload), status

    @app.post("/api/irrigation/pilot/evaluate")
    def create_irrigation_pilot_decision():
        payload, status = get_irrigation_service().create_pilot_decision()
        return jsonify(payload), status

    @app.post("/api/irrigation/weather/fetch")
    def fetch_irrigation_weather():
        payload, status = get_irrigation_service().fetch_weather()
        return jsonify(payload), status

    @app.get("/api/irrigation/state")
    def irrigation_state():
        return jsonify(json_ready(get_context_service().section("irrigation")))

    @app.get("/api/irrigation/statistics")
    def irrigation_statistics():
        range_key = request.args.get("range", "24h")
        hours = request.args.get("hours")
        if hours not in (None, "") or range_key not in (None, "", "24h"):
            return jsonify(json_ready(get_irrigation_service().statistics_payload(range_key, hours)))
        return jsonify(json_ready(get_context_service().section("irrigation_statistics")))


def register_system_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_admin_service: Callable[[], Any],
    get_system_status_service: Callable[[], Any],
    json_ready: Callable[[Any], Any],
) -> None:
    @app.get("/api/homecontrol/statistics")
    def homecontrol_statistics():
        range_key = request.args.get("range", "24h")
        payload = get_admin_service().homecontrol_statistics_payload(range_key, request.args.get("hours"))
        return jsonify(json_ready(payload))

    @app.get("/api/performance")
    def performance_state():
        return jsonify(json_ready(get_context_service().section("performance")))

    @app.get("/api/about")
    def about_state():
        return jsonify(json_ready(get_system_status_service().about_snapshot()))

    @app.get("/api/documentation")
    def documentation_state():
        return jsonify(json_ready(get_system_status_service().documentation_snapshot()))

    @app.get("/api/debug/logs")
    def debug_log_sources():
        return jsonify(json_ready(get_system_status_service().debug_log_sources()))

    @app.get("/api/debug/logs/<path:container_ref>")
    def debug_container_log(container_ref):
        try:
            tail = int(request.args.get("tail", "300"))
        except (TypeError, ValueError):
            tail = 300
        payload = get_system_status_service().debug_container_log(container_ref, tail=tail)
        return jsonify(json_ready(payload)), 200 if payload.get("ok") else 404
