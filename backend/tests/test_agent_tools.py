import json
from unittest.mock import MagicMock, patch

import pytest

from app.agent.tools import dispatch_tool
from app.core.phase_config import Phase, PhaseConfig
from app.services.document_service import upload_document
from app.services.client_service import get_or_create_client
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
        rest,
        storage,
        storage,
        CONFIG,
        "request_template",
        {"doc_type": "NotARealDocument"},
    )
    assert result["allowed"] is False
    assert "NotARealDocument" in result["reason"]


def test_request_template_never_gated_no_client_name_needed(rest, storage):
    # Templates are master files, not client-scoped — request_template must
    # never ask for or require a client name, and must never be blocked by
    # phase-gating (only upload_document is gated).
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "request_template",
        {"doc_type": "BRD"},
    )
    assert result["allowed"] is False  # no template seeded in this test's DB
    assert "reason" in result
    assert "missing_documents" not in result


def test_ask_clarifying_question_is_a_safe_no_op(rest, storage):
    # ask_clarifying_question exists so the model has a safe tool to call
    # instead of guessing/inventing a client_name or doc_type when it's
    # required to call some tool this turn (tool_choice="required" leaves it
    # no way to just reply in plain text on that round). It must never touch
    # the DB/storage — verified here by asserting it doesn't create a client.
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "ask_clarifying_question",
        {"question": "Which client is this for?"},
    )
    assert result == {"acknowledged": True}

    from app.services.client_service import find_client

    assert find_client(rest, "SOW") is None
    assert find_client(rest, "ask_clarifying_question") is None


def test_get_client_status_reports_all_phases(rest, storage):
    result = dispatch_tool(
        rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"}
    )
    assert result["client_name"] == "Acme"
    assert len(result["phases"]) == 2
    assert result["phases"][0]["complete"] is False


def test_get_client_status_reports_required_and_completed_documents(rest, storage):
    # Needed for the status table UI: each phase must carry its full document
    # list plus which of those are actually done, not just what's missing.
    result = dispatch_tool(
        rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"}
    )
    prereq_phase = result["phases"][0]
    assert prereq_phase["required_documents"]
    assert set(prereq_phase["completed_documents"]) | set(
        prereq_phase["missing_documents"]
    ) == set(prereq_phase["required_documents"])


def test_get_or_create_client_is_idempotent_across_calls(rest, storage):
    first = dispatch_tool(
        rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"}
    )
    second = dispatch_tool(
        rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"}
    )
    assert rest.select("clients", name="Acme") != []
    assert len(rest.select("clients", name="Acme")) == 1
    assert first == second


def test_get_client_status_returns_canonical_casing_regardless_of_input(rest, storage):
    dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "get_client_status",
        {"client_name": "Hillenbrand"},
    )
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "get_client_status",
        {"client_name": "hillenbrand"},
    )

    assert result["client_name"] == "Hillenbrand"  # not the lowercase input
    assert len(rest.select("clients")) == 1  # still just the one client


def test_propose_delete_client_never_creates_the_client(rest, storage):
    # The whole point of "propose" is look-without-touch — a PM asking to delete
    # a client that doesn't exist must not accidentally materialize one.
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "propose_delete_client",
        {"client_name": "Ghost"},
    )
    assert result == {"found": False, "client_name": "Ghost"}
    assert rest.select("clients") == []


def test_propose_delete_client_never_deletes_anything_itself(rest, storage):
    dispatch_tool(
        rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"}
    )

    result = dispatch_tool(
        rest, storage, storage, CONFIG, "propose_delete_client", {"client_name": "Acme"}
    )

    assert result["found"] is True
    assert result["needs_confirmation"] is True
    assert result["client_name"] == "Acme"
    assert result["phases_complete"] == 0
    assert result["total_phases"] == 2
    assert result["document_count"] == 0


def test_propose_delete_client_finds_client_regardless_of_casing(rest, storage):
    # This is the exact bug that was reported: typing "hillenbrand" to delete
    # an existing "Hillenbrand" incorrectly came back found=false.
    dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "get_client_status",
        {"client_name": "Hillenbrand"},
    )

    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "propose_delete_client",
        {"client_name": "hillenbrand"},
    )

    assert result["found"] is True
    assert result["client_name"] == "Hillenbrand"  # canonical casing in the response
    # Still there — proposing is not deleting
    assert rest.select("clients", name="Hillenbrand") != []
    assert storage.exists("Hillenbrand")


def test_search_document_types_unambiguous_query_returns_one_match(rest, storage):
    result = dispatch_tool(
        rest, storage, storage, CONFIG, "search_document_types", {"query": "SOW"}
    )

    assert result["count"] == 1
    assert result["matches"][0]["doc_type"] == "SOW"
    assert result["matches"][0]["phase_name"] == "Pre-requisites"


