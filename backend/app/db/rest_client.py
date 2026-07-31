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

    def close(self) -> None:
        self._client.close()
