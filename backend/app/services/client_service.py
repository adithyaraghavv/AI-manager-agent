"""Client folder lifecycle: creation of the client row + full phase sub-structure
on first contact, and lookup of which documents already exist for a client."""
from datetime import datetime, timedelta, timezone

from app.core.phase_config import PhaseConfig
from app.db.rest_client import SupabaseRestClient
from app.storage.base import StorageBackend


def get_or_create_client(
    rest: SupabaseRestClient, storage: StorageBackend, config: PhaseConfig, client_name: str
) -> dict:
    """Case-insensitive lookup — "Hillenbrand" and "hillenbrand" resolve to the
    same client, never two different ones. Callers must use the returned dict's
    `name` (the canonical stored casing) for any storage path they build
    afterward, not the raw `client_name` argument — see upload_document, which
    does exactly that. Using whatever casing happened to be typed this time
    would file documents under a different folder on a case-sensitive
    filesystem (Linux), even though the DB record correctly points to the same
    client either way.

    Only matches an ACTIVE (not soft-deleted) client — if "Acme" was deleted
    and someone later uploads for "Acme" again before the retention window's
    cleanup runs, this creates a fresh client rather than silently reviving
    the deleted one."""
    client = rest.select_one_ci_active("clients", "name", client_name)
    is_new = client is None
    if client is None:
        client = rest.insert("clients", {"name": client_name})

    canonical_name = client["name"]
    if is_new or not storage.exists(canonical_name):
        storage.make_dir(canonical_name)
        for phase in config.phases:
            storage.make_dir(f"{canonical_name}/{phase.sequence:02d}_{phase.name}")

    return client


def existing_document_types(rest: SupabaseRestClient, client: dict) -> set[str]:
    """Document types actually FILED for this client — does not include
    types marked not-applicable (see not_applicable_document_types).
    Callers that feed gating usually want the two combined; callers that
    display real filing status (dashboard, status checks) want this alone
    so they can show "filed" vs "not applicable" as distinct states."""
    rows = rest.select("client_documents", client_id=client["id"])
    return {row["doc_type"] for row in rows}


def not_applicable_document_types(rest: SupabaseRestClient, client: dict) -> set[str]:
    """Document types explicitly marked as not required for this client —
    see mark_document_not_applicable. Gating treats these the same as
    filed documents (they stop counting as missing) without a fake
    ClientDocument row ever being created."""
    rows = rest.select("not_applicable_documents", client_id=client["id"])
    return {row["doc_type"] for row in rows}


def satisfied_document_types(rest: SupabaseRestClient, client: dict) -> set[str]:
    """Everything gating should treat as "not missing": actually filed
    documents, union not-applicable ones. This is what request_template/
    upload_document must pass to check_gate — never existing_document_types
    alone, or a not-applicable earlier-phase document would wrongly keep
    blocking every later phase forever."""
    return existing_document_types(rest, client) | not_applicable_document_types(rest, client)


def mark_document_not_applicable(
    rest: SupabaseRestClient, client: dict, doc_type: str, reason: str | None = None, marked_by: str | None = None
) -> None:
    """Marks a document type as not required for this client. Idempotent —
    marking an already-marked doc_type just updates the reason/marked_by
    rather than erroring or duplicating."""
    existing = rest.select_one("not_applicable_documents", client_id=client["id"], doc_type=doc_type)
    if existing is None:
        rest.insert(
            "not_applicable_documents",
            {"client_id": client["id"], "doc_type": doc_type, "reason": reason, "marked_by": marked_by},
        )
    else:
        rest.update("not_applicable_documents", {"id": existing["id"]}, {"reason": reason, "marked_by": marked_by})


def unmark_document_not_applicable(rest: SupabaseRestClient, client: dict, doc_type: str) -> bool:
    """Reverses a not-applicable mark — the document type goes back to being
    treated as genuinely required/missing. Returns False (no-op, not an
    error) if it was never marked."""
    existing = rest.select_one("not_applicable_documents", client_id=client["id"], doc_type=doc_type)
    if existing is None:
        return False
    rest.delete("not_applicable_documents", id=existing["id"])
    return True


def find_client(rest: SupabaseRestClient, client_name: str) -> dict | None:
    """Look up a client by name (case-insensitively — see get_or_create_client)
    WITHOUT creating one. Used anywhere that must not have the side effect of
    materializing a client that doesn't exist yet (e.g. proposing/performing
    a deletion). Only finds ACTIVE (not soft-deleted) clients."""
    return rest.select_one_ci_active("clients", "name", client_name)


def delete_client(rest: SupabaseRestClient, storage: StorageBackend, client: dict) -> None:
    """Soft-deletes a client: marks it deleted (hiding it from every lookup —
    chat, dashboard, uploads, search) but keeps its database row, document
    records, and storage folder intact. A routine cleanup (see
    purge_deleted_clients) permanently removes it after a retention window,
    giving a recovery window for an accidental confirm — added per team
    review feedback that permanent-on-confirm was too risky with no undo."""
    rest.update(
        "clients",
        {"id": client["id"]},
        {"deleted_at": datetime.now(timezone.utc).isoformat()},
    )


def purge_deleted_clients(rest: SupabaseRestClient, storage: StorageBackend, older_than_days: int) -> list[str]:
    """Permanently removes clients soft-deleted more than `older_than_days` ago:
    their document records, database row, and storage folder. Irreversible.
    Meant to be run periodically (see app/db/cleanup_deleted_clients.py) — not
    part of the normal request path, so it has no timing pressure to be fast."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    purged_names = []

    for client in rest.select("clients"):
        deleted_at = client.get("deleted_at")
        if not deleted_at:
            continue
        deleted_ts = datetime.fromisoformat(deleted_at.replace("Z", "+00:00"))
        if deleted_ts.tzinfo is None:
            deleted_ts = deleted_ts.replace(tzinfo=timezone.utc)
        if deleted_ts > cutoff:
            continue

        rest.delete("client_documents", client_id=client["id"])
        rest.delete("clients", id=client["id"])
        storage.delete_dir(client["name"])
        purged_names.append(client["name"])

    return purged_names