def test_search_document_types_ambiguous_query_returns_every_match():
    ambiguous_config = PhaseConfig(
        [
            Phase(
                name="Testing",
                sequence=1,
                required_documents=("Approved Test Plan", "Test Data Prepared"),
            ),
            Phase(
                name="Deployment",
                sequence=2,
                required_documents=("Signed-off Test Summary Report",),
            ),
        ]
    )
    result = dispatch_tool(
        None, None, None, ambiguous_config, "search_document_types", {"query": "test"}
    )

    assert result["count"] == 3


def test_search_document_types_no_match_returns_empty_not_an_error(rest, storage):
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "search_document_types",
        {"query": "nonexistent"},
    )

    assert result["count"] == 0
    assert result["matches"] == []


def test_get_document_location_returns_folder_path(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"filled", "pdf")

    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "get_document_location",
        {"client_name": "Acme", "doc_type": "MSA"},
    )

    assert result["found"] is True
    assert result["folder_path"] == "Acme/01_Pre-requisites"
    # Never a download_url — this tool is explicitly the "path only" answer.
    assert "download_url" not in result
    # LocalFilesystemStorage can't provide a browsable URL — must be null,
    # never fabricated.
    assert result["web_url"] is None


def test_get_document_location_unfiled_doc_reports_not_found(rest, storage):
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "get_document_location",
        {"client_name": "Ghost", "doc_type": "MSA"},
    )

    assert result["found"] is False


def test_get_document_versions_lists_full_history(rest, storage):
    upload_document(
        rest,
        storage,
        CONFIG,
        "MSA",
        "Acme",
        b"v1",
        "pdf",
        uploaded_by="Priya",
        comment="First",
    )
    upload_document(
        rest,
        storage,
        CONFIG,
        "MSA",
        "Acme",
        b"v2",
        "pdf",
        uploaded_by="Priya",
        comment="Second",
    )

    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "get_document_versions",
        {"client_name": "Acme", "doc_type": "MSA"},
    )

    assert result["found"] is True
    assert [v["version_number"] for v in result["versions"]] == [1, 2]
    assert result["versions"][1]["comment"] == "Second"


def test_get_document_versions_unknown_client_reports_not_found(rest, storage):
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "get_document_versions",
        {"client_name": "Ghost", "doc_type": "MSA"},
    )

    assert result["found"] is False


def test_mark_document_not_applicable_dispatch_marks_it(rest, storage):
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "mark_document_not_applicable",
        {
            "client_name": "Acme",
            "doc_type": "SOW",
            "reason": "Client already provided this",
        },
    )

    assert result["ok"] is True
    assert result["client_name"] == "Acme"
    assert result["doc_type"] == "SOW"

    status = dispatch_tool(
        rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"}
    )
    prereq_phase = status["phases"][0]
    assert prereq_phase["not_applicable_documents"] == ["SOW"]
    assert "SOW" not in prereq_phase["missing_documents"]


def test_mark_document_not_applicable_unknown_doc_type_does_not_raise(rest, storage):
    # Same guard as request_template's unknown-doc_type test — a hallucinated
    # or misspelled doc_type must be a graceful in-conversation message, not
    # an unhandled 500.
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "mark_document_not_applicable",
        {"client_name": "Acme", "doc_type": "NotARealDocument"},
    )

    assert result["ok"] is False
    assert "NotARealDocument" in result["reason"]


def test_unmark_document_not_applicable_dispatch_reverses_it(rest, storage):
    dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "mark_document_not_applicable",
        {"client_name": "Acme", "doc_type": "SOW"},
    )

    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "unmark_document_not_applicable",
        {"client_name": "Acme", "doc_type": "SOW"},
    )

    assert result["ok"] is True
    assert result["was_marked"] is True

    status = dispatch_tool(
        rest, storage, storage, CONFIG, "get_client_status", {"client_name": "Acme"}
    )
    assert status["phases"][0]["not_applicable_documents"] == []
    assert "SOW" in status["phases"][0]["missing_documents"]


def test_unmark_document_not_applicable_unknown_client_reports_not_found(rest, storage):
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "unmark_document_not_applicable",
        {"client_name": "Ghost", "doc_type": "SOW"},
    )

    assert result["ok"] is False
    assert "Ghost" in result["reason"]


def test_unmark_document_not_applicable_unknown_doc_type_reports_error_not_silent_no_op(
    rest, storage
):
    # The exact live bug this guards against: marking "SOW" then unmarking
    # with a differently-worded string (e.g. "Statement of Work") must raise
    # a clear error, not silently report was_marked=False as if it were
    # simply never marked.
    dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "mark_document_not_applicable",
        {"client_name": "Acme", "doc_type": "SOW"},
    )

    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "unmark_document_not_applicable",
        {"client_name": "Acme", "doc_type": "Statement of Work"},
    )

    assert result["ok"] is False
    assert "Statement of Work" in result["reason"]


