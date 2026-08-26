from unittest.mock import MagicMock, patch

from app.core.phase_config import Phase, PhaseConfig
from app.services.document_service import upload_document

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA",)),
    ]
)


def _mock_match_response():
    response = MagicMock()
    response.choices[0].message.content = '{"outcome": "match", "reason": "looks right"}'
    return response


def test_upload_route_accepts_uploader_and_comment(route_client):
    client, _, _ = route_client(config=CONFIG)
    with patch("app.core.document_type_validation.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.return_value = (
            _mock_match_response()
        )
        response = client.post(
            "/api/clients/Acme/documents",
            data={"doc_type": "MSA", "uploaded_by": "Priya", "comment": "Initial upload"},
            files={"file": ("msa.pdf", b"v1 content", "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["version_number"] == 1


def test_upload_route_blocks_when_document_type_does_not_match(route_client):
    client, _, _ = route_client(config=CONFIG)
    with patch("app.core.document_type_validation.OpenAI") as MockOpenAI:
        response = MagicMock()
        response.choices[0].message.content = (
            '{"outcome": "mismatch", "reason": "this is a SOW, not an MSA"}'
        )
        MockOpenAI.return_value.chat.completions.create.return_value = response
        result = client.post(
            "/api/clients/Acme/documents",
            data={"doc_type": "MSA"},
            files={"file": ("SOW_Acme.pdf", b"statement of work content", "application/pdf")},
        )

    assert result.status_code == 422
    detail = result.json()["detail"]
    assert detail["code"] == "type_mismatch"
    assert "does not appear to match" in detail["message"]


def test_upload_route_blocks_on_uncertain_match(route_client):
    client, _, _ = route_client(config=CONFIG)
    with patch("app.core.document_type_validation.OpenAI") as MockOpenAI:
        response = MagicMock()
        response.choices[0].message.content = '{"outcome": "uncertain", "reason": "not sure"}'
        MockOpenAI.return_value.chat.completions.create.return_value = response
        result = client.post(
            "/api/clients/Acme/documents",
            data={"doc_type": "MSA"},
            files={"file": ("file.pdf", b"ambiguous content", "application/pdf")},
        )

    assert result.status_code == 422
    detail = result.json()["detail"]
    assert detail["code"] == "type_uncertain"
    assert "could not confidently verify" in detail["message"]


def test_upload_route_blocks_when_validation_call_fails(route_client):
    client, _, _ = route_client(config=CONFIG)
    with patch("app.core.document_type_validation.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create.side_effect = RuntimeError("down")
        result = client.post(
            "/api/clients/Acme/documents",
            data={"doc_type": "MSA"},
            files={"file": ("file.pdf", b"some content", "application/pdf")},
        )

    assert result.status_code == 422
    detail = result.json()["detail"]
    assert detail["code"] == "validation_failed"
    assert "could not be completed" in detail["message"]


def test_upload_route_rejects_unknown_document_type_before_validating(route_client):
    client, _, _ = route_client(config=CONFIG)
    # No OpenAI mock installed — if this reached validate_document_type it would
    # hit a real API call and fail for the wrong reason; it must never get there.
    result = client.post(
        "/api/clients/Acme/documents",
        data={"doc_type": "NotARealDocType"},
        files={"file": ("file.pdf", b"content", "application/pdf")},
    )

    assert result.status_code == 400
    detail = result.json()["detail"]
    assert detail["code"] == "unknown_doc_type"
    assert "unable to identify the document type" in detail["message"]


def test_list_versions_route_returns_full_history(route_client):
    client, fake_rest, storage = route_client(config=CONFIG)
    upload_document(
        fake_rest,
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
        fake_rest,
        storage,
        CONFIG,
        "MSA",
        "Acme",
        b"v2",
        "pdf",
        uploaded_by="Priya",
        comment="Second",
    )

    response = client.get("/api/clients/Acme/documents/MSA/versions")

    assert response.status_code == 200
    body = response.json()
    assert [v["version_number"] for v in body["versions"]] == [1, 2]
    assert body["versions"][0]["comment"] == "First"
    assert body["versions"][1]["comment"] == "Second"
    assert "download_url" in body["versions"][0]


def test_list_versions_route_unknown_client_returns_404(route_client):
    client, _, _ = route_client(config=CONFIG)
    response = client.get("/api/clients/Ghost/documents/MSA/versions")

    assert response.status_code == 404


def test_download_specific_version_route(route_client):
    client, fake_rest, storage = route_client(config=CONFIG)
    upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v1 content", "pdf")
    upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v2 content", "pdf")

    response = client.get("/api/clients/Acme/documents/MSA/versions/1/download")

    assert response.status_code == 200
    assert response.content == b"v1 content"


def test_download_unknown_version_returns_404(route_client):
    client, fake_rest, storage = route_client(config=CONFIG)
    upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf")

    response = client.get("/api/clients/Acme/documents/MSA/versions/99/download")

    assert response.status_code == 404


def test_restore_route_creates_new_version(route_client):
    client, fake_rest, storage = route_client(config=CONFIG)
    upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v1 content", "pdf")
    upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v2 content", "pdf")

    response = client.post(
        "/api/clients/Acme/documents/MSA/versions/1/restore",
        data={"uploaded_by": "Priya"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["restored_from_version"] == 1
    assert body["new_version_number"] == 3


def test_restore_route_unknown_version_returns_404(route_client):
    client, fake_rest, storage = route_client(config=CONFIG)
    upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf")

    response = client.post("/api/clients/Acme/documents/MSA/versions/99/restore")

    assert response.status_code == 404
