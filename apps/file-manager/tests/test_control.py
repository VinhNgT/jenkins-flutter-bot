"""Smoke tests for control endpoints."""

from __future__ import annotations


async def test_control_status(client):
    """GET /control/status returns valid JSON without real config."""
    resp = await client.get("/control/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert "configured" in data


async def test_control_schema(client):
    """GET /control/schema returns the service schema."""
    resp = await client.get("/control/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert "title" in data
    assert "fields" in data


async def test_control_config_get(client):
    """GET /control/config returns empty values when no config exists."""
    resp = await client.get("/control/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "values" in data
    assert "secret_lengths" in data


async def test_control_config_put(client):
    """PUT /control/config saves and merges config."""
    payload = {"jenkins": {"user": "testuser"}}
    resp = await client.put("/control/config", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    # Verify the value persists
    resp = await client.get("/control/config")
    data = resp.json()
    assert data["values"]["jenkins"]["user"] == "testuser"
