"""Tests for BotContext — active builds, build results, consume_building."""

from unittest.mock import AsyncMock
import pytest

from telegram import Bot

from tg_jenkins_bot.bot.context import BotContext, _format_duration
from tg_jenkins_bot.bot.store import ActiveBuild


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
    config.allowed_chat_ids = overrides.get("allowed_chat_ids", [12345])
    config.branches = overrides.get("branches", {"Stable Release": "main"})
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
# find_building_for_branch / list_building
# ---------------------------------------------------------------------------


class TestBuildQueries:
    def test_find_building_for_branch(self, ctx):
        ctx.store.register(
            request_id="req-123",
            chat_id=100,
            ref="main",
            label="Stable Release",
            triggered_by="Alice",
        )
        assert ctx.store.find_by_branch("main") is not None
        assert ctx.store.find_by_branch("dev") is None

    def test_list_building(self, ctx):
        ctx.store.register(
            request_id="req-1",
            chat_id=100,
            ref="main",
            label="Stable Release",
            triggered_by="Alice",
        )
        ctx.store.register(
            request_id="req-2",
            chat_id=200,
            ref="dev",
            label="Testing Version",
            triggered_by="Bob",
        )
        assert len(ctx.list_building()) == 2


# ---------------------------------------------------------------------------
# consume_building
# ---------------------------------------------------------------------------


class TestConsumeBuilding:
    def test_first_consumer_gets_it(self, ctx):
        ctx.store.register(
            request_id="abc123",
            chat_id=100,
            ref="main",
            label="Stable Release",
            triggered_by="Alice",
        )
        result = ctx.consume_building("abc123")
        assert result is not None
        assert result.request_id == "abc123"

    def test_second_consumer_gets_none(self, ctx):
        ctx.store.register(
            request_id="abc123",
            chat_id=100,
            ref="main",
            label="Stable Release",
            triggered_by="Alice",
        )
        ctx.consume_building("abc123")
        assert ctx.consume_building("abc123") is None

    def test_unknown_request_id_returns_none(self, ctx):
        assert ctx.consume_building("nonexistent") is None


# ---------------------------------------------------------------------------
# Build result handlers
# ---------------------------------------------------------------------------


class TestBuildResults:
    async def test_on_build_success_sends_notification(self, ctx, bot):
        build = ActiveBuild(
            chat_id=100,
            ref="main",
            label="Stable Release",
            request_id="req-123",
            triggered_at=1_700_000_000.0,
            triggered_by="Alice",
            triggered_by_id=67890,
        )
        ctx._clock_ref[0] = 1_700_000_120.0  # 2 minutes later
        await ctx.on_build_success(
            build,
            {
                "download_url": "https://drive.google.com/file/123",
                "commit_hash": "abcdef123",
            },
        )

        # Verify bot.send_message was called to deliver APK link
        bot.send_message.assert_awaited_once()
        call_args = bot.send_message.call_args
        assert call_args[0][0] == 100
        text = call_args[0][1]
        assert "TestApp Stable Release is ready!" in text
        assert "Branch: <code>main</code>" in text
        assert "Commit: <code>abcdef1</code>" in text
        assert "Duration: 2 min" in text
        assert "Triggered by: Alice" in text

        # Verify reply markup download button
        reply_markup = call_args.kwargs.get("reply_markup")
        assert reply_markup is not None

    async def test_on_build_success_no_download_url(self, ctx, bot):
        build = ActiveBuild(
            chat_id=100,
            ref="main",
            label="Stable Release",
            request_id="req-123",
            triggered_at=1_700_000_000.0,
            triggered_by="Alice",
            triggered_by_id=67890,
        )
        await ctx.on_build_success(build, {"download_url": ""})

        call_args = bot.send_message.call_args
        assert call_args.kwargs.get("reply_markup") is None

    async def test_on_build_failure_sends_notification(self, ctx, bot):
        build = ActiveBuild(
            chat_id=100,
            ref="main",
            label="Stable Release",
            request_id="req-123",
            triggered_at=1_700_000_000.0,
            triggered_by="Alice",
            triggered_by_id=67890,
        )
        ctx._clock_ref[0] = 1_700_000_060.0  # 1 minute later
        await ctx.on_build_failure(build, {"commit_hash": "abcdef123"})

        bot.send_message.assert_awaited_once()
        call_args = bot.send_message.call_args
        assert call_args[0][0] == 100
        text = call_args[0][1]
        assert "TestApp Stable Release build failed" in text
        assert "Branch: <code>main</code>" in text
        assert "Commit: <code>abcdef1</code>" in text
        assert "Duration: 1 min" in text
        assert "Triggered by: Alice" in text
        assert "Contact your admin" in text

    async def test_on_build_timeout_sends_notification(self, ctx, bot):
        build = ActiveBuild(
            chat_id=100,
            ref="main",
            label="Stable Release",
            request_id="req-123",
            triggered_at=1_700_000_000.0,
            triggered_by="Alice",
            triggered_by_id=67890,
        )
        ctx._clock_ref[0] = 1_700_000_120.0  # 2 minutes later
        await ctx.on_build_timeout(build, {})

        bot.send_message.assert_awaited_once()
        call_args = bot.send_message.call_args
        assert call_args[0][0] == 100
        text = call_args[0][1]
        assert "TestApp Stable Release build timed out" in text
        assert "Branch: <code>main</code>" in text
        assert "Waited: 2 min" in text
        assert "Triggered by: Alice" in text

    async def test_on_build_cancelled_without_user(self, ctx, bot):
        build = ActiveBuild(
            chat_id=100,
            ref="main",
            label="Stable Release",
            request_id="req-123",
            triggered_at=1_700_000_000.0,
            triggered_by="Alice",
            triggered_by_id=67890,
        )
        await ctx.on_build_cancelled(build)
        bot.send_message.assert_called_once()
        text = bot.send_message.call_args[0][1]
        assert "TestApp Stable Release build cancelled" in text
        assert "Branch: <code>main</code>" in text

    async def test_on_build_cancelled_with_user(self, ctx, bot):
        build = ActiveBuild(
            chat_id=100,
            ref="main",
            label="Stable Release",
            request_id="req-123",
            triggered_at=1_700_000_000.0,
            triggered_by="Alice",
            triggered_by_id=67890,
        )
        await ctx.on_build_cancelled(build, cancelled_by="Bob")
        bot.send_message.assert_called_once()
        text = bot.send_message.call_args[0][1]
        assert "TestApp Stable Release build cancelled" in text
        assert "Cancelled by: Bob" in text
        assert "Branch: <code>main</code>" in text

    async def test_no_bot_instance_no_crash(self):
        """bot=None → no crash."""
        config = _make_config()
        ctx = BotContext(config=config, build_client=_make_build_client(), bot=None)
        build = ActiveBuild(
            chat_id=100,
            ref="main",
            label="Stable Release",
            request_id="req-123",
            triggered_at=1_700_000_000.0,
            triggered_by="Alice",
            triggered_by_id=67890,
        )
        # Should not raise
        await ctx.on_build_success(build, {"download_url": ""})
        await ctx.on_build_failure(build, {})
        await ctx.on_build_timeout(build, {})


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
