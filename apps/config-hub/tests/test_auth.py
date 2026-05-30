"""Tests for config-hub Basic Authentication."""

from __future__ import annotations

import httpx

from config_hub.config import HubBootstrap
from config_hub.main import create_app
from config_hub.manager import ConfigHubManager


async def test_auth_not_configured(client):
    """If auth is not configured but JFB_DEV_MODE is set, endpoints are accessible."""
    resp = await client.get("/api/version")
    assert resp.status_code == 200
    assert "version" in resp.json()

    resp = await client.get("/")
    assert resp.status_code == 200


async def test_auth_not_configured_fail_closed_in_production(monkeypatch):
    """If auth is not configured and JFB_DEV_MODE is not set, endpoints return 503."""
    monkeypatch.delenv("JFB_DEV_MODE", raising=False)

    test_config = HubBootstrap(
        bot_control_url=None,
        agent_control_url=None,
        file_manager_url=None,
        build_manager_url=None,
    )
    app = create_app()
    app.state.manager = ConfigHubManager(config=test_config)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as prod_client:
        resp = await prod_client.get("/api/version")
        assert resp.status_code == 503
        assert "Authentication not configured" in resp.json()["detail"]


async def test_auth_configured_requires_credentials():
    """If auth is configured, endpoints demand credentials and accept valid ones."""
    test_config = HubBootstrap(
        bot_control_url=None,
        agent_control_url=None,
        file_manager_url=None,
        build_manager_url=None,
        auth_username="admin",
        auth_password="securepassword123",
    )
    app = create_app()
    app.state.manager = ConfigHubManager(config=test_config)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as auth_client:
        # 1. No credentials -> 401
        resp = await auth_client.get("/api/version")
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Basic"

        resp = await auth_client.get("/")
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Basic"

        # 2. Correct credentials -> 200
        resp = await auth_client.get(
            "/api/version", auth=("admin", "securepassword123"),
        )
        assert resp.status_code == 200
        assert "version" in resp.json()

        resp = await auth_client.get("/", auth=("admin", "securepassword123"))
        assert resp.status_code == 200

        # 3. Incorrect username -> 401
        resp = await auth_client.get(
            "/api/version", auth=("wronguser", "securepassword123"),
        )
        assert resp.status_code == 401

        # 4. Incorrect password -> 401
        resp = await auth_client.get(
            "/api/version", auth=("admin", "wrongpassword"),
        )
        assert resp.status_code == 401

        # 5. OAuth callback exemption — error path returns 400, not 401
        resp = await auth_client.get(
            "/api/drive/oauth/callback?error=access_denied",
        )
        assert resp.status_code == 400
