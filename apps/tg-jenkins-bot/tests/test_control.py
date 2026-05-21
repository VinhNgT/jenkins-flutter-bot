"""Smoke tests for tg-jenkins-bot control endpoints."""


def test_control_status(client):
    """GET /control/status returns valid JSON without real config."""
    resp = client.get("/control/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert "configured" in data


def test_control_schema(client):
    """GET /control/schema returns the bot schema."""
    resp = client.get("/control/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert "title" in data
    assert "fields" in data


def test_control_config_get(client):
    """GET /control/config returns empty values when no config exists."""
    resp = client.get("/control/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "values" in data
    assert "secret_lengths" in data


def test_control_config_put(client):
    """PUT /control/config saves and merges config."""
    payload = {"telegram": {"admin_contact": "@testadmin"}}
    resp = client.put("/control/config", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    resp = client.get("/control/config")
    data = resp.json()
    assert data["values"]["telegram"]["admin_contact"] == "@testadmin"
