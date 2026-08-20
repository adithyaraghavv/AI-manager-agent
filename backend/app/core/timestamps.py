"""Shared helpers for parsing timestamps returned by Supabase.

Supabase's REST API returns timestamps as ISO 8601 strings, sometimes with a
trailing ``Z`` (UTC) and sometimes with a numeric offset. On Python 3.11+
``datetime.fromisoformat`` accepts both, so we don't need the historical
``.replace("Z", "+00:00")`` dance. We *do* still normalize naive datetimes to
UTC because a bare timestamp from Postgres arrives without tzinfo and downstream
code compares against ``datetime.now(timezone.utc)``.
"""

from datetime import datetime, timezone


def parse_supabase_ts(value: str) -> datetime:
    """Parse a Supabase ISO timestamp into a timezone-aware ``datetime``.

    Naive timestamps (no offset, no ``Z``) are assumed to be UTC — consistent
    with how Postgres stores ``timestamp with time zone`` when returned in the
    default representation.
    """
    ts = datetime.fromisoformat(value)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts
