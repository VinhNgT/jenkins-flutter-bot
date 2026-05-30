"""Tests for POST /callback/build-result — webhook processing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from telegram import Bot

from tg_jenkins_bot.bot.context import BotContext


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


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    monkeypatch.setenv("JFB_DATA_DIR", str(tmp_path))


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
    from tg_jenkins_bot.main import create_app

    app = create_app()
    ctx = _make_ctx()
    app.state.manager._bot_context = ctx
    return TestClient(app), ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_result_success_dispatches(client_with_ctx):
    client, ctx = client_with_ctx
    ctx.store.register(
        request_id="abc123",
        chat_id=100,
        ref="main",
        label="Stable Release",
        triggered_by="Alice",
    )
    ctx.on_build_success = AsyncMock()

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "success",
            "branch": "main",
            "commit_hash": "a" * 40,
            "download_url": "https://example.com/file.apk",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"
    ctx.on_build_success.assert_awaited_once()


def test_build_result_failure_dispatches(client_with_ctx):
    client, ctx = client_with_ctx
    ctx.store.register(
        request_id="abc123",
        chat_id=100,
        ref="main",
        label="Stable Release",
        triggered_by="Alice",
    )
    ctx.on_build_failure = AsyncMock()

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "failure",
        },
    )
    assert resp.status_code == 200
    ctx.on_build_failure.assert_awaited_once()


def test_build_result_timeout_dispatches(client_with_ctx):
    client, ctx = client_with_ctx
    ctx.store.register(
        request_id="abc123",
        chat_id=100,
        ref="main",
        label="Stable Release",
        triggered_by="Alice",
    )
    ctx.on_build_timeout = AsyncMock()

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "timeout",
        },
    )
    assert resp.status_code == 200
    ctx.on_build_timeout.assert_awaited_once()


def test_build_result_unknown_request_id_ignored(client_with_ctx):
    client, ctx = client_with_ctx

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "unknown",
            "result": "success",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_build_result_duplicate_callback_ignored(client_with_ctx):
    """Same request_id twice → second is ignored (consume_building returns None)."""
    client, ctx = client_with_ctx
    ctx.store.register(
        request_id="abc123",
        chat_id=100,
        ref="main",
        label="Stable Release",
        triggered_by="Alice",
    )
    ctx.on_build_success = AsyncMock()

    # First callback
    resp1 = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "success",
        },
    )
    assert resp1.json()["status"] == "processed"

    # Second callback — building already consumed
    resp2 = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "success",
        },
    )
    assert resp2.json()["status"] == "ignored"
    # on_build_success should only have been called once
    assert ctx.on_build_success.await_count == 1


def test_build_result_cancelled_dispatches(client_with_ctx):
    client, ctx = client_with_ctx
    ctx.store.register(
        request_id="abc123",
        chat_id=100,
        ref="main",
        label="Stable Release",
        triggered_by="Alice",
    )
    ctx.on_build_cancelled = AsyncMock()

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "cancelled",
        },
    )
    assert resp.status_code == 200
    ctx.on_build_cancelled.assert_awaited_once()


def test_build_result_aborted_dispatches(client_with_ctx):
    client, ctx = client_with_ctx
    ctx.store.register(
        request_id="abc123",
        chat_id=100,
        ref="main",
        label="Stable Release",
        triggered_by="Alice",
    )
    ctx.on_build_cancelled = AsyncMock()

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "aborted",
        },
    )
    assert resp.status_code == 200
    ctx.on_build_cancelled.assert_awaited_once()


def test_build_result_bot_not_running(isolate_config):
    """No bot context → ignored."""
    from tg_jenkins_bot.main import create_app

    app = create_app()
    # Don't set bot_context → manager._bot_context is None
    client = TestClient(app)

    resp = client.post(
        "/callback/build-result",
        json={
            "request_id": "abc123",
            "result": "success",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
