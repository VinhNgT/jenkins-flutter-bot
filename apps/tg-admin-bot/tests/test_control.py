"""Smoke tests for tg-admin-bot control endpoints."""


def test_control_status(client):
    """GET /control/status returns valid JSON without real config."""
    resp = client.get("/control/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert "configured" in data
