from typing import Any, Iterable, Optional

import psycopg
from psycopg.rows import dict_row


class DatabaseService:
    def __init__(self, database_url: str, *, expected_role=None):
        self.database_url = database_url
        self.expected_role = expected_role

    def conn(self, row_factory=None):
        connection = psycopg.connect(self.database_url, row_factory=row_factory)
        if self.expected_role is not None:
            try:
                with connection.transaction():
                    with connection.cursor(row_factory=psycopg.rows.tuple_row) as cursor:
                        cursor.execute('''select current_user=%s and session_user=%s
                          and not(rolsuper or rolcreatedb or rolcreaterole or rolreplication or rolbypassrls or rolinherit)
                          and not exists(select 1 from pg_auth_members where member=r.oid)
                          and not has_schema_privilege('hc','CREATE')
                          and not has_database_privilege(current_database(),'CREATE')
                          and not exists(select 1 from pg_class where relowner=r.oid)
                          from pg_roles r where rolname=current_user''', (self.expected_role, self.expected_role))
                        row = cursor.fetchone()
                        if not row or row[0] is not True:
                            raise RuntimeError('Unsafe runtime database role')
            except Exception:
                connection.close()
                raise RuntimeError('Runtime requires the restricted HC-39 application role.') from None
        return connection

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
