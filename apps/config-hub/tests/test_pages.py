"""Tests for config-hub page routing endpoints."""

from __future__ import annotations


async def test_pages_without_slash(client):
    """GET /webapp-admin serves the SPA shell (index.html)."""
    # The client fixture doesn't have Telegram headers, but by default the dummy test
    # token bypass in verify_admin_auth allows it.
    resp = await client.get("/webapp-admin")
    assert resp.status_code == 200
    assert "Stack Control" in resp.text


async def test_pages_with_slash(client):
    """GET /webapp-admin/ serves the SPA shell (index.html)."""
    resp = await client.get("/webapp-admin/")
    assert resp.status_code == 200
    assert "Stack Control" in resp.text
