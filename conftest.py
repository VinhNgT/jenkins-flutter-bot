"""Shared test fixtures and domain-object factories.

Provides reusable factory functions for creating domain objects with
sensible defaults, and a ``mock_http_client`` fixture for injecting
``httpx.MockTransport``-backed clients into any service adapter.

Factories are plain functions (not fixtures) so tests can call them
inline with overrides:  ``pending_build_factory(branch="dev")``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest


# ── Domain Object Factories ─────────────────────────────────────────


def pending_build_factory(**overrides: Any) -> Any:
    """Create a ``PendingBuild`` with sensible defaults."""
    from build_manager.builds.state import PendingBuild

    defaults: dict[str, Any] = {
        "request_id": "abc123def456",
        "branch": "main",
        "triggered_at": 1_700_000_000.0,
        "queue_id": 1,
        "frontend_callback_url": "",
    }
    defaults.update(overrides)
    return PendingBuild(**defaults)


def completed_build_factory(**overrides: Any) -> Any:
    """Create a ``CompletedBuild`` with sensible defaults."""
    from build_manager.builds.state import CompletedBuild

    defaults: dict[str, Any] = {
        "request_id": "abc123def456",
        "branch": "main",
        "commit_hash": "a" * 40,
        "result": "success",
        "triggered_at": 1_700_000_000.0,
        "completed_at": 1_700_000_120.0,
        "download_url": "https://example.com/build.apk",
        "file_id": "drive_file_id_123",
    }
    defaults.update(overrides)
    return CompletedBuild(**defaults)


def jenkins_build_factory(**overrides: Any) -> Any:
    """Create a ``JenkinsBuild`` with sensible defaults."""
    from build_manager.builds.jenkins_client import JenkinsBuild

    defaults: dict[str, Any] = {
        "number": 42,
        "result": "SUCCESS",
        "building": False,
        "timestamp": 1_700_000_000.0,
        "duration_ms": 60_000,
        "branch": "main",
        "commit_hash": "a" * 40,
        "request_id": "abc123def456",
    }
    defaults.update(overrides)
    return JenkinsBuild(**defaults)


def tracked_message_factory(**overrides: Any) -> Any:
    """Create a ``TrackedMessage`` with sensible defaults."""
    from tg_jenkins_bot.bot.tracker import TrackedMessage

    defaults: dict[str, Any] = {
        "chat_id": 12345,
        "message_id": 100,
        "user_id": 67890,
        "state": "building",
        "created_at": 1_700_000_000.0,
        "data": {"ref": "main", "request_id": "abc123def456"},
    }
    defaults.update(overrides)
    return TrackedMessage(**defaults)


# ── HTTP Mock Fixtures ───────────────────────────────────────────────


@pytest.fixture
def mock_http_client():
    """Create an ``httpx.AsyncClient`` backed by ``MockTransport``.

    Usage::

        def my_handler(request):
            return httpx.Response(200, json={"ok": True})

        client = mock_http_client(my_handler)
    """
    clients: list[httpx.AsyncClient] = []

    def _factory(handler):  # noqa: ANN001
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        clients.append(client)
        return client

    yield _factory

    import asyncio

    for c in clients:
        try:
            asyncio.get_event_loop().run_until_complete(c.aclose())
        except Exception:
            pass


# ── Telegram Test Helpers ────────────────────────────────────────────


def make_mock_bot() -> Any:
    """Create an ``AsyncMock`` that acts as a ``telegram.Bot``.

    Sets the required attributes that PTB internals check
    (token, id, username, defaults, etc.) so ``ApplicationBuilder().bot()``
    and ``process_update()`` work without hitting the network.
    """
    from unittest.mock import AsyncMock

    from telegram import Bot

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


def make_telegram_update(
    chat_id: int = 12345,
    user_id: int = 67890,
    message_id: int = 1,
    text: str = "/start",
    *,
    update_id: int = 1,
    bot: Any = None,
) -> Any:
    """Create a ``telegram.Update`` with a realistic ``Message``.

    Automatically adds a ``BOT_COMMAND`` entity when *text* starts with
    ``/`` so ``CommandHandler`` dispatch works.  Calls ``set_bot()`` on
    all objects so ``process_update()`` succeeds.
    """
    from datetime import datetime, timezone

    from telegram import Chat, Message, MessageEntity, Update, User

    bot = bot or make_mock_bot()
    user = User(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=chat_id, type="private")

    entities = None
    if text.startswith("/"):
        cmd = text.split()[0]
        entities = [
            MessageEntity(
                type=MessageEntity.BOT_COMMAND, offset=0, length=len(cmd),
            )
        ]

    message = Message(
        message_id=message_id,
        date=datetime.now(tz=timezone.utc),
        chat=chat,
        from_user=user,
        text=text,
        entities=entities,
    )
    message.set_bot(bot)
    update = Update(update_id=update_id, message=message)
    update.set_bot(bot)
    return update


def make_callback_update(
    data: str,
    *,
    chat_id: int = 12345,
    user_id: int = 67890,
    message_id: int = 100,
    update_id: int = 1,
    bot: Any = None,
) -> Any:
    """Create a ``telegram.Update`` with a ``CallbackQuery``.

    Used for testing inline button callbacks dispatched by
    ``CallbackQueryHandler``.
    """
    from datetime import datetime, timezone

    from telegram import CallbackQuery, Chat, Message, Update, User

    bot = bot or make_mock_bot()
    user = User(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=chat_id, type="private")
    message = Message(
        message_id=message_id,
        date=datetime.now(tz=timezone.utc),
        chat=chat,
    )
    message.set_bot(bot)

    query = CallbackQuery(
        id="test_cb_1",
        from_user=user,
        chat_instance="test",
        data=data,
        message=message,
    )
    query.set_bot(bot)

    update = Update(update_id=update_id, callback_query=query)
    update.set_bot(bot)
    return update


def make_handler_context(bot_context: Any, *, bot: Any = None) -> Any:
    """Create a mock ``ContextTypes.DEFAULT_TYPE`` for unit-testing handlers.

    Wires *bot_context* into ``context.bot_data["bot_context"]``.
    Sets ``context.bot`` and ``context.job_queue`` as mocks.
    """
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.bot_data = {"bot_context": bot_context}
    ctx.bot = bot or make_mock_bot()
    ctx.job_queue = MagicMock()
    ctx.job_queue.run_once = MagicMock()
    return ctx


async def make_test_application(bot_context: Any, *, bot: Any = None) -> Any:
    """Build a fully-wired ``Application`` for integration testing.

    Uses ``_build_application()`` with a mock bot so the full handler
    dispatch chain (``CommandHandler`` → handler function → bot method)
    is exercised via ``await app.process_update(update)``.

    Caller must ``await app.shutdown()`` after testing.
    """
    from tg_jenkins_bot.manager import _build_application

    bot = bot or bot_context.bot or make_mock_bot()
    application, _ = _build_application(
        bot_context.config,
        bot_context.build_client,
        bot,
        clock=bot_context._clock,
    )
    await application.initialize()
    return application

