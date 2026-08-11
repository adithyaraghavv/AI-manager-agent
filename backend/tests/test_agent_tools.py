import pytest

from app.agent.tools import dispatch_tool
from app.core.phase_config import Phase, PhaseConfig
from app.services.document_service import upload_document
from app.storage.local import LocalFilesystemStorage

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA", "SOW")),
        Phase(name="Requirement Analysis", sequence=2, required_documents=("BRD",)),
    ]
)


@pytest.fixture
def storage(tmp_path):
    return LocalFilesystemStorage(tmp_path)


def test_request_template_unknown_doc_type_does_not_raise(rest, storage):
    # Previously: resolve_phase_for_document's ValueError wasn't caught here,
    # so an AI-hallucinated or misspelled doc_type crashed the whole chat turn
    # with an unhandled 500 instead of a graceful in-conversation message.
    result = dispatch_tool(
        rest, storage, storage, CONFIG, "request_template",
        {"doc_type": "NotARealDocument", "client_name": "Acme"},
    )
    assert result["allowed"] is False
    assert "NotARealDocument" in result["reason"]


def test_request_template_blocked_reports_missing_docs(rest, storage):
    result = dispatch_tool(
        rest, storage, storage, CONFIG, "request_template",
        {"doc_type": "BRD", "client_name": "Acme"},
    )
    assert result["allowed"] is False
    assert set(result["missing_documents"]) == {"MSA", "SOW"}


def test_get_client_status_reports_all_phases(rest, storage):
    result = dispatch_tool(
        rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"}
    )
    assert result["client_name"] == "Acme"
    assert len(result["phases"]) == 2
    assert result["phases"][0]["complete"] is False


def test_get_or_create_client_is_idempotent_across_calls(rest, storage):
    first = dispatch_tool(rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"})
    second = dispatch_tool(rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"})
    assert rest.select("clients", name="Acme") != []
    assert len(rest.select("clients", name="Acme")) == 1
    assert first == second


def test_get_client_status_returns_canonical_casing_regardless_of_input(rest, storage):
    dispatch_tool(rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Hillenbrand"})
    result = dispatch_tool(rest, storage, storage, CONFIG, "get_client_status", {"client_name": "hillenbrand"})

    assert result["client_name"] == "Hillenbrand"  # not the lowercase input
    assert len(rest.select("clients")) == 1  # still just the one client


def test_propose_delete_client_never_creates_the_client(rest, storage):
    # The whole point of "propose" is look-without-touch — a PM asking to delete
    # a client that doesn't exist must not accidentally materialize one.
    result = dispatch_tool(rest, storage, storage, CONFIG, "propose_delete_client", {"client_name": "Ghost"})
    assert result == {"found": False, "client_name": "Ghost"}
    assert rest.select("clients") == []


def test_propose_delete_client_never_deletes_anything_itself(rest, storage):
    dispatch_tool(rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"})

    result = dispatch_tool(rest, storage, storage, CONFIG, "propose_delete_client", {"client_name": "Acme"})

    assert result["found"] is True
    assert result["needs_confirmation"] is True
    assert result["client_name"] == "Acme"
    assert result["phases_complete"] == 0
    assert result["total_phases"] == 2
    assert result["document_count"] == 0


def test_propose_delete_client_finds_client_regardless_of_casing(rest, storage):
    # This is the exact bug that was reported: typing "hillenbrand" to delete
    # an existing "Hillenbrand" incorrectly came back found=false.
    dispatch_tool(rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Hillenbrand"})

    result = dispatch_tool(rest, storage, storage, CONFIG, "propose_delete_client", {"client_name": "hillenbrand"})

    assert result["found"] is True
    assert result["client_name"] == "Hillenbrand"  # canonical casing in the response
    # Still there — proposing is not deleting
    assert rest.select("clients", name="Hillenbrand") != []
    assert storage.exists("Hillenbrand")


def test_get_document_versions_lists_full_history(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf", uploaded_by="Priya", comment="First")
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v2", "pdf", uploaded_by="Priya", comment="Second")

    result = dispatch_tool(rest, storage, storage, CONFIG, "get_document_versions", {"client_name": "Acme", "doc_type": "MSA"})

    assert result["found"] is True
    assert [v["version_number"] for v in result["versions"]] == [1, 2]
    assert result["versions"][1]["comment"] == "Second"


def test_get_document_versions_unknown_client_reports_not_found(rest, storage):
    result = dispatch_tool(rest, storage, storage, CONFIG, "get_document_versions", {"client_name": "Ghost", "doc_type": "MSA"})

    assert result["found"] is False
