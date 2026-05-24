"""Tests for Telegram command handlers (start, recent, status)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram import Bot, Chat, Message, Update, User

from tg_jenkins_bot.bot.context import BotContext
from tg_jenkins_bot.bot.handlers import start_handler, help_handler, status_handler


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
    chat_type: str = "group",
) -> Update:
    """Create a telegram.Update containing a Message with mocked reply_text."""
    bot = bot or make_mock_bot()
    user = User(id=user_id, is_bot=False, first_name=user_first_name)
    chat = Chat(id=chat_id, type=chat_type)

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
    config.allowed_chat_ids = overrides.get("allowed_chat_ids", [12345])
    config.branches = overrides.get("branches", {"Stable Release": "main"})
    config.bot_callback_url = overrides.get("bot_callback_url", "http://bot/cb")
    config.github_url = ""
    config.webapp_url = overrides.get("webapp_url", "https://example.com/webapp/")
    config.webapp_short_name = overrides.get("webapp_short_name", "")
    return config


def _make_build_client():
    client = AsyncMock()
    client.trigger_build = AsyncMock(
        return_value={"request_id": "new_req", "status": "queued"}
    )
    client.cancel_build = AsyncMock(return_value={"status": "cancelled"})
    client.get_build_status = AsyncMock(return_value={"completed_count": 5})

    # Mock recent builds
    b1 = MagicMock()
    b1.branch = "main"
    b1.result = "success"
    b1.commit_hash = "abcdef123"
    b1.completed_at = 1700000100.0
    b1.triggered_at = 1700000000.0
    b1.download_url = "https://example.com/download.apk"
    client.get_recent_builds = AsyncMock(return_value=[b1])
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
        clock=lambda: 1_700_000_200.0,
    )


def _make_context(ctx, bot):
    """Create a mock telegram.ext context with bot_data wired."""
    context = MagicMock()
    context.bot_data = {"bot_context": ctx}
    context.bot = bot
    context.bot.username = "test_bot"
    context.job_queue = MagicMock()
    context.args = []
    return context


class TestCommandHandlers:
    async def test_start_handler(self, ctx, bot) -> None:
        """Verify welcome message displays Web App trigger instructions."""
        update = make_message_update("/start", chat_id=12345)
        context = _make_context(ctx, bot)

        await start_handler(update, context)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Tap 🚀 Build below" in text
        assert "TestApp" in text

    async def test_start_handler_no_button_when_no_short_name(self, ctx, bot) -> None:
        """Without webapp_short_name, no keyboard button is attached."""
        update = make_message_update("/start", chat_id=12345)
        context = _make_context(ctx, bot)
        # Ensure no short name is set (default config)
        ctx.config.webapp_short_name = ""

        await start_handler(update, context)

        kwargs = update.message.reply_text.call_args[1]
        assert kwargs.get("reply_markup") is None

    async def test_start_handler_shows_native_deeplink_button(self, ctx, bot) -> None:
        """With webapp_short_name set, button uses t.me native Mini App deep link."""
        ctx.config.webapp_short_name = "builds"
        update = make_message_update("/start", chat_id=12345)
        context = _make_context(ctx, bot)

        await start_handler(update, context)

        kwargs = update.message.reply_text.call_args[1]
        keyboard = kwargs["reply_markup"]
        assert keyboard is not None
        button = keyboard.inline_keyboard[0][0]
        assert button.url == "https://t.me/test_bot/builds?startapp=12345"
        assert button.web_app is None

    async def test_start_handler_no_button_when_no_webapp_url(self, ctx, bot) -> None:
        """Without webapp_url configured, no keyboard is attached."""
        ctx.config.webapp_url = ""
        update = make_message_update("/start", chat_id=12345)
        context = _make_context(ctx, bot)

        await start_handler(update, context)

        kwargs = update.message.reply_text.call_args[1]
        assert kwargs.get("reply_markup") is None

    async def test_help_handler(self, ctx, bot) -> None:
        """Verify help handler returns detailed help instructions."""
        update = make_message_update("/help", chat_id=12345)
        context = _make_context(ctx, bot)

        await help_handler(update, context)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "ℹ️ <b>TestApp Build Bot</b>" in text
        assert "🚀 <b>How to Build</b>" in text
        assert "/start" in text
        assert "/status" in text
        assert "/help" in text
        assert "Contact @admin for access issues" in text

    async def test_status_handler_ready(self, ctx, bot) -> None:
        """Verify status handler when no builds are active."""
        update = make_message_update("/status", chat_id=12345)
        context = _make_context(ctx, bot)

        await status_handler(update, context)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "TestApp — System Diagnostics" in text
        assert "Service: <code>tg-jenkins-bot v" in text
        assert "Build Manager: 5 completed" in text

    async def test_status_handler_building(self, ctx, bot) -> None:
        """Verify status handler lists active builds from store with details."""
        ctx.store.register(
            request_id="req-111",
            chat_id=12345,
            ref="develop",
            label="Testing Version",
            triggered_by="Alice",
        )

        update = make_message_update("/status", chat_id=12345)
        context = _make_context(ctx, bot)

        await status_handler(update, context)

        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Active builds: 1" in text
        assert "develop" in text
        assert "req: <code>req-111</code>" in text

    async def test_start_handler_private_chat_rejected(self, ctx, bot) -> None:
        """Verify that private chats are rejected and receive an error message with a group redirect button."""
        update = make_message_update("/start", chat_id=12345, chat_type="private")
        context = _make_context(ctx, bot)

        await start_handler(update, context)

        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        text = args[0]
        assert "Private chats are disabled" in text
        assert "authorized" in text
        assert "request access from your admin" in text

        reply_markup = kwargs.get("reply_markup")
        assert reply_markup is not None
        button = reply_markup.inline_keyboard[0][0]
        assert button.text == "➕ Add Bot to Group"
        assert button.url == "https://t.me/test_bot?startgroup=auth"
