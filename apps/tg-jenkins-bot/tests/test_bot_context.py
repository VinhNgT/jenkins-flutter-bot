"""Tests for BotContext — picker expiry, build results, consume_building."""

from unittest.mock import AsyncMock

import pytest

from telegram import Bot

from tg_jenkins_bot.bot.context import BotContext, _format_duration
from tg_jenkins_bot.bot.tracker import TrackedMessage


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    """Create a minimal BotSettings-like object for testing."""
    from unittest.mock import MagicMock

    config = MagicMock()
    config.app_name = overrides.get("app_name", "TestApp")
    config.admin_contact = overrides.get("admin_contact", "@admin")
    config.session_ttl = overrides.get("session_ttl", 60)
    config.allowed_chat_ids = overrides.get("allowed_chat_ids", [12345])
    config.branch_list = overrides.get("branch_list", ["main", "dev"])
    config.bot_callback_url = overrides.get("bot_callback_url", "http://bot/cb")
    config.github_url = overrides.get("github_url", "")
    return config


def _make_build_client():
    return AsyncMock()


@pytest.fixture
def bot():
    return make_mock_bot()


@pytest.fixture
def ctx(bot):
    clock_time = [1_700_000_000.0]
    context = BotContext(
        config=_make_config(),
        build_client=_make_build_client(),
        bot=bot,
        clock=lambda: clock_time[0],
    )
    context._clock_ref = clock_time
    return context


# ---------------------------------------------------------------------------
# has_active_picker
# ---------------------------------------------------------------------------


class TestHasActivePicker:
    def test_picking_state(self, ctx):
        ctx.tracker.register(100, 1, 42, "picking")
        assert ctx.has_active_picker(100) is not None

    def test_awaiting_text_state(self, ctx):
        ctx.tracker.register(100, 1, 42, "awaiting_text")
        assert ctx.has_active_picker(100) is not None

    def test_consumed_returns_none(self, ctx):
        ctx.tracker.register(100, 1, 42, "consumed")
        assert ctx.has_active_picker(100) is None

    def test_building_returns_none(self, ctx):
        ctx.tracker.register(100, 1, 42, "building")
        assert ctx.has_active_picker(100) is None

    def test_no_messages_returns_none(self, ctx):
        assert ctx.has_active_picker(100) is None


# ---------------------------------------------------------------------------
# find_building_for_branch / list_building
# ---------------------------------------------------------------------------


class TestBuildQueries:
    def test_find_building_for_branch(self, ctx):
        ctx.tracker.register(100, 1, 42, "building", data={"ref": "main"})
        assert ctx.find_building_for_branch("main") is not None
        assert ctx.find_building_for_branch("dev") is None

    def test_list_building(self, ctx):
        ctx.tracker.register(100, 1, 42, "building")
        ctx.tracker.register(200, 2, 43, "building")
        assert len(ctx.list_building()) == 2


# ---------------------------------------------------------------------------
# consume_building — atomicity
# ---------------------------------------------------------------------------


class TestConsumeBuilding:
    def test_first_consumer_gets_it(self, ctx):
        ctx.tracker.register(100, 1, 42, "building", data={"request_id": "abc123"})
        result = ctx.consume_building("abc123")
        assert result is not None
        assert result.data["request_id"] == "abc123"

    def test_second_consumer_gets_none(self, ctx):
        ctx.tracker.register(100, 1, 42, "building", data={"request_id": "abc123"})
        ctx.consume_building("abc123")
        assert ctx.consume_building("abc123") is None

    def test_wrong_state_returns_none(self, ctx):
        ctx.tracker.register(100, 1, 42, "picking", data={"request_id": "abc123"})
        assert ctx.consume_building("abc123") is None

    def test_unknown_request_id_returns_none(self, ctx):
        assert ctx.consume_building("nonexistent") is None


# ---------------------------------------------------------------------------
# expire_picker
# ---------------------------------------------------------------------------


class TestExpirePicker:
    async def test_edits_message(self, ctx, bot):
        ctx.tracker.register(100, 1, 42, "picking")
        result = await ctx.expire_picker(100, 1)
        assert result is True
        bot.edit_message_text.assert_awaited_once()
        assert ctx.tracker.get(100, 1) is None

    async def test_awaiting_text_also_expired(self, ctx, bot):
        ctx.tracker.register(100, 1, 42, "awaiting_text")
        result = await ctx.expire_picker(100, 1)
        assert result is True

    async def test_already_consumed(self, ctx):
        ctx.tracker.register(100, 1, 42, "consumed")
        result = await ctx.expire_picker(100, 1)
        assert result is False

    async def test_missing_message(self, ctx):
        result = await ctx.expire_picker(100, 999)
        assert result is False

    async def test_building_not_expired(self, ctx):
        ctx.tracker.register(100, 1, 42, "building")
        result = await ctx.expire_picker(100, 1)
        assert result is False


# ---------------------------------------------------------------------------
# Build result handlers
# ---------------------------------------------------------------------------


