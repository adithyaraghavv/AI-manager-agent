"""Search across stored client documents by client name, document type, or filename.

Read-only, no gating concept involved — same spirit as dashboard_service. A
manager should be able to find a document without knowing which client
folder it's filed under.
"""

from collections import Counter
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

    # Pull every document belonging to a matched client in ONE batch instead of
    # a per-client select (was the biggest N+1 in this path — search fires on
    # every keystroke via a 350ms debounce, so it was hot). setdefault preserves
    # the "first-seen wins" dedup contract for docs that also matched by
    # filename/doc_type above.
    if matching_clients:
        for doc in rest.select_in("client_documents", "client_id", list(matching_clients)):
            matching_docs.setdefault(doc["id"], doc)

    # Any doc whose client wasn't found via the name search (matched purely by
    # filename/doc_type) needs a client-name lookup. Batch those in ONE call
    # instead of a select_one per orphan doc, and honor the same
    # soft-delete-hides-the-client contract as above.
    missing_ids = {doc["client_id"] for doc in matching_docs.values() if doc["client_id"] not in matching_clients}
    if missing_ids:
        for c in rest.select_in("clients", "id", list(missing_ids)):
            if c.get("deleted_at") is None:
                matching_clients[c["id"]] = c["name"]

    # Version counts, also batched: one select_in over document_versions for
    # every client whose docs we're about to return, then count (client_id,
    # doc_type) pairs in Python. Same output as len(select("document_versions",
    # client_id=..., doc_type=...)) per doc, but O(1) round-trips instead of O(N).
    doc_client_ids = {doc["client_id"] for doc in matching_docs.values() if doc["client_id"] in matching_clients}
    version_counts: Counter[tuple[object, str]] = Counter()
    if doc_client_ids:
        for v in rest.select_in("document_versions", "client_id", list(doc_client_ids)):
            version_counts[(v["client_id"], v["doc_type"])] += 1

    results = []
    for doc in matching_docs.values():
        client_name = matching_clients.get(doc["client_id"])
        if client_name is None:
            # Orphan whose client is soft-deleted or missing — same skip as before.
            continue
        results.append(
            DocumentSearchResult(
                client_name=client_name,
                doc_type=doc["doc_type"],
                filename=doc["filename"],
                phase_name=doc["phase_name"],
                version_count=version_counts[(doc["client_id"], doc["doc_type"])],
            )
        )

    results.sort(key=lambda r: (r.client_name.lower(), r.filename.lower()))
    return results