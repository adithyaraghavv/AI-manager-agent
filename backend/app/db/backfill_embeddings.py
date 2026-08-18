"""One-off backfill: embeds every already-uploaded document currently on
file, so uploads that happened before RAG existed (or before their doc_type
was in scope, back when stage 1 only covered SOW) aren't invisible to
search_document_content — a document only gets indexed automatically going
forward, at upload time; this script is what covers everything that came
before.

Only embeds each client's CURRENT document version (client_documents),
same scope a fresh upload gets embedded at — not the full version history.
Skips soft-deleted clients, matching every other lookup in this app.

Idempotent: safe to re-run. embed_document replaces any existing chunks for
the same (client, doc_type, version) rather than duplicating them, so
re-running this after new uploads have already been embedded just leaves
those untouched (embedding the same content again is a harmless no-op).

Uses the same Supabase REST client the running app uses (SUPABASE_URL/
SUPABASE_KEY in .env) — run wherever the app itself runs:
    python -m app.db.backfill_embeddings
"""
from app.config import settings
from app.db.rest_client import SupabaseRestClient
from app.services import embedding_service
from app.storage.base import StorageBackend
from app.storage.local import LocalFilesystemStorage


def backfill(rest: SupabaseRestClient, storage: StorageBackend) -> dict[str, int]:
    """Returns {"documents_seen": N, "documents_embedded": N, "chunks_stored": N}
    so a caller (or the CLI entrypoint) can report what actually happened."""
    stats = {"documents_seen": 0, "documents_embedded": 0, "chunks_stored": 0}

    clients = rest.select_active("clients")
    for client in clients:
        documents = rest.select("client_documents", client_id=client["id"])
        for document in documents:
            stats["documents_seen"] += 1
            try:
                content = storage.get(document["storage_path"])
            except FileNotFoundError:
                # Same "database is shared, local files aren't" gap the rest
                # of the app already tolerates — skip, don't crash the run.
                continue

            filename = document["filename"]
            extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
            # client_documents doesn't store its own version number — it
            # always points at the CURRENT version, whose number is the
            # highest one recorded in document_versions for this doc_type
            # (see version_service.next_version_number, same logic minus the +1).
            versions = rest.select("document_versions", client_id=client["id"], doc_type=document["doc_type"])
            version_number = max((v["version_number"] for v in versions), default=1)

            chunk_count = embedding_service.embed_document(
                rest, client["id"], document["doc_type"], version_number, content, extension,
            )
            if chunk_count:
                stats["documents_embedded"] += 1
                stats["chunks_stored"] += chunk_count

    return stats


if __name__ == "__main__":
    rest_client = SupabaseRestClient(settings.supabase_url, settings.supabase_key)
    client_storage = LocalFilesystemStorage(settings.client_store_path)

    result = backfill(rest_client, client_storage)
    print(
        f"Checked {result['documents_seen']} document(s); "
        f"embedded {result['documents_embedded']} with a total of "
        f"{result['chunks_stored']} chunk(s) stored."
    )