class TestBuildResults:
    async def test_on_build_success_edits_and_sends(self, ctx, bot):
        msg = TrackedMessage(
            chat_id=100, message_id=1, user_id=42, state="building",
            data={"ref": "main", "triggered_at": 1_700_000_000.0},
        )
        await ctx.on_build_success(msg, {
            "download_url": "https://drive.google.com/file/123",
        })
        # Check that the original message was edited with a simple status text
        bot.edit_message_text.assert_awaited_once_with(
            "✅ Build on <code>main</code> completed successfully.",
            chat_id=100,
            message_id=1,
            parse_mode="HTML",
            reply_markup=None,
        )
        # Check that the rich notification message was sent to the bottom of the chat
        bot.send_message.assert_awaited_once()
        sent_args = bot.send_message.call_args
        assert "TestApp is ready!" in sent_args[0][1]
        assert "Built from <code>main</code>" in sent_args[0][1]

    async def test_on_build_success_with_download_url(self, ctx, bot):
        msg = TrackedMessage(
            chat_id=100, message_id=1, user_id=42, state="building",
            data={"ref": "main", "triggered_at": 1_700_000_000.0},
        )
        await ctx.on_build_success(msg, {
            "download_url": "https://drive.google.com/file/123",
        })
        # Check that InlineKeyboardMarkup with download button was sent
        call_args = bot.send_message.call_args
        assert call_args.kwargs.get("reply_markup") is not None

    async def test_on_build_success_no_download_url(self, ctx, bot):
        msg = TrackedMessage(
            chat_id=100, message_id=1, user_id=42, state="building",
            data={"ref": "main", "triggered_at": 1_700_000_000.0},
        )
        await ctx.on_build_success(msg, {"download_url": ""})
        call_args = bot.send_message.call_args
        assert call_args.kwargs.get("reply_markup") is None

    async def test_on_build_failure_edits_and_sends(self, ctx, bot):
        msg = TrackedMessage(
            chat_id=100, message_id=1, user_id=42, state="building",
            data={"ref": "main"},
        )
        await ctx.on_build_failure(msg, {})
        bot.edit_message_text.assert_awaited_once_with(
            "❌ Build on <code>main</code> failed.",
            chat_id=100,
            message_id=1,
            parse_mode="HTML",
            reply_markup=None,
        )
        bot.send_message.assert_awaited_once()
        sent_args = bot.send_message.call_args
        assert "TestApp build failed" in sent_args[0][1]

    async def test_on_build_timeout_edits_and_sends(self, ctx, bot):
        msg = TrackedMessage(
            chat_id=100, message_id=1, user_id=42, state="building",
            data={"ref": "main"},
        )
        await ctx.on_build_timeout(msg, {})
        bot.edit_message_text.assert_awaited_once_with(
            "⏰ Build on <code>main</code> timed out.",
            chat_id=100,
            message_id=1,
            parse_mode="HTML",
            reply_markup=None,
        )
        bot.send_message.assert_awaited_once()
        sent_args = bot.send_message.call_args
        assert "TestApp build timed out" in sent_args[0][1]

    async def test_on_build_cancelled_edits_only(self, ctx, bot):
        msg = TrackedMessage(
            chat_id=100, message_id=1, user_id=42, state="building",
            data={"ref": "main"},
        )
        await ctx.on_build_cancelled(msg)
        bot.edit_message_text.assert_awaited_once_with(
            "🚫 Build on <code>main</code> was cancelled.",
            chat_id=100,
            message_id=1,
            parse_mode="HTML",
            reply_markup=None,
        )
        bot.send_message.assert_not_called()

    async def test_no_bot_instance_logs_error(self):
        """bot=None → logs error, no crash."""
        config = _make_config()
        ctx = BotContext(config=config, build_client=_make_build_client(), bot=None)
        msg = TrackedMessage(
            chat_id=100, message_id=1, user_id=42, state="building",
            data={"ref": "main", "triggered_at": 1_700_000_000.0},
        )
        # Should not raise
        await ctx.on_build_success(msg, {"download_url": ""})
        await ctx.on_build_failure(msg, {})
        await ctx.on_build_timeout(msg, {})


# ---------------------------------------------------------------------------
# format_elapsed
# ---------------------------------------------------------------------------


class TestFormatElapsed:
    def test_just_now(self, ctx):
        ctx._clock_ref[0] = 1_700_000_030.0
        msg_time = 1_700_000_000.0
        assert ctx.format_elapsed(msg_time) == "just now"

    def test_one_minute(self, ctx):
        ctx._clock_ref[0] = 1_700_000_060.0
        assert ctx.format_elapsed(1_700_000_000.0) == "1 min ago"

    def test_multiple_minutes(self, ctx):
        ctx._clock_ref[0] = 1_700_000_120.0
        assert ctx.format_elapsed(1_700_000_000.0) == "2 min ago"


# ---------------------------------------------------------------------------
# _format_duration (module-level helper)
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_seconds(self):
        assert _format_duration(0, 30) == "30s"

    def test_minutes(self):
        assert _format_duration(0, 120) == "2 min"

    def test_zero(self):
        assert _format_duration(0, 0) == "0s"


# ---------------------------------------------------------------------------
# Admin hint
# ---------------------------------------------------------------------------


class TestAdminHint:
    def test_with_contact(self):
        config = _make_config(admin_contact="@myadmin")
        ctx = BotContext(config=config, build_client=_make_build_client(), bot=None)
        assert "@myadmin" in ctx._admin_hint()

    def test_without_contact(self):
        config = _make_config(admin_contact="")
        ctx = BotContext(config=config, build_client=_make_build_client(), bot=None)
        assert "Contact your admin" in ctx._admin_hint()


# ---------------------------------------------------------------------------
# TTL duration formatting
# ---------------------------------------------------------------------------


class TestTtlDuration:
    def test_exact_minutes(self):
        config = _make_config(session_ttl=120)
        ctx = BotContext(config=config, build_client=_make_build_client(), bot=None)
        assert ctx._format_ttl_duration() == "2 minutes"

    def test_one_minute(self):
        config = _make_config(session_ttl=60)
        ctx = BotContext(config=config, build_client=_make_build_client(), bot=None)
        assert ctx._format_ttl_duration() == "1 minute"

    def test_seconds(self):
        config = _make_config(session_ttl=45)
        ctx = BotContext(config=config, build_client=_make_build_client(), bot=None)
        assert ctx._format_ttl_duration() == "45 seconds"
