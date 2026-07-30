from typing import Any, Iterable, Optional

import psycopg
from psycopg.rows import dict_row


class DatabaseService:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def conn(self, row_factory=None):
        return psycopg.connect(self.database_url, row_factory=row_factory)

    def fetch_all(self, sql: str, params: Iterable[Any] = ()):
        with self.conn(dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())

    def fetch_one(self, sql: str, params: Iterable[Any] = ()):
        with self.conn(dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()

    def execute_one(self, sql: str, params: Iterable[Any] = ()):
        with self.conn(dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                try:
                    return cur.fetchone()
                except psycopg.ProgrammingError:
                    return None

    def execute_sql(self, sql: str, params: Optional[Iterable[Any]] = None):
        with self.conn() as conn:
            with conn.cursor() as cur:
                if params is None:
                    cur.execute(sql)
                else:
                    cur.execute(sql, params)

    def check(self) -> bool:
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return cur.fetchone()[0] == 1
