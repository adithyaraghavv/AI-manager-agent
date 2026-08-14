import json
from unittest.mock import MagicMock, patch

import pytest

from app.core.phase_config import Phase, PhaseConfig
from app.services.document_service import upload_document
from app.services.sow_extraction_service import SowExtractionFailed, get_sow_summary
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
    upload_document(rest, storage, CONFIG, "SOW", "Acme", b"Contract value: $50,000. Ends Dec 2026.", "txt")
    fields = {
        "contract_value": "$50,000",
        "start_date": "Jan 2026",
        "end_date": "Dec 2026",
        "scope_summary": "Build and deploy a delivery tracking tool.",
        "team_assignments": [{"name": "Jane Doe", "role": "Project Manager"}],
        "document_responsibilities": {"BRD": "Client team", "HLD": "Marlabs team"},
    }

    with patch("app.services.sow_extraction_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = _mock_openai_response(fields)
        result = get_sow_summary(rest, storage, "Acme")

    assert result.client_name == "Acme"
    assert result.contract_value == "$50,000"
    assert result.start_date == "Jan 2026"
    assert result.end_date == "Dec 2026"
    assert result.scope_summary == "Build and deploy a delivery tracking tool."
    assert result.team_assignments == [{"name": "Jane Doe", "role": "Project Manager"}]
    assert result.document_responsibilities == {"BRD": "Client team", "HLD": "Marlabs team"}

    client = rest.select_one("clients", name="Acme")
    stored = rest.select_one("sow_metadata", client_id=client["id"])
    assert stored["contract_value"] == "$50,000"
    assert stored["team_assignments"] == [{"name": "Jane Doe", "role": "Project Manager"}]
    assert stored["document_responsibilities"] == {"BRD": "Client team", "HLD": "Marlabs team"}


def test_get_sow_summary_team_and_document_ownership_null_when_not_stated(rest, storage):
    # The exact fabrication risk this guards against: a SOW that names no
    # project team and assigns no document ownership must come back with
    # both fields null, not an empty-but-invented team/ownership map.
    upload_document(rest, storage, CONFIG, "SOW", "Acme", b"a bare-bones SOW", "txt")

    with patch("app.services.sow_extraction_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = _mock_openai_response(
            {
                "contract_value": None,
                "start_date": None,
                "end_date": None,
                "scope_summary": None,
                "team_assignments": None,
                "document_responsibilities": None,
            }
        )
        result = get_sow_summary(rest, storage, "Acme")

    assert result.team_assignments is None
    assert result.document_responsibilities is None


def test_get_sow_summary_re_extraction_overwrites_not_duplicates(rest, storage):
    upload_document(rest, storage, CONFIG, "SOW", "Acme", b"v1 content", "txt")

    with patch("app.services.sow_extraction_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = _mock_openai_response(
            {"contract_value": "$10", "start_date": None, "end_date": None, "scope_summary": None}
        )
        get_sow_summary(rest, storage, "Acme")

        MockOpenAI.return_value.chat.completions.create.return_value = _mock_openai_response(
            {"contract_value": "$20", "start_date": None, "end_date": None, "scope_summary": None}
        )
        result = get_sow_summary(rest, storage, "Acme")

    assert result.contract_value == "$20"
    client = rest.select_one("clients", name="Acme")
    rows = rest.select("sow_metadata", client_id=client["id"])
    assert len(rows) == 1


def test_get_sow_summary_fields_can_be_null_when_sow_doesnt_state_them(rest, storage):
    upload_document(rest, storage, CONFIG, "SOW", "Acme", b"a bare-bones SOW with no dates", "txt")

    with patch("app.services.sow_extraction_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = _mock_openai_response(
            {"contract_value": None, "start_date": None, "end_date": None, "scope_summary": "Unclear scope."}
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


def test_get_sow_summary_raises_when_file_type_unsupported_for_extraction(rest, storage):
    upload_document(rest, storage, CONFIG, "SOW", "Acme", b"binary pptx content", "pptx")

    with pytest.raises(SowExtractionFailed, match="Couldn't read text"):
        get_sow_summary(rest, storage, "Acme")
