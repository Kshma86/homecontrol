import json
import math
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from flask import g, request
from read_model_cache import ReadModelCache


def json_default(value: Any):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def json_dumps(value: Any, **kwargs):
    return json.dumps(value, default=json_default, **kwargs)


def json_ready(value: Any):
    return json.loads(json_dumps(value))


def normalize_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


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


def percentile(values, pct: float):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100) * len(ordered)) - 1))
    return ordered[index]


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


class ApiCache(ReadModelCache):
    def set(self, key: str, data: Any, ttl_seconds: float):
        return super().set(key, data, ttl_seconds)

    def delete_prefix(self, prefix: str):
        return self.invalidate(prefix=prefix)

    def cached_payload(self, key: str, ttl_seconds: float, builder):
        return super().cached_payload(key, ttl_seconds, builder)


class ApiPerformanceLog:
    def __init__(self, *, window_sec: float, max_samples: int):
        self.window_sec = float(window_sec)
        self.max_samples = int(max_samples)
        self._samples = []
        self._lock = threading.Lock()

    def route_label(self):
        rule = getattr(request, "url_rule", None)
        if rule is not None and getattr(rule, "rule", None):
            return rule.rule
        return request.path or "-"

    def record_request(self, response):
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
            "route": self.route_label(),
            "endpoint": request.endpoint or "",
            "status": getattr(response, "status_code", None),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        cutoff = now_epoch - self.window_sec
        with self._lock:
            self._samples.append(sample)
            if len(self._samples) > self.max_samples or (self._samples and self._samples[0]["ts"] < cutoff):
                self._samples[:] = [
                    item for item in self._samples[-self.max_samples:]
                    if item["ts"] >= cutoff
                ]

    def payload(self, limit: int = 60):
        now_epoch = time.time()
        cutoff = now_epoch - self.window_sec
        with self._lock:
            samples = [item.copy() for item in self._samples if item["ts"] >= cutoff]

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
            "window_sec": self.window_sec,
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
