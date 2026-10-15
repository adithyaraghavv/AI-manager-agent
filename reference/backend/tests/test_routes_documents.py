from fastapi.testclient import TestClient

from app.main import app


def test_list_phases_returns_config_driven_data():
    # No DB/network involved — this endpoint only reads config/sdlc_phase_config.json,
    # which is exactly why it's safe to hit directly in a test without any fixtures.
    client = TestClient(app)
    response = client.get("/api/phases")

    assert response.status_code == 200
    body = response.json()
    assert len(body["phases"]) == 7
    assert body["phases"][0]["name"] == "Pre-requisites"
    assert "MSA" in body["phases"][0]["required_documents"]
