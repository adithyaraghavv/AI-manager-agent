"""Thin client for Supabase's auto-generated REST API (PostgREST).

Used for runtime app queries instead of a direct Postgres connection,
specifically because a direct connection (raw TCP to port 5432/6543) gets
blocked by some corporate network firewalls, while plain HTTPS (this) does
not. Schema management (Alembic migrations, one-off seed scripts) still uses
a direct connection via DATABASE_URL — that's a rare, occasional operation
you can run from any network that can reach Supabase directly. This client
is for the frequent, everyday path (chat, upload, download) that must work
from wherever the app happens to be running.

Auth uses the Supabase *service_role* key, which bypasses Row Level Security
entirely — this backend is the sole trusted access point (the frontend never
talks to Supabase directly), so that's the correct key here. Never send this
key to a browser/frontend.
"""
import httpx


class SupabaseRestClient:
    def __init__(self, url: str, key: str, timeout: float = 15.0):
        self._client = httpx.Client(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def select(self, table: str, **filters: object) -> list[dict]:
        """Rows in `table` matching all filters (AND-combined equality)."""
        params = {k: f"eq.{v}" for k, v in filters.items()}
        response = self._client.get(f"/{table}", params=params)
        response.raise_for_status()
        return response.json()

    def select_one(self, table: str, **filters: object) -> dict | None:
        rows = self.select(table, **filters)
        return rows[0] if rows else None

    def select_one_ci(self, table: str, column: str, value: str) -> dict | None:
        """Case-insensitive exact-match lookup — "Hillenbrand" and "hillenbrand"
        resolve to the same row. Escapes ILIKE's wildcard characters (%, _, \\)
        so this stays an exact match, not a pattern search."""
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params = {column: f"ilike.{escaped}"}
        response = self._client.get(f"/{table}", params=params)
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    def select_active(self, table: str, active_column: str = "deleted_at", **filters: object) -> list[dict]:
        """Like select(), but excludes soft-deleted rows (where `active_column` is set)."""
        params = {k: f"eq.{v}" for k, v in filters.items()}
        params[active_column] = "is.null"
        response = self._client.get(f"/{table}", params=params)
        response.raise_for_status()
        return response.json()

    def select_one_ci_active(self, table: str, column: str, value: str, active_column: str = "deleted_at") -> dict | None:
        """Same as select_one_ci, but additionally excludes soft-deleted rows."""
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params = {column: f"ilike.{escaped}", active_column: "is.null"}
        response = self._client.get(f"/{table}", params=params)
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    def select_ilike_any(self, table: str, columns: list[str], query: str) -> list[dict]:
        """Rows in `table` where ANY of `columns` contains `query` (case-insensitive,
        substring match — not an exact match like select_one_ci). Escapes ILIKE's
        wildcard characters so the search term itself can't inject a pattern."""
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        or_clause = ",".join(f"{col}.ilike.*{escaped}*" for col in columns)
        response = self._client.get(f"/{table}", params={"or": f"({or_clause})"})
        response.raise_for_status()
        return response.json()

    def insert(self, table: str, data: dict) -> dict:
        response = self._client.post(
            f"/{table}", json=data, headers={"Prefer": "return=representation"}
        )
        response.raise_for_status()
        return response.json()[0]

    def update(self, table: str, match: dict, data: dict) -> dict:
        params = {k: f"eq.{v}" for k, v in match.items()}
        response = self._client.patch(
            f"/{table}", params=params, json=data, headers={"Prefer": "return=representation"}
        )
        response.raise_for_status()
        return response.json()[0]

    def delete(self, table: str, **filters: object) -> None:
        """Delete rows in `table` matching all filters (AND-combined equality).
        No-op (not an error) if nothing matches."""
        params = {k: f"eq.{v}" for k, v in filters.items()}
        response = self._client.delete(f"/{table}", params=params)
        response.raise_for_status()

    def close(self) -> None:
        self._client.close()
