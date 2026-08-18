from datetime import datetime, timezone


def test_clients_status_route_serializes_correctly(route_client):
    client, fake, _ = route_client()
    client_row = fake.insert("clients", {"name": "Acme", "created_at": datetime.now(timezone.utc).isoformat()})
    fake.insert(
        "client_documents",
        {"client_id": client_row["id"], "doc_type": "MSA", "uploaded_at": datetime.now(timezone.utc).isoformat()},
    )

    response = client.get("/api/clients/status")

    assert response.status_code == 200
    body = response.json()
    assert len(body["clients"]) == 1
    entry = body["clients"][0]
    assert entry["client_name"] == "Acme"
    assert entry["current_phase"] == "Pre-requisites"
    assert "SOW" in entry["missing_documents"]
    assert entry["is_stale"] is False
    assert isinstance(entry["last_activity_at"], str)
