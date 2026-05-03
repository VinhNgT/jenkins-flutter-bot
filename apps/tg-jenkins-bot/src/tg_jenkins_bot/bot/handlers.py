"""Telegram command handlers — thin trigger layer for Jenkins builds."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from .context import BotContext

logger = logging.getLogger(__name__)


def _get_ctx(context: ContextTypes.DEFAULT_TYPE) -> BotContext:
    """Retrieve the shared BotContext from bot_data."""
    return context.bot_data["bot_context"]


def _config_ui_hint(ctx: BotContext) -> str:
    """Point users at the config UI when Drive setup is required."""
    if ctx.config.config_ui_url:
        return f"Open {ctx.config.config_ui_url} to complete Drive setup."
    return "Open the config UI dashboard to complete Drive setup."


async def _ensure_authorized(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Reject chats that are not allowed to use the bot."""
    if not update.message or not update.effective_chat:
        return False

    chat_id = update.effective_chat.id
    if chat_id not in _get_ctx(context).config.allowed_chat_ids:
        await update.message.reply_text(
            "❌ This chat is not allowed to use the build bot."
        )
        return False

    return True


# ------------------------------------------------------------------
# /start
# ------------------------------------------------------------------


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — welcome message."""
    if not update.message:
        return
    ctx = _get_ctx(context)
    await update.message.reply_text(
        "🤖 *Flutter Build Bot*\n\n"
        "This bot triggers Jenkins builds, tracks only the builds started "
        "from Telegram, and delivers finished APKs through Google Drive.\n\n"
        "Before using `/build`:\n"
        f"1. {_config_ui_hint(ctx)}\n"
        "2. Check `/status` to confirm the bot is ready\n\n"
        "Available commands:\n"
        "▸ `/help` — Show this message\n"
        "▸ `/build` — Build latest commit on main\n"
        "▸ `/build <branch>` — Build latest on a branch\n"
        "▸ `/build <hash>` — Build a specific commit\n"
        "▸ `/status` — Bot readiness and pending build status\n"
        "▸ `/recent` — Recent bot-triggered builds",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /build
# ------------------------------------------------------------------


async def build_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger a Jenkins build and track for notification."""
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)
    config = ctx.config

    # Check allowed chats
    if not await _ensure_authorized(update, context):
        return

    chat_id = update.effective_chat.id

    ref = context.args[0] if context.args else "main"

    # Check Drive connection
    if not ctx.drive.is_connected():
        await update.message.reply_text(
            "❌ Google Drive setup is required before builds can run.\n"
            f"{_config_ui_hint(ctx)}\n"
            "Run /status again after setup finishes.",
            parse_mode="Markdown",
        )
        return

    # Trigger Jenkins build
    request_id = secrets.token_hex(16)
    queue_id = await ctx.jenkins.trigger_build(
        branch=ref,
        callback_url=config.bot_callback_url,
        request_id=request_id,
        job_id=config.jenkins_job_id,
    )

    if queue_id is None:
        await update.message.reply_text(
            "❌ Failed to trigger Jenkins build.\nCheck bot logs for details."
        )
        return

    ctx.add_pending(request_id, chat_id, ref)

    await update.message.reply_text(
        f"🚀 Build triggered for `{ref}`\n"
        f"🆔 Request: `{request_id[:8]}`\n"
        f"☁️ Delivery: Google Drive\n"
        f"⏳ You'll be notified here when Jenkins completes.",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /status
# ------------------------------------------------------------------


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Query bot readiness and status."""
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    lines = ["📊 *Bot Status*\n"]
    lines.append(
        f"▸ Job: `{ctx.config.jenkins_job_name}` (ID: `{ctx.config.jenkins_job_id}`)"
    )

    # Drive connection
    if ctx.drive.is_connected():
        lines.append("▸ Drive: ✅ Connected")
        lines.append("▸ Ready to build: ✅ Yes")
    else:
        lines.append("▸ Drive: ❌ Setup required in config UI")
        lines.append("▸ Ready to build: ❌ No")

    # Pending builds
    lines.append(f"▸ Pending bot-triggered builds: {ctx.pending_count}")

    # Bot build history
    lines.append(f"▸ Completed builds tracked: {ctx.history_count}")
    recent = ctx.recent_builds(count=1)
    if recent:
        lines.append(f"▸ Last bot build: `{recent[0].ref}` — `{recent[0].filename}`")

    # Jenkins connection check
    try:
        reachable = await ctx.jenkins.check_connection()
        if reachable:
            lines.append("▸ Jenkins: ✅ Connected")
        else:
            lines.append("▸ Jenkins: ❌ Unreachable")
    except Exception as exc:
        lines.append(f"▸ Jenkins: ❌ Unreachable ({exc.__class__.__name__})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /recent
# ------------------------------------------------------------------


async def recent_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent bot-triggered builds from build history."""
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    builds = ctx.recent_builds(count=5)

    if not builds:
        await update.message.reply_text("📭 No bot-triggered builds yet.")
        return

    lines = [
        "📦 *Recent Bot Builds*\n",
    ]
    for b in builds:
        dt = datetime.fromtimestamp(b.completed_at, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(
            f"✅ `{b.ref}` — {date_str}\n"
            f"    📄 `{b.filename}`\n"
            f"    🔗 [Download]({b.drive_link})"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
