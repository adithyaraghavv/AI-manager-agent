from app.core.phase_config import Phase, PhaseConfig
from app.services.client_service import get_or_create_client
from app.services.document_service import upload_document

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA", "SOW")),
    ]
)


def test_search_finds_uploaded_document(route_client):
    client, fake_rest, storage = route_client(config=CONFIG)
    upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"filled msa", "pdf")

    response = client.get("/api/documents/search", params={"q": "Acme"})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["client_name"] == "Acme"
    assert body["results"][0]["doc_type"] == "MSA"
    assert "download_url" in body["results"][0]


def test_search_requires_query_param(route_client):
    client, _, _ = route_client(config=CONFIG)
    response = client.get("/api/documents/search")

    assert response.status_code == 422


def test_download_stored_document_succeeds(route_client):
    client, fake_rest, storage = route_client(config=CONFIG)
    upload_document(fake_rest, storage, CONFIG, "MSA", "Acme", b"filled msa content", "pdf")

    response = client.get("/api/clients/Acme/documents/MSA/download")

    assert response.status_code == 200
    assert response.content == b"filled msa content"


def test_download_unknown_client_returns_404(route_client):
    client, _, _ = route_client(config=CONFIG)
    response = client.get("/api/clients/Ghost/documents/MSA/download")

    assert response.status_code == 404


def test_download_unknown_doc_type_returns_404(route_client):
    client, fake_rest, storage = route_client(config=CONFIG)
    get_or_create_client(fake_rest, storage, CONFIG, "Acme")

    response = client.get("/api/clients/Acme/documents/SOW/download")

    assert response.status_code == 404
