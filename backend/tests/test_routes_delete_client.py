from fastapi.testclient import TestClient

from app.core.phase_config import Phase, PhaseConfig
from app.deps import get_client_storage, get_config, get_rest_client
from app.main import app
from app.services.client_service import get_or_create_client
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


def test_delete_unknown_client_returns_404(tmp_path):
    client, _, _ = _client_with_overrides(tmp_path)
    try:
        response = client.delete("/api/clients/Ghost")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_delete_existing_client_removes_everything(tmp_path):
    client, fake_rest, storage = _client_with_overrides(tmp_path)
    try:
        acme = get_or_create_client(fake_rest, storage, CONFIG, "Acme")
        fake_rest.insert("client_documents", {"client_id": acme["id"], "doc_type": "MSA"})

        response = client.delete("/api/clients/Acme")

        assert response.status_code == 200
        assert response.json() == {"deleted": True, "client_name": "Acme"}
        assert fake_rest.select("clients", name="Acme") == []
        assert fake_rest.select("client_documents", client_id=acme["id"]) == []
        assert not storage.exists("Acme")
    finally:
        app.dependency_overrides.clear()
