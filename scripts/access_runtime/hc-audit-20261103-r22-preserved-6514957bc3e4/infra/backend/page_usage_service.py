from runtime_schema_contract import check_runtime_schema
import threading
from typing import Any, Callable, Dict


class PageUsageService:
    def __init__(self, *, fetch_all: Callable[..., Any], execute_one: Callable[..., Any], execute_sql: Callable[..., Any]):
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
            check_runtime_schema(self.execute_sql, "page_usage")
            self._schema_ready = True

    def record(self, row: Dict[str, Any]) -> None:
        self.ensure_schema()
        self.execute_one(
            """
            insert into hc.page_usage_event (
                page_id, client_id, device_class, viewport_width, viewport_height, standalone, user_agent
            ) values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["page_id"], row["client_id"], row["device_class"], row.get("viewport_width"),
                row.get("viewport_height"), bool(row.get("standalone")), row.get("user_agent"),
            ),
        )

    def summary(self, days: int = 30) -> Dict[str, Any]:
        self.ensure_schema()
        days = max(1, min(int(days), 365))
        rows = self.fetch_all(
            """
            with filtered as (
                select * from hc.page_usage_event
                where created_at >= now() - (%s * interval '1 day')
            ), totals as (
                select count(distinct client_id)::int as total_devices from filtered
            )
            select page_id, device_class, count(*)::int as views,
                   count(distinct client_id)::int as devices,
                   max(created_at) as last_seen,
                   totals.total_devices
            from filtered cross join totals
            group by page_id, device_class, totals.total_devices
            order by views desc, page_id, device_class
            """,
            (days,),
        )
        return {"ok": True, "days": days, "rows": rows}
