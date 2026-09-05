from unittest.mock import patch

from app.services.search_service import search_documents


def _seed(rest):
    acme = rest.insert("clients", {"name": "Acme"})
    globex = rest.insert("clients", {"name": "Globex"})
    rest.insert(
        "client_documents",
        {"client_id": acme["id"], "phase_name": "Pre-requisites", "doc_type": "MSA", "storage_path": "Acme/MSA.pdf", "filename": "Marlabs_MSA_Acme_20260101.pdf"},
    )
    rest.insert(
        "client_documents",
        {"client_id": acme["id"], "phase_name": "Pre-requisites", "doc_type": "SOW", "storage_path": "Acme/SOW.pdf", "filename": "Marlabs_SOW_Acme_20260101.pdf"},
    )
    rest.insert(
        "client_documents",
        {"client_id": globex["id"], "phase_name": "Pre-requisites", "doc_type": "MSA", "storage_path": "Globex/MSA.pdf", "filename": "Marlabs_MSA_Globex_20260101.pdf"},
    )
    return acme, globex


def test_search_by_client_name_returns_all_their_documents(rest):
    _seed(rest)
    results = search_documents(rest, "acme")
    assert {r.doc_type for r in results} == {"MSA", "SOW"}
    assert all(r.client_name == "Acme" for r in results)


def test_search_by_doc_type_returns_matches_across_clients(rest):
    _seed(rest)
    results = search_documents(rest, "MSA")
    assert {r.client_name for r in results} == {"Acme", "Globex"}


def test_search_by_filename_fragment(rest):
    _seed(rest)
    results = search_documents(rest, "SOW_Acme")
    assert len(results) == 1
    assert results[0].filename == "Marlabs_SOW_Acme_20260101.pdf"


def test_search_is_case_insensitive(rest):
    _seed(rest)
    results = search_documents(rest, "GLOBEX")
    assert len(results) == 1
    assert results[0].client_name == "Globex"


def test_search_no_matches_returns_empty(rest):
    _seed(rest)
    assert search_documents(rest, "nonexistent") == []


def test_search_blank_query_returns_empty(rest):
    _seed(rest)
    assert search_documents(rest, "   ") == []


def test_search_excludes_soft_deleted_clients(rest):
    acme, _ = _seed(rest)
    rest.update("clients", {"id": acme["id"]}, {"deleted_at": "2026-01-01T00:00:00+00:00"})

    assert search_documents(rest, "Acme") == []
    # "MSA" matched both Acme and Globex before — only Globex's should remain now.
    results = search_documents(rest, "MSA")
    assert {r.client_name for r in results} == {"Globex"}


def test_search_excludes_a_soft_deleted_document(rest):
    acme, globex = _seed(rest)
    msa = rest.select_one("client_documents", client_id=acme["id"], doc_type="MSA")
    rest.update("client_documents", {"id": msa["id"]}, {"deleted_at": "2026-01-01T00:00:00+00:00"})

    # The deleted MSA must not surface even though its client is still active.
    results = search_documents(rest, "MSA")
    assert {r.client_name for r in results} == {"Globex"}
    # Acme's still-active SOW must still surface.
    results = search_documents(rest, "Acme")
    assert {r.doc_type for r in results} == {"SOW"}


def test_search_does_not_duplicate_results(rest):
    # A document matching both by client name AND doc_type/filename should
    # only appear once, not twice.
    _seed(rest)
    results = search_documents(rest, "Acme")
    filenames = [r.filename for r in results]
    assert len(filenames) == len(set(filenames))


def test_search_reports_version_count(rest):
    acme, _ = _seed(rest)
    rest.insert("document_versions", {"client_id": acme["id"], "doc_type": "MSA", "version_number": 1})
    rest.insert("document_versions", {"client_id": acme["id"], "doc_type": "MSA", "version_number": 2})
    rest.insert("document_versions", {"client_id": acme["id"], "doc_type": "SOW", "version_number": 1})

    results = search_documents(rest, "Acme")
    counts = {r.doc_type: r.version_count for r in results}
    assert counts["MSA"] == 2
    assert counts["SOW"] == 1


def test_search_fallback_path_is_batched(rest):
    # 30 clients whose names match "Acme" (so ilike hits all of them), each
    # with several documents whose filenames/doc_types intentionally DO NOT
    # match the query — this forces every doc into the fallback "look them up
    # via matching client_ids" path that PR-4 batches.
    for i in range(30):
        client = rest.insert("clients", {"name": f"Acme Corp {i}"})
        # Enough docs to make an N+1 obviously distinguishable from O(1) —
        # ~7 doc_types × 30 clients = 210 documents.
        for doc_type in ["MSA", "SOW", "BRD", "HLD", "LLD", "TDD", "PRD"]:
            rest.insert(
                "client_documents",
                {
                    "client_id": client["id"],
                    "phase_name": "Pre-requisites",
                    "doc_type": doc_type,
                    "storage_path": f"Acme{i}/{doc_type}.pdf",
                    # Filename intentionally does NOT contain "Acme" so the
                    # doc-level ilike returns 0 and every doc is discovered
                    # via the batched client_id lookup instead.
                    "filename": f"file_{i}_{doc_type}.pdf",
                },
            )
            rest.insert("document_versions", {"client_id": client["id"], "doc_type": doc_type, "version_number": 1})

    # Instrument the batch/fallback helpers this path relies on and assert
    # they're each called at most once — the whole point of PR-4 is that a
    # 350ms-debounced keystroke search doesn't fan out to N per-client and
    # per-orphan-doc lookups.
    real_select_in = rest.select_in
    real_select = rest.select
    real_select_one = rest.select_one
    calls = {"select_in": 0, "select": 0, "select_one": 0}

    def counting_select_in(*args, **kwargs):
        calls["select_in"] += 1
        return real_select_in(*args, **kwargs)

    def counting_select(*args, **kwargs):
        calls["select"] += 1
        return real_select(*args, **kwargs)

    def counting_select_one(*args, **kwargs):
        calls["select_one"] += 1
        return real_select_one(*args, **kwargs)

    with patch.object(rest, "select_in", side_effect=counting_select_in), \
         patch.object(rest, "select", side_effect=counting_select), \
         patch.object(rest, "select_one", side_effect=counting_select_one):
        results = search_documents(rest, "Acme")

    # Sanity check the actual output — every seeded doc should surface, with
    # the right version count — before we start asserting call counts.
    assert len(results) == 30 * 7
    assert all(r.version_count == 1 for r in results)

    # The batched fallback path issues at most 3 select_in calls total:
    # (1) documents for matched clients, (2) missing clients (skipped here
    # since every doc's client is already matched), (3) version rollup. And
    # ZERO per-row select/select_one, which was the N+1 that made this hot.
    assert calls["select_in"] <= 3, f"expected ≤3 batch calls, got {calls['select_in']}"
    assert calls["select"] == 0, f"per-row select() leaked into the batched path: {calls['select']} calls"
    assert calls["select_one"] == 0, f"per-row select_one() leaked into the batched path: {calls['select_one']} calls"
