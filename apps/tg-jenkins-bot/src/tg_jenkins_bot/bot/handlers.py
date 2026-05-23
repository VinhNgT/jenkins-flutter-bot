"""Telegram command handlers."""

from __future__ import annotations

import html
import logging
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from datetime import datetime, timezone

from telegram import (
    Update,
    LinkPreviewOptions,
)
from telegram.ext import ContextTypes

from .context import BotContext, _format_duration

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

    chat_id = update.effective_chat.id
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
    """Handle /start and /help commands — welcome message."""
    if not update.message:
        return
    ctx = _get_ctx(context)
    app_name = _escape(ctx.config.app_name)

    github_url = ctx.config.github_url
    version_str = f"<i>v{_bot_version()}</i>"
    footer = (
        f'<a href="{github_url}">⭐ GitHub</a>  ·  {version_str}'
        if github_url
        else version_str
    )

    await update.message.reply_text(
        f"👋 Hi! I'll build <b>{app_name}</b> and send you a download link "
        "when it's ready.\n"
        "\n"
        "Tap the 🚀 Build button below to get started, or use /recent to see past builds.\n"
        "\n"
        f"{footer}",
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


# ---------------------------------------------------------------------------
# /status (semi-technical, admin-facing)
# ---------------------------------------------------------------------------


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot readiness and active builds."""
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
    if building:
        headline = f"🟡 <b>Building {app_name} ({len(building)} active)</b>"
    else:
        headline = f"🟢 <b>Ready to build {app_name}</b>"

    lines = [headline, ""]

    # Build counts
    completed = sm_status.get("completed_count", 0)
    if completed:
        lines.append(f"Completed builds: {completed}")

    # Pending builds
    if building:
        lines.append("")
        lines.append("In progress:")
        for b in building:
            lines.append(
                f"  • <code>{_escape(b.ref)}</code>"
                f" (started {ctx.format_elapsed(b.triggered_at)})"
            )

    # Recent successful build
    recent = await ctx.build_client.get_recent_builds(count=1)
    successful = [b for b in recent if b.result == "success"]
    if successful:
        last = successful[0]
        short_hash = last.commit_hash[:7] if last.commit_hash else ""
        date_str = _format_date(last.completed_at) if last.completed_at else ""
        parts = [f"✅ {_escape(last.branch or 'unknown')}"]
        if short_hash:
            parts.append(f"<code>{_escape(short_hash)}</code>")
        if date_str:
            parts.append(date_str)
        lines.append("")
        lines.append(f"Last build: {' · '.join(parts)}")

    # Not-ready hint
    if not building and not completed:
        lines.append("")
        lines.append(ctx._admin_hint())

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# /recent command
# ---------------------------------------------------------------------------


async def recent_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/recent — show recent successful builds with download links."""
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    builds = await ctx.build_client.get_recent_builds(count=5)
    successful = [b for b in builds if b.result == "success"]

    if not successful:
        await update.message.reply_text(
            "📭 No successful builds yet.",
        )
        return

    app_name = _escape(ctx.config.app_name)
    lines = [f"📦 <b>Recent {app_name} Builds</b>\n"]
    for b in successful:
        date_str = _format_date(b.completed_at) if b.completed_at else ""
        duration = _format_duration(b.triggered_at, b.completed_at)
        parts = [f"<code>{_escape(b.branch or 'unknown')}</code>"]
        if date_str:
            parts.append(date_str)
        if duration:
            parts.append(duration)
        entry = " · ".join(parts)

        if b.download_url:
            lines.append(
                f'• ✅ {entry}    <a href="{_escape(b.download_url)}">📲 Download</a>'
            )
        else:
            lines.append(f"• ✅ {entry}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )
