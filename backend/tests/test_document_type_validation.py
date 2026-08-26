import json
from unittest.mock import MagicMock, patch

from app.core.document_type_validation import ValidationOutcome, validate_document_type


def _mock_response(outcome: str, reason: str = "because"):
    response = MagicMock()
    response.choices[0].message.content = json.dumps({"outcome": outcome, "reason": reason})
    return response


def test_matching_document_returns_match():
    with patch("app.core.document_type_validation.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = _mock_response("match")
        result = validate_document_type(
            b"This is the Approved Low Level Design for Acme.",
            "txt",
            "Approved_LLD_Acme.txt",
            "Approved LLD",
        )
    assert result.outcome == ValidationOutcome.MATCH


def test_mismatched_document_returns_mismatch():
    with patch("app.core.document_type_validation.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = _mock_response(
            "mismatch", "This is clearly a Statement of Work, not an Approved LLD"
        )
        result = validate_document_type(
            b"This Statement of Work covers scope, pricing, and timelines.",
            "txt",
            "SOW_Lilly.txt",
            "Approved LLD",
        )
    assert result.outcome == ValidationOutcome.MISMATCH
    assert "Statement of Work" in result.reason


def test_ambiguous_document_returns_uncertain():
    with patch("app.core.document_type_validation.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = _mock_response(
            "uncertain"
        )
        result = validate_document_type(
            b"",
            "bin",
            "file.bin",
            "Approved LLD",
        )
    assert result.outcome == ValidationOutcome.UNCERTAIN


def test_classification_api_failure_fails_closed_not_open():
    # This is a gate against misfiling, not a bonus feature — unlike RAG
    # embedding, an API error must never be treated as "fine, let it through."
    with patch("app.core.document_type_validation.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.side_effect = RuntimeError("down")
        result = validate_document_type(
            b"some content", "txt", "file.txt", "Approved LLD"
        )
    assert result.outcome == ValidationOutcome.FAILED


def test_unparseable_response_fails_closed():
    with patch("app.core.document_type_validation.OpenAI") as MockOpenAI:
        response = MagicMock()
        response.choices[0].message.content = "not valid json"
        MockOpenAI.return_value.chat.completions.create.return_value = response
        result = validate_document_type(
            b"some content", "txt", "file.txt", "Approved LLD"
        )
    assert result.outcome == ValidationOutcome.FAILED
