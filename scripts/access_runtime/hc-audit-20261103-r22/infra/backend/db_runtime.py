from typing import Any, Iterable, Optional

from database_service import DatabaseService
from runtime_utils import record_db_query


class DatabaseRuntime:
    def __init__(self, database_url: str):
        self.database = DatabaseService(database_url, expected_role='hc_app')

    def conn(self, row_factory=None):
        return self.database.conn(row_factory)

    def fetch_all(self, sql: str, params: Iterable[Any] = ()):
        record_db_query()
        return self.database.fetch_all(sql, params)

    def fetch_one(self, sql: str, params: Iterable[Any] = ()):
        record_db_query()
        return self.database.fetch_one(sql, params)

    def execute_one(self, sql: str, params: Iterable[Any] = ()):
        record_db_query()
        return self.database.execute_one(sql, params)

    def execute_sql(self, sql: str, params: Optional[Iterable[Any]] = None):
        record_db_query()
        return self.database.execute_sql(sql, params)

    def check(self) -> bool:
        return self.database.check()
