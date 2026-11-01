X10_DAY_MASK_INDEX_BY_HC_DAY = [1, 2, 3, 4, 5, 6, 0]


def irrigation_topics(device_id: str):
    return {
        "esp_nano_status": f"homecontrol/tele/irrigation/{device_id}/nano_status",
        "esp_diag": f"homecontrol/tele/irrigation/{device_id}/diag",
        "esp_availability": f"homecontrol/stat/irrigation/{device_id}/availability",
        "nano_config": f"homecontrol/tele/irrigation/{device_id}/nano_cfg",
        "cmd_ack": f"homecontrol/stat/irrigation/{device_id}/cmd_ack",
        "solar": f"homecontrol/tele/irrigation/{device_id}/solar",
        "nano_event": f"homecontrol/tele/irrigation/{device_id}/nano_event",
        "pump_metrics": f"homecontrol/tele/irrigation/{device_id}/pump_metrics",
        "tank_level": "zigbee/0xa4c13880b130079c",
        "moisture_sensor_02": "zigbee/0xa4c13844a0908898",
        "moisture_sensor_03": "zigbee/0xa4c1387594b09c83",
    }


def irrigation_command_topics(command_base: str):
    return {
        "mode": f"{command_base}/mode",
        "pump": f"{command_base}/pump",
        "valve": f"{command_base}/valve",
        "config": f"{command_base}/config",
        "system": f"{command_base}/system",
    }


def x10_schedule_clean_topic(base_topic: str) -> str:
    return f"{base_topic}/command/schedule_clean"


def x10_weekly_schedule_topic(base_topic: str) -> str:
    return f"{base_topic}/command/schedule_clean_week"


def climate_command_topic(base_topic: str) -> str:
    return f"{base_topic}/command"
