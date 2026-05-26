"""Tests for config-hub Basic Authentication."""

from __future__ import annotations

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from config_hub.config import HubBootstrap
from config_hub.main import create_app
from config_hub.manager import ConfigHubManager


def test_auth_not_configured(client):
    """If auth is not configured but JFB_DEV_MODE is set, endpoints are accessible."""
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert "version" in resp.json()

    resp = client.get("/")
    assert resp.status_code == 200


def test_auth_not_configured_fail_closed_in_production():
    """If auth is not configured and JFB_DEV_MODE is not set, endpoints return 503."""
    test_config = HubBootstrap(
        bot_control_url=None,
        agent_control_url=None,
        file_manager_url=None,
        build_manager_url=None,
    )
    app = create_app()
    app.state.manager = ConfigHubManager(config=test_config)

    # Remove JFB_DEV_MODE to simulate production
    env = {k: v for k, v in os.environ.items() if k != "JFB_DEV_MODE"}
    with patch.dict(os.environ, env, clear=True):
        prod_client = TestClient(app)
        resp = prod_client.get("/api/version")
        assert resp.status_code == 503
        assert "Authentication not configured" in resp.json()["detail"]


def test_auth_configured_requires_credentials():
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
    auth_client = TestClient(app)

    # 1. No credentials -> 401
    resp = auth_client.get("/api/version")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Basic"

    resp = auth_client.get("/")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Basic"

    # 2. Correct credentials -> 200
    resp = auth_client.get("/api/version", auth=("admin", "securepassword123"))
    assert resp.status_code == 200
    assert "version" in resp.json()

    resp = auth_client.get("/", auth=("admin", "securepassword123"))
    assert resp.status_code == 200

    # 3. Incorrect username -> 401
    resp = auth_client.get("/api/version", auth=("wronguser", "securepassword123"))
    assert resp.status_code == 401

    # 4. Incorrect password -> 401
    resp = auth_client.get("/api/version", auth=("admin", "wrongpassword"))
    assert resp.status_code == 401

    # 5. OAuth callback exemption -> 200 (renders template since fm_client is mocked, but doesn't raise 401)
    # We pass query params representing an error to avoid making a real post call to file-manager during unit tests
    resp = auth_client.get("/api/drive/oauth/callback?error=access_denied")
    assert resp.status_code == 400  # Returns 400 (Bad Request due to oauth error), NOT 401 (Unauthorized)

