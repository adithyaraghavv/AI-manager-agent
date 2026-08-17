"""End-to-end regression net for PR #38's SOW extraction pipeline.

Exercises the whole chain: FakeSupabaseRestClient + a real client/document row
+ mocked text extraction + mocked LLM. Verifies the invariants that would
break under a real refactor:

  1. Fresh call: extract → LLM → persist to sow_metadata. Row must exist after.
  2. Idempotency: a second call for the same client doesn't blow up and
     upsert leaves at most one sow_metadata row.
  3. Unknown client: raises SowExtractionFailed instead of silently
     fabricating.
  4. Extraction-fails: raises SowExtractionFailed with a helpful message
     (the operator-facing invariant PR #38 was careful to preserve).
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeSupabaseRestClient
from app.services.sow_extraction_service import (
    SowExtractionFailed,
    get_sow_summary,
)


class InMemoryStorage:
    """Minimal StorageBackend stand-in — .get() returning bytes is all the
    SOW pipeline actually consumes."""

    def __init__(self, files: dict[str, bytes]):
        self._files = files

    def get(self, path: str) -> bytes:
        return self._files[path]

    def exists(self, path: str) -> bool:
        return path in self._files


def _mock_openai_response(fields: dict) -> MagicMock:
    """Copies the pattern from backend/tests/test_sow_extraction_service.py."""
    choice = MagicMock()
    choice.message.content = json.dumps(fields)
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture
def fake_rest() -> FakeSupabaseRestClient:
    rest = FakeSupabaseRestClient()
    rest._tables["clients"] = [{"id": 1, "name": "Acme", "deleted_at": None}]
    rest._tables["client_documents"] = [
        {
            "id": 10,
            "client_id": 1,
            "doc_type": "SOW",
            "filename": "acme_sow_v1.docx",
            "storage_path": "clients/Acme/SOW/acme_sow_v1.docx",
            "deleted_at": None,
        }
    ]
    return rest


@pytest.fixture
def fake_storage() -> InMemoryStorage:
    return InMemoryStorage(
        {
            "clients/Acme/SOW/acme_sow_v1.docx": b"(placeholder DOCX bytes)"
        }
    )


@pytest.fixture
def fields() -> dict:
    return {
        "contract_value": "$100,000",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "scope_summary": "Cloud migration for Acme.",
        "team_assignments": {"alice": "Lead", "bob": "Engineer"},
        "document_responsibilities": {
            "MSA": {"owner": "Alice Admin", "approver": "Bob Boss"},
        },
    }


def _patch_pipeline(fields: dict):
    """Patch the text_extraction symbol as imported inside the service,
    plus the OpenAI class the service instantiates internally."""
    # get_stored_document may or may not exist as an importable symbol — but
    # we don't need to mock it; the FakeSupabaseRestClient + InMemoryStorage
    # together satisfy its needs.
    return (
        patch("app.services.sow_extraction_service.extract_text", return_value="mock SOW text with team, owner, approver"),
        patch("app.services.sow_extraction_service.OpenAI"),
    )


def test_first_call_extracts_and_persists(fake_rest, fake_storage, fields):
    extract_patch, openai_patch = _patch_pipeline(fields)
    with extract_patch, openai_patch as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = _mock_openai_response(fields)
        result = get_sow_summary(fake_rest, fake_storage, "Acme")

    assert result is not None
    rows = fake_rest.select("sow_metadata", client_id=1)
    assert len(rows) == 1, f"expected exactly one sow_metadata row, got {len(rows)}: {rows}"
    persisted = rows[0]
    # Round-trip check: what the LLM said should end up in the row
    assert persisted["contract_value"] == fields["contract_value"]
    assert persisted["scope_summary"] == fields["scope_summary"]


def test_repeat_call_is_idempotent(fake_rest, fake_storage, fields):
    """A second call for the same client shouldn't create a duplicate row —
    _persist uses insert-or-update. This catches a regression where someone
    switches to plain insert() and starts accumulating rows."""
    extract_patch, openai_patch = _patch_pipeline(fields)
    with extract_patch, openai_patch as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = _mock_openai_response(fields)
        get_sow_summary(fake_rest, fake_storage, "Acme")
        get_sow_summary(fake_rest, fake_storage, "Acme")

    rows = fake_rest.select("sow_metadata", client_id=1)
    assert len(rows) == 1, f"repeat call created duplicate rows: {rows}"


def test_unknown_client_raises(fake_rest, fake_storage, fields):
    """Guardrail: the service must not fabricate metadata for a client that
    doesn't exist — it should raise a specific exception."""
    extract_patch, openai_patch = _patch_pipeline(fields)
    with extract_patch, openai_patch as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.side_effect = AssertionError(
            "LLM should not be called when the client doesn't exist"
        )
        with pytest.raises(SowExtractionFailed) as excinfo:
            get_sow_summary(fake_rest, fake_storage, "NonExistentClient")
    assert "NonExistentClient" in str(excinfo.value)


def test_extraction_failure_surfaces_helpful_message(fake_rest, fake_storage, fields):
    """If text extraction returns empty (unsupported file type / scanned image),
    the service must raise SowExtractionFailed with the client name in the
    message — that's what the chat surfaces to the user. Regression net for
    the operator-facing error text PR #38 was careful to write."""
    with patch("app.services.sow_extraction_service.extract_text", return_value=None):
        with pytest.raises(SowExtractionFailed) as excinfo:
            get_sow_summary(fake_rest, fake_storage, "Acme")
    msg = str(excinfo.value)
    assert "Acme" in msg
    # Should mention either the file type or the extraction problem
    assert "extract" in msg.lower() or "file type" in msg.lower() or "text" in msg.lower()
