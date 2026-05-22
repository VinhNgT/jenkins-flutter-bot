from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram import Bot, CallbackQuery, Chat, Message, Update, User

from tg_jenkins_bot.bot.context import BotContext
from tg_jenkins_bot.bot.callbacks import callback_router


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


def make_callback_update(
    data: str,
    *,
    chat_id: int = 12345,
    user_id: int = 67890,
    message_id: int = 100,
    update_id: int = 1,
    bot: AsyncMock | None = None,
) -> Update:
    """Create a telegram.Update with a CallbackQuery."""
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    config = MagicMock()
    config.app_name = overrides.get("app_name", "TestApp")
    config.admin_contact = overrides.get("admin_contact", "@admin")
    config.session_ttl = overrides.get("session_ttl", 60)
    config.allowed_chat_ids = overrides.get("allowed_chat_ids", [12345])
    config.branch_list = overrides.get("branch_list", ["main", "dev"])
    config.bot_callback_url = overrides.get("bot_callback_url", "http://bot/cb")
    config.github_url = ""
    return config


def _make_build_client():
    client = AsyncMock()
    client.trigger_build = AsyncMock(return_value={"request_id": "new_req", "status": "queued"})
    client.cancel_build = AsyncMock(return_value={"status": "cancelled"})
    return client


@pytest.fixture
def bot():
    return make_mock_bot()


@pytest.fixture
def ctx(bot):
    return BotContext(
        config=_make_config(),
        build_client=_make_build_client(),
        bot=bot,
        clock=lambda: 1_700_000_000.0,
    )


def _make_context(ctx, bot):
    """Create a mock telegram.ext context with bot_data wired."""
    context = MagicMock()
    context.bot_data = {"bot_context": ctx}
    context.bot = bot
    context.job_queue = MagicMock()
    context.args = []
    return context


# ---------------------------------------------------------------------------
# Branch selection callbacks
# ---------------------------------------------------------------------------


class TestBranchSelect:
    async def test_happy_path(self, ctx, bot):
        """Tap 'main' on a tracked picker → triggers build."""
        ctx.tracker.register(12345, 100, 67890, "picking")
        update = make_callback_update("build:branch:main", chat_id=12345, message_id=100)
        context = _make_context(ctx, bot)

        await callback_router(update, context)

        # Picker should have been consumed (transition picking → consumed)
        tracked = ctx.tracker.get(12345, 100)
        # After _trigger_build, message might be re-registered as "building"
        # or left as "consumed" — either way, it shouldn't be "picking"
        if tracked:
            assert tracked.state != "picking"

    async def test_double_tap_rejected(self, ctx, bot):
        """Second tap on same picker → no-op."""
        ctx.tracker.register(12345, 100, 67890, "picking")
        update = make_callback_update("build:branch:main", chat_id=12345, message_id=100)
        context = _make_context(ctx, bot)

        # First tap
        await callback_router(update, context)
        # The tracker should no longer be in "picking" state
        # Second tap with fresh update
        update2 = make_callback_update("build:branch:main", chat_id=12345, message_id=100)
        await callback_router(update2, context)
        # Should not crash — just silently ignored

    async def test_stale_picker_expired(self, ctx, bot):
        """Picker already consumed → shows expired message."""
        ctx.tracker.register(12345, 100, 67890, "consumed")
        update = make_callback_update("build:branch:main", chat_id=12345, message_id=100)
        context = _make_context(ctx, bot)

        await callback_router(update, context)
        # Should call expire_picker, which edits the message

    async def test_untracked_picker(self, ctx, bot):
        """Tap on a message not in tracker → expire/edit."""
        update = make_callback_update("build:branch:main", chat_id=12345, message_id=999)
        context = _make_context(ctx, bot)
        await callback_router(update, context)
        # Should not crash


# ---------------------------------------------------------------------------
# Custom branch
# ---------------------------------------------------------------------------


class TestCustomBranch:
    async def test_transitions_to_awaiting_text(self, ctx, bot):
        ctx.tracker.register(12345, 100, 67890, "picking")
        update = make_callback_update("build:custom", chat_id=12345, message_id=100)
        context = _make_context(ctx, bot)

        await callback_router(update, context)

        tracked = ctx.tracker.get(12345, 100)
        assert tracked is not None
        assert tracked.state == "awaiting_text"


# ---------------------------------------------------------------------------
# Cancel flow
# ---------------------------------------------------------------------------


class TestCancelFlow:
    async def test_cancel_shows_confirmation(self, ctx, bot):
        ctx.tracker.register(12345, 100, 67890, "building", data={"ref": "main"})
        update = make_callback_update("cancel:req123", chat_id=12345, message_id=100)
        context = _make_context(ctx, bot)

        await callback_router(update, context)

        tracked = ctx.tracker.get(12345, 100)
        assert tracked.state == "confirming_cancel"

    async def test_cancel_confirm_cancels_build(self, ctx, bot):
        ctx.tracker.register(12345, 100, 67890, "confirming_cancel", data={"ref": "main"})
        update = make_callback_update("cancel:confirm:req123", chat_id=12345, message_id=100)
        context = _make_context(ctx, bot)

        await callback_router(update, context)

        # Message should be removed from tracker
        assert ctx.tracker.get(12345, 100) is None
        # Cancel should have been called
        ctx.build_client.cancel_build.assert_awaited_once_with("req123")

    async def test_cancel_back_restores_building(self, ctx, bot):
        ctx.tracker.register(12345, 100, 67890, "confirming_cancel", data={"ref": "main"})
        update = make_callback_update("cancel:back:req123", chat_id=12345, message_id=100)
        context = _make_context(ctx, bot)

        await callback_router(update, context)

        tracked = ctx.tracker.get(12345, 100)
        assert tracked.state == "building"

    async def test_cancel_double_confirm_rejected(self, ctx, bot):
        """Second confirm after first → no-op."""
        ctx.tracker.register(12345, 100, 67890, "confirming_cancel", data={"ref": "main"})
        update = make_callback_update("cancel:confirm:req123", chat_id=12345, message_id=100)
        context = _make_context(ctx, bot)

        await callback_router(update, context)
        # First confirm worked
        ctx.build_client.cancel_build.assert_awaited_once()

        # Second confirm
        update2 = make_callback_update("cancel:confirm:req123", chat_id=12345, message_id=100)
        await callback_router(update2, context)
        # Should not call cancel again
        assert ctx.build_client.cancel_build.await_count == 1

    async def test_cancel_stale_message_shows_stale(self, ctx, bot):
        """Cancel on non-tracked or wrong-state message → stale."""
        ctx.tracker.register(12345, 100, 67890, "picking")  # wrong state
        update = make_callback_update("cancel:req123", chat_id=12345, message_id=100)
        context = _make_context(ctx, bot)

        await callback_router(update, context)
        # Should show stale, not crash


# ---------------------------------------------------------------------------
# Unknown callback
# ---------------------------------------------------------------------------


class TestUnknown:
    async def test_unknown_callback_data_logged(self, ctx, bot, caplog):
        update = make_callback_update("totally:unknown:data", chat_id=12345, message_id=100)
        context = _make_context(ctx, bot)

        import logging
        with caplog.at_level(logging.WARNING):
            await callback_router(update, context)
        assert any("Unknown callback_data" in r.message for r in caplog.records)
