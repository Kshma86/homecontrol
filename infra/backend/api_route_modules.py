import subprocess
import time
from typing import Any, Callable, Iterable

from context_payload_service import compact_context_payload
from flask import jsonify, request
from system_status_service import docker_socket_request


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
        try:
            docker_socket_request("POST", "/containers/homecontrol-ai-server/restart?t=10", timeout=20)
        except RuntimeError as exc:
            return jsonify({"ok": False, "cache_cleared": True, "error": f"AI gateway restart failed: {exc}"}), 502

        checks = []
        for delay in (0.8, 1.5, 2.5, 4.0):
            time.sleep(delay)
            payload, status = service.status()
            checks.append({"status": status, "ready": bool(payload.get("ready")), "ok": bool(payload.get("ok") or payload.get("gateway_ok"))})
            if status < 400 and payload.get("ready"):
                payload["ok"] = True
                payload["cache_cleared"] = True
                payload["restart_requested"] = True
                return jsonify(payload), 200
        return jsonify({"ok": True, "cache_cleared": True, "restart_requested": True, "ready": False, "checks": checks}), 202

    @app.get("/api/ai/node/status")
    def ai_node_status():
        return jsonify(get_ai_node_service().health()), 200

    @app.post("/api/ai/node/wake")
    def ai_node_wake():
        service = get_ai_node_service()
        power_result = service.set_power_plug(True, "homecontrol-ai-node-wake")
        if not service.mac:
            return jsonify({"ok": bool(power_result.get("ok")), "error": "AI_NODE_MAC is not configured", "power": power_result}), 400
        try:
            service.send_wake_on_lan()
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc), "power": power_result}), 400
        except OSError as exc:
            return jsonify({"ok": False, "error": f"Wake-on-LAN failed: {exc}", "power": power_result}), 502
        return jsonify({"ok": True, "message": "power on requested and wake packet sent", "power": power_result, "node": service.public_config()}), 202

    @app.post("/api/ai/node/command")
    def ai_node_command():
        body = request.get_json(force=True, silent=True) or {}
        action = str(body.get("action") or "").strip()
        schedule_power_off_on_failure = bool(body.get("schedule_power_off_on_failure"))
        power_off_delay_sec = body.get("power_off_delay_sec")
        defer_if_backup_running = body.get("defer_if_backup_running", True) is not False
        service = get_ai_node_service()
        if action == "shutdown" and defer_if_backup_running and service.ai_backup_running():
            return jsonify(service.request_deferred_shutdown(power_off_delay_sec)), 202
        try:
            result = service.remote_command(action)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except subprocess.TimeoutExpired:
            result = {"ok": False, "error": f"AI node SSH command timed out after {service.ssh_timeout:g}s", "action": action}
            if action == "shutdown" and schedule_power_off_on_failure:
                result["power_off"] = service.schedule_power_off(power_off_delay_sec)
                result["message"] = "AI node SSH timed out; delayed power off was scheduled anyway"
                return jsonify(result), 202
            return jsonify(result), 504
        except OSError as exc:
            result = {"ok": False, "error": f"AI node SSH command failed: {exc}", "action": action}
            if action == "shutdown" and schedule_power_off_on_failure:
                result["power_off"] = service.schedule_power_off(power_off_delay_sec)
                result["message"] = "AI node SSH failed; delayed power off was scheduled anyway"
                return jsonify(result), 202
            return jsonify(result), 502
        if action == "shutdown" and result.get("ok"):
            result["power_off"] = service.schedule_power_off(power_off_delay_sec)
        elif action == "shutdown" and schedule_power_off_on_failure:
            result["power_off"] = service.schedule_power_off(power_off_delay_sec)
            result["message"] = "AI node shutdown command failed; delayed power off was scheduled anyway"
            return jsonify(result), 202
        return jsonify(result), 200 if result.get("ok") else 502

    @app.post("/api/ai/chat")
    def ai_chat():
        body = request.get_json(force=True, silent=True) or {}
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


def register_backup_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_backup_service: Callable[[], Any],
    invalidate_context_sections: Callable[..., Any],
    context_command_meta: Callable[..., Any],
    json_ready: Callable[[Any], Any],
) -> None:
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
        return jsonify({"ok": True, "schedules": fetch_climate_schedule_rules()})

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
    json_ready: Callable[[Any], Any],
) -> None:
    @app.get("/api/admin/bootstrap")
    def admin_bootstrap():
        return jsonify(get_admin_service().bootstrap_payload())

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

    @app.put("/api/irrigation/schedules/<int:schedule_id>")
    def update_irrigation_schedule(schedule_id: int):
        data = request.get_json(force=True, silent=True) or {}
        payload, status = get_irrigation_service().update_schedule(schedule_id, data)
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
        return jsonify(json_ready(get_context_service().section("irrigation_statistics")))


def register_system_routes(
    app,
    *,
    get_context_service: Callable[[], Any],
    get_system_status_service: Callable[[], Any],
    json_ready: Callable[[Any], Any],
) -> None:
    @app.get("/api/homecontrol/statistics")
    def homecontrol_statistics():
        return jsonify(json_ready(get_context_service().section("home_statistics")))

    @app.get("/api/performance")
    def performance_state():
        return jsonify(json_ready(get_context_service().section("performance")))

    @app.get("/api/about")
    def about_state():
        return jsonify(json_ready(get_system_status_service().about_snapshot()))

    @app.get("/api/documentation")
    def documentation_state():
        return jsonify(json_ready(get_system_status_service().documentation_snapshot()))