def _mock_openai_response(fields: dict) -> MagicMock:
    choice = MagicMock()
    choice.message.content = json.dumps(fields)
    response = MagicMock()
    response.choices = [choice]
    return response


def test_get_sow_summary_dispatch_returns_extracted_fields(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"filled msa", "pdf")
    upload_document(
        rest, storage, CONFIG, "SOW", "Acme", b"Contract value: $50,000", "txt"
    )

    with patch("app.services.sow_extraction_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = (
            _mock_openai_response(
                {
                    "contract_value": "$50,000",
                    "start_date": None,
                    "end_date": None,
                    "scope_summary": None,
                    "team_assignments": [
                        {"name": "Jane Doe", "role": "Project Manager"}
                    ],
                    "document_responsibilities": {
                        "BRD": {"owner": "Client team", "approver": "Client team"}
                    },
                }
            )
        )
        result = dispatch_tool(
            rest, storage, storage, CONFIG, "get_sow_summary", {"client_name": "Acme"}
        )

    assert result["found"] is True
    assert result["client_name"] == "Acme"
    assert result["contract_value"] == "$50,000"
    assert result["team_assignments"] == [
        {"name": "Jane Doe", "role": "Project Manager"}
    ]
    assert result["document_responsibilities"] == {
        "BRD": {"owner": "Client team", "approver": "Client team"}
    }


def test_get_sow_summary_dispatch_reports_not_found_when_no_sow_filed(rest, storage):
    result = dispatch_tool(
        rest, storage, storage, CONFIG, "get_sow_summary", {"client_name": "Acme"}
    )

    assert result["found"] is False
    assert (
        "No client named" in result["reason"] or "No SOW is on file" in result["reason"]
    )


def test_generate_approval_reminder_dispatch_returns_owner_approver_and_message(
    rest, storage
):
    upload_document(rest, storage, CONFIG, "SOW", "Acme", b"SOW text", "txt")

    with patch("app.services.sow_extraction_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = (
            _mock_openai_response(
                {
                    "contract_value": None,
                    "start_date": None,
                    "end_date": None,
                    "scope_summary": None,
                    "team_assignments": None,
                    "document_responsibilities": {
                        "HLD": {"owner": "Marlabs team", "approver": "Client Sponsor"}
                    },
                }
            )
        )
        result = dispatch_tool(
            rest,
            storage,
            storage,
            CONFIG,
            "generate_approval_reminder",
            {"client_name": "Acme", "doc_type": "HLD"},
        )

    assert result["found"] is True
    assert result["owner"] == "Marlabs team"
    assert result["approver"] == "Client Sponsor"
    assert "Client Sponsor" in result["reminder_message"]


def test_generate_approval_reminder_dispatch_not_found_when_unassigned(rest, storage):
    upload_document(rest, storage, CONFIG, "SOW", "Acme", b"SOW text", "txt")

    with patch("app.services.sow_extraction_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = (
            _mock_openai_response(
                {
                    "contract_value": None,
                    "start_date": None,
                    "end_date": None,
                    "scope_summary": None,
                    "team_assignments": None,
                    "document_responsibilities": None,
                }
            )
        )
        result = dispatch_tool(
            rest,
            storage,
            storage,
            CONFIG,
            "generate_approval_reminder",
            {"client_name": "Acme", "doc_type": "HLD"},
        )

    assert result["found"] is False
    assert "reminder_message" not in result


# ---- search_document_content ----


def test_search_document_content_unknown_client_returns_not_found(rest, storage):
    result = dispatch_tool(
        rest,
        storage,
        storage,
        CONFIG,
        "search_document_content",
        {"client_name": "Ghost", "query": "termination clause"},
    )
    assert result["found"] is False


def test_search_document_content_returns_matches_for_known_client(rest, storage):
    client = get_or_create_client(rest, storage, CONFIG, "Acme")
    rest.insert(
        "document_chunks",
        {
            "client_id": client["id"],
            "doc_type": "SOW",
            "version_number": 1,
            "chunk_index": 0,
            "content": "Either party may terminate with 30 days written notice.",
            "embedding": [1.0, 0.0],
        },
    )

    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[1.0, 0.0])]
        )
        result = dispatch_tool(
            rest,
            storage,
            storage,
            CONFIG,
            "search_document_content",
            {"client_name": "Acme", "query": "how do I terminate the contract"},
        )

    assert result["found"] is True
    assert result["client_name"] == "Acme"
    assert "30 days written notice" in result["matches"][0]["content"]


def test_search_document_content_no_matches_is_not_an_error(rest, storage):
    get_or_create_client(rest, storage, CONFIG, "Acme")

    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[1.0, 0.0])]
        )
        result = dispatch_tool(
            rest,
            storage,
            storage,
            CONFIG,
            "search_document_content",
            {"client_name": "Acme", "query": "anything"},
        )

    assert result["found"] is False
    assert result["matches"] == []
