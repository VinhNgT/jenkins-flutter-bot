"""Smoke tests for config-hub API endpoints."""

from __future__ import annotations

from unittest.mock import patch


async def test_version_endpoint(client):
    """GET /api/version returns version info."""
    resp = await client.get("/api/version")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data


async def test_version_denormalization(client):
    """GET /api/version correctly denormalizes PEP 440 pre-release version strings."""
    with patch("config_hub.routers.version.version") as mock_version:
        # Dev pre-release
        mock_version.return_value = "0.3.2.dev2"
        resp = await client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json() == {"version": "0.3.2-dev.2"}

        # RC pre-release
        mock_version.return_value = "1.0.0.rc12"
        resp = await client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json() == {"version": "1.0.0-rc.12"}

        # Stable release (should remain unchanged)
        mock_version.return_value = "0.3.2"
        resp = await client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json() == {"version": "0.3.2"}


async def test_services_status(client):
    """GET /api/services/status returns status for all services."""
    resp = await client.get("/api/services/status")
    assert resp.status_code == 200
    data = resp.json()
    # All services should be unavailable since no URLs are configured
    for service in ("bot", "agent", "file_manager", "builds"):
        assert data[service]["available"] is False
