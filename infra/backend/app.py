import json
import math
import os
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlencode

from flask import Flask, g, jsonify, request, send_from_directory
from psycopg.rows import dict_row

from admin_service import AdminService
from api_route_modules import (
    register_admin_routes,
    register_ai_routes,
    register_backup_routes,
    register_climate_routes,
    register_context_routes,
    register_energy_routes,
    register_irrigation_routes,
    register_robot_routes,
    register_scheduler_routes,
    register_system_routes,
)
from ai_node_service import AiNodeService
from ai_proxy_service import AiProxyService
from backup_service import BackupService
from climate_service import ClimateService
from command_service import CommandService
from context_service import ContextService
from database_service import DatabaseService
from energy_device_service import EnergyDeviceService
from irrigation_service import IrrigationService
from mqtt_monitor_service import BaseTopicMonitorState, IrrigationMqttMonitorState, MqttClientService
from power_wall_service import PowerWallService
from process_binding_service import ProcessBindingService
from repository_service import RepositoryRegistry
from robot_service import RobotService
from scheduler_service import SchedulerService
from schema_service import HcSchemaService
from startup_service import BootstrapService, StartupService
from system_status_service import SystemStatusService, docker_exec_capture, docker_socket_request

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
X10_BASE_TOPIC = os.environ.get("X10_BASE_TOPIC", "homecontrol/xiaomi_x10").rstrip("/")
X10_MAP_DIR = Path(os.environ.get("X10_MAP_DIR", "/srv/docker/homecontrol/apps/xiaomi-x10/x10_maps"))
CLIMATE_BASE_TOPIC = os.environ.get("CLIMATE_BASE_TOPIC", "homecontrol/gree_climate").rstrip("/")
GREE_CLIMATE_IP = os.environ.get("GREE_CLIMATE_IP", "192.168.1.72")
GREE_CLIMATE_PORT = int(os.environ.get("GREE_CLIMATE_PORT", "7000"))
GREE_CLIMATE_MAC = os.environ.get("GREE_CLIMATE_MAC", "9424b8ba43f7")
GREE_CLIMATE_NAME = os.environ.get("GREE_CLIMATE_NAME", "Gree klíma")
AI_SERVER_URL = os.environ.get("AI_SERVER_URL", "http://ai-server:8088").rstrip("/")
AI_SERVER_TIMEOUT = float(os.environ.get("AI_SERVER_TIMEOUT", "360"))
CLIMATE_POWER_METER_EXT_ID = os.environ.get("CLIMATE_POWER_METER_EXT_ID", "bf7bda0d19d3934720scjs")
CLIMATE_POWER_METER_POWER_DIVISOR = float(os.environ.get("CLIMATE_POWER_METER_POWER_DIVISOR", "10"))
AI_NODE_POWER_ENTITY_ID = os.environ.get("AI_NODE_POWER_ENTITY_ID", "").strip()
HC_V2_EXECUTION_ENABLED = os.environ.get("HC_V2_EXECUTION_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
HC_V2_EXECUTION_ALLOW_IRRIGATION = os.environ.get("HC_V2_EXECUTION_ALLOW_IRRIGATION", "0").strip().lower() in {"1", "true", "yes", "on"}
HC_V2_EXECUTION_ALLOW_X10 = os.environ.get("HC_V2_EXECUTION_ALLOW_X10", "0").strip().lower() in {"1", "true", "yes", "on"}
HC_V2_EXECUTION_ALLOW_CLIMATE = os.environ.get("HC_V2_EXECUTION_ALLOW_CLIMATE", "0").strip().lower() in {"1", "true", "yes", "on"}
SCHEDULER_MODES = {
    "v2_execute_irrigation",
    "v2_execute_x10",
    "v2_execute_climate",
    "v2_execute_x10_climate",
    "v2_execute_all",
}

IRRIGATION_DEVICE_ID = os.environ.get("IRRIGATION_DEVICE_ID", "esp-irrigation-1")
IRRIGATION_CMD_BASE = f"homecontrol/cmd/irrigation/{IRRIGATION_DEVICE_ID}"
MANUAL_MAX_MINUTES = int(os.environ.get("IRRIGATION_MANUAL_MAX_MINUTES", "180"))
IRRIGATION_SNAPSHOT_CACHE_TTL = float(os.environ.get("IRRIGATION_SNAPSHOT_CACHE_TTL", "10"))
IRRIGATION_PILOT_CACHE_TTL = float(os.environ.get("IRRIGATION_PILOT_CACHE_TTL", "300"))
IRRIGATION_WEATHER_SUMMARY_CACHE_TTL = float(os.environ.get("IRRIGATION_WEATHER_SUMMARY_CACHE_TTL", "300"))
API_CACHE: Dict[str, Dict[str, Any]] = {}
API_CACHE_LOCK = threading.Lock()
API_PERF_LOG_WINDOW_SEC = float(os.environ.get("API_PERF_LOG_WINDOW_SEC", str(6 * 3600)))
API_PERF_LOG_MAX_SAMPLES = int(os.environ.get("API_PERF_LOG_MAX_SAMPLES", "20000"))
API_PERF_LOG = []
API_PERF_LOG_LOCK = threading.Lock()
IRRIGATION_DAILY_SUMMARY_DAYS = int(os.environ.get("IRRIGATION_DAILY_SUMMARY_DAYS", "200"))
IRRIGATION_DAILY_SUMMARY_REFRESH_SEC = float(os.environ.get("IRRIGATION_DAILY_SUMMARY_REFRESH_SEC", "300"))
SAFETY_WORKER_ENABLED = os.environ.get("HC_ENABLE_SAFETY_WORKER", "1") != "0"
SCHEDULER_POLL_SECONDS = int(os.environ.get("IRRIGATION_SCHEDULER_POLL_SECONDS", "5"))
STOP_CONFIRM_ATTEMPTS = int(os.environ.get("IRRIGATION_STOP_CONFIRM_ATTEMPTS", "3"))
STOP_REACTION_DELAY_SECONDS = int(os.environ.get("IRRIGATION_STOP_REACTION_DELAY_SECONDS", "5"))
STOP_CLOSED_DELAY_SECONDS = int(os.environ.get("IRRIGATION_STOP_CLOSED_DELAY_SECONDS", "30"))
OPEN_CONFIRM_ATTEMPTS = int(os.environ.get("IRRIGATION_OPEN_CONFIRM_ATTEMPTS", "3"))
OPEN_REACTION_DELAY_SECONDS = int(os.environ.get("IRRIGATION_OPEN_REACTION_DELAY_SECONDS", "5"))
OPEN_READY_DELAY_SECONDS = int(os.environ.get("IRRIGATION_OPEN_READY_DELAY_SECONDS", "30"))
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
OPENWEATHER_LAT = os.environ.get("OPENWEATHER_LAT", "")
OPENWEATHER_LON = os.environ.get("OPENWEATHER_LON", "")
OPENWEATHER_UNITS = os.environ.get("OPENWEATHER_UNITS", "metric")
OPENWEATHER_LANG = os.environ.get("OPENWEATHER_LANG", "hu")
WEATHER_POLL_SECONDS = int(os.environ.get("OPENWEATHER_POLL_SECONDS", "3600"))
POWER_WALL_GUARD_SECONDS = int(os.environ.get("POWER_WALL_GUARD_SECONDS", "10"))
POWER_WALL_GUARD_REPEAT_SECONDS = int(os.environ.get("POWER_WALL_GUARD_REPEAT_SECONDS", "30"))
HC_CONTEXT_REALTIME_TTL = float(os.environ.get("HC_CONTEXT_REALTIME_TTL", "5"))
HC_CONTEXT_STATISTICS_TTL = float(os.environ.get("HC_CONTEXT_STATISTICS_TTL", "60"))
HC_CONTEXT_REFRESH_SECONDS = int(os.environ.get("HC_CONTEXT_REFRESH_SECONDS", "4"))
HC_CONTEXT_REFRESH_ENABLED = os.environ.get("HC_CONTEXT_REFRESH_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
DEFAULT_CONTEXT_SECTIONS = (
    "weather",
    "irrigation",
    "climate",
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
        ",".join(DEFAULT_CONTEXT_SECTIONS + ("scheduler", "scheduler_ai", "performance")),
    ).split(",")
    if item.strip()
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
_process_binding_service = None
_process_binding_service_lock = threading.Lock()
_scheduler_service = None
_scheduler_service_lock = threading.Lock()
_climate_service = None
_climate_service_lock = threading.Lock()
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
_database_service = None
_database_service_lock = threading.Lock()
_repository_registry = None
_repository_registry_lock = threading.Lock()
_ai_chat_audit_schema_ready = False
_ai_chat_audit_schema_lock = threading.Lock()


IRRIGATION_TOPICS = {
    "esp_nano_status": f"homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/nano_status",
    "esp_diag": f"homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/diag",
    "esp_availability": f"homecontrol/stat/irrigation/{IRRIGATION_DEVICE_ID}/availability",
    "nano_config": f"homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/nano_cfg",
    "cmd_ack": f"homecontrol/stat/irrigation/{IRRIGATION_DEVICE_ID}/cmd_ack",
    "solar": f"homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/solar",
    "nano_event": f"homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/nano_event",
    "pump_metrics": f"homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/pump_metrics",
    "tank_level": "zigbee/0xa4c13880b130079c",
    "moisture_sensor_02": "zigbee/0xa4c13844a0908898",
    "moisture_sensor_03": "zigbee/0xa4c1387594b09c83",
}


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


def get_database_service():
    global _database_service
    with _database_service_lock:
        if _database_service is None:
            _database_service = DatabaseService(DATABASE_URL)
        return _database_service


def db_conn(row_factory=None):
    return get_repository_registry().shared.conn(row_factory)


def get_repository_registry():
    global _repository_registry
    with _repository_registry_lock:
        if _repository_registry is None:
            _repository_registry = RepositoryRegistry(get_database_service())
        return _repository_registry


def fetch_all(sql: str, params: Iterable[Any] = ()):
    record_db_query()
    return get_repository_registry().shared.fetch_all(sql, params)


def fetch_one(sql: str, params: Iterable[Any] = ()):
    record_db_query()
    return get_repository_registry().shared.fetch_one(sql, params)


def execute_one(sql: str, params: Iterable[Any] = ()):
    record_db_query()
    return get_repository_registry().shared.execute_one(sql, params)


def execute_sql(sql: str, params: Optional[Iterable[Any]] = None):
    record_db_query()
    return get_repository_registry().shared.execute_sql(sql, params)


def record_db_query() -> None:
    try:
        g.db_query_count = int(getattr(g, "db_query_count", 0) or 0) + 1
    except RuntimeError:
        return


def current_db_query_count() -> Optional[int]:
    try:
        return int(getattr(g, "db_query_count", 0) or 0)
    except RuntimeError:
        return None


def ensure_ai_chat_audit_schema() -> None:
    global _ai_chat_audit_schema_ready
    if _ai_chat_audit_schema_ready:
        return
    with _ai_chat_audit_schema_lock:
        if _ai_chat_audit_schema_ready:
            return
        execute_sql(
            """
            create table if not exists hc.ai_chat_audit (
                id bigserial primary key,
                created_at timestamptz not null default now(),
                started_at timestamptz,
                question text not null,
                answer text,
                provider text,
                model text,
                status_code integer,
                ok boolean,
                error text,
                source text,
                total_ms numeric,
                context_ms numeric,
                knowledge_ms numeric,
                model_ms numeric,
                db_query_count integer,
                skills jsonb not null default '[]'::jsonb,
                data_sources jsonb not null default '[]'::jsonb,
                skill_timings jsonb not null default '[]'::jsonb,
                context_timings jsonb not null default '[]'::jsonb,
                upstream jsonb not null default '{}'::jsonb,
                request_meta jsonb not null default '{}'::jsonb
            );
            create index if not exists ix_ai_chat_audit_created_at on hc.ai_chat_audit (created_at desc);
            create index if not exists ix_ai_chat_audit_skills on hc.ai_chat_audit using gin (skills);
            create index if not exists ix_ai_chat_audit_data_sources on hc.ai_chat_audit using gin (data_sources);
            """
        )
        _ai_chat_audit_schema_ready = True


def insert_ai_chat_audit(row: Dict[str, Any]) -> None:
    ensure_ai_chat_audit_schema()
    execute_one(
        """
        insert into hc.ai_chat_audit (
            started_at,
            question,
            answer,
            provider,
            model,
            status_code,
            ok,
            error,
            source,
            total_ms,
            context_ms,
            knowledge_ms,
            model_ms,
            db_query_count,
            skills,
            data_sources,
            skill_timings,
            context_timings,
            upstream,
            request_meta
        )
        values (
            %s::timestamptz,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s::jsonb,
            %s::jsonb,
            %s::jsonb,
            %s::jsonb,
            %s::jsonb,
            %s::jsonb
        )
        returning id
        """,
        (
            row.get("started_at"),
            row.get("question") or "",
            row.get("answer"),
            row.get("provider"),
            row.get("model"),
            row.get("status_code"),
            row.get("ok"),
            row.get("error"),
            row.get("source"),
            row.get("total_ms"),
            row.get("context_ms"),
            row.get("knowledge_ms"),
            row.get("model_ms"),
            row.get("db_query_count"),
            json.dumps(row.get("skills") or [], ensure_ascii=False),
            json.dumps(row.get("data_sources") or [], ensure_ascii=False),
            json.dumps(row.get("skill_timings") or [], ensure_ascii=False),
            json.dumps(row.get("context_timings") or [], ensure_ascii=False),
            json.dumps(row.get("upstream") or {}, ensure_ascii=False),
            json.dumps(row.get("request_meta") or {}, ensure_ascii=False),
        ),
    )


def ai_chat_audit_summary_payload(limit: int = 80) -> Dict[str, Any]:
    ensure_ai_chat_audit_schema()
    rows = fetch_all(
        """
        select
            id,
            created_at,
            question,
            provider,
            model,
            status_code,
            ok,
            error,
            source,
            total_ms,
            context_ms,
            knowledge_ms,
            model_ms,
            db_query_count,
            skills,
            data_sources,
            skill_timings,
            context_timings
        from hc.ai_chat_audit
        order by id desc
        limit %s
        """,
        (max(1, min(int(limit or 80), 200)),),
    )
    total = len(rows)
    ok_count = len([row for row in rows if row.get("ok")])
    total_times = [_float(row.get("total_ms")) for row in rows if _float(row.get("total_ms")) is not None]
    db_counts = [_float(row.get("db_query_count")) for row in rows if _float(row.get("db_query_count")) is not None]
    skill_counts: Dict[str, int] = defaultdict(int)
    source_counts: Dict[str, int] = defaultdict(int)
    context_durations: Dict[str, list] = defaultdict(list)
    skill_durations: Dict[str, list] = defaultdict(list)

    for row in rows:
        for skill in _json_list(row.get("skills")):
            skill_counts[str(skill)] += 1
        for source in _json_list(row.get("data_sources")):
            if not isinstance(source, dict):
                continue
            source_type = source.get("type") or "unknown"
            name = source.get("name") or "-"
            source_counts[f"{source_type}:{name}"] += 1
        for item in _json_list(row.get("context_timings")):
            if not isinstance(item, dict):
                continue
            section = item.get("section")
            duration = _float(item.get("duration_ms"))
            if section and duration is not None:
                context_durations[str(section)].append(duration)
        for item in _json_list(row.get("skill_timings")):
            if not isinstance(item, dict):
                continue
            skill = item.get("skill")
            duration = _float(item.get("duration_ms"))
            if skill and duration is not None:
                skill_durations[str(skill)].append(duration)

    return {
        "ok": True,
        "sample_size": total,
        "window": {"latest_rows": total, "limit": max(1, min(int(limit or 80), 200))},
        "success": {
            "ok_count": ok_count,
            "error_count": total - ok_count,
            "ok_rate_percent": _round((ok_count / total) * 100 if total else None, 1),
        },
        "latency": {
            "avg_total_ms": _average(total_times, 1),
            "max_total_ms": _round(max(total_times), 1) if total_times else None,
            "avg_db_query_count": _average(db_counts, 1),
            "max_db_query_count": int(max(db_counts)) if db_counts else None,
        },
        "top_skills": _top_counts(skill_counts, 10),
        "top_data_sources": _top_counts(source_counts, 12),
        "slow_context_sections": _top_average(context_durations, 10),
        "slow_skills": _top_average(skill_durations, 10),
        "recent_questions": [
            {
                "created_at": row.get("created_at"),
                "question": row.get("question"),
                "provider": row.get("provider"),
                "source": row.get("source"),
                "ok": row.get("ok"),
                "status_code": row.get("status_code"),
                "total_ms": _float(row.get("total_ms")),
                "db_query_count": row.get("db_query_count"),
                "skills": _json_list(row.get("skills")),
                "error": row.get("error"),
            }
            for row in rows[:20]
        ],
    }


def _json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 1):
    numeric = _float(value)
    return round(numeric, digits) if numeric is not None else None


def _average(values: Iterable[Any], digits: int = 1):
    clean = [_float(value) for value in values]
    clean = [value for value in clean if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), digits)


