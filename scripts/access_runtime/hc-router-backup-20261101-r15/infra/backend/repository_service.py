from typing import Any, Iterable, Optional


class SqlRepository:
    def __init__(self, database):
        self.database = database

    def conn(self, row_factory=None):
        return self.database.conn(row_factory)

    def fetch_all(self, sql: str, params: Iterable[Any] = ()):
        return self.database.fetch_all(sql, params)

    def fetch_one(self, sql: str, params: Iterable[Any] = ()):
        return self.database.fetch_one(sql, params)

    def execute_one(self, sql: str, params: Iterable[Any] = ()):
        return self.database.execute_one(sql, params)

    def execute_sql(self, sql: str, params: Optional[Iterable[Any]] = None):
        return self.database.execute_sql(sql, params)


class RepositoryRegistry:
    def __init__(self, database):
        self.shared = SqlRepository(database)
