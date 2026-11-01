from worker_runtime import RequestCapacity
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlencode

from flask import Flask, g, jsonify, request, send_from_directory
from flask_sock import Sock
from psycopg.rows import dict_row

from admin_service import AdminService
from api_route_modules import (
    register_admin_routes,
    register_ai_routes,
    register_backup_routes,
    register_climate_routes,
    register_combustion_safety_routes,
    register_context_routes,
    register_energy_routes,
    register_irrigation_routes,
    register_mower_routes,
    register_page_usage_routes,
    register_robot_routes,
    register_scheduler_routes,
    register_sql_lab_routes,
    register_system_routes,
)
from ai_chat_audit_service import AiChatAuditService
from ai_node_service import AiNodeService
from scoped_ai_power_coordination import ScopedAiPowerCoordinator as AiPowerCoordinator
from deployment_policy import install_routes as install_deployment_policy
from ai_proxy_service import AiProxyService
from host_operations_client import HostBackupService, HostOperationsUnavailable
from climate_service import ClimateService
from climate_window_guard import ClimateWindowGuard
from combustion_safety_service import CombustionSafetyService
from command_service import CommandService
from context_service import ContextService
from db_runtime import DatabaseRuntime
from sql_lab_database import SqlLabDatabase
from energy_device_service import EnergyDeviceService
from irrigation_service import IrrigationService
from irrigation_admission import IrrigationSessionAdmission
from mqtt_monitor_service import BaseTopicMonitorState, IrrigationMqttMonitorState, MqttClientService
from mower_service import MowerService
from mower_v3_service import MowerV3Service
from mower_service_read import MowerServiceRead, register_mower_service_read
from mower_bringup_read import MowerBringupRead, register_mower_bringup_read
from mower_operator_auth import MowerOperatorAuth
from mower_manual_service import ManualRelay
from mower_v3_routes import register_mower_v3_controls
from mower_parameters_service import MowerParametersService
from mower_parameters_store import MowerParametersStore
from mower_parameters_routes import register_mower_parameter_routes
from mower_firmware_routes import register_mower_firmware_routes
from mower_firmware_service import MowerFirmwareService
from mower_firmware_store import MowerFirmwareStore
from mower_firmware_staging import MowerFirmwareStaging
from mower_firmware_sessions_store import MowerFirmwareSessionsStore
from mower_firmware_operations_store import MowerFirmwareOperationsStore
from mower_firmware_updates import MowerFirmwareUpdates
from page_usage_service import PageUsageService
from power_wall_service import PowerWallService
from process_binding_service import ProcessBindingService
from climate_fan_coordination import ClimateFanCoordinator
from robot_service import RobotService
from scheduler_service import SchedulerService
from scheduler_audit import scheduler_audit_transaction
from season_profile_service import SeasonProfileService
from schema_service import HcSchemaService
from sql_lab_service import SqlLabService
from settings import DEFAULT_CONTEXT_REFRESH_SECTIONS, DEFAULT_CONTEXT_SECTIONS, SCHEDULER_MODES, SETTINGS
from startup_service import BootstrapService, StartupService, run_guarded_callbacks
from system_status_service import SystemStatusService, docker_exec_capture, docker_socket_request
from runtime_utils import (
    ApiCache,
    ApiPerformanceLog,
    absolute_humidity_g_m3,
    current_db_query_count,
    json_dumps,
    json_ready,
    json_time,
    normalize_text,
    to_float,
    to_int,
    unix_to_iso,
)
from topic_contract import (
    X10_DAY_MASK_INDEX_BY_HC_DAY,
    climate_command_topic,
    irrigation_command_topics,
    irrigation_topics,
    x10_schedule_clean_topic,
    x10_weekly_schedule_topic,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = Flask(__name__)

@app.errorhandler(HostOperationsUnavailable)
def host_operation_unavailable(error):
    return jsonify({"ok": False, "error": str(error), "code": "host_executor_unavailable"}), 503

install_deployment_policy(app)
sock = Sock(app)

DATABASE_URL = SETTINGS.database_url
MQTT_HOST = SETTINGS.mqtt_host
MQTT_PORT = SETTINGS.mqtt_port
X10_BASE_TOPIC = SETTINGS.x10_base_topic
X10_MAP_DIR = SETTINGS.x10_map_dir
CLIMATE_BASE_TOPIC = SETTINGS.climate_base_topic
MOWER_BASE_TOPIC = SETTINGS.mower_base_topic
MOWER_REMOTE_URL = SETTINGS.mower_remote_url
GREE_CLIMATE_IP = SETTINGS.gree_climate_ip
GREE_CLIMATE_PORT = SETTINGS.gree_climate_port
GREE_CLIMATE_MAC = SETTINGS.gree_climate_mac
GREE_CLIMATE_NAME = SETTINGS.gree_climate_name
AI_SERVER_URL = SETTINGS.ai_server_url
AI_SERVER_TIMEOUT = SETTINGS.ai_server_timeout
CLIMATE_POWER_METER_EXT_ID = SETTINGS.climate_power_meter_ext_id
CLIMATE_POWER_METER_POWER_DIVISOR = SETTINGS.climate_power_meter_power_divisor
AI_NODE_POWER_ENTITY_ID = SETTINGS.ai_node_power_entity_id
HC_V2_EXECUTION_ENABLED = SETTINGS.hc_v2_execution_enabled
HC_V2_EXECUTION_ALLOW_IRRIGATION = SETTINGS.hc_v2_execution_allow_irrigation
HC_V2_EXECUTION_ALLOW_X10 = SETTINGS.hc_v2_execution_allow_x10
HC_V2_EXECUTION_ALLOW_CLIMATE = SETTINGS.hc_v2_execution_allow_climate
IRRIGATION_DEVICE_ID = SETTINGS.irrigation_device_id
IRRIGATION_CMD_BASE = SETTINGS.irrigation_cmd_base
MANUAL_MAX_MINUTES = SETTINGS.manual_max_minutes
IRRIGATION_SNAPSHOT_CACHE_TTL = SETTINGS.irrigation_snapshot_cache_ttl
IRRIGATION_PILOT_CACHE_TTL = SETTINGS.irrigation_pilot_cache_ttl
IRRIGATION_WEATHER_SUMMARY_CACHE_TTL = SETTINGS.irrigation_weather_summary_cache_ttl
IRRIGATION_DAILY_SUMMARY_DAYS = SETTINGS.irrigation_daily_summary_days
IRRIGATION_DAILY_SUMMARY_REFRESH_SEC = SETTINGS.irrigation_daily_summary_refresh_sec
SAFETY_WORKER_ENABLED = SETTINGS.safety_worker_enabled
SCHEDULER_POLL_SECONDS = SETTINGS.scheduler_poll_seconds
STOP_CONFIRM_ATTEMPTS = SETTINGS.stop_confirm_attempts
STOP_REACTION_DELAY_SECONDS = SETTINGS.stop_reaction_delay_seconds
STOP_CLOSED_DELAY_SECONDS = SETTINGS.stop_closed_delay_seconds
OPEN_CONFIRM_ATTEMPTS = SETTINGS.open_confirm_attempts
OPEN_REACTION_DELAY_SECONDS = SETTINGS.open_reaction_delay_seconds
OPEN_READY_DELAY_SECONDS = SETTINGS.open_ready_delay_seconds
OPENWEATHER_API_KEY = SETTINGS.openweather_api_key
OPENWEATHER_LAT = SETTINGS.openweather_lat
OPENWEATHER_LON = SETTINGS.openweather_lon
OPENWEATHER_UNITS = SETTINGS.openweather_units
OPENWEATHER_LANG = SETTINGS.openweather_lang
WEATHER_POLL_SECONDS = SETTINGS.weather_poll_seconds
POWER_WALL_GUARD_SECONDS = SETTINGS.power_wall_guard_seconds
POWER_WALL_GUARD_REPEAT_SECONDS = SETTINGS.power_wall_guard_repeat_seconds
HC_CONTEXT_REALTIME_TTL = SETTINGS.hc_context_realtime_ttl
HC_CONTEXT_STATISTICS_TTL = SETTINGS.hc_context_statistics_ttl
HC_CONTEXT_REFRESH_SECONDS = SETTINGS.hc_context_refresh_seconds
HC_CONTEXT_REFRESH_ENABLED = SETTINGS.hc_context_refresh_enabled
API_CACHE = ApiCache()
API_PERF_LOG = ApiPerformanceLog(
    window_sec=SETTINGS.api_perf_log_window_sec,
    max_samples=SETTINGS.api_perf_log_max_samples,
)

_context_service = None
_context_service_lock = threading.Lock()
_command_service = None
_command_service_lock = threading.Lock()
_mqtt_client_service = None
_mqtt_client_service_lock = threading.Lock()
_irrigation_service = None
_irrigation_service_lock = threading.Lock()
_power_wall_service = None
_power_wall_service_lock = threading.Lock()
_climate_fan_coordinator = ClimateFanCoordinator(lambda: db_conn(dict_row))
_process_binding_service = None
_process_binding_service_lock = threading.Lock()
_scheduler_service = None
_scheduler_service_lock = threading.Lock()
_climate_service = None
_climate_service_lock = threading.Lock()
_mower_service = None
_mower_service_lock = threading.Lock()
_mower_v3_service = MowerV3Service(
    origin=SETTINGS.mower_v3_remote_url,
    token=SETTINGS.rover_api_token,
    read_only=SETTINGS.mower_v3_read_only,
    motor_test_enabled=SETTINGS.mower_v3_motor_test_enabled,
    simple_control=True,
)
_mower_operator_auth = MowerOperatorAuth(superuser=True)
_mower_manual_relay = ManualRelay(_mower_v3_service)
_combustion_safety_service = None
_combustion_safety_service_lock = threading.Lock()
_robot_service = None
_robot_service_lock = threading.Lock()
_energy_device_service = None
_energy_device_service_lock = threading.Lock()
_admin_service = None
_admin_service_lock = threading.Lock()
_ai_proxy_service = None
_ai_proxy_service_lock = threading.Lock()
_ai_node_service = None
_ai_node_service_lock = threading.Lock()
_startup_service = None
_startup_service_lock = threading.Lock()
_schema_service = None
_schema_service_lock = threading.Lock()
_ai_chat_audit_service = None
_ai_chat_audit_service_lock = threading.Lock()
_page_usage_service = None
_page_usage_service_lock = threading.Lock()
_sql_lab_service = None
_sql_lab_service_lock = threading.Lock()


IRRIGATION_TOPICS = irrigation_topics(IRRIGATION_DEVICE_ID)
DB_RUNTIME = DatabaseRuntime(DATABASE_URL)
SQL_LAB_DATABASE = SqlLabDatabase(SETTINGS.sql_lab_database_url)


mqtt_monitor = IrrigationMqttMonitorState(
    MQTT_HOST,
    MQTT_PORT,
    IRRIGATION_DEVICE_ID,
    IRRIGATION_TOPICS,
    observe_topic=lambda topic: get_command_service().observe_mqtt_topic(topic),
)
x10_monitor = BaseTopicMonitorState(
    MQTT_HOST,
    MQTT_PORT,
    X10_BASE_TOPIC,
    client_id="hc-admin-xiaomi-x10",
    thread_name="xiaomi-x10-mqtt-monitor",
    max_raw_messages=160,
    observe_topic=lambda topic: get_command_service().observe_mqtt_topic(topic),
)
climate_monitor = BaseTopicMonitorState(
    MQTT_HOST,
    MQTT_PORT,
    CLIMATE_BASE_TOPIC,
    client_id="hc-admin-gree-climate",
    thread_name="gree-climate-mqtt-monitor",
    max_raw_messages=120,
    observe_topic=lambda topic: get_command_service().observe_mqtt_topic(topic),
)
mower_monitor = BaseTopicMonitorState(
    MQTT_HOST,
    MQTT_PORT,
    MOWER_BASE_TOPIC,
    client_id="hc-admin-mower",
    thread_name="mower-mqtt-monitor",
    max_raw_messages=180,
    observe_topic=lambda topic: get_command_service().observe_mqtt_topic(topic),
)


def get_database_service():
    return DB_RUNTIME.database


def db_conn(row_factory=None):
    return DB_RUNTIME.conn(row_factory)


def get_repository_registry():
    return DB_RUNTIME.repositories


def fetch_all(sql: str, params: Iterable[Any] = ()):
    return DB_RUNTIME.fetch_all(sql, params)


def fetch_one(sql: str, params: Iterable[Any] = ()):
    return DB_RUNTIME.fetch_one(sql, params)


def execute_one(sql: str, params: Iterable[Any] = ()):
    return DB_RUNTIME.execute_one(sql, params)


def execute_sql(sql: str, params: Optional[Iterable[Any]] = None):
    return DB_RUNTIME.execute_sql(sql, params)


def get_sql_lab_service():
    global _sql_lab_service
    with _sql_lab_service_lock:
        if _sql_lab_service is None:
            _sql_lab_service = SqlLabService(
                db_conn=SQL_LAB_DATABASE.conn,
                fetch_all=SQL_LAB_DATABASE.fetch_all,
                fetch_one=SQL_LAB_DATABASE.fetch_one,
            )
        return _sql_lab_service


def get_ai_chat_audit_service():
    global _ai_chat_audit_service
    with _ai_chat_audit_service_lock:
        if _ai_chat_audit_service is None:
            _ai_chat_audit_service = AiChatAuditService(
                fetch_all=fetch_all,
                execute_one=execute_one,
                execute_sql=execute_sql,
            )
        return _ai_chat_audit_service


def ensure_ai_chat_audit_schema() -> None:
    return get_ai_chat_audit_service().ensure_schema()


def insert_ai_chat_audit(row: Dict[str, Any]) -> None:
    return get_ai_chat_audit_service().insert(row)


def ai_chat_audit_summary_payload(limit: int = 80) -> Dict[str, Any]:
    return get_ai_chat_audit_service().summary_payload(limit)


def get_page_usage_service():
    global _page_usage_service
    with _page_usage_service_lock:
        if _page_usage_service is None:
            _page_usage_service = PageUsageService(fetch_all=fetch_all, execute_one=execute_one, execute_sql=execute_sql)
        return _page_usage_service


def api_cache_get(key: str):
    return API_CACHE.get(key)


def api_cache_set(key: str, data: Any, ttl_seconds: float):
    return API_CACHE.set(key, data, ttl_seconds)


def api_cache_delete_prefix(prefix: str):
    context = globals().get("_context_service")
    sections = api_cache_context_sections(prefix)
    if context is not None and sections:
        for section in sections:
            context.invalidate(section)
    return API_CACHE.delete_prefix(prefix)


def api_cache_context_sections(prefix: str):
    owners = {
        "irrigation_statistics": ("irrigation_statistics",),
        "homecontrol_statistics": ("home_statistics",),
        "power_wall_": ("power_wall",),
        "marten_motion": ("power_wall",),
        "tuya_state": ("tuya",),
        "solar_state": ("solar",),
        "climate_power_history": ("climate_power_history",),
        "climate_history": ("climate_history",),
        "performance_server_power": ("server_power", "performance"),
    }
    return list(dict.fromkeys(section for owner, sections in owners.items()
                             if owner.startswith(prefix) or prefix.startswith(owner)
                             for section in sections))


def get_command_service():
    global _command_service
    if _command_service is None:
        with _command_service_lock:
            if _command_service is None:
                _command_service = CommandService(get_context_service)
    return _command_service


def get_mqtt_client_service():
    global _mqtt_client_service
    if _mqtt_client_service is None:
        with _mqtt_client_service_lock:
            if _mqtt_client_service is None:
                _mqtt_client_service = MqttClientService(MQTT_HOST, MQTT_PORT, lambda payload: json.dumps(payload, ensure_ascii=False))
    return _mqtt_client_service


def invalidate_context_sections(*sections: str):
    return get_command_service().invalidate(*sections)


def context_command_meta(*sections: str):
    return get_command_service().meta(*sections)


def cached_api_payload(key: str, ttl_seconds: float, builder):
    return API_CACHE.cached_payload(key, ttl_seconds, builder)


def record_api_request(response):
    return API_PERF_LOG.record_request(response)


def api_performance_log(limit: int = 60):
    return API_PERF_LOG.payload(limit)


def get_schema_service():
    global _schema_service
    with _schema_service_lock:
        if _schema_service is None:
            _schema_service = HcSchemaService(execute_sql, fetch_one)
        return _schema_service


def invalidate_irrigation_snapshot_cache():
    context = globals().get("_context_service")
    if context is not None:
        return context.invalidate("irrigation")
    service = globals().get("_irrigation_service")
    if service is not None:
        service.invalidate_snapshot_cache()


def invalidate_irrigation_pilot_cache():
    context = globals().get("_context_service")
    if context is not None:
        return context.invalidate("irrigation_pilot")
    service = globals().get("_irrigation_service")
    if service is not None:
        service.invalidate_pilot_cache()


def invalidate_irrigation_weather_summary_cache():
    context = globals().get("_context_service")
    if context is not None:
        return context.invalidate("weather")
    service = globals().get("_irrigation_service")
    if service is not None:
        service.invalidate_weather_summary_cache()


def cached_irrigation_weather_summary(force: bool = False):
    return get_irrigation_service().cached_weather_summary(force=force)


def cached_irrigation_pilot_recommendation(force: bool = False):
    return get_irrigation_service().cached_pilot_recommendation(force=force)


def ensure_pilot_schema():
    return get_schema_service().ensure_pilot_schema()


def ensure_scheduler_schema():
    return get_scheduler_service().ensure_scheduler_schema()


def ensure_power_wall_schema():
    return get_schema_service().ensure_power_wall_schema()


def ensure_process_binding_schema():
    return get_process_binding_service().ensure_schema()


def ensure_irrigation_summary_schema():
    return get_irrigation_service().ensure_summary_schema()


def ensure_notes_schema():
    return get_admin_service().ensure_notes_schema()


def fetch_notes():
    return get_admin_service().fetch_notes()


def fetch_climate_schedule_rules(profile=None):
    get_season_profile_service().ensure_schema()
    ensure_scheduler_schema()
    profile = normalize_text(profile) or None
    if profile not in (None, "summer", "winter"):
        raise ValueError("profile must be summer or winter")
    return fetch_all(
        """
        with schedule_state as (
          select
            r.*,
            a.profile as active_profile,
            day_of_week = extract(isodow from now())::int - 1 as is_today,
            is_enabled
              and r.season_profile = a.profile
              and day_of_week = extract(isodow from now())::int - 1
              and to_char(localtime, 'HH24:MI') = to_char(start_time, 'HH24:MI')
              as should_run_now
          from hc.climate_schedule_rule r
          join hc.domain_season_active a on a.domain = 'climate'
          where r.season_profile = coalesce(%s, a.profile)
        )
        select
          id,
          label,
          day_of_week,
          to_char(start_time, 'HH24:MI') as start_time,
          is_enabled,
          season_profile,
          active_profile,
          season_profile = active_profile as is_active_profile,
          is_today,
          should_run_now,
          case
            when should_run_now then 'due_now'
            when is_enabled and is_today then 'armed_today'
            when is_enabled then 'armed'
            else 'disabled'
          end as schedule_status,
          power,
          mode,
          target_temperature,
          fan_speed,
          light,
          coalesce(extra_fan, 'keep') as extra_fan,
          rule_engine,
          updated_at
        from schedule_state
        order by day_of_week, start_time, id
        """,
        (profile,),
    )


def record_scheduler_shadow_audit():
    return get_scheduler_service().record_shadow_audit()


def check_db():
    return get_database_service().check()


def check_mqtt(timeout_s: float = 2.0) -> bool:
    return get_mqtt_client_service().check(timeout_s=timeout_s)


def publish_mqtt(topic: str, payload: Any, qos: int = 0, retain: bool = False) -> Tuple[bool, str]:
    if topic == f"{CLIMATE_BASE_TOPIC}/command" and isinstance(payload, dict):
        return get_climate_window_guard().command(topic, payload, qos=qos, retain=retain)
    return get_mqtt_client_service().publish(topic, payload, qos=qos, retain=retain)


_climate_window_guard = None
_climate_window_guard_lock = threading.Lock()


def get_climate_window_guard():
    global _climate_window_guard
    with _climate_window_guard_lock:
        if _climate_window_guard is None:
            _climate_window_guard = ClimateWindowGuard(
                fetch_all, fetch_one, execute_one,
                lambda topic, payload, **kwargs: get_mqtt_client_service().publish(topic, payload, **kwargs),
                lambda: climate_monitor.value("state") or get_climate_service().latest_parameter_state(),
                lambda: get_combustion_safety_service().last_snapshot,
                lambda ext_id: get_admin_service().zigbee_radio_status(ext_id),
                sync_auto_climate_power_wall,
            )
    return _climate_window_guard


def climate_and_combustion_tick():
    run_guarded_callbacks("CLIMATE_SAFETY", (
        ("combustion", lambda: get_combustion_safety_service().tick()),
        ("window guard", lambda: get_climate_window_guard().tick(f"{CLIMATE_BASE_TOPIC}/command")),
    ))


def command_topics():
    return irrigation_command_topics(IRRIGATION_CMD_BASE)


def irrigation_stop_payload(reason: str) -> Dict[str, Any]:
    return get_irrigation_service().stop_payload(reason)


def validate_schedule_time(value: Any, field: str) -> str:
    return get_irrigation_service().validate_schedule_time(value, field)


def fetch_pilot_config():
    return get_irrigation_service().fetch_pilot_config()


_backup_service = None
_system_status_service = None
_season_profile_service = None


def get_season_profile_service():
    global _season_profile_service
    if _season_profile_service is None:
        _season_profile_service = SeasonProfileService(
            fetch_all=fetch_all,
            fetch_one=fetch_one,
            execute_one=execute_one,
            execute_sql=execute_sql,
            invalidate_context=invalidate_context_sections,
        )
    return _season_profile_service


def get_backup_service():
    global _backup_service
    if _backup_service is None:
        _backup_service = HostBackupService()
    return _backup_service


def latest_backup_info():
    return get_backup_service().latest_info()


def get_system_status_service():
    global _system_status_service
    if _system_status_service is None:
        _system_status_service = SystemStatusService(
            fetch_all=fetch_all,
            fetch_one=fetch_one,
            mqtt_monitor=mqtt_monitor,
            api_performance_log=api_performance_log,
            cached_api_payload=cached_api_payload,
            server_power_history_payload=lambda: get_energy_device_service().server_power_history_payload(),
            latest_backup_info=latest_backup_info,
            safety_worker_enabled=SAFETY_WORKER_ENABLED,
            worker_status=backend_worker_status,
        )
    return _system_status_service


def get_irrigation_service():
    global _irrigation_service
    if _irrigation_service is None:
        with _irrigation_service_lock:
            if _irrigation_service is None:
                _irrigation_service = IrrigationService(
                    fetch_all=fetch_all,
                    fetch_one=fetch_one,
                    execute_one=execute_one,
                    execute_sql=execute_sql,
                    reserve_session=IrrigationSessionAdmission(lambda: db_conn(dict_row)).reserve,
                    publish_mqtt=publish_mqtt,
                    normalize_text=normalize_text,
                    command_topics=command_topics,
                    invalidate_snapshot=invalidate_irrigation_snapshot_cache,
                    invalidate_pilot=invalidate_irrigation_pilot_cache,
                    invalidate_weather_summary=invalidate_irrigation_weather_summary_cache,
                    invalidate_context=invalidate_context_sections,
                    context_meta=context_command_meta,
                    ensure_pilot_schema=ensure_pilot_schema,
                    to_float=to_float,
                    to_int=to_int,
                    manual_max_minutes=MANUAL_MAX_MINUTES,
                    cached_api_payload=cached_api_payload,
                    api_cache_get=api_cache_get,
                    api_cache_set=api_cache_set,
                    api_cache_delete_prefix=api_cache_delete_prefix,
                    mqtt_snapshot=mqtt_monitor.snapshot,
                    scheduler_config=lambda: get_scheduler_service().config(),
                    v2_execution_engine_state=lambda config: get_scheduler_service().engine_state(config),
                    json_time=json_time,
                    stop_confirm_attempts=STOP_CONFIRM_ATTEMPTS,
                    stop_reaction_delay_seconds=STOP_REACTION_DELAY_SECONDS,
                    stop_closed_delay_seconds=STOP_CLOSED_DELAY_SECONDS,
                    open_confirm_attempts=OPEN_CONFIRM_ATTEMPTS,
                    open_reaction_delay_seconds=OPEN_REACTION_DELAY_SECONDS,
                    open_ready_delay_seconds=OPEN_READY_DELAY_SECONDS,
                    valve_tele_max_age_seconds=SETTINGS.irrigation_valve_tele_max_age_seconds,
                    valve_status_max_age_seconds=SETTINGS.irrigation_valve_status_max_age_seconds,
                    nano_online_max_age_seconds=SETTINGS.irrigation_nano_online_max_age_seconds,
                    start_recovery_grace_seconds=SETTINGS.irrigation_start_recovery_grace_seconds,
                    recovery_retry_seconds=SETTINGS.irrigation_recovery_retry_seconds,
                    recovery_max_attempts=SETTINGS.irrigation_recovery_max_attempts,
                    openweather_api_key=OPENWEATHER_API_KEY,
                    openweather_lat=OPENWEATHER_LAT,
                    openweather_lon=OPENWEATHER_LON,
                    openweather_units=OPENWEATHER_UNITS,
                    openweather_lang=OPENWEATHER_LANG,
                    weather_poll_seconds=WEATHER_POLL_SECONDS,
                    absolute_humidity_g_m3=absolute_humidity_g_m3,
                    process_binding_topic=lambda key: get_process_binding_service().selected_topic_base(key),
                    process_binding_payload=lambda key: get_process_binding_service().binding(key, include_candidates=True),
                    pilot_cache_ttl=IRRIGATION_PILOT_CACHE_TTL,
                    weather_summary_cache_ttl=IRRIGATION_WEATHER_SUMMARY_CACHE_TTL,
                    daily_summary_days=IRRIGATION_DAILY_SUMMARY_DAYS,
                    daily_summary_refresh_sec=IRRIGATION_DAILY_SUMMARY_REFRESH_SEC,
                    snapshot_ttl=IRRIGATION_SNAPSHOT_CACHE_TTL,
                    capability_allowed=lambda capability: get_season_profile_service().capability_allowed("irrigation", capability),
                    active_season_profile=lambda: get_season_profile_service().active("irrigation"),
                )
    return _irrigation_service


def fetch_irrigation_v2_session(source_ref: str):
    return fetch_one(
        """
        select requested_stop_at
        from hc.irrigation_manual_session
        where started_by = 'v2_scheduler'
          and start_payload ->> 'schedule_id' = %s
          and started_at::date = current_date
        order by started_at desc
        limit 1
        """,
        (str(source_ref),),
    )


def get_scheduler_service():
    global _scheduler_service
    if _scheduler_service is None:
        with _scheduler_service_lock:
            if _scheduler_service is None:
                _scheduler_service = SchedulerService(
                    audit_transaction=lambda: scheduler_audit_transaction(lambda: db_conn(dict_row)),
                    climate_monitor_snapshot=climate_monitor.snapshot,
                    x10_monitor_snapshot=x10_monitor.snapshot,
                    feedback_max_age_seconds=SETTINGS.scheduler_feedback_max_age_seconds,
                    confirmation_timeout_seconds=SETTINGS.scheduler_confirmation_timeout_seconds,
                    fetch_all=fetch_all,
                    fetch_one=fetch_one,
                    execute_one=execute_one,
                    ensure_schema=ensure_scheduler_schema,
                    execute_sql=execute_sql,
                    normalize_text=normalize_text,
                    json_time=json_time,
                    json_dumps=json_dumps,
                    fetch_irrigation_schedules=lambda: get_irrigation_service().fetch_schedules(),
                    fetch_climate_schedule_rules=fetch_climate_schedule_rules,
                    x10_scheduler_entries=lambda: x10_monitor.value("scheduler/entries") or [],
                    x10_day_mask_index_by_hc_day=lambda: X10_DAY_MASK_INDEX_BY_HC_DAY,
                    x10_monitor_value=x10_monitor.value,
                    scheduler_modes=SCHEDULER_MODES,
                    v2_execution_enabled=HC_V2_EXECUTION_ENABLED,
                    v2_allow_irrigation=HC_V2_EXECUTION_ALLOW_IRRIGATION,
                    v2_allow_x10=HC_V2_EXECUTION_ALLOW_X10,
                    v2_allow_climate=HC_V2_EXECUTION_ALLOW_CLIMATE,
                    evaluate_irrigation_pilot=lambda **kwargs: get_irrigation_service().evaluate_pilot(**kwargs),
                    fetch_irrigation_v2_session=fetch_irrigation_v2_session,
                    irrigation_command_topic=lambda: command_topics()["valve"],
                    x10_schedule_clean_topic=x10_schedule_clean_topic(X10_BASE_TOPIC),
                    x10_weekly_schedule_topic=x10_weekly_schedule_topic(X10_BASE_TOPIC),
                    climate_command_topic=climate_command_topic(CLIMATE_BASE_TOPIC),
                    climate_state_payload=lambda: get_climate_service().state_payload(),
                    publish_mqtt=publish_mqtt,
                    sync_auto_climate_power_wall=sync_auto_climate_power_wall,
                    check_db=check_db,
                    check_mqtt=check_mqtt,
                    manual_valve_scheduler_guard=lambda: get_irrigation_service().manual_valve_scheduler_guard(),
                    running_irrigation_session=lambda: get_irrigation_service().running_session(),
                )
    return _scheduler_service


def get_climate_service():
    global _climate_service
    if _climate_service is None:
        with _climate_service_lock:
            if _climate_service is None:
                _climate_service = ClimateService(
                    fetch_all=fetch_all,
                    fetch_one=fetch_one,
                    execute_one=execute_one,
                    normalize_text=normalize_text,
                    validate_schedule_time=validate_schedule_time,
                    publish_mqtt=publish_mqtt,
                    invalidate_context=invalidate_context_sections,
                    context_meta=context_command_meta,
                    monitor=climate_monitor,
                    window_guard=get_climate_window_guard,
                    base_topic=CLIMATE_BASE_TOPIC,
                    name=GREE_CLIMATE_NAME,
                    ip=GREE_CLIMATE_IP,
                    port=GREE_CLIMATE_PORT,
                    mac=GREE_CLIMATE_MAC,
                    power_meter_ext_id=CLIMATE_POWER_METER_EXT_ID,
                    power_meter_divisor=CLIMATE_POWER_METER_POWER_DIVISOR,
                    sync_auto_power_wall=sync_auto_climate_power_wall,
                    process_binding_payload=lambda key: get_process_binding_service().binding(key, include_candidates=True),
                    process_binding_entity_id=lambda key: get_process_binding_service().selected_entity_id(key),
                )
    return _climate_service


def get_combustion_safety_service():
    global _combustion_safety_service
    if _combustion_safety_service is None:
        with _combustion_safety_service_lock:
            if _combustion_safety_service is None:
                _combustion_safety_service = CombustionSafetyService(
                    fetch_all=fetch_all,
                    fetch_one=fetch_one,
                    execute_one=execute_one,
                    publish_mqtt=publish_mqtt,
                    binding_entity_id=lambda key: get_process_binding_service().selected_entity_id(key),
                    zigbee_radio_status=get_admin_service().zigbee_radio_status,
                    command_retry_seconds=SETTINGS.combustion_command_retry_seconds,
                    command_max_attempts=SETTINGS.combustion_command_max_attempts,
                    observation_max_age_seconds=SETTINGS.combustion_observation_max_age_seconds,
                    input_max_age_seconds=SETTINGS.combustion_input_max_age_seconds,
                    snapshot_max_age_seconds=SETTINGS.combustion_snapshot_max_age_seconds,
                )
    return _combustion_safety_service


def get_robot_service():
    global _robot_service
    if _robot_service is None:
        with _robot_service_lock:
            if _robot_service is None:
                _robot_service = RobotService(
                    fetch_all=fetch_all,
                    normalize_text=normalize_text,
                    publish_mqtt=publish_mqtt,
                    invalidate_context=invalidate_context_sections,
                    context_meta=context_command_meta,
                    monitor=x10_monitor,
                    base_topic=X10_BASE_TOPIC,
                    map_dir=X10_MAP_DIR,
                )
    return _robot_service


def get_energy_device_service():
    global _energy_device_service
    if _energy_device_service is None:
        with _energy_device_service_lock:
            if _energy_device_service is None:
                _energy_device_service = EnergyDeviceService(
                    fetch_all=fetch_all,
                    fetch_one=fetch_one,
                    cached_api_payload=cached_api_payload,
                    api_cache_get=api_cache_get,
                    api_cache_set=api_cache_set,
                    json_ready=json_ready,
                    process_binding_payload=lambda key: get_process_binding_service().binding(key, include_candidates=True),
                    process_binding_entity_id=lambda key: get_process_binding_service().selected_entity_id(key),
                )
    return _energy_device_service


def get_admin_service():
    global _admin_service
    if _admin_service is None:
        with _admin_service_lock:
            if _admin_service is None:
                _admin_service = AdminService(
                    db_conn=db_conn,
                    dict_row=dict_row,
                    fetch_all=fetch_all,
                    fetch_one=fetch_one,
                    execute_one=execute_one,
                    execute_sql=execute_sql,
                    normalize_text=normalize_text,
                    json_ready=json_ready,
                    cached_api_payload=cached_api_payload,
                    api_cache_get=api_cache_get,
                    api_cache_set=api_cache_set,
                    api_cache_delete_prefix=api_cache_delete_prefix,
                    invalidate_context=invalidate_context_sections,
                    context_meta=context_command_meta,
                    absolute_humidity_g_m3=absolute_humidity_g_m3,
                    irrigation_context=lambda: get_context_service().section("irrigation"),
                    scheduler_state=lambda: get_scheduler_service().state_payload(),
                )
    return _admin_service


def get_process_binding_service():
    global _process_binding_service
    if _process_binding_service is None:
        with _process_binding_service_lock:
            if _process_binding_service is None:
                _process_binding_service = ProcessBindingService(
                    fetch_all=fetch_all,
                    fetch_one=fetch_one,
                    execute_one=execute_one,
                    execute_sql=execute_sql,
                    normalize_text=normalize_text,
                    api_cache_delete_prefix=api_cache_delete_prefix,
                    invalidate_context=invalidate_context_sections,
                    invalidate_pilot=invalidate_irrigation_pilot_cache,
                    invalidate_weather_summary=invalidate_irrigation_weather_summary_cache,
                    legacy_fallbacks={
                        "climate_power_meter_ext_id": CLIMATE_POWER_METER_EXT_ID,
                        "ai_node_power_entity_id": AI_NODE_POWER_ENTITY_ID,
                    },
                    ai_power_coordinator=AiPowerCoordinator(get_backup_service().backup_root),
                    climate_fan_coordinator=_climate_fan_coordinator,
                )
    return _process_binding_service


def get_power_wall_service():
    global _power_wall_service
    if _power_wall_service is None:
        with _power_wall_service_lock:
            if _power_wall_service is None:
                _power_wall_service = PowerWallService(
                    fetch_all=fetch_all,
                    climate_fan_coordinator=_climate_fan_coordinator,
                    fetch_one=fetch_one,
                    execute_one=execute_one,
                    publish_mqtt=publish_mqtt,
                    ensure_schema=ensure_power_wall_schema,
                    cached_api_payload=cached_api_payload,
                    api_cache_get=api_cache_get,
                    api_cache_set=api_cache_set,
                    api_cache_delete_prefix=api_cache_delete_prefix,
                    normalize_text=normalize_text,
                    guard_repeat_seconds=POWER_WALL_GUARD_REPEAT_SECONDS,
                    process_binding_payload=lambda key: get_process_binding_service().binding(key, include_candidates=True),
                    process_binding_entity_id=lambda key: get_process_binding_service().selected_entity_id(key),
                )
    return _power_wall_service


def get_mower_service():
    global _mower_service
    if _mower_service is None:
        with _mower_service_lock:
            if _mower_service is None:
                _mower_service = MowerService(
                    monitor=mower_monitor,
                    publish_mqtt=publish_mqtt,
                    base_topic=MOWER_BASE_TOPIC,
                    remote_url=MOWER_REMOTE_URL,
                )
    return _mower_service


def context_builders():
    return {
        "weather": lambda: {
            "ok": True,
            **get_irrigation_service().build_weather_snapshot(
                get_process_binding_service().selected_topic_base("irrigation_soil_moisture")
            ),
        },
        "irrigation": lambda: get_irrigation_service().build_snapshot(),
        "irrigation_pilot": lambda: get_irrigation_service().pilot_payload(),
        "irrigation_statistics": lambda: get_irrigation_service().statistics_payload(),
        "climate": lambda: get_climate_service().state_payload(),
        "mower": lambda: get_mower_service().state_payload(),
        "combustion_safety": lambda: get_combustion_safety_service().state_payload(),
        "climate_power_history": lambda: get_climate_service().power_history_payload(),
        "climate_history": lambda: get_climate_service().parameter_history_payload(),
        "climate_schedules": lambda: {"ok": True, "schedules": fetch_climate_schedule_rules()},
        "robot": lambda: get_robot_service().state_payload(),
        "power_wall": lambda: get_power_wall_service().state_payload(),
        "solar": solar_state_payload,
        "tuya": tuya_state_payload,
        "scheduler": lambda: get_scheduler_service().state_payload(),
        "scheduler_ai": lambda: get_scheduler_service().ai_summary_payload(),
        "notes": lambda: {"ok": True, **get_admin_service().fetch_notes()},
        "performance": lambda: get_system_status_service().performance_snapshot(),
        "server_power": lambda: get_energy_device_service().server_power_history_payload(),
        "home_statistics": lambda: get_admin_service().homecontrol_statistics_payload(),
        "ai_chat_audit": lambda: ai_chat_audit_summary_payload(),
        "backup": lambda: get_backup_service().payload(),
    }


def context_invalidators():
    # Call only already-instantiated services; no DB, publish or construction
    # under the context cache lock. These callbacks only invalidate memory.
    def domain(method):
        def invalidate():
            service = globals().get("_irrigation_service")
            if service is not None:
                getattr(service, method)()
        return invalidate

    def prefixes(*names):
        def invalidate():
            for name in names:
                API_CACHE.delete_prefix(name)
        return invalidate

    return {
        "irrigation": domain("invalidate_snapshot_cache"),
        "irrigation_pilot": domain("invalidate_pilot_inputs"),
        "weather": domain("invalidate_weather_summary_cache"),
        "irrigation_statistics": prefixes("irrigation_statistics"),
        "home_statistics": prefixes("homecontrol_statistics"),
        "power_wall": prefixes("power_wall_", "marten_motion"),
        "tuya": prefixes("tuya_state"),
        "solar": prefixes("solar_state"),
        "climate_power_history": prefixes("climate_power_history"),
        "climate_history": prefixes("climate_history"),
        "server_power": prefixes("performance_server_power"),
        "performance": prefixes("performance_server_power"),
    }


def get_context_service():
    global _context_service
    with _context_service_lock:
        if _context_service is None:
            _context_service = ContextService(
                context_builders(),
                realtime_ttl=HC_CONTEXT_REALTIME_TTL,
                statistics_ttl=HC_CONTEXT_STATISTICS_TTL,
                invalidators=context_invalidators(),
                section_ttls={"irrigation": IRRIGATION_SNAPSHOT_CACHE_TTL},
            )
        return _context_service


def get_ai_proxy_service():
    global _ai_proxy_service
    with _ai_proxy_service_lock:
        if _ai_proxy_service is None:
            _ai_proxy_service = AiProxyService(
                AI_SERVER_URL,
                AI_SERVER_TIMEOUT,
                context_summary=lambda trace=None, sections=None: get_context_service().ai_summary(trace=trace, sections=sections),
                json_ready=json_ready,
                audit_logger=insert_ai_chat_audit,
                db_query_count=current_db_query_count,
            )
        return _ai_proxy_service


def get_ai_node_service():
    global _ai_node_service
    with _ai_node_service_lock:
        if _ai_node_service is None:
            _ai_node_service = AiNodeService(
                fetch_power_wall_command_entity=lambda entity_id: get_power_wall_service().command_entity(entity_id),
                publish_power_wall_switch=lambda row, value, source: get_power_wall_service().publish_switch(row, value, source),
                api_cache_delete_prefix=api_cache_delete_prefix,
                invalidate_context_sections=invalidate_context_sections,
                process_binding_payload=lambda key: get_process_binding_service().binding(key, include_candidates=True),
                process_binding_entity_id=lambda key: get_process_binding_service().selected_entity_id(key),
                coordinator=AiPowerCoordinator(get_backup_service().backup_root),
            )
        return _ai_node_service


def get_startup_service():
    global _startup_service
    with _startup_service_lock:
        if _startup_service is None:
            bootstrap = BootstrapService(
                [
                    ensure_pilot_schema,
                    ensure_scheduler_schema,
                    get_season_profile_service().ensure_schema,
                    ensure_power_wall_schema,
                    ensure_process_binding_schema,
                    ensure_irrigation_summary_schema,
                    ensure_notes_schema,
                    lambda: get_ai_node_service().start_power_guard(),
                ]
            )
            _startup_service = StartupService(
                bootstrap=bootstrap,
                scheduler_poll_seconds=SCHEDULER_POLL_SECONDS,
                weather_poll_seconds=WEATHER_POLL_SECONDS,
                power_wall_guard_seconds=POWER_WALL_GUARD_SECONDS,
                safety_worker_enabled=SAFETY_WORKER_ENABLED,
                record_scheduler_shadow_audit=record_scheduler_shadow_audit,
                climate_scheduler_tick=lambda: get_scheduler_service().climate_scheduler_tick(),
                irrigation_scheduler_tick=lambda: get_irrigation_service().scheduler_tick(),
                irrigation_scheduler_stop_tick=lambda: get_irrigation_service().scheduler_stop_tick(),
                irrigation_recovery_tick=lambda: get_irrigation_service().session_recovery.tick(),
                x10_scheduler_tick=lambda: get_scheduler_service().x10_scheduler_tick(),
                stop_overdue_sessions=lambda: get_irrigation_service().stop_overdue_sessions(),
                fail_sessions_without_physical_watering=lambda: get_irrigation_service().fail_sessions_without_physical_watering(),
                openweather_ready=lambda: get_irrigation_service().openweather_ready(),
                store_openweather_snapshot=lambda: get_irrigation_service().store_openweather_snapshot(),
                power_wall_guard_tick=lambda: get_power_wall_service().guard_tick(),
                power_wall_scheduler_tick=lambda: get_power_wall_service().scheduler_tick(),
                mqtt_monitor_start=mqtt_monitor.start,
                x10_monitor_start=x10_monitor.start,
                climate_monitor_start=climate_monitor.start,
                mower_monitor_start=mower_monitor.start,
                combustion_safety_tick=climate_and_combustion_tick,
                combustion_safety_poll_seconds=1,
                context_refresh=lambda: get_context_service().warmup(DEFAULT_CONTEXT_REFRESH_SECTIONS),
                context_refresh_seconds=HC_CONTEXT_REFRESH_SECONDS,
                context_refresh_enabled=HC_CONTEXT_REFRESH_ENABLED,
                summary_refresh=lambda: get_irrigation_service().refresh_daily_summaries(),
                owner_path="/tmp/homecontrol-backend-workers.lock",
                shutdown_resources=shutdown_backend_resources,
            )
        return _startup_service


def backend_worker_status():
    status = get_startup_service().status()
    node = globals().get('_ai_node_service')
    if node is not None:
        status['workers'].append(node.worker_status())
    proxy = globals().get('_ai_proxy_service')
    if proxy is not None and hasattr(proxy, 'worker_status'):
        status['jobs'] = [proxy.worker_status()]
    return status


def shutdown_backend_resources(timeout=0):
    deadline = time.monotonic() + max(0, timeout)
    stopped = True
    for name, method in (('_ai_proxy_service', 'stop_worker'), ('_ai_node_service', 'stop_worker')):
        service = globals().get(name)
        if service is not None and hasattr(service, method):
            stopped = getattr(service, method)(max(0, deadline-time.monotonic())) and stopped
    from system_status_service import DOCKER_REQUEST_JOBS, DOCKER_STATS_JOBS
    stopped = DOCKER_REQUEST_JOBS.stop(max(0, deadline-time.monotonic())) and stopped
    stopped = DOCKER_STATS_JOBS.stop(max(0, deadline-time.monotonic())) and stopped
    return stopped


def shutdown_backend(timeout=8):
    service = globals().get('_startup_service')
    return service.stop(timeout) if service is not None else True


_REQUEST_CAPACITY = RequestCapacity()


@app.before_request
def admit_long_request():
    category = _REQUEST_CAPACITY.category(request.path, request.headers.get('Upgrade', ''))
    if category:
        if not _REQUEST_CAPACITY.acquire(category):
            return jsonify({'ok': False, 'code': 'capacity_exhausted',
                            'error': 'Long request capacity exhausted; retry later.'}), 503, {'Retry-After': '2'}
        g.hc_capacity_category = category


@app.teardown_request
def release_long_request(error=None):
    category = g.pop('hc_capacity_category', None)
    if category:
        _REQUEST_CAPACITY.release(category)


def parse_context_sections(value: str):
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


@app.before_request
def _start_worker_once():
    from health_routes import PROBE_PATHS
    if request.path in PROBE_PATHS:
        return
    g.api_perf_started_at = time.perf_counter()
    g.db_query_count = 0
    get_startup_service().ensure_started()


@app.after_request
def _record_api_request(response):
    from health_routes import PROBE_PATHS
    if request.path in PROBE_PATHS:
        return response
    record_api_request(response)
    return response


register_context_routes(
    app,
    get_context_service=get_context_service,
    get_command_service=get_command_service,
    parse_context_sections=parse_context_sections,
    json_ready=json_ready,
    default_context_sections=DEFAULT_CONTEXT_SECTIONS,
)
register_page_usage_routes(app, get_page_usage_service=get_page_usage_service)
register_ai_routes(
    app,
    get_ai_proxy_service=get_ai_proxy_service,
    get_ai_node_service=get_ai_node_service,
)
register_sql_lab_routes(
    app,
    get_sql_lab_service=get_sql_lab_service,
    json_ready=json_ready,
)
register_backup_routes(
    app,
    get_context_service=get_context_service,
    get_backup_service=get_backup_service,
    invalidate_context_sections=invalidate_context_sections,
    context_command_meta=context_command_meta,
    json_ready=json_ready,
)
register_climate_routes(
    app,
    get_context_service=get_context_service,
    get_climate_service=get_climate_service,
    fetch_climate_schedule_rules=fetch_climate_schedule_rules,
    json_ready=json_ready,
)
register_mower_routes(
    app,
    get_context_service=get_context_service,
    get_mower_service=get_mower_service,
    get_mower_v3_service=lambda: _mower_v3_service,
    get_admin_service=get_admin_service,
    json_ready=json_ready,
)
register_mower_v3_controls(app, rover=_mower_v3_service, auth=_mower_operator_auth, relay=_mower_manual_relay)
_mower_service_read = MowerServiceRead(
    origin=SETTINGS.mower_v3_remote_url, token=SETTINGS.rover_api_token,
    activity_lock=_mower_v3_service.activity_lock,
    guard=lambda: _mower_v3_service.maintenance_guard(),
)
register_mower_service_read(app, service=_mower_service_read)
_mower_bringup_read = MowerBringupRead(
    origin=SETTINGS.mower_v3_remote_url, token=SETTINGS.rover_api_token,
    activity_lock=_mower_v3_service.activity_lock,
    guard=lambda: _mower_v3_service.maintenance_guard(),
)
register_mower_bringup_read(app, service=_mower_bringup_read)
_mower_parameters_service = MowerParametersService(MowerParametersStore(db_conn, execute_sql))
register_mower_parameter_routes(app, service=_mower_parameters_service, auth=_mower_operator_auth)
from mower_motor_test import MotorTestService
from mower_motor_test_routes import register_motor_test_routes
_mower_motor_test = MotorTestService(_mower_v3_service, _mower_manual_relay,
    config_path="/srv/docker/homecontrol/infra/private/rover-config.json")
register_motor_test_routes(app, service=_mower_motor_test, auth=_mower_operator_auth)

_mower_firmware_service = MowerFirmwareService(STATIC_DIR / "mower-approved-releases.json")
_mower_firmware_store = MowerFirmwareStore(db_conn, execute_sql)
_mower_firmware_staging = MowerFirmwareStaging(_mower_firmware_service, _mower_firmware_store)
_mower_firmware_sessions = MowerFirmwareSessionsStore(db_conn, execute_sql, _mower_firmware_store)
_mower_firmware_updates = MowerFirmwareUpdates(rover=_mower_v3_service, preflight=_mower_firmware_service,
    staging=_mower_firmware_staging, sessions=_mower_firmware_sessions, manual=_mower_manual_relay,
    operations=MowerFirmwareOperationsStore(db_conn, execute_sql, _mower_firmware_sessions))
register_mower_firmware_routes(app, service=_mower_firmware_service,
                              staging=_mower_firmware_staging, auth=_mower_operator_auth, updates=_mower_firmware_updates)
register_combustion_safety_routes(
    app,
    get_combustion_safety_service=get_combustion_safety_service,
    json_ready=json_ready,
)
register_scheduler_routes(
    app,
    get_context_service=get_context_service,
    get_scheduler_service=get_scheduler_service,
    invalidate_context_sections=invalidate_context_sections,
    context_command_meta=context_command_meta,
    json_ready=json_ready,
)
register_robot_routes(
    app,
    get_context_service=get_context_service,
    get_robot_service=get_robot_service,
    x10_monitor=x10_monitor,
    x10_map_dir=X10_MAP_DIR,
    json_ready=json_ready,
    send_from_directory=send_from_directory,
    path_cls=Path,
)
register_energy_routes(
    app,
    get_context_service=get_context_service,
    get_power_wall_service=get_power_wall_service,
    invalidate_context_sections=invalidate_context_sections,
    context_command_meta=context_command_meta,
    normalize_text=normalize_text,
    json_ready=json_ready,
)
register_admin_routes(
    app,
    get_context_service=get_context_service,
    get_admin_service=get_admin_service,
    get_process_binding_service=get_process_binding_service,
    get_season_profile_service=get_season_profile_service,
    json_ready=json_ready,
)
register_irrigation_routes(
    app,
    get_context_service=get_context_service,
    get_irrigation_service=get_irrigation_service,
    json_ready=json_ready,
)
register_system_routes(
    app,
    get_context_service=get_context_service,
    get_admin_service=get_admin_service,
    get_system_status_service=get_system_status_service,
    json_ready=json_ready,
)


@sock.route("/api/xiaomi-x10/live")
def xiaomi_x10_live_socket(ws):
    last_signature = None
    last_send = 0.0
    while not get_startup_service()._stop.is_set():
        try:
            ws.receive(timeout=.05)
            live_map = x10_monitor.value("robot/live_map")
            position = x10_monitor.value("robot/position")
            position_px = x10_monitor.value("robot/position_px")
            dock_position = x10_monitor.value("dock/position")
            dock_position_px = x10_monitor.value("dock/position_px")
            live_png = x10_monitor.value("robot/live_png")
            signature = json.dumps(
                [live_map, position, position_px, live_png],
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            now = time.time()
            if signature != last_signature or now - last_send >= 15:
                ws.send(json.dumps({
                    "type": "x10_live_map",
                    "robot_live_map": live_map,
                    "robot_position": position,
                    "robot_position_px": position_px,
                    "robot_live_png_url": get_robot_service().map_url(live_png),
                    "dock_position": dock_position,
                    "dock_position_px": dock_position_px,
                    "server_ts": now,
                }, ensure_ascii=False))
                last_signature = signature
                last_send = now
            get_startup_service()._stop.wait(.1)
        except Exception:
            break


@sock.route("/api/irrigation/pump-current/live")
def irrigation_pump_current_live_socket(ws):
    last_source_received_at = None
    while not get_startup_service()._stop.is_set():
        try:
            ws.receive(timeout=.05)
            payload = get_irrigation_service().pump_current_live_snapshot()
            source_received_at = payload.get("source_received_at_epoch")
            if source_received_at is not None and source_received_at != last_source_received_at:
                ws.send(json.dumps(payload, ensure_ascii=False, default=str))
                last_source_received_at = source_received_at
            get_startup_service()._stop.wait(.25)
        except Exception:
            break


@app.get("/health")
def health():
    db_ok = False
    mqtt_ok = False
    err = None

    try:
        db_ok = check_db()
    except Exception as e:
        err = f"db: {e}"

    try:
        mqtt_ok = check_mqtt()
    except Exception as e:
        err = (err + "; " if err else "") + f"mqtt: {e}"

    status = 200 if (db_ok and mqtt_ok) else 503
    return jsonify({"ok": db_ok and mqtt_ok, "db_ok": db_ok, "mqtt_ok": mqtt_ok, "error": err}), status


from health_routes import register_health_routes
register_health_routes(app, lambda: globals().get('_startup_service'))


@app.get("/")
def root():
    return "HomeControl backend up. Try /health or the React dashboard.\n", 200


@app.get("/admin")
def admin_index():
    return jsonify({"ok": False, "error": "Legacy admin dashboard is disabled"}), 410


@app.get("/static/<path:path>")
def static_files(path):
    if path in {"admin.html", "admin.css", "admin.js"}:
        return jsonify({"ok": False, "error": "Legacy admin assets are disabled"}), 410
    response = send_from_directory(STATIC_DIR, path)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


def tuya_state_payload():
    return get_energy_device_service().tuya_state_payload()


def solar_state_payload():
    return get_energy_device_service().solar_state_payload()


def sync_auto_climate_power_wall(power: str):
    return get_power_wall_service().sync_auto_climate(power)
if __name__ == "__main__":
    get_startup_service().start_application()
    get_context_service().snapshot(sections=DEFAULT_CONTEXT_SECTIONS)
    app.run(host="0.0.0.0", port=5000)