def _top_counts(counter: Dict[str, int], limit: int) -> list:
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _top_average(groups: Dict[str, list], limit: int) -> list:
    rows = [
        {"name": name, "avg_ms": _average(values, 1), "max_ms": _round(max(values), 1), "samples": len(values)}
        for name, values in groups.items()
        if values
    ]
    return sorted(rows, key=lambda item: (-(item.get("avg_ms") or 0), item["name"]))[:limit]


def api_cache_get(key: str):
    now = time.monotonic()
    with API_CACHE_LOCK:
        item = API_CACHE.get(key)
        if item and item["expires_at"] > now:
            return item["data"]
        if item:
            API_CACHE.pop(key, None)
    return None


def api_cache_set(key: str, data: Any, ttl_seconds: float):
    with API_CACHE_LOCK:
        API_CACHE[key] = {"expires_at": time.monotonic() + ttl_seconds, "data": data}
    return data


def api_cache_delete_prefix(prefix: str):
    with API_CACHE_LOCK:
        for key in list(API_CACHE):
            if key.startswith(prefix):
                API_CACHE.pop(key, None)


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
    cached = api_cache_get(key)
    if cached is not None:
        return cached
    return api_cache_set(key, builder(), ttl_seconds)


def json_default(value: Any):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def json_dumps(value: Any, **kwargs):
    return json.dumps(value, default=json_default, **kwargs)


