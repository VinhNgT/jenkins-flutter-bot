"""Unit tests for the Telegram Web App API router."""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tg_jenkins_bot.bot.context import BotContext
from tg_jenkins_bot.bot.store import ActiveBuildStore
from tg_jenkins_bot.config import BotSettings
from tg_jenkins_bot.main import create_app


def _generate_valid_init_data(token: str, chat_id: int | None = None) -> str:
    """Generate a valid signed Telegram Web App initData string."""
    user = {"id": 67890, "first_name": "Alice", "username": "alice_tg"}
    init_params = {
        "user": json.dumps(user),
        "auth_date": "1715500000",
        "query_id": "AAH6854",
    }
    if chat_id is not None:
        init_params["chat"] = json.dumps({"id": chat_id, "type": "group"})

    sorted_params = sorted(init_params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)

    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    sig = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    init_params["hash"] = sig
    return urllib.parse.urlencode(init_params)


@pytest.fixture
def mock_build_client():
    client = AsyncMock()
    client.trigger_build = AsyncMock(return_value={"request_id": "req-999", "status": "queued"})
    client.cancel_build = AsyncMock(return_value={"status": "cancelled"})
    return client


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def app_with_mocks(mock_build_client, mock_bot):
    """Create app with mocked dependencies."""
    app = create_app()

    config = BotSettings(
        telegram_token="123456:test-token",
        allowed_chat_ids=[12345, 67890],
        app_name="TestApp",
        branches={"Stable Release": "main", "Testing Version": "develop"},
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        webapp_url="https://example.com/webapp",
    )

    ctx = BotContext(
        config=config,
        build_client=mock_build_client,
        bot=mock_bot,
    )

    # Replace manager and bot context
    app.state.manager._bot_context = ctx
    app.state.manager._config = config
    app.state.manager._build_client = mock_build_client

    return app


@pytest.fixture
def test_client(app_with_mocks):
    return TestClient(app_with_mocks)


def test_webapp_config_preview_bypass(test_client) -> None:
    """Test standard config access using preview mode."""
    response = test_client.get(
        "/api/webapp/config",
        headers={"X-Telegram-Init-Data": "preview"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "TestApp"
    assert data["branches"] == [
        {"label": "Stable Release", "ref": "main"},
        {"label": "Testing Version", "ref": "develop"},
    ]
    assert len(data["active_builds"]) == 0


def test_webapp_config_real_hmac(test_client) -> None:
    """Test config access using valid HMAC signature."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=12345)
    response = test_client.get(
        "/api/webapp/config",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "TestApp"


def test_webapp_config_invalid_hmac(test_client) -> None:
    """Test config access using invalid HMAC signature."""
    init_data = _generate_valid_init_data(token="WRONG-TOKEN", chat_id=12345)
    response = test_client.get(
        "/api/webapp/config",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert response.status_code == 401
    assert "Authentication failed" in response.json()["detail"]


def test_webapp_config_unauthorized_chat(test_client) -> None:
    """Test config access from unauthorized chat."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=99999)
    response = test_client.get(
        "/api/webapp/config",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"]


def test_webapp_trigger_build_happy_path(test_client, mock_build_client, mock_bot) -> None:
    """Test successful build trigger from Web App."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=12345)

    response = test_client.post(
        "/api/webapp/trigger",
        headers={"X-Telegram-Init-Data": init_data},
        json={"branch": "main"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "request_id": "req-999"}

    # Verify build-manager call
    mock_build_client.trigger_build.assert_called_once_with(
        branch="main",
        callback_url="http://bot:9090/callback/build-result",
    )

    # Verify Telegram notification sent
    mock_bot.send_message.assert_called_once_with(
        chat_id=12345,
        text="🔨 <b>Alice started a Stable Release build</b>",
        parse_mode="HTML",
    )


def test_webapp_trigger_duplicate_blocked(test_client, mock_build_client, app_with_mocks) -> None:
    """Test that starting a build on a branch already building is blocked."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=12345)
    ctx = app_with_mocks.state.manager.bot_context

    # Register an active build on 'main'
    ctx.store.register(
        request_id="req-existing",
        chat_id=12345,
        ref="main",
        label="Stable Release",
        triggered_by="Bob",
    )

    response = test_client.post(
        "/api/webapp/trigger",
        headers={"X-Telegram-Init-Data": init_data},
        json={"branch": "main"},
    )

    assert response.status_code == 400
    assert "already in progress" in response.json()["detail"]
    assert not mock_build_client.trigger_build.called


def test_webapp_cancel_build_happy_path(test_client, mock_build_client, app_with_mocks) -> None:
    """Test successful build cancellation from Web App."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=12345)
    ctx = app_with_mocks.state.manager.bot_context

    # Register an active build
    ctx.store.register(
        request_id="req-999",
        chat_id=12345,
        ref="main",
        label="Stable Release",
        triggered_by="Alice",
    )

    response = test_client.post(
        "/api/webapp/cancel",
        headers={"X-Telegram-Init-Data": init_data},
        json={"request_id": "req-999"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    # Verify build-manager cancel call
    mock_build_client.cancel_build.assert_called_once_with("req-999")

    # Verify build is consumed from store
    assert len(ctx.store.list_active()) == 0
