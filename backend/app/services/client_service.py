"""Client folder lifecycle: creation of the client row + full phase sub-structure
on first contact, and lookup of which documents already exist for a client."""
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
    client either way."""
    client = rest.select_one_ci("clients", "name", client_name)
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
    rows = rest.select("client_documents", client_id=client["id"])
    return {row["doc_type"] for row in rows}


def find_client(rest: SupabaseRestClient, client_name: str) -> dict | None:
    """Look up a client by name (case-insensitively — see get_or_create_client)
    WITHOUT creating one. Used anywhere that must not have the side effect of
    materializing a client that doesn't exist yet (e.g. proposing/performing
    a deletion)."""
    return rest.select_one_ci("clients", "name", client_name)


def delete_client(rest: SupabaseRestClient, storage: StorageBackend, client: dict) -> None:
    """Permanently remove a client: its document records, its DB row, and its
    storage folder. Irreversible — callers are responsible for confirming
    with a human first; this function just does the deletion."""
    rest.delete("client_documents", client_id=client["id"])
    rest.delete("clients", id=client["id"])
    storage.delete_dir(client["name"])
