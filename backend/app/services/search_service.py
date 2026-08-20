"""Search across stored client documents by client name, document type, or filename.

Read-only, no gating concept involved — same spirit as dashboard_service. A
manager should be able to find a document without knowing which client
folder it's filed under.
"""

from dataclasses import dataclass

from app.db.rest_client import SupabaseRestClient


@dataclass
class DocumentSearchResult:
    client_name: str
    doc_type: str
    filename: str
    phase_name: str
    version_count: int


def search_documents(
    rest: SupabaseRestClient, query: str
) -> list[DocumentSearchResult]:
    query = query.strip()
    if not query:
        return []

    # Soft-deleted clients (and their documents) must never surface in search —
    # same "hidden until purged" contract as the dashboard and chat lookups.
    matching_clients = {
        c["id"]: c["name"]
        for c in rest.select_ilike_any("clients", ["name"], query)
        if c.get("deleted_at") is None
    }
    matching_docs = {
        doc["id"]: doc
        for doc in rest.select_ilike_any(
            "client_documents", ["filename", "doc_type"], query
        )
    }

    for client_id in matching_clients:
        for doc in rest.select("client_documents", client_id=client_id):
            matching_docs.setdefault(doc["id"], doc)

    results = []
    for doc in matching_docs.values():
        client_name = matching_clients.get(doc["client_id"])
        if client_name is None:
            client = rest.select_one("clients", id=doc["client_id"])
            if client is None or client.get("deleted_at") is not None:
                continue
            client_name = client["name"]
        version_count = len(
            rest.select(
                "document_versions",
                client_id=doc["client_id"],
                doc_type=doc["doc_type"],
            )
        )
        results.append(
            DocumentSearchResult(
                client_name=client_name,
                doc_type=doc["doc_type"],
                filename=doc["filename"],
                phase_name=doc["phase_name"],
                version_count=version_count,
            )
        )

    results.sort(key=lambda r: (r.client_name.lower(), r.filename.lower()))
    return results
