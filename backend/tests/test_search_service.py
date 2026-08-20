from app.services.search_service import search_documents


def _seed(rest):
    acme = rest.insert("clients", {"name": "Acme"})
    globex = rest.insert("clients", {"name": "Globex"})
    rest.insert(
        "client_documents",
        {
            "client_id": acme["id"],
            "phase_name": "Pre-requisites",
            "doc_type": "MSA",
            "storage_path": "Acme/MSA.pdf",
            "filename": "Marlabs_MSA_Acme_20260101.pdf",
        },
    )
    rest.insert(
        "client_documents",
        {
            "client_id": acme["id"],
            "phase_name": "Pre-requisites",
            "doc_type": "SOW",
            "storage_path": "Acme/SOW.pdf",
            "filename": "Marlabs_SOW_Acme_20260101.pdf",
        },
    )
    rest.insert(
        "client_documents",
        {
            "client_id": globex["id"],
            "phase_name": "Pre-requisites",
            "doc_type": "MSA",
            "storage_path": "Globex/MSA.pdf",
            "filename": "Marlabs_MSA_Globex_20260101.pdf",
        },
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
    rest.update(
        "clients", {"id": acme["id"]}, {"deleted_at": "2026-01-01T00:00:00+00:00"}
    )

    assert search_documents(rest, "Acme") == []
    # "MSA" matched both Acme and Globex before — only Globex's should remain now.
    results = search_documents(rest, "MSA")
    assert {r.client_name for r in results} == {"Globex"}


def test_search_does_not_duplicate_results(rest):
    # A document matching both by client name AND doc_type/filename should
    # only appear once, not twice.
    _seed(rest)
    results = search_documents(rest, "Acme")
    filenames = [r.filename for r in results]
    assert len(filenames) == len(set(filenames))


def test_search_reports_version_count(rest):
    acme, _ = _seed(rest)
    rest.insert(
        "document_versions",
        {"client_id": acme["id"], "doc_type": "MSA", "version_number": 1},
    )
    rest.insert(
        "document_versions",
        {"client_id": acme["id"], "doc_type": "MSA", "version_number": 2},
    )
    rest.insert(
        "document_versions",
        {"client_id": acme["id"], "doc_type": "SOW", "version_number": 1},
    )

    results = search_documents(rest, "Acme")
    counts = {r.doc_type: r.version_count for r in results}
    assert counts["MSA"] == 2
    assert counts["SOW"] == 1
