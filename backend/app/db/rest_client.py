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
from collections.abc import Sequence

import httpx

# PostgREST accepts arbitrarily long URLs in theory, but proxies (Cloudflare,
# nginx defaults) typically cap request lines around 8 KiB. Chunking at 500
# values keeps a single ?col=in.(...) filter well under that even when values
# are UUIDs (~40 chars each including quoting/commas). Callers with tighter
# limits can loop over their own chunks.
_SELECT_IN_CHUNK_SIZE = 500


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

    def _get_rows(self, table: str, params: dict) -> list[dict]:
        """Send a GET to `/{table}` with `params`, raise on HTTP error, return
        the parsed JSON body. Shared boilerplate for every select* variant —
        each caller's job is just to build the params dict for its filter shape."""
        response = self._client.get(f"/{table}", params=params)
        response.raise_for_status()
        return response.json()

    def select(self, table: str, **filters: object) -> list[dict]:
        """Rows in `table` matching all filters (AND-combined equality)."""
        params = {k: f"eq.{v}" for k, v in filters.items()}
        return self._get_rows(table, params)

    def select_one(self, table: str, **filters: object) -> dict | None:
        rows = self.select(table, **filters)
        return rows[0] if rows else None

    def select_one_ci(self, table: str, column: str, value: str) -> dict | None:
        """Case-insensitive exact-match lookup — "Hillenbrand" and "hillenbrand"
        resolve to the same row. Escapes ILIKE's wildcard characters (%, _, \\)
        so this stays an exact match, not a pattern search."""
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self._get_rows(table, {column: f"ilike.{escaped}"})
        return rows[0] if rows else None

    def select_active(self, table: str, active_column: str = "deleted_at", **filters: object) -> list[dict]:
        """Like select(), but excludes soft-deleted rows (where `active_column` is set)."""
        params = {k: f"eq.{v}" for k, v in filters.items()}
        params[active_column] = "is.null"
        return self._get_rows(table, params)

    def select_one_ci_active(self, table: str, column: str, value: str, active_column: str = "deleted_at") -> dict | None:
        """Same as select_one_ci, but additionally excludes soft-deleted rows."""
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self._get_rows(table, {column: f"ilike.{escaped}", active_column: "is.null"})
        return rows[0] if rows else None

    def select_ilike_any(self, table: str, columns: list[str], query: str) -> list[dict]:
        """Rows in `table` where ANY of `columns` contains `query` (case-insensitive,
        substring match — not an exact match like select_one_ci).

        Issues one plain request per column and merges results, rather than
        building a composite `or=(...)` filter by hand — PostgREST's OR syntax
        treats commas/parentheses as structural, and escaping only the ILIKE
        wildcard characters (%, _, \\) left those unescaped, so a search term
        containing a comma or paren could inject extra conditions into the
        query and widen it far beyond a genuine substring match. Per-column
        requests avoid that mini-language entirely — each one is a single
        simple `column=ilike.value` filter, which isn't comma/paren-parsed."""
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        seen_ids: set = set()
        results: list[dict] = []
        for col in columns:
            for row in self._get_rows(table, {col: f"ilike.*{escaped}*"}):
                row_id = row.get("id")
                if row_id in seen_ids:
                    continue
                seen_ids.add(row_id)
                results.append(row)
        return results

    def select_in(self, table: str, column: str, values: Sequence) -> list[dict]:
        """Rows in `table` where `column` is any of `values` (SQL `IN (...)`).

        The point is doing this in *one* HTTP round-trip instead of len(values)
        per-id lookups — this is the foundation for eliminating N+1 patterns
        in the dashboard/search paths (see PRs 3 and 4). Returns [] without
        any HTTP call when `values` is empty (a common edge case worth
        short-circuiting).

        PostgREST's `in.(v1,v2,...)` filter treats commas, parentheses, and
        quotes as structural characters, so values that contain any of those
        must be wrapped in double quotes with inner quotes and backslashes
        escaped. Bare numeric/simple values pass through unquoted.

        For very large value lists we chunk into multiple requests
        (_SELECT_IN_CHUNK_SIZE) to stay under typical proxy URL-length limits,
        then concatenate the results. Order across chunks is not guaranteed
        (PostgREST returns rows in an unspecified order without an explicit
        ORDER BY anyway, so callers should not rely on it)."""
        if not values:
            return []

        rows: list[dict] = []
        for start in range(0, len(values), _SELECT_IN_CHUNK_SIZE):
            chunk = values[start : start + _SELECT_IN_CHUNK_SIZE]
            encoded = ",".join(self._encode_in_value(v) for v in chunk)
            rows.extend(self._get_rows(table, {column: f"in.({encoded})"}))
        return rows

    @staticmethod
    def _encode_in_value(value: object) -> str:
        """Render one value for PostgREST's `in.(...)` list.

        Strings containing any of PostgREST's structural characters (comma,
        parentheses, double quote, backslash, whitespace) are wrapped in
        double quotes with `\\` and `"` escaped. Everything else is stringified
        as-is — numeric ids and UUIDs are the common case and stay unquoted."""
        if isinstance(value, str):
            if any(c in value for c in ',()"\\ \t\n'):
                escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                return f'"{escaped}"'
            return value
        return str(value)

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

    def rpc(self, function_name: str, params: dict) -> list[dict]:
        """Calls a Postgres function exposed via PostgREST's /rpc/ endpoint —
        for queries a plain select/filter can't express, e.g. vector
        similarity search (see match_document_chunks)."""
        response = self._client.post(f"/rpc/{function_name}", json=params)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._client.close()
