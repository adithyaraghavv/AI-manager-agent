import json
from unittest.mock import MagicMock, patch

import pytest

from app.core.phase_config import Phase, PhaseConfig
from app.services.document_service import upload_document
from app.services.sow_extraction_service import (
    SowExtractionFailed,
    generate_approval_reminder,
    get_sow_summary,
)
from app.storage.local import LocalFilesystemStorage

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA", "SOW")),
    ]
)


@pytest.fixture
def storage(tmp_path):
    return LocalFilesystemStorage(tmp_path)


def _mock_openai_response(fields: dict) -> MagicMock:
    choice = MagicMock()
    choice.message.content = json.dumps(fields)
    response = MagicMock()
    response.choices = [choice]
    return response


def test_get_sow_summary_extracts_and_persists_fields(rest, storage):
    upload_document(
        rest,
        storage,
        CONFIG,
        "SOW",
        "Acme",
        b"Contract value: $50,000. Ends Dec 2026.",
        "txt",
    )
    fields = {
        "contract_value": "$50,000",
        "start_date": "Jan 2026",
        "end_date": "Dec 2026",
        "scope_summary": "Build and deploy a delivery tracking tool.",
        "team_assignments": [{"name": "Jane Doe", "role": "Project Manager"}],
        "document_responsibilities": {
            "BRD": {"owner": "Client team", "approver": "Client team"},
            "HLD": {"owner": "Marlabs team", "approver": "Client Sponsor"},
        },
    }

    with patch("app.services.sow_extraction_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = (
            _mock_openai_response(fields)
        )
        result = get_sow_summary(rest, storage, "Acme")

    assert result.client_name == "Acme"
    assert result.contract_value == "$50,000"
    assert result.start_date == "Jan 2026"
    assert result.end_date == "Dec 2026"
    assert result.scope_summary == "Build and deploy a delivery tracking tool."
    assert result.team_assignments == [{"name": "Jane Doe", "role": "Project Manager"}]
    assert result.document_responsibilities["BRD"] == {
        "owner": "Client team",
        "approver": "Client team",
    }
    assert result.document_responsibilities["HLD"] == {
        "owner": "Marlabs team",
        "approver": "Client Sponsor",
    }

    client = rest.select_one("clients", name="Acme")
    stored = rest.select_one("sow_metadata", client_id=client["id"])
    assert stored["contract_value"] == "$50,000"
    assert stored["team_assignments"] == [
        {"name": "Jane Doe", "role": "Project Manager"}
    ]
    assert stored["document_responsibilities"]["HLD"] == {
        "owner": "Marlabs team",
        "approver": "Client Sponsor",
    }


def test_get_sow_summary_team_and_document_ownership_null_when_not_stated(
    rest, storage
):
    # The exact fabrication risk this guards against: a SOW that names no
    # project team and assigns no document ownership must come back with
    # both fields null, not an empty-but-invented team/ownership map.
    upload_document(rest, storage, CONFIG, "SOW", "Acme", b"a bare-bones SOW", "txt")

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
        result = get_sow_summary(rest, storage, "Acme")

    assert result.team_assignments is None
    assert result.document_responsibilities is None


def test_get_sow_summary_re_extraction_overwrites_not_duplicates(rest, storage):
    upload_document(rest, storage, CONFIG, "SOW", "Acme", b"v1 content", "txt")

    with patch("app.services.sow_extraction_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = (
            _mock_openai_response(
                {
                    "contract_value": "$10",
                    "start_date": None,
                    "end_date": None,
                    "scope_summary": None,
                }
            )
        )
        get_sow_summary(rest, storage, "Acme")

        MockOpenAI.return_value.chat.completions.create.return_value = (
            _mock_openai_response(
                {
                    "contract_value": "$20",
                    "start_date": None,
                    "end_date": None,
                    "scope_summary": None,
                }
            )
        )
        result = get_sow_summary(rest, storage, "Acme")

    assert result.contract_value == "$20"
    client = rest.select_one("clients", name="Acme")
    rows = rest.select("sow_metadata", client_id=client["id"])
    assert len(rows) == 1


def test_get_sow_summary_fields_can_be_null_when_sow_doesnt_state_them(rest, storage):
    upload_document(
        rest, storage, CONFIG, "SOW", "Acme", b"a bare-bones SOW with no dates", "txt"
    )

    with patch("app.services.sow_extraction_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = (
            _mock_openai_response(
                {
                    "contract_value": None,
                    "start_date": None,
                    "end_date": None,
                    "scope_summary": "Unclear scope.",
                }
            )
        )
        result = get_sow_summary(rest, storage, "Acme")

    assert result.contract_value is None
    assert result.start_date is None
    assert result.scope_summary == "Unclear scope."


