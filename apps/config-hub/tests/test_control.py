"""Smoke tests for config-hub API endpoints."""


def test_version_endpoint(client):
    """GET /api/version returns version info."""
    resp = client.get("/api/version")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data


def test_services_status(client):
    """GET /api/services/status returns status for all services."""
    resp = client.get("/api/services/status")
    assert resp.status_code == 200
    data = resp.json()
    # All services should be unavailable since no URLs are configured
    for service in ("bot", "agent", "file_manager", "builds"):
        assert data[service]["available"] is False
