"""Seeds one realistic-looking stale demo client for showing the manager
dashboard's stale-flagging + copy-reminder feature to someone.

Not part of the app's normal data — this is purely a demo aid. It creates
(or refreshes) a client that finished Pre-requisites `--days-stale` days ago
and hasn't been touched since, so it shows up on the dashboard as stuck on
Requirement Analysis with the real STALE_AFTER_DAYS threshold, no config
hacks required. Safe to re-run any time before a demo to refresh the
timestamps back to "N days ago" from now.

Uses the same Supabase REST client the running app uses (SUPABASE_URL/
SUPABASE_KEY in .env) — not a direct Postgres connection — since this is
meant to be run wherever the app itself runs, on any network.
"""

import argparse
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.core.file_naming import build_filename
from app.core.phase_config import get_phase_config
from app.db.rest_client import SupabaseRestClient

DEMO_CLIENT_NAME = "Globex Industries"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def seed_demo_dashboard(
    rest: SupabaseRestClient, client_name: str, days_stale: int
) -> None:
    config = get_phase_config()
    prereqs = config.phases[0]  # "Pre-requisites" — filed and done
    backdate = datetime.now(timezone.utc) - timedelta(days=days_stale)

    client = rest.select_one("clients", name=client_name)
    if client is None:
        client = rest.insert(
            "clients", {"name": client_name, "created_at": _iso(backdate)}
        )
    else:
        rest.update("clients", {"id": client["id"]}, {"created_at": _iso(backdate)})

    for doc_type in prereqs.required_documents:
        filename = build_filename(doc_type, client_name, "txt", timestamp=backdate)
        storage_path = f"{client_name}/{prereqs.sequence:02d}_{prereqs.name}/{filename}"
        record = rest.select_one(
            "client_documents", client_id=client["id"], doc_type=doc_type
        )
        if record is None:
            rest.insert(
                "client_documents",
                {
                    "client_id": client["id"],
                    "phase_name": prereqs.name,
                    "doc_type": doc_type,
                    "storage_path": storage_path,
                    "filename": filename,
                    "uploaded_at": _iso(backdate),
                },
            )
        else:
            rest.update(
                "client_documents",
                {"id": record["id"]},
                {"uploaded_at": _iso(backdate)},
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-name", default=DEMO_CLIENT_NAME)
    parser.add_argument(
        "--days-stale",
        type=int,
        default=5,
        help="How many days ago the client's last activity should look (default 5, "
        "comfortably past the default 3-day STALE_AFTER_DAYS threshold)",
    )
    args = parser.parse_args()

    rest = SupabaseRestClient(settings.supabase_url, settings.supabase_key)
    try:
        seed_demo_dashboard(rest, args.client_name, args.days_stale)
        print(
            f"Seeded/refreshed demo client {args.client_name!r}: "
            f"Pre-requisites complete {args.days_stale} days ago, "
            "stuck on Requirement Analysis, should show as Stale on the dashboard."
        )
    finally:
        rest.close()


if __name__ == "__main__":
    main()
