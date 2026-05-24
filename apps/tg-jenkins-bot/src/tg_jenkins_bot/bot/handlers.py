"""Telegram command handlers."""

from __future__ import annotations

import html
import logging
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from datetime import datetime, timezone

from telegram import (
    Update,
    LinkPreviewOptions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from .context import BotContext

logger = logging.getLogger(__name__)


def _bot_version() -> str:
    """Return the installed tg-jenkins-bot package version, or 'unknown'."""
    try:
        v = _pkg_version("tg-jenkins-bot")
        import re

        return re.sub(r"^(\d+\.\d+\.\d+)\.(dev|rc)(\d+)$", r"\1-\2.\3", v)
    except PackageNotFoundError:
        return "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_ctx(context: ContextTypes.DEFAULT_TYPE) -> BotContext:
    """Retrieve the shared BotContext from bot_data."""
    return context.bot_data["bot_context"]


def _escape(text: str) -> str:
    """Escape user-supplied text for safe inclusion in HTML messages."""
    return html.escape(text, quote=False)


def _get_webapp_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | None = None,
) -> InlineKeyboardMarkup | None:
    """Build a 🚀 Build inline keyboard button that opens the Telegram native Mini App.

    If ``webapp_short_name`` is configured in BotSettings **and** the bot's
    username is available, the button URL is a native Telegram Mini App deep
    link (``https://t.me/<bot>/<shortname>``). Telegram clients intercept
    this link and open the Mini App as a native slide-up panel/modal, even in group
    chats.

    Returns ``None`` when webapp_short_name is missing or the bot username is not resolved.
    """
    ctx = _get_ctx(context)
    if not ctx.config.webapp_url:
        return None

    short_name = ctx.config.webapp_short_name.strip()
    bot_username = getattr(context.bot, "username", None)
    if short_name and bot_username:
        # Native Mini App deep link — works in group chats.
        url = f"https://t.me/{bot_username}/{short_name}"
        if chat_id is not None:
            url += f"?startapp={chat_id}"
        return InlineKeyboardMarkup([[InlineKeyboardButton(text="🚀 Build", url=url)]])

    # Return None to hide the button when the native Mini App is not configured.
    return None


def _format_date(ts: float) -> str:
    """Format a Unix timestamp as '6 May at 14:30' in UTC."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%-d %b at %H:%M")


async def _ensure_authorized(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Reject chats that are not allowed to use the bot."""
    msg = update.message
    if not msg or not update.effective_chat:
        return False

    chat = update.effective_chat
    if chat.type == "private":
        reply_markup = None
        bot_username = getattr(context.bot, "username", None)
        if bot_username:
            url = f"https://t.me/{bot_username}?startgroup=auth"
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("➕ Add Bot to Group", url=url)]]
            )
        await msg.reply_text(
            "❌ Private chats are disabled.\n"
            "This bot can only be used in <b>authorized</b> group chats.\n"
            "\n"
            "If your group is already authorized, tap the button below to add the bot. Otherwise, adding the bot to a new group will show its Chat ID so you can request access from your admin.",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return False

    chat_id = chat.id
    if chat_id not in _get_ctx(context).config.allowed_chat_ids:
        await msg.reply_text(
            "❌ This chat isn't authorized.\n"
            f"Your Chat ID: <code>{chat_id}</code>\n"
            "\n"
            "Send this to your admin to request access.",
            parse_mode="HTML",
        )
        return False

    return True


# ---------------------------------------------------------------------------
# /start and /help
# ---------------------------------------------------------------------------


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — welcome message."""
    if not update.message:
        return

    if not await _ensure_authorized(update, context):
        return

    ctx = _get_ctx(context)
    app_name = _escape(ctx.config.app_name)

    github_url = ctx.config.github_url
    version_str = f"v{_bot_version()}"
    footer = (
        f'<a href="{github_url}">{version_str} · GitHub</a>'
        if github_url
        else version_str
    )

    chat_id = update.effective_chat.id if update.effective_chat else None

    await update.message.reply_text(
        f"👋 Hi! I'm your build assistant for <b>{app_name}</b>.\n"
        "\n"
        "Tap 🚀 Build below to open the build panel.\n"
        "\n"
        f"{footer}",
        parse_mode="HTML",
        reply_markup=_get_webapp_keyboard(context, chat_id),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command — detailed static help message."""
    if not update.message:
        return

    if not await _ensure_authorized(update, context):
        return

    ctx = _get_ctx(context)
    app_name = _escape(ctx.config.app_name)
    admin_contact = _escape(ctx.config.admin_contact or "your administrator")

    github_url = ctx.config.github_url
    version_str = f"v{_bot_version()}"
    footer = (
        f'<a href="{github_url}">{version_str} · GitHub</a>'
        if github_url
        else version_str
    )

    await update.message.reply_text(
        f"ℹ️ <b>{app_name} Build Bot</b>\n"
        "\n"
        "🚀 <b>How to Build</b>\n"
        "Use /start to get the 🚀 Build button, then tap it to\n"
        "open the build panel. Select a branch and tap Trigger Build.\n"
        "\n"
        "📲 <b>Notifications</b>\n"
        "When your build finishes, I'll send a message here with\n"
        "a download link. Failed builds include the branch and\n"
        "commit for debugging.\n"
        "\n"
        "💡 <b>Commands</b>\n"
        "/start — Welcome message + Build button\n"
        "/status — System diagnostics (technical)\n"
        "/help — This help message\n"
        "\n"
        "🔧 <b>Admin</b>\n"
        f"Contact {admin_contact} for access issues.\n"
        "\n"
        f"{footer}",
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


# ---------------------------------------------------------------------------
# /status (technical diagnostic command)
# ---------------------------------------------------------------------------


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show technical diagnostics of the system."""
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    # Current active builds from ActiveBuildStore
    building = ctx.list_building()

    # Fetch build status from build-manager
    sm_status = await ctx.build_client.get_build_status()

    # Headline
    app_name = _escape(ctx.config.app_name)
    version = _escape(_bot_version())
    
    lines = [
        f"🔧 <b>{app_name} — System Diagnostics</b>",
        "",
        f"Service: <code>tg-jenkins-bot v{version}</code>",
        "Status: 🟢 Online",
        f"Active builds: {len(building)}",
    ]

    # Pending builds list
    if building:
        lines.append("")
        lines.append("Pending:")
        for b in building:
            req_id = b.request_id[:8] if b.request_id else "unknown"
            lines.append(
                f"  • {_escape(b.ref)} (req: <code>{_escape(req_id)}</code>, started {ctx.format_elapsed(b.triggered_at)})"
            )

    # Recent completed build
    recent = await ctx.build_client.get_recent_builds(count=1)
    if recent:
        last = recent[0]
        result_emoji = "✅" if last.result == "success" else "❌" if last.result == "failure" else "⏰" if last.result == "timeout" else "🛑"
        short_hash = last.commit_hash[:7] if last.commit_hash else "unknown"
        date_str = _format_date(last.completed_at) if last.completed_at else "unknown"
        lines.append("")
        lines.append("Last build:")
        lines.append(
            f"  {result_emoji} {_escape(last.branch or 'unknown')} · <code>{_escape(short_hash)}</code> · {date_str}"
        )

    # Build manager completed count
    completed = sm_status.get("completed_count", 0)
    lines.append("")
    lines.append(f"Build Manager: {completed} completed")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )
