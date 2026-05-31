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

from config_core.redact import _redactor


# ── Global Cleanup Fixtures ─────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_redactor():
    """Reset the process-global secret redactor between tests.

    Prevents secret values registered in one test from leaking into
    subsequent tests and causing false-positive redaction.
    """
    yield
    _redactor.clear()


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


# ── HTTP Mock Fixtures ───────────────────────────────────────────────


@pytest.fixture
async def mock_http_client():
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

    for c in clients:
        await c.aclose()


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