def percentile(values, pct: float):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100) * len(ordered)) - 1))
    return ordered[index]


def api_perf_route_label():
    rule = getattr(request, "url_rule", None)
    if rule is not None and getattr(rule, "rule", None):
        return rule.rule
    return request.path or "-"


def record_api_request(response):
    started = getattr(g, "api_perf_started_at", None)
    if started is None:
        return
    path = request.path or ""
    if not path.startswith("/api/"):
        return

    now_epoch = time.time()
    sample = {
        "ts": now_epoch,
        "iso": datetime.fromtimestamp(now_epoch).isoformat(timespec="seconds"),
        "method": request.method,
        "path": path,
        "route": api_perf_route_label(),
        "endpoint": request.endpoint or "",
        "status": getattr(response, "status_code", None),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    cutoff = now_epoch - API_PERF_LOG_WINDOW_SEC
    with API_PERF_LOG_LOCK:
        API_PERF_LOG.append(sample)
        if len(API_PERF_LOG) > API_PERF_LOG_MAX_SAMPLES or (API_PERF_LOG and API_PERF_LOG[0]["ts"] < cutoff):
            API_PERF_LOG[:] = [
                item for item in API_PERF_LOG[-API_PERF_LOG_MAX_SAMPLES:]
                if item["ts"] >= cutoff
            ]


def api_performance_log(limit: int = 60):
    now_epoch = time.time()
    cutoff = now_epoch - API_PERF_LOG_WINDOW_SEC
    with API_PERF_LOG_LOCK:
        samples = [item.copy() for item in API_PERF_LOG if item["ts"] >= cutoff]

    groups = defaultdict(list)
    for sample in samples:
        groups[(sample["method"], sample["route"])].append(sample)

    endpoints = []
    for (method, route), rows in groups.items():
        durations = [row["duration_ms"] for row in rows if isinstance(row.get("duration_ms"), (int, float))]
        statuses = [int(row.get("status") or 0) for row in rows]
        error_count = sum(1 for status in statuses if status >= 500)
        warn_count = sum(1 for status in statuses if 400 <= status < 500)
        last = max(rows, key=lambda row: row["ts"])
        endpoints.append({
            "method": method,
            "route": route,
            "count": len(rows),
            "avg_ms": round(sum(durations) / len(durations), 1) if durations else None,
            "p95_ms": round(percentile(durations, 95), 1) if durations else None,
            "max_ms": round(max(durations), 1) if durations else None,
            "min_ms": round(min(durations), 1) if durations else None,
            "last_ms": round(last.get("duration_ms"), 1) if isinstance(last.get("duration_ms"), (int, float)) else None,
            "last_status": last.get("status"),
            "last_seen": last.get("iso"),
            "error_count": error_count,
            "warn_count": warn_count,
        })

    endpoints.sort(key=lambda item: (item["p95_ms"] or 0, item["count"]), reverse=True)
    slow = endpoints[:limit]
    frequent = sorted(endpoints, key=lambda item: (item["count"], item["avg_ms"] or 0), reverse=True)[:limit]
    durations = [sample["duration_ms"] for sample in samples if isinstance(sample.get("duration_ms"), (int, float))]
    return {
        "window_sec": API_PERF_LOG_WINDOW_SEC,
        "sample_count": len(samples),
        "endpoint_count": len(endpoints),
        "started_at": datetime.fromtimestamp(min((sample["ts"] for sample in samples), default=now_epoch)).isoformat(timespec="seconds") if samples else None,
        "last_seen": datetime.fromtimestamp(max((sample["ts"] for sample in samples), default=now_epoch)).isoformat(timespec="seconds") if samples else None,
        "avg_ms": round(sum(durations) / len(durations), 1) if durations else None,
        "p95_ms": round(percentile(durations, 95), 1) if durations else None,
        "max_ms": round(max(durations), 1) if durations else None,
        "slow_endpoints": slow,
        "frequent_endpoints": frequent,
    }


def json_ready(value: Any):
    return json.loads(json_dumps(value))


def get_schema_service():
    global _schema_service
    with _schema_service_lock:
        if _schema_service is None:
            _schema_service = HcSchemaService(execute_sql)
        return _schema_service


def invalidate_irrigation_snapshot_cache():
    service = globals().get("_irrigation_service")
    if service is not None:
        service.invalidate_snapshot_cache()
    service = globals().get("_context_service")
    if service is not None:
        service.invalidate("irrigation")


def invalidate_irrigation_pilot_cache():
    service = globals().get("_irrigation_service")
    if service is not None:
        service.invalidate_pilot_cache()


def invalidate_irrigation_weather_summary_cache():
    service = globals().get("_irrigation_service")
    if service is not None:
        service.invalidate_weather_summary_cache()
    service = globals().get("_context_service")
    if service is not None:
        service.invalidate("weather")


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


def fetch_climate_schedule_rules():
    ensure_scheduler_schema()
    return fetch_all(
        """
        with schedule_state as (
          select
            *,
            day_of_week = extract(isodow from now())::int - 1 as is_today,
            is_enabled
              and day_of_week = extract(isodow from now())::int - 1
              and to_char(localtime, 'HH24:MI') = to_char(start_time, 'HH24:MI')
              as should_run_now
          from hc.climate_schedule_rule
        )
        select
          id,
          label,
          day_of_week,
          to_char(start_time, 'HH24:MI') as start_time,
          is_enabled,
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
          rule_engine,
          updated_at
        from schedule_state
        order by day_of_week, start_time, id
        """
    )


def record_scheduler_shadow_audit():
    scheduler = get_scheduler_service()
    inserted = 0

    for event in scheduler.shadow_audit_events():
        domain = event["domain"]
        source = event["source"]
        source_ref = event["source_ref"]
        action = event["action"]
        status = event["status"]
        event_payload = dict(event["payload"])
        key = event["key"]
        row = scheduler.insert_run_once(
            key,
            domain,
            action,
            status,
            payload=event_payload,
        )
        if row:
            event_payload["scheduler_run_id"] = row.get("id")
            event_row = scheduler.insert_v2_event_once(
                f"v2:{key}",
                domain,
                action,
                status,
                event_payload,
            )
            plan_row = scheduler.insert_v2_irrigation_plan_once(event_row, action, event_payload)
            scheduler.insert_v2_irrigation_execution_once(plan_row, action, event_payload)
            x10_plan_row = scheduler.insert_v2_x10_plan_once(event_row, action, event_payload)
            scheduler.insert_v2_x10_execution_once(x10_plan_row, event_payload)
            climate_plan_row = scheduler.insert_v2_climate_plan_once(event_row, action, event_payload)
            scheduler.insert_v2_climate_execution_once(climate_plan_row, event_payload)
            inserted += 1
            print(f"[SCHEDULER] {status} domain={domain} source={source} ref={source_ref}", flush=True)
    return inserted


def check_db():
    return get_database_service().check()


def check_mqtt(timeout_s: float = 2.0) -> bool:
    return get_mqtt_client_service().check(timeout_s=timeout_s)


def publish_mqtt(topic: str, payload: Any, qos: int = 0, retain: bool = False) -> Tuple[bool, str]:
    return get_mqtt_client_service().publish(topic, payload, qos=qos, retain=retain)


def command_topics():
    return {
        "mode": f"{IRRIGATION_CMD_BASE}/mode",
        "pump": f"{IRRIGATION_CMD_BASE}/pump",
        "valve": f"{IRRIGATION_CMD_BASE}/valve",
        "config": f"{IRRIGATION_CMD_BASE}/config",
        "system": f"{IRRIGATION_CMD_BASE}/system",
    }


def irrigation_stop_payload(reason: str) -> Dict[str, Any]:
    return get_irrigation_service().stop_payload(reason)


def validate_schedule_time(value: Any, field: str) -> str:
    return get_irrigation_service().validate_schedule_time(value, field)


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        value = default
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def to_int(value: Any, default: int = 0) -> int:
    number = to_float(value)
    return default if number is None else int(round(number))


def unix_to_iso(value: Any):
    number = to_int(value, 0)
    if not number:
        return None
    return datetime.fromtimestamp(number).isoformat()


def json_time(value: Any):
    return value.isoformat() if hasattr(value, "isoformat") else value


def fetch_pilot_config():
    return get_irrigation_service().fetch_pilot_config()


def normalize_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def absolute_humidity_g_m3(temperature_c: Any, relative_humidity: Any):
    if temperature_c is None or relative_humidity is None:
        return None
    try:
        temp = float(temperature_c)
        humidity = float(relative_humidity)
    except (TypeError, ValueError):
        return None
    saturation_hpa = 6.112 * math.exp((17.62 * temp) / (243.12 + temp))
    vapor_pressure_hpa = (humidity / 100.0) * saturation_hpa
    return round((216.7 * vapor_pressure_hpa) / (273.15 + temp), 2)


_backup_service = None
_system_status_service = None


def get_backup_service():
    global _backup_service
    if _backup_service is None:
        _backup_service = BackupService(
            docker_socket_request=docker_socket_request,
            docker_exec_capture=docker_exec_capture,
        )
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
                    api_cache_get=api_cache_get,
                    api_cache_set=api_cache_set,
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
                    x10_day_mask_index_by_hc_day=lambda: [1, 2, 3, 4, 5, 6, 0],
                    x10_monitor_value=x10_monitor.value,
                    scheduler_modes=SCHEDULER_MODES,
                    v2_execution_enabled=HC_V2_EXECUTION_ENABLED,
                    v2_allow_irrigation=HC_V2_EXECUTION_ALLOW_IRRIGATION,
                    v2_allow_x10=HC_V2_EXECUTION_ALLOW_X10,
                    v2_allow_climate=HC_V2_EXECUTION_ALLOW_CLIMATE,
                    evaluate_irrigation_pilot=lambda **kwargs: get_irrigation_service().evaluate_pilot(**kwargs),
                    fetch_irrigation_v2_session=fetch_irrigation_v2_session,
                    irrigation_command_topic=lambda: command_topics()["valve"],
                    x10_schedule_clean_topic=f"{X10_BASE_TOPIC}/command/schedule_clean",
                    x10_weekly_schedule_topic=f"{X10_BASE_TOPIC}/command/schedule_clean_week",
                    climate_command_topic=f"{CLIMATE_BASE_TOPIC}/command",
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
                )
    return _process_binding_service


