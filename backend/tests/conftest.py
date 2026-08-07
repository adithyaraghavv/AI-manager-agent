import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


class FakeSupabaseRestClient:
    """In-memory stand-in for SupabaseRestClient, same interface, no network calls.

    Mirrors how LocalFilesystemStorage stands in for a real StorageBackend in tests —
    exercises the exact select/select_one/insert/update contract the services layer relies on.
    """

    def __init__(self):
        self._tables: dict[str, list[dict]] = {}
        self._next_id = 1

    def select(self, table: str, **filters) -> list[dict]:
        rows = self._tables.get(table, [])
        return [r for r in rows if all(r.get(k) == v for k, v in filters.items())]

    def select_one(self, table: str, **filters) -> dict | None:
        rows = self.select(table, **filters)
        return rows[0] if rows else None

    def select_one_ci(self, table: str, column: str, value: str) -> dict | None:
        for row in self._tables.get(table, []):
            if str(row.get(column, "")).lower() == value.lower():
                return row
        return None

    def select_ilike_any(self, table: str, columns: list[str], query: str) -> list[dict]:
        q = query.lower()
        return [
            row for row in self._tables.get(table, [])
            if any(q in str(row.get(col, "")).lower() for col in columns)
        ]

    def insert(self, table: str, data: dict) -> dict:
        row = {"id": self._next_id, **data}
        self._next_id += 1
        self._tables.setdefault(table, []).append(row)
        return row

    def update(self, table: str, match: dict, data: dict) -> dict:
        rows = self.select(table, **match)
        for row in rows:
            row.update(data)
        return rows[0]

    def delete(self, table: str, **filters) -> None:
        rows = self._tables.get(table, [])
        self._tables[table] = [r for r in rows if not all(r.get(k) == v for k, v in filters.items())]


@pytest.fixture
def rest():
    return FakeSupabaseRestClient()
