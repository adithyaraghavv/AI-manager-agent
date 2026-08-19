from app.core.phase_config import Phase, PhaseConfig
from app.services.client_service import get_or_create_client

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA", "SOW")),
    ]
)


def test_delete_unknown_client_returns_404(route_client):
    client, _, _ = route_client(config=CONFIG)
    response = client.delete("/api/clients/Ghost")

    assert response.status_code == 404


def test_delete_existing_client_soft_deletes_it(route_client):
    client, fake_rest, storage = route_client(config=CONFIG)
    acme = get_or_create_client(fake_rest, storage, CONFIG, "Acme")
    fake_rest.insert("client_documents", {"client_id": acme["id"], "doc_type": "MSA"})

    response = client.delete("/api/clients/Acme")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "client_name": "Acme"}
    # Hidden from normal lookups...
    assert client.get("/api/clients/status").json()["clients"] == []
    # ...but nothing was actually erased — recoverable until the retention window's cleanup runs.
    assert fake_rest.select_one("clients", id=acme["id"])["deleted_at"] is not None
    assert fake_rest.select("client_documents", client_id=acme["id"]) != []
    assert storage.exists("Acme")