def get_power_wall_service():
    global _power_wall_service
    if _power_wall_service is None:
        with _power_wall_service_lock:
            if _power_wall_service is None:
                _power_wall_service = PowerWallService(
                    fetch_all=fetch_all,
                    fetch_one=fetch_one,
                    execute_one=execute_one,
                    publish_mqtt=publish_mqtt,
                    ensure_schema=ensure_power_wall_schema,
                    api_cache_get=api_cache_get,
                    api_cache_set=api_cache_set,
                    api_cache_delete_prefix=api_cache_delete_prefix,
                    normalize_text=normalize_text,
                    guard_repeat_seconds=POWER_WALL_GUARD_REPEAT_SECONDS,
                    process_binding_payload=lambda key: get_process_binding_service().binding(key, include_candidates=True),
                    process_binding_entity_id=lambda key: get_process_binding_service().selected_entity_id(key),
                )
    return _power_wall_service


def context_builders():
    return {
        "weather": lambda: {
            "ok": True,
            **get_irrigation_service().build_weather_snapshot(
                get_process_binding_service().selected_topic_base("irrigation_soil_moisture")
            ),
        },
        "irrigation": lambda: get_irrigation_service().snapshot(),
        "irrigation_pilot": lambda: get_irrigation_service().pilot_payload(),
        "irrigation_statistics": lambda: get_irrigation_service().statistics_payload(),
        "climate": lambda: get_climate_service().state_payload(),
        "climate_power_history": lambda: cached_api_payload("climate_power_history", 60, get_climate_service().power_history_payload),
        "climate_history": lambda: cached_api_payload("climate_history", 60, get_climate_service().parameter_history_payload),
        "climate_schedules": lambda: {"ok": True, "schedules": fetch_climate_schedule_rules()},
        "robot": lambda: get_robot_service().state_payload(),
        "power_wall": lambda: get_power_wall_service().state_payload(),
        "solar": lambda: cached_api_payload("solar_state", 8, solar_state_payload),
        "tuya": tuya_state_payload,
        "scheduler": lambda: get_scheduler_service().state_payload(),
        "scheduler_ai": lambda: get_scheduler_service().ai_summary_payload(),
        "notes": lambda: {"ok": True, **get_admin_service().fetch_notes()},
        "performance": lambda: get_system_status_service().performance_snapshot(),
        "server_power": lambda: cached_api_payload("performance_server_power", 60, get_energy_device_service().server_power_history_payload),
        "home_statistics": lambda: get_admin_service().homecontrol_statistics_payload(),
        "ai_chat_audit": lambda: ai_chat_audit_summary_payload(),
        "backup": lambda: get_backup_service().payload(),
    }