def test_get_sow_summary_raises_when_no_sow_filed(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"filled msa", "pdf")

    with pytest.raises(SowExtractionFailed, match="No SOW is on file"):
        get_sow_summary(rest, storage, "Acme")


def test_get_sow_summary_raises_for_unknown_client(rest, storage):
    with pytest.raises(SowExtractionFailed, match="No client named"):
        get_sow_summary(rest, storage, "Ghost")


def test_get_sow_summary_raises_when_file_type_unsupported_for_extraction(
    rest, storage
):
    upload_document(
        rest, storage, CONFIG, "SOW", "Acme", b"binary pptx content", "pptx"
    )

    with pytest.raises(SowExtractionFailed, match="Couldn't read text"):
        get_sow_summary(rest, storage, "Acme")


def test_generate_approval_reminder_finds_approver_and_drafts_message(rest, storage):
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
                        "BRD": {"owner": "Client team", "approver": "Client team"},
                        "HLD": {"owner": "Marlabs team", "approver": "Client Sponsor"},
                    },
                }
            )
        )
        result = generate_approval_reminder(rest, storage, "Acme", "HLD")

    assert result.found is True
    assert result.owner == "Marlabs team"
    assert result.approver == "Client Sponsor"
    assert result.matched_doc_type == "HLD"
    # The reminder targets the APPROVER, not the owner — the owner just
    # authored it, the approver is who actually needs to act.
    assert "Client Sponsor" in result.reminder_message
    assert "Acme" in result.reminder_message
    assert "HLD" in result.reminder_message


def test_generate_approval_reminder_falls_back_to_shared_owner_approver(rest, storage):
    # When the SOW names only one party for a document (no distinction
    # made), owner and approver come back as the same value — that's the
    # only information available, not a guess, so the reminder still works.
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
                        "BRD": {"owner": "Client team", "approver": "Client team"}
                    },
                }
            )
        )
        result = generate_approval_reminder(rest, storage, "Acme", "BRD")

    assert result.found is True
    assert result.owner == "Client team"
    assert result.approver == "Client team"
    assert "Client team" in result.reminder_message


def test_generate_approval_reminder_matches_loosely_worded_doc_type(rest, storage):
    # The exact real-world mismatch this guards against: the SOW might say
    # "Business Requirement Document (BRD)" while the PM just says "BRD".
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
                        "Business Requirement Document (BRD)": {
                            "owner": "Client team",
                            "approver": "Client team",
                        }
                    },
                }
            )
        )
        result = generate_approval_reminder(rest, storage, "Acme", "BRD")

    assert result.found is True
    assert result.approver == "Client team"
    assert result.matched_doc_type == "Business Requirement Document (BRD)"


def test_generate_approval_reminder_not_found_when_owner_named_but_no_approver(
    rest, storage
):
    # The exact fabrication risk this guards against: the SOW names who
    # OWNS the document but doesn't say who approves it — the tool must not
    # quietly treat the owner as a stand-in approver.
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
                        "HLD": {"owner": "Marlabs team", "approver": None}
                    },
                }
            )
        )
        result = generate_approval_reminder(rest, storage, "Acme", "HLD")

    assert result.found is False
    assert result.reminder_message is None
    assert "doesn't say who approves it" in result.reason


def test_generate_approval_reminder_not_found_when_document_not_assigned(rest, storage):
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
                        "BRD": {"owner": "Client team", "approver": "Client team"}
                    },
                }
            )
        )
        result = generate_approval_reminder(rest, storage, "Acme", "Deployment Plan")

    assert result.found is False
    assert result.reminder_message is None
    assert "Deployment Plan" in result.reason


def test_generate_approval_reminder_not_found_when_no_ownership_at_all(rest, storage):
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
        result = generate_approval_reminder(rest, storage, "Acme", "BRD")

    assert result.found is False
    assert "doesn't assign responsibility" in result.reason


def test_generate_approval_reminder_raises_when_no_sow_filed(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"filled msa", "pdf")

    with pytest.raises(SowExtractionFailed, match="No SOW is on file"):
        generate_approval_reminder(rest, storage, "Acme", "BRD")
