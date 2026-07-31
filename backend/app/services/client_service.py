"""Client folder lifecycle: creation of the client row + full phase sub-structure
on first contact, and lookup of which documents already exist for a client."""
from app.core.phase_config import PhaseConfig
from app.db.rest_client import SupabaseRestClient
from app.storage.base import StorageBackend


def get_or_create_client(
    rest: SupabaseRestClient, storage: StorageBackend, config: PhaseConfig, client_name: str
) -> dict:
    client = rest.select_one("clients", name=client_name)
    is_new = client is None
    if client is None:
        client = rest.insert("clients", {"name": client_name})

    if is_new or not storage.exists(client_name):
        storage.make_dir(client_name)
        for phase in config.phases:
            storage.make_dir(f"{client_name}/{phase.sequence:02d}_{phase.name}")

    return client


def existing_document_types(rest: SupabaseRestClient, client: dict) -> set[str]:
    rows = rest.select("client_documents", client_id=client["id"])
    return {row["doc_type"] for row in rows}
