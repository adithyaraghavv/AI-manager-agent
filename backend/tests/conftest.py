import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


def _fs_is_case_sensitive() -> bool:
    """Runtime check — Linux ext4 is case-sensitive, macOS APFS/HFS+ and
    Windows NTFS are case-insensitive by default. Tests that assert two
    identically-named-but-differently-cased files/folders are distinct only
    make sense on the former."""
    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "casetest_lower"
        probe.touch()
        return not (Path(td) / "CASETEST_LOWER").exists()


requires_case_sensitive_fs = pytest.mark.skipif(
    not _fs_is_case_sensitive(),
    reason=(
        "requires a case-sensitive filesystem — the invariant being tested "
        "protects against a Linux (ext4) bug that can't reproduce on macOS "
        "APFS/HFS+ or Windows NTFS. CI runs on ubuntu-latest which is case-sensitive."
    ),
)


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

    def select_active(self, table: str, active_column: str = "deleted_at", **filters) -> list[dict]:
        rows = self.select(table, **filters)
        return [r for r in rows if r.get(active_column) is None]

    def select_one_ci_active(self, table: str, column: str, value: str, active_column: str = "deleted_at") -> dict | None:
        for row in self._tables.get(table, []):
            if str(row.get(column, "")).lower() == value.lower() and row.get(active_column) is None:
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

    def rpc(self, function_name: str, params: dict) -> list[dict]:
        """Only simulates match_document_chunks (the one RPC this app uses) —
        ranks document_chunks rows by cosine similarity in plain Python,
        standing in for the real Postgres vector index."""
        if function_name != "match_document_chunks":
            raise ValueError(f"FakeSupabaseRestClient.rpc doesn't simulate {function_name!r}")

        def cosine_similarity(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(y * y for y in b) ** 0.5
            return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

        query_embedding = params["query_embedding"]
        match_doc_type = params.get("match_doc_type")
        match_count = params.get("match_count", 5)

        candidates = [
            row for row in self._tables.get("document_chunks", [])
            if row["client_id"] == params["match_client_id"]
            and (match_doc_type is None or row["doc_type"] == match_doc_type)
        ]
        ranked = sorted(candidates, key=lambda r: cosine_similarity(r["embedding"], query_embedding), reverse=True)
        return [
            {
                "id": row["id"],
                "doc_type": row["doc_type"],
                "version_number": row["version_number"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "similarity": cosine_similarity(row["embedding"], query_embedding),
            }
            for row in ranked[:match_count]
        ]


@pytest.fixture
def rest():
    return FakeSupabaseRestClient()
