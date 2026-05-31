"""Tests for POST /callback/build-result — webhook processing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from telegram import Bot

from tg_bot.bot.context import BotContext


def make_mock_bot() -> AsyncMock:
    """Create an AsyncMock that acts as a telegram.Bot."""
    bot = AsyncMock(spec=Bot)
    bot.token = "fake:token"
    bot.id = 123
    bot.first_name = "TestBot"
    bot.username = "test_bot"
    bot.can_join_groups = True
    bot.can_read_all_group_messages = False
    bot.supports_inline_queries = False
    bot.defaults = None
    bot.name = "@test_bot"
    bot.local_mode = False
    return bot





def _make_config():
    config = MagicMock()
    config.app_name = "TestApp"
    config.admin_contact = "@admin"
    config.allowed_chat_ids = [12345]
    config.branches = {"Stable Release": "main"}
    config.bot_callback_url = "http://bot/cb"
    config.github_url = ""
    return config


def _make_ctx(bot=None):
    """Create a BotContext with a mock bot."""
    bot = bot or make_mock_bot()
    ctx = BotContext(
        config=_make_config(),
        build_client=AsyncMock(),
        bot=bot,
    )
    return ctx


@pytest.fixture
def client_with_ctx():
    """Return (TestClient, BotContext) with the ctx wired into the app."""
    from tg_bot.main import create_app

    app = create_app()
    ctx = _make_ctx()
    app.state.manager._bot_context = ctx
    return TestClient(app), ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_result_success_dispatches(client_with_ctx):
    client, ctx = client_with_ctx
    ctx.on_build_success = AsyncMock()

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "success",
            "chat_id": 100,
            "branch": "main",
            "label": "Stable Release",
            "triggered_by": "Alice",
            "commit_hash": "a" * 40,
            "download_url": "https://example.com/file.apk",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"
    ctx.on_build_success.assert_awaited_once()


def test_build_result_failure_dispatches(client_with_ctx):
    client, ctx = client_with_ctx
    ctx.on_build_failure = AsyncMock()

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "failure",
            "chat_id": 100,
            "branch": "main",
            "label": "Stable Release",
            "triggered_by": "Alice",
        },
    )
    assert resp.status_code == 200
    ctx.on_build_failure.assert_awaited_once()


def test_build_result_timeout_dispatches(client_with_ctx):
    client, ctx = client_with_ctx
    ctx.on_build_timeout = AsyncMock()

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "timeout",
            "chat_id": 100,
            "branch": "main",
            "label": "Stable Release",
            "triggered_by": "Alice",
        },
    )
    assert resp.status_code == 200
    ctx.on_build_timeout.assert_awaited_once()


def test_build_result_missing_chat_id_ignored(client_with_ctx):
    client, ctx = client_with_ctx

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "success",
            # missing chat_id
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert resp.json()["reason"] == "no chat_id"


def test_build_result_cancelled_dispatches(client_with_ctx):
    client, ctx = client_with_ctx
    ctx.on_build_cancelled = AsyncMock()

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "cancelled",
            "chat_id": 100,
            "branch": "main",
            "label": "Stable Release",
            "triggered_by": "Alice",
        },
    )
    assert resp.status_code == 200
    ctx.on_build_cancelled.assert_awaited_once()


def test_build_result_aborted_dispatches(client_with_ctx):
    client, ctx = client_with_ctx
    ctx.on_build_cancelled = AsyncMock()

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "aborted",
            "chat_id": 100,
            "branch": "main",
            "label": "Stable Release",
            "triggered_by": "Alice",
        },
    )
    assert resp.status_code == 200
    ctx.on_build_cancelled.assert_awaited_once()


def test_build_result_bot_not_running(isolate_config):
    """No bot context → ignored."""
    from tg_bot.main import create_app

    app = create_app()
    # Don't set bot_context → manager._bot_context is None
    client = TestClient(app)

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "success",
            "chat_id": 100,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

