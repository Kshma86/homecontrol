import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repository_service import RepositoryRegistry


class FakeDatabase:
    def __init__(self):
        self.calls = []

    def fetch_one(self, sql, params=()):
        self.calls.append(("fetch_one", sql, params))
        return {"ok": True}


class RepositoryServiceTest(unittest.TestCase):
    def test_shared_repository_delegates_to_database(self):
        database = FakeDatabase()
        registry = RepositoryRegistry(database)

        row = registry.shared.fetch_one("select 1", (1,))

        self.assertEqual(row, {"ok": True})
        self.assertEqual(database.calls, [("fetch_one", "select 1", (1,))])


if __name__ == "__main__":
    unittest.main()
