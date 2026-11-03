import re
import time
from typing import Any, Callable, Dict, Iterable, List, Tuple

from psycopg.rows import dict_row
from sql_lab_database import SqlLabUnavailable


READ_ONLY_STARTERS = {"select", "with", "explain"}
FORBIDDEN_KEYWORDS = {
    "alter",
    "analyze",
    "call",
    "copy",
    "create",
    "delete",
    "drop",
    "execute",
    "grant",
    "insert",
    "merge",
    "notify",
    "refresh",
    "reindex",
    "reset",
    "revoke",
    "set",
    "truncate",
    "update",
    "vacuum",
}


class SqlLabService:
    def __init__(
        self,
        *,
        db_conn: Callable[..., Any],
        fetch_all: Callable[..., Any],
        fetch_one: Callable[..., Any],
        max_rows: int = 500,
        statement_timeout_ms: int = 7000,
    ):
        self.db_conn = db_conn
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.max_rows = max_rows
        self.statement_timeout_ms = statement_timeout_ms

    def schema(self) -> Dict[str, Any]:
        tables = self.fetch_all(
            """
            select
              n.nspname as schema_name,
              c.relname as table_name,
              case c.relkind
                when 'r' then 'table'
                when 'v' then 'view'
                when 'm' then 'materialized_view'
                when 'p' then 'partitioned_table'
                else c.relkind::text
              end as object_type,
              coalesce(s.n_live_tup, 0)::bigint as estimated_rows,
              obj_description(c.oid, 'pg_class') as description
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            left join pg_stat_user_tables s on s.relid = c.oid
            where n.nspname = 'hc'
              and n.nspname not like 'pg_toast%%'
              and c.relkind in ('r', 'v', 'm', 'p')
            order by n.nspname, c.relname
            """
        )
        columns = self.fetch_all(
            """
            select
              table_schema as schema_name,
              table_name,
              column_name,
              ordinal_position,
              data_type,
              udt_name,
              is_nullable,
              column_default
            from information_schema.columns
            where table_schema = 'hc'
            order by table_schema, table_name, ordinal_position
            """
        )
        indexes = self.fetch_all(
            """
            select schemaname as schema_name, tablename as table_name, indexname, indexdef
            from pg_indexes
            where schemaname = 'hc'
            order by schemaname, tablename, indexname
            """
        )
        constraints = self.fetch_all(
            """
            select
              tc.table_schema as schema_name,
              tc.table_name,
              tc.constraint_name,
              tc.constraint_type
            from information_schema.table_constraints tc
            where tc.table_schema = 'hc'
            order by tc.table_schema, tc.table_name, tc.constraint_name
            """
        )
        return {
            "ok": True,
            "tables": tables,
            "columns": columns,
            "indexes": indexes,
            "constraints": constraints,
            "limits": {
                "max_rows": self.max_rows,
                "statement_timeout_ms": self.statement_timeout_ms,
                "allowed": sorted(READ_ONLY_STARTERS),
            },
        }

    def preview(self, schema_name: str, table_name: str, limit: int = 25) -> Tuple[Dict[str, Any], int]:
        schema_name = str(schema_name or "").strip()
        table_name = str(table_name or "").strip()
        if schema_name != "hc":
            return {"ok": False, "error": "Only the hc schema is available"}, 400
        if not schema_name or not table_name:
            return {"ok": False, "error": "schema and table are required"}, 400
        exists = self.fetch_one(
            """
            select 1
            from information_schema.tables
            where table_schema = %s and table_name = %s
            """,
            (schema_name, table_name),
        )
        if not exists:
            return {"ok": False, "error": "table not found"}, 404
        safe_limit = max(1, min(int(limit or 25), 100))
        sql = f"select * from {self.quote_ident(schema_name)}.{self.quote_ident(table_name)} limit {safe_limit}"
        payload, status = self.run({"sql": sql, "limit": safe_limit})
        payload["preview"] = {"schema": schema_name, "table": table_name}
        return payload, status

    def run(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        sql = str(data.get("sql") or "").strip()
        if not sql:
            return {"ok": False, "error": "SQL is required"}, 400
        limit = max(1, min(int(data.get("limit") or self.max_rows), self.max_rows))
        safe_sql, error = self.read_only_sql(sql)
        if error:
            return {"ok": False, "error": error}, 400

        executable_sql = safe_sql
        limited = False
        if not safe_sql.lstrip().lower().startswith("explain"):
            executable_sql = f"select * from ({safe_sql}) as sql_lab_result limit {limit}"
            limited = True

        started = time.monotonic()
        try:
            with self.db_conn(dict_row) as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("set local transaction_read_only = on")
                        cur.execute(f"set local statement_timeout = {int(self.statement_timeout_ms)}")
                        cur.execute(executable_sql)
                        rows = list(cur.fetchall())
                        columns = [item.name for item in (cur.description or [])]
        except SqlLabUnavailable as exc:
            return {"ok": False, "error": str(exc), "read_only": True}, 503
        except Exception as exc:
            return {"ok": False, "error": str(exc), "read_only": True}, 400

        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        return {
            "ok": True,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "elapsed_ms": elapsed_ms,
            "limit": limit,
            "limited": limited,
            "read_only": True,
        }, 200

    def read_only_sql(self, sql: str) -> Tuple[str, str]:
        cleaned = self.strip_comments(sql).strip()
        cleaned = self.strip_single_trailing_semicolon(cleaned)
        if not cleaned:
            return "", "SQL is required"
        if self.has_statement_separator(cleaned):
            return "", "Only one SQL statement can be executed"

        starter_match = re.match(r"^\s*([a-zA-Z]+)", cleaned)
        starter = starter_match.group(1).lower() if starter_match else ""
        if starter not in READ_ONLY_STARTERS:
            return "", "Only SELECT, WITH and EXPLAIN queries are allowed"
        if starter == "explain" and not re.match(r"^\s*explain\s+(\([^)]+\)\s*)?(select|with)\b", cleaned, flags=re.IGNORECASE | re.DOTALL):
            return "", "EXPLAIN is allowed only for SELECT/WITH queries"

        lowered = re.sub(r"'([^']|'')*'", "''", cleaned.lower())
        forbidden = sorted(word for word in FORBIDDEN_KEYWORDS if re.search(rf"\b{re.escape(word)}\b", lowered))
        if forbidden:
            return "", f"Read-only lab rejected keyword: {', '.join(forbidden)}"
        return cleaned, ""

    @staticmethod
    def strip_comments(sql: str) -> str:
        result: List[str] = []
        i = 0
        in_single = False
        in_double = False
        while i < len(sql):
            char = sql[i]
            next_char = sql[i + 1] if i + 1 < len(sql) else ""
            if in_single:
                result.append(char)
                if char == "'" and next_char == "'":
                    result.append(next_char)
                    i += 2
                    continue
                if char == "'":
                    in_single = False
                i += 1
                continue
            if in_double:
                result.append(char)
                if char == '"':
                    in_double = False
                i += 1
                continue
            if char == "'":
                in_single = True
                result.append(char)
                i += 1
                continue
            if char == '"':
                in_double = True
                result.append(char)
                i += 1
                continue
            if char == "-" and next_char == "-":
                i = sql.find("\n", i)
                if i == -1:
                    break
                result.append("\n")
                i += 1
                continue
            if char == "/" and next_char == "*":
                end = sql.find("*/", i + 2)
                i = len(sql) if end == -1 else end + 2
                result.append(" ")
                continue
            result.append(char)
            i += 1
        return "".join(result)

    @staticmethod
    def strip_single_trailing_semicolon(sql: str) -> str:
        stripped = sql.rstrip()
        if stripped.endswith(";"):
            return stripped[:-1].rstrip()
        return stripped

    @staticmethod
    def has_statement_separator(sql: str) -> bool:
        in_single = False
        in_double = False
        for index, char in enumerate(sql):
            next_char = sql[index + 1] if index + 1 < len(sql) else ""
            if in_single:
                if char == "'" and next_char == "'":
                    continue
                if char == "'":
                    in_single = False
                continue
            if in_double:
                if char == '"':
                    in_double = False
                continue
            if char == "'":
                in_single = True
                continue
            if char == '"':
                in_double = True
                continue
            if char == ";":
                return True
        return False

    @staticmethod
    def quote_ident(value: str) -> str:
        return '"' + str(value).replace('"', '""') + '"'
