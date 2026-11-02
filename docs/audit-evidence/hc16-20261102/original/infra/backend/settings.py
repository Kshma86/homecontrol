import os
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


def env_bool(name: str, default: bool = False) -> bool:
    fallback = "1" if default else "0"
    return os.environ.get(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


def load_rover_api_token():
    """Backend-only provisioning; never return file contents in diagnostics."""
    direct = os.environ.get("ROVER_API_TOKEN", "").strip()
    filename = os.environ.get("ROVER_API_TOKEN_FILE", "").strip()
    if direct and filename:
        return ""  # Ambiguous credentials fail closed.
    if not filename:
        return direct
    try:
        with Path(filename).open("r", encoding="utf-8") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return ""
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        data = json.loads(raw, object_pairs_hook=unique)
        token = data.get("api_token") if type(data) is dict else None
        return token if type(token) is str and re.fullmatch(r"[0-9A-Fa-f]{64}", token) else ""
    except (OSError, ValueError, UnicodeError, RecursionError):
        return ""


@dataclass(frozen=True)
class BackendSettings:
    database_url: str = os.environ.get("DATABASE_URL", "")
    sql_lab_database_url: str = field(default_factory=lambda: os.environ.get("SQL_LAB_DATABASE_URL", ""), repr=False)
    mqtt_host: str = os.environ.get("MQTT_HOST", "localhost")
    mqtt_port: int = env_int("MQTT_PORT", 1883)
    x10_base_topic: str = os.environ.get("X10_BASE_TOPIC", "homecontrol/xiaomi_x10").rstrip("/")
    x10_map_dir: Path = Path(os.environ.get("X10_MAP_DIR", "/srv/docker/homecontrol/apps/xiaomi-x10/x10_maps"))
    climate_base_topic: str = os.environ.get("CLIMATE_BASE_TOPIC", "homecontrol/gree_climate").rstrip("/")
    mower_base_topic: str = os.environ.get("MOWER_BASE_TOPIC", "homecontrol/mower").rstrip("/")
    mower_remote_url: str = os.environ.get("MOWER_REMOTE_URL", "http://mower-remote.local/").strip()
    mower_v3_remote_url: str = os.environ.get("MOWER_V3_REMOTE_URL", "").strip()
    mower_v3_motor_test_enabled: bool = env_bool("MOWER_V3_MOTOR_TEST_ENABLED")
    mower_v3_read_only: bool = env_bool("MOWER_V3_READ_ONLY")
    rover_api_token: str = field(default_factory=load_rover_api_token, repr=False)
    rover_api_token_file: str = field(default_factory=lambda: os.environ.get("ROVER_API_TOKEN_FILE", "").strip(), repr=False)
    mower_operator_password_hash: str = field(default_factory=lambda: os.environ.get("MOWER_OPERATOR_PASSWORD_HASH", "").strip(), repr=False)
    mower_operator_session_secret: str = field(default_factory=lambda: os.environ.get("MOWER_OPERATOR_SESSION_SECRET", "").strip(), repr=False)
    gree_climate_ip: str = os.environ.get("GREE_CLIMATE_IP", "192.168.1.72")
    gree_climate_port: int = env_int("GREE_CLIMATE_PORT", 7000)
    gree_climate_mac: str = os.environ.get("GREE_CLIMATE_MAC", "9424b8ba43f7")
    gree_climate_name: str = os.environ.get("GREE_CLIMATE_NAME", "Gree klíma")
    ai_server_url: str = os.environ.get("AI_SERVER_URL", "http://ai-server:8088").rstrip("/")
    ai_server_timeout: float = env_float("AI_SERVER_TIMEOUT", 360)
    climate_power_meter_ext_id: str = os.environ.get("CLIMATE_POWER_METER_EXT_ID", "bf7bda0d19d3934720scjs")
    climate_power_meter_power_divisor: float = env_float("CLIMATE_POWER_METER_POWER_DIVISOR", 10)
    ai_node_power_entity_id: str = os.environ.get("AI_NODE_POWER_ENTITY_ID", "").strip()
    hc_v2_execution_enabled: bool = env_bool("HC_V2_EXECUTION_ENABLED")
    hc_v2_execution_allow_irrigation: bool = env_bool("HC_V2_EXECUTION_ALLOW_IRRIGATION")
    hc_v2_execution_allow_x10: bool = env_bool("HC_V2_EXECUTION_ALLOW_X10")
    hc_v2_execution_allow_climate: bool = env_bool("HC_V2_EXECUTION_ALLOW_CLIMATE")
    irrigation_device_id: str = os.environ.get("IRRIGATION_DEVICE_ID", "esp-irrigation-1")
    manual_max_minutes: int = env_int("IRRIGATION_MANUAL_MAX_MINUTES", 180)
    irrigation_snapshot_cache_ttl: float = env_float("IRRIGATION_SNAPSHOT_CACHE_TTL", 10)
    irrigation_pilot_cache_ttl: float = env_float("IRRIGATION_PILOT_CACHE_TTL", 300)
    irrigation_weather_summary_cache_ttl: float = env_float("IRRIGATION_WEATHER_SUMMARY_CACHE_TTL", 300)
    api_perf_log_window_sec: float = env_float("API_PERF_LOG_WINDOW_SEC", 6 * 3600)
    api_perf_log_max_samples: int = env_int("API_PERF_LOG_MAX_SAMPLES", 20000)
    irrigation_daily_summary_days: int = env_int("IRRIGATION_DAILY_SUMMARY_DAYS", 200)
    irrigation_daily_summary_refresh_sec: float = env_float("IRRIGATION_DAILY_SUMMARY_REFRESH_SEC", 300)
    safety_worker_enabled: bool = os.environ.get("HC_ENABLE_SAFETY_WORKER", "1") != "0"
    scheduler_poll_seconds: int = env_int("IRRIGATION_SCHEDULER_POLL_SECONDS", 5)
    scheduler_feedback_max_age_seconds: float = env_float("HC_SCHEDULER_FEEDBACK_MAX_AGE_SECONDS", 90)
    scheduler_confirmation_timeout_seconds: float = env_float("HC_SCHEDULER_CONFIRMATION_TIMEOUT_SECONDS", 120)
    combustion_command_retry_seconds: float = env_float("COMBUSTION_COMMAND_RETRY_SECONDS", 10)
    combustion_command_max_attempts: int = env_int("COMBUSTION_COMMAND_MAX_ATTEMPTS", 3)
    combustion_observation_max_age_seconds: float = env_float("COMBUSTION_OBSERVATION_MAX_AGE_SECONDS", 60)
    combustion_input_max_age_seconds: float = env_float("COMBUSTION_INPUT_MAX_AGE_SECONDS", 300)
    combustion_snapshot_max_age_seconds: float = env_float("COMBUSTION_SNAPSHOT_MAX_AGE_SECONDS", 5)
    stop_confirm_attempts: int = env_int("IRRIGATION_STOP_CONFIRM_ATTEMPTS", 3)
    stop_reaction_delay_seconds: int = env_int("IRRIGATION_STOP_REACTION_DELAY_SECONDS", 5)
    stop_closed_delay_seconds: int = env_int("IRRIGATION_STOP_CLOSED_DELAY_SECONDS", 30)
    open_confirm_attempts: int = env_int("IRRIGATION_OPEN_CONFIRM_ATTEMPTS", 3)
    open_reaction_delay_seconds: int = env_int("IRRIGATION_OPEN_REACTION_DELAY_SECONDS", 5)
    open_ready_delay_seconds: int = env_int("IRRIGATION_OPEN_READY_DELAY_SECONDS", 30)
    irrigation_valve_tele_max_age_seconds: float = env_float("IRRIGATION_VALVE_TELE_MAX_AGE_SECONDS", 25)
    irrigation_valve_status_max_age_seconds: float = env_float("IRRIGATION_VALVE_STATUS_MAX_AGE_SECONDS", 70)
    irrigation_nano_online_max_age_seconds: float = env_float("IRRIGATION_NANO_ONLINE_MAX_AGE_SECONDS", 40)
    irrigation_start_recovery_grace_seconds: float = env_float("IRRIGATION_START_RECOVERY_GRACE_SECONDS", 120)
    irrigation_recovery_retry_seconds: float = env_float("IRRIGATION_RECOVERY_RETRY_SECONDS", 60)
    irrigation_recovery_max_attempts: int = env_int("IRRIGATION_RECOVERY_MAX_ATTEMPTS", 3)
    openweather_api_key: str = os.environ.get("OPENWEATHER_API_KEY", "")
    openweather_lat: str = os.environ.get("OPENWEATHER_LAT", "")
    openweather_lon: str = os.environ.get("OPENWEATHER_LON", "")
    openweather_units: str = os.environ.get("OPENWEATHER_UNITS", "metric")
    openweather_lang: str = os.environ.get("OPENWEATHER_LANG", "hu")
    weather_poll_seconds: int = env_int("OPENWEATHER_POLL_SECONDS", 3600)
    power_wall_guard_seconds: int = env_int("POWER_WALL_GUARD_SECONDS", 10)
    power_wall_guard_repeat_seconds: int = env_int("POWER_WALL_GUARD_REPEAT_SECONDS", 30)
    hc_context_realtime_ttl: float = env_float("HC_CONTEXT_REALTIME_TTL", 5)
    hc_context_statistics_ttl: float = env_float("HC_CONTEXT_STATISTICS_TTL", 60)
    hc_context_refresh_seconds: int = env_int("HC_CONTEXT_REFRESH_SECONDS", 30)
    hc_context_refresh_enabled: bool = env_bool("HC_CONTEXT_REFRESH_ENABLED", False)

    @property
    def irrigation_cmd_base(self) -> str:
        return f"homecontrol/cmd/irrigation/{self.irrigation_device_id}"


SETTINGS = BackendSettings()

SCHEDULER_MODES = {
    "v2_execute_irrigation",
    "v2_execute_x10",
    "v2_execute_climate",
    "v2_execute_x10_climate",
    "v2_execute_all",
}

DEFAULT_CONTEXT_SECTIONS = (
    "weather",
    "irrigation",
    "climate",
    "mower",
    "robot",
    "power_wall",
    "solar",
    "tuya",
    "backup",
    "notes",
)

DEFAULT_CONTEXT_REFRESH_SECTIONS = tuple(
    item.strip()
    for item in os.environ.get(
        "HC_CONTEXT_REFRESH_SECTIONS",
        ",".join(DEFAULT_CONTEXT_SECTIONS + ("scheduler", "scheduler_ai")),
    ).split(",")
    if item.strip()
)
