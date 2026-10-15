from fastapi.testclient import TestClient

from app.core.phase_config import Phase, PhaseConfig
from app.deps import get_client_storage, get_config, get_rest_client
from app.main import app
from app.services.client_service import get_or_create_client
from app.services.document_service import upload_document
from app.storage.local import LocalFilesystemStorage
from tests.conftest import FakeSupabaseRestClient

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA", "SOW")),
    ]
)


def _client_with_overrides(tmp_path):
    fake_rest = FakeSupabaseRestClient()
    storage = LocalFilesystemStorage(tmp_path)

    app.dependency_overrides[get_rest_client] = lambda: fake_rest
    app.dependency_overrides[get_client_storage] = lambda: storage
    app.dependency_overrides[get_config] = lambda: CONFIG

    return TestClient(app), fake_rest, storage


def test_search_finds_uploaded_document(tmp_path):
    client, fake_rest, storage = _client_with_overrides(tmp_path)
    try:
        upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"filled msa", "pdf")

        response = client.get("/api/documents/search", params={"q": "Acme"})

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["results"][0]["client_name"] == "Acme"
        assert body["results"][0]["doc_type"] == "MSA"
        assert "download_url" in body["results"][0]
    finally:
        app.dependency_overrides.clear()


def test_search_requires_query_param(tmp_path):
    client, _, _ = _client_with_overrides(tmp_path)
    try:
        response = client.get("/api/documents/search")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_download_stored_document_succeeds(tmp_path):
    client, fake_rest, storage = _client_with_overrides(tmp_path)
    try:
        upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"filled msa content", "pdf")

        response = client.get("/api/clients/Acme/documents/MSA/download")

        assert response.status_code == 200
        assert response.content == b"filled msa content"
    finally:
        app.dependency_overrides.clear()


def test_download_unknown_client_returns_404(tmp_path):
    client, _, _ = _client_with_overrides(tmp_path)
    try:
        response = client.get("/api/clients/Ghost/documents/MSA/download")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_download_unknown_doc_type_returns_404(tmp_path):
    client, fake_rest, storage = _client_with_overrides(tmp_path)
    try:
        get_or_create_client(fake_rest, storage, CONFIG, "Acme")

        response = client.get("/api/clients/Acme/documents/SOW/download")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
