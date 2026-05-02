"""Telegram command handlers — thin trigger layer for Jenkins builds."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from .context import BotContext


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
    assert update.message
    assert update.effective_chat

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
    assert update.message
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
        "▸ `/recent` — Recent Jenkins history (not bot-scoped)",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------------
# /build
# ------------------------------------------------------------------


async def build_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger a Jenkins build and track for notification."""
    assert update.message
    assert update.effective_chat
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
    """Query Jenkins for current build status."""
    assert update.message
    assert update.effective_chat
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    lines = ["📊 *Bot Status*\n"]
    lines.append(
        f"▸ Job: `{ctx.config.jenkins_job_name}` (ID: `{ctx.config.jenkins_job_id}`)"
    )
    lines.append("▸ Scope: only builds triggered from this bot are tracked")

    # Drive connection
    if ctx.drive.is_connected():
        lines.append("▸ Drive: ✅ Connected")
        lines.append("▸ Ready to build: ✅ Yes")
    else:
        lines.append("▸ Drive: ❌ Setup required in config UI")
        lines.append("▸ Ready to build: ❌ No")

    # Pending builds
    pending_count = len(ctx._pending)
    lines.append(f"▸ Pending bot-triggered builds: {pending_count}")

    # Jenkins connection check — try to get recent builds
    try:
        builds = await ctx.jenkins.get_recent_builds(count=1)
        if builds:
            last = builds[0]
            result = last.get("result") or "IN PROGRESS"
            lines.append("▸ Jenkins: ✅ Connected")
            lines.append(f"▸ Latest Jenkins build: #{last['number']} — {result}")
            lines.append("▸ Note: latest Jenkins build may include manual runs")
        else:
            lines.append("▸ Jenkins: ✅ Connected (no builds yet)")
    except Exception as exc:
        lines.append(f"▸ Jenkins: ❌ Unreachable ({exc.__class__.__name__})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ------------------------------------------------------------------
# /recent
# ------------------------------------------------------------------


async def recent_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Query Jenkins for recent build history."""
    assert update.message
    assert update.effective_chat
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    try:
        builds = await ctx.jenkins.get_recent_builds(count=5)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to query Jenkins: {e}")
        return

    if not builds:
        await update.message.reply_text("📭 No Jenkins builds found.")
        return

    lines = [
        "📦 *Recent Jenkins Builds*\n",
        "_This history is not limited to bot-triggered builds._\n",
    ]
    for b in builds:
        number = b.get("number", "?")
        result = b.get("result") or "IN PROGRESS"
        ts = b.get("timestamp", 0)

        icon = {
            "SUCCESS": "✅",
            "FAILURE": "❌",
            "ABORTED": "⏹️",
            "IN PROGRESS": "🔨",
        }.get(result, "❓")

        # Convert Jenkins timestamp (ms) to readable date
        if ts:
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            date_str = dt.strftime("%Y-%m-%d %H:%M UTC")
        else:
            date_str = "unknown"

        lines.append(f"{icon} #{number} — {result} — {date_str}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
