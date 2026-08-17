from fastapi.testclient import TestClient

from app.core.phase_config import Phase, PhaseConfig
from app.deps import get_client_storage, get_config, get_rest_client
from app.main import app
from app.services.document_service import upload_document
from app.storage.local import LocalFilesystemStorage
from tests.conftest import FakeSupabaseRestClient

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA",)),
    ]
)


def _client_with_overrides(tmp_path):
    fake_rest = FakeSupabaseRestClient()
    storage = LocalFilesystemStorage(tmp_path)

    app.dependency_overrides[get_rest_client] = lambda: fake_rest
    app.dependency_overrides[get_client_storage] = lambda: storage
    app.dependency_overrides[get_config] = lambda: CONFIG

    return TestClient(app), fake_rest, storage


def test_upload_route_accepts_uploader_and_comment(tmp_path):
    client, fake_rest, storage = _client_with_overrides(tmp_path)
    try:
        response = client.post(
            "/api/clients/Acme/documents",
            data={"doc_type": "MSA", "uploaded_by": "Priya", "comment": "Initial upload"},
            files={"file": ("msa.pdf", b"v1 content", "application/pdf")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["version_number"] == 1


def test_list_versions_route_returns_full_history(tmp_path):
    client, fake_rest, storage = _client_with_overrides(tmp_path)
    try:
        upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf", uploaded_by="Priya", comment="First")
        upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v2", "pdf", uploaded_by="Priya", comment="Second")

        response = client.get("/api/clients/Acme/documents/MSA/versions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [v["version_number"] for v in body["versions"]] == [1, 2]
    assert body["versions"][0]["comment"] == "First"
    assert body["versions"][1]["comment"] == "Second"
    assert "download_url" in body["versions"][0]


def test_list_versions_route_unknown_client_returns_404(tmp_path):
    client, _, _ = _client_with_overrides(tmp_path)
    try:
        response = client.get("/api/clients/Ghost/documents/MSA/versions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_download_specific_version_route(tmp_path):
    client, fake_rest, storage = _client_with_overrides(tmp_path)
    try:
        upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v1 content", "pdf")
        upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v2 content", "pdf")

        response = client.get("/api/clients/Acme/documents/MSA/versions/1/download")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"v1 content"


def test_download_unknown_version_returns_404(tmp_path):
    client, fake_rest, storage = _client_with_overrides(tmp_path)
    try:
        upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf")

        response = client.get("/api/clients/Acme/documents/MSA/versions/99/download")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_restore_route_creates_new_version(tmp_path):
    client, fake_rest, storage = _client_with_overrides(tmp_path)
    try:
        upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v1 content", "pdf")
        upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v2 content", "pdf")

        response = client.post(
            "/api/clients/Acme/documents/MSA/versions/1/restore",
            data={"uploaded_by": "Priya"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["restored_from_version"] == 1
    assert body["new_version_number"] == 3


def test_restore_route_unknown_version_returns_404(tmp_path):
    client, fake_rest, storage = _client_with_overrides(tmp_path)
    try:
        upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf")

        response = client.post("/api/clients/Acme/documents/MSA/versions/99/restore")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
