def compact_context_payload(payload):
    compact = dict(payload)
    realtime = dict(compact.get("realtime") or {})
    compact["realtime"] = realtime

    if "backup" in realtime:
        backup = dict(realtime["backup"] or {})
        backups = list(backup.get("backups") or [])
        backup["backup_count"] = len(backups)
        backup["backups"] = backups[:5]
        realtime["backup"] = backup

    if "climate" in realtime:
        climate = realtime["climate"] or {}
        realtime["climate"] = _pick(climate, [
            "ok", "_context", "bridge_online", "power", "mode", "target_temperature",
            "current_temperature", "current_humidity", "fan_speed", "light", "error", "power_meter",
        ])

    if "power_wall" in realtime:
        power_wall = dict(realtime["power_wall"] or {})
        devices = list(power_wall.get("devices") or [])
        power_wall["device_count"] = len(devices)
        power_wall["devices"] = [_compact_device(item) for item in devices[:12]]
        power_wall.pop("recent_measurements", None)
        realtime["power_wall"] = power_wall

    if "tuya" in realtime:
        tuya = dict(realtime["tuya"] or {})
        devices = list(tuya.get("devices") or [])
        tuya["device_count"] = len(devices)
        tuya["devices"] = [_compact_device(item) for item in devices[:12]]
        tuya.pop("recent_measurements", None)
        realtime["tuya"] = tuya

    if "solar" in realtime:
        solar = realtime["solar"] or {}
        realtime["solar"] = _pick(solar, ["ok", "_context", "current", "summary", "error"])

    compact["compact"] = True
    return compact


def _pick(payload, keys):
    return {key: payload.get(key) for key in keys if key in payload}


def _compact_device(device):
    state = device.get("state") if isinstance(device.get("state"), dict) else {}
    return {
        "entity_id": device.get("entity_id"),
        "entity_name": device.get("entity_name"),
        "device_name": device.get("device_name"),
        "location": device.get("location"),
        "online": device.get("online"),
        "status": device.get("status"),
        "switch_state": state.get("switch_state"),
        "power_w": state.get("power_w"),
        "battery": state.get("battery"),
    }
