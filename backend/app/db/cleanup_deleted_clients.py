"""Permanently purges clients soft-deleted more than N days ago.

Soft-delete (app.services.client_service.delete_client) only hides a client —
it keeps the database row, document records, and storage folder intact so an
accidental confirm can be undone. This script is the other half: the actual,
irreversible cleanup, meant to be run periodically (cron, scheduled task,
or by hand) rather than automatically on every request.

Uses the same Supabase REST client the running app uses (SUPABASE_URL/
SUPABASE_KEY in .env), not a direct Postgres connection — same reasoning as
seed_templates.py and seed_demo_dashboard.py: this should be runnable from
any network, not just ones that can reach Postgres directly.
"""

import argparse

from app.config import settings
from app.db.rest_client import SupabaseRestClient
from app.deps import get_client_storage
from app.services.client_service import purge_deleted_clients


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=45,
        help="Permanently remove clients deleted more than this many days ago (default: 45)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be purged without actually deleting anything",
    )
    args = parser.parse_args()

    rest = SupabaseRestClient(settings.supabase_url, settings.supabase_key)
    storage = get_client_storage()

    try:
        if args.dry_run:
            from datetime import datetime, timedelta, timezone

            from app.core.timestamps import parse_supabase_ts

            cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than_days)
            candidates = []
            for client in rest.select("clients"):
                deleted_at = client.get("deleted_at")
                if not deleted_at:
                    continue
                deleted_ts = parse_supabase_ts(deleted_at)
                if deleted_ts <= cutoff:
                    candidates.append(client["name"])
            if candidates:
                print(
                    f"Would permanently purge {len(candidates)} client(s): {', '.join(candidates)}"
                )
            else:
                print("Nothing to purge.")
        else:
            purged = purge_deleted_clients(rest, storage, args.older_than_days)
            if purged:
                print(
                    f"Permanently purged {len(purged)} client(s): {', '.join(purged)}"
                )
            else:
                print("Nothing to purge.")
    finally:
        rest.close()


if __name__ == "__main__":
    main()
