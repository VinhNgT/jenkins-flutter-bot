"""Tests for Telegram command and text handlers (multi-user and session-stealing guards)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram import Bot, Chat, Message, Update, User

from tg_jenkins_bot.bot.context import BotContext
from tg_jenkins_bot.bot.handlers import build_handler, text_branch_handler


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


def make_message_update(
    text: str,
    *,
    chat_id: int = 12345,
    user_id: int = 67890,
    user_first_name: str = "Alice",
    message_id: int = 100,
    update_id: int = 1,
    bot: AsyncMock | None = None,
) -> Update:
    """Create a telegram.Update containing a Message with mocked reply_text."""
    bot = bot or make_mock_bot()
    user = User(id=user_id, is_bot=False, first_name=user_first_name)
    chat = Chat(id=chat_id, type="group")

    # We mock the message that is sent in the update
    message = MagicMock(spec=Message)
    message.message_id = message_id
    message.date = datetime.now(tz=timezone.utc)
    message.chat = chat
    message.from_user = user
    message.text = text
    message.set_bot(bot)

    # Make reply_text return a reply message with an incremented ID
    reply_msg = MagicMock(spec=Message)
    reply_msg.message_id = message_id + 1
    reply_msg.chat = chat
    reply_msg.from_user = user
    reply_msg.set_bot(bot)
    
    message.reply_text = AsyncMock(return_value=reply_msg)

    # Mock the overall Update
    update = MagicMock(spec=Update)
    update.update_id = update_id
    update.message = message
    update.effective_chat = chat
    update.effective_user = user
    update.set_bot(bot)
    return update


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
# Multi-User Build Picker Tests
# ---------------------------------------------------------------------------


class TestMultiUserBuildPicker:
    async def test_build_handler_no_active_picker(self, ctx, bot):
        """Happy path: start picker when none is active."""
        update = make_message_update("/build", chat_id=12345, user_id=67890, user_first_name="Alice")
        context = _make_context(ctx, bot)

        await build_handler(update, context)

        # Alice's picker should be registered in tracking
        # message_id + 1 = 101 because reply_text returns msg 101
        tracked = ctx.tracker.get(12345, 101)
        assert tracked is not None
        assert tracked.state == "picking"
        assert tracked.user_id == 67890
        assert tracked.data["user_name"] == "Alice"
        
        # Verify reply message was sent
        update.message.reply_text.assert_called_once()
        assert "Choose a version to build" in update.message.reply_text.call_args[0][0]

    async def test_build_handler_same_user_already_has_picker(self, ctx, bot):
        """Same user tries to open a second picker → tells them they have one open."""
        # Pre-register an active picker for Alice
        ctx.tracker.register(12345, 101, 67890, "picking", data={"user_name": "Alice"})

        update = make_message_update("/build", chat_id=12345, user_id=67890, user_first_name="Alice")
        context = _make_context(ctx, bot)

        await build_handler(update, context)

        # Should not open a new picker, but reply with warning
        update.message.reply_text.assert_called_once_with(
            "☝️ You already have a branch picker open. Use it or wait for it to expire."
        )

    async def test_build_handler_different_user_picker_blocked(self, ctx, bot):
        """Bob tries to open a picker while Alice's is active → blocks Bob and tells him Alice is picking."""
        # Pre-register an active picker for Alice
        ctx.tracker.register(12345, 101, 67890, "picking", data={"user_name": "Alice"})

        # Bob (user_id 11111) tries to run /build
        update = make_message_update("/build", chat_id=12345, user_id=11111, user_first_name="Bob")
        context = _make_context(ctx, bot)

        await build_handler(update, context)

        # Bob's attempt should be blocked, pointing out Alice is picking
        update.message.reply_text.assert_called_once_with(
            "🔇 Alice is picking a branch right now.",
            parse_mode="HTML",
        )


# ---------------------------------------------------------------------------
# Multi-User Text Input (Awaiting Text) Tests
# ---------------------------------------------------------------------------


class TestMultiUserTextInput:
    async def test_text_branch_handler_no_active_custom_picker(self, ctx, bot):
        """Text message received when no custom branch picker is active → does nothing."""
        update = make_message_update("feature/my-branch", chat_id=12345, user_id=67890)
        context = _make_context(ctx, bot)

        await text_branch_handler(update, context)

        # Build client shouldn't be called, no response sent
        assert not ctx.build_client.trigger_build.called
        assert not update.message.reply_text.called

    async def test_text_branch_handler_same_user_triggers_build(self, ctx, bot):
        """Alice typed a branch name during her active session → consumes picker and triggers build."""
        # Pre-register awaiting_text picker for Alice on message 101
        ctx.tracker.register(12345, 101, 67890, "awaiting_text", data={"user_name": "Alice"})

        update = make_message_update("feature/my-branch", chat_id=12345, user_id=67890, message_id=102)
        context = _make_context(ctx, bot)

        await text_branch_handler(update, context)

        # Alice's custom branch input should trigger the build
        ctx.build_client.trigger_build.assert_called_once_with(
            branch="feature/my-branch",
            callback_url="http://bot/cb",
            app_name="TestApp",
        )

        # Awaiting text picker on 101 should transition to building state
        tracked = ctx.tracker.get(12345, 101)
        assert tracked is not None
        assert tracked.state == "building"
        assert tracked.data["ref"] == "feature/my-branch"

    async def test_text_branch_handler_different_user_is_ignored(self, ctx, bot):
        """Bob types a branch name during Alice's active custom session → ignored."""
        # Pre-register awaiting_text picker for Alice on message 101
        ctx.tracker.register(12345, 101, 67890, "awaiting_text", data={"user_name": "Alice"})

        # Bob (user_id 11111) types a branch name
        update = make_message_update("feature/bob-branch", chat_id=12345, user_id=11111, message_id=102)
        context = _make_context(ctx, bot)

        await text_branch_handler(update, context)

        # Bob's attempt should be completely ignored (build client not called)
        assert not ctx.build_client.trigger_build.called

        # Alice's picker on message 101 should still be active in awaiting_text state
        tracked = ctx.tracker.get(12345, 101)
        assert tracked is not None
        assert tracked.state == "awaiting_text"
        assert tracked.user_id == 67890
