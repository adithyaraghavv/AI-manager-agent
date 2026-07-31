import pytest

from app.agent.tools import dispatch_tool
from app.core.phase_config import Phase, PhaseConfig
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
