"""Permanently deletes every client NOT in a given keep-list, for cleaning up
demo/test data before a real demo (e.g. keeping only 5 curated clients).

This is a hard delete — unlike client_service.delete_client (soft-delete,
recoverable) and purge_deleted_clients (only purges clients already
soft-deleted, after a retention window), this removes a client immediately
regardless of its deleted_at state. There is no undo.

For each client not being kept, this removes every row that references it
(document_chunks, document_versions, not_applicable_documents, sow_metadata,
client_documents), the client row itself, and its SharePoint/local storage
folder. purge_deleted_clients() only cleans up client_documents — this
script additionally cleans up the other client-scoped tables so no orphaned
rows are left behind for a client that no longer exists.

Defaults to a dry run; --apply actually deletes.

Usage (from backend/):
    uv run python -m app.db.purge_clients_except "Lilly" "SiriusXM" "WestPharma" "Hillenbrand-AI" "Adithya"
    uv run python -m app.db.purge_clients_except "Lilly" "SiriusXM" "WestPharma" "Hillenbrand-AI" "Adithya" --apply
"""

import argparse

from app.config import settings
from app.db.rest_client import SupabaseRestClient
from app.deps import get_client_storage
from app.storage.base import StorageBackend

# Tables that reference clients.id, in the order they must be deleted (all
# before the clients row itself, to respect foreign keys).
_CLIENT_SCOPED_TABLES = (
    "document_chunks",
    "document_versions",
    "not_applicable_documents",
    "sow_metadata",
    "client_documents",
)


def purge_clients_except(
    rest: SupabaseRestClient,
    storage: StorageBackend,
    keep_names: list[str],
    apply: bool,
) -> list[str]:
    """Returns the names of clients purged (or that would be purged, in a
    dry run)."""
    keep_normalized = {name.strip().lower() for name in keep_names}
    to_purge = [
        client
        for client in rest.select("clients")
        if client["name"].strip().lower() not in keep_normalized
    ]

    purged_names = []
    for client in to_purge:
        purged_names.append(client["name"])
        if not apply:
            continue
        for table in _CLIENT_SCOPED_TABLES:
            rest.delete(table, client_id=client["id"])
        rest.delete("clients", id=client["id"])
        storage.delete_dir(client["name"])

    return purged_names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "keep",
        nargs="+",
        help="Names of the clients to KEEP — every other client is purged.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete (default: dry run, just prints what would be purged).",
    )
    args = parser.parse_args()

    rest = SupabaseRestClient(settings.supabase_url, settings.supabase_key)
    storage = get_client_storage()
    try:
        purged = purge_clients_except(rest, storage, args.keep, apply=args.apply)
        if not purged:
            print("Nothing to purge — every client is already in the keep list.")
        elif args.apply:
            print(f"Permanently purged {len(purged)} client(s): {', '.join(purged)}")
        else:
            print(f"Would permanently purge {len(purged)} client(s): {', '.join(purged)}")
            print("\nDry run only — re-run with --apply to actually delete.")
    finally:
        rest.close()


if __name__ == "__main__":
    main()