def get_context_service():
    global _context_service
    with _context_service_lock:
        if _context_service is None:
            _context_service = ContextService(
                context_builders(),
                realtime_ttl=HC_CONTEXT_REALTIME_TTL,
                statistics_ttl=HC_CONTEXT_STATISTICS_TTL,
            )
        return _context_service


def get_ai_proxy_service():
    global _ai_proxy_service
    with _ai_proxy_service_lock:
        if _ai_proxy_service is None:
            _ai_proxy_service = AiProxyService(
                AI_SERVER_URL,
                AI_SERVER_TIMEOUT,
                context_summary=lambda trace=None: get_context_service().ai_summary(trace=trace),
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
                    ensure_power_wall_schema,
                    ensure_process_binding_schema,
                    ensure_irrigation_summary_schema,
                    ensure_notes_schema,
                ]
            )
            _startup_service = StartupService(
                bootstrap=bootstrap,
                scheduler_poll_seconds=SCHEDULER_POLL_SECONDS,
                weather_poll_seconds=WEATHER_POLL_SECONDS,
                power_wall_guard_seconds=POWER_WALL_GUARD_SECONDS,
                safety_worker_enabled=SAFETY_WORKER_ENABLED,
                record_scheduler_shadow_audit=record_scheduler_shadow_audit,
                irrigation_scheduler_tick=lambda: get_irrigation_service().scheduler_tick(),
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
                context_refresh=lambda: get_context_service().warmup(DEFAULT_CONTEXT_REFRESH_SECTIONS),
                context_refresh_seconds=HC_CONTEXT_REFRESH_SECONDS,
                context_refresh_enabled=HC_CONTEXT_REFRESH_ENABLED,
            )
        return _startup_service


def parse_context_sections(value: str):
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


@app.before_request
def _start_worker_once():
    g.api_perf_started_at = time.perf_counter()
    g.db_query_count = 0
    get_startup_service().ensure_started()


@app.after_request
def _record_api_request(response):
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
register_ai_routes(
    app,
    get_ai_proxy_service=get_ai_proxy_service,
    get_ai_node_service=get_ai_node_service,
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
    get_system_status_service=get_system_status_service,
    json_ready=json_ready,
)


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
