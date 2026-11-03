from runtime_schema_contract import check_runtime_schema
import json
import threading
from collections import defaultdict
from typing import Any, Callable, Dict, Iterable, Optional


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


class AiChatAuditService:
    def __init__(
        self,
        *,
        fetch_all: Callable[..., Any],
        execute_one: Callable[..., Any],
        execute_sql: Callable[..., Any],
    ):
        self.fetch_all = fetch_all
        self.execute_one = execute_one
        self.execute_sql = execute_sql
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            check_runtime_schema(self.execute_sql, "ai_audit")
            self._schema_ready = True

    def insert(self, row: Dict[str, Any]) -> None:
        self.ensure_schema()
        self.execute_one(
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

    def summary_payload(self, limit: int = 80) -> Dict[str, Any]:
        self.ensure_schema()
        rows = self.fetch_all(
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
