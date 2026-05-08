"""Telegram command handlers — thin trigger layer for Jenkins builds."""

from __future__ import annotations

import html
import logging
import secrets
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from .context import BotContext, _format_duration

logger = logging.getLogger(__name__)


def _get_ctx(context: ContextTypes.DEFAULT_TYPE) -> BotContext:
    """Retrieve the shared BotContext from bot_data."""
    return context.bot_data["bot_context"]


def _escape(text: str) -> str:
    """Escape user-supplied text for safe inclusion in HTML messages."""
    return html.escape(text, quote=False)


def _format_time(ts: float) -> str:
    """Format a Unix timestamp as HH:MM in UTC."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M")


def _format_date(ts: float) -> str:
    """Format a Unix timestamp as '6 May at 14:30' in UTC."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%-d %b at %H:%M")


async def _ensure_authorized(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Reject chats that are not allowed to use the bot."""
    if not update.message or not update.effective_chat:
        return False

    chat_id = update.effective_chat.id
    if chat_id not in _get_ctx(context).config.allowed_chat_ids:
        await update.message.reply_text(
            "❌ This chat isn't authorized. Contact your admin to get access."
        )
        return False

    return True


# ------------------------------------------------------------------
# /start and /help
# ------------------------------------------------------------------


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start and /help commands — welcome message."""
    if not update.message:
        return
    ctx = _get_ctx(context)
    app_name = _escape(ctx.config.app_name)
    await update.message.reply_text(
        f"👋 Hi! I'll build <b>{app_name}</b> and send you a download link "
        "when it's ready.\n"
        "\n"
        "<b>Commands:</b>\n"
        "• /build — Build the latest version (main branch)\n"
        "• /build &lt;branch&gt; — Build a specific branch\n"
        "• /status — Check if the bot is ready\n"
        "• /recent — View recent builds\n"
        "• /cancel — Cancel a build in progress\n"
        "• /help — Show this message",
        parse_mode="HTML",
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
            "❌ The bot isn't fully set up yet. Contact your admin."
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
            "❌ Couldn't start the build. Try again, or contact your admin."
        )
        return

    ctx.add_pending(request_id, chat_id, ref, queue_id=queue_id)

    app_name = _escape(ctx.config.app_name)
    started = _format_time(ctx.get_pending(request_id).triggered_at)
    await update.message.reply_text(
        f"🔨 <b>Building {app_name}...</b>\n"
        "\n"
        f"Branch:  <code>{_escape(ref)}</code>\n"
        f"Started: {started}\n"
        "\n"
        "I'll notify you here when it's done.",
        parse_mode="HTML",
    )


# ------------------------------------------------------------------
# /status
# ------------------------------------------------------------------


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot readiness, active builds, and last build info."""
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    drive_ok = ctx.drive.is_connected()

    # Jenkins connection check
    try:
        jenkins_ok = await ctx.jenkins.check_connection()
    except Exception:
        logger.exception("Jenkins connection check failed")
        jenkins_ok = False

    ready = drive_ok and jenkins_ok

    # Validate pending builds against Jenkins (detect cancelled/deleted)
    stale_builds: list = []
    if jenkins_ok and ctx.pending_count > 0:
        try:
            stale_builds = await ctx.validate_pending_builds()
        except Exception:
            logger.exception("Failed to validate pending builds")

    # Notify users about cancelled builds (best-effort)
    if stale_builds and ctx.bot:
        for _rid, stale_pending in stale_builds:
            try:
                app_name = _escape(ctx.config.app_name)
                await ctx.bot.send_message(
                    stale_pending.chat_id,
                    f"⚠️ <b>{app_name} build cancelled</b>\n"
                    "\n"
                    f"Branch:  <code>{_escape(stale_pending.ref)}</code>\n"
                    "\n"
                    "The build was cancelled or removed on Jenkins.",
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception("Failed to notify about cancelled build")

    # Current pending builds (after validation cleanup)
    pending = ctx.list_pending()

    # Headline
    app_name = _escape(ctx.config.app_name)
    if pending:
        headline = f"🟡 <b>Building {app_name} ({len(pending)} active)</b>"
    elif ready:
        headline = f"🟢 <b>Ready to build {app_name}</b>"
    else:
        headline = f"🔴 <b>{app_name} — Not ready</b>"

    job_name = _escape(ctx.config.jenkins_job_name)
    folder_name = _escape(ctx.config.drive_folder_name or "flutter-builds")
    lines = [headline, ""]

    # Service status
    if jenkins_ok:
        lines.append(f"Jenkins       ✅  {job_name}")
    else:
        lines.append("Jenkins       ❌  Not responding")

    if drive_ok:
        lines.append(f"Google Drive  ✅  {folder_name}")
    else:
        lines.append("Google Drive  ❌  Setup required")

    # Pending builds
    if pending:
        lines.append("")
        lines.append("In progress:")
        for p in pending.values():
            lines.append(
                f"  • <code>{_escape(p.ref)}</code>"
                f" (since {_format_time(p.triggered_at)})"
            )

    # Last completed build — from local tracked data
    recent = ctx.recent_builds(count=1)
    if recent:
        b = recent[0]
        short_hash = b.commit_hash[:7] if b.commit_hash else ""
        date_str = _format_date(b.completed_at) if b.completed_at else ""
        result_icon = "✅" if b.result == "success" else "❌"
        parts = [f"{result_icon} {_escape(b.ref or 'unknown')}"]
        if short_hash:
            parts.append(f"<code>{_escape(short_hash)}</code>")
        if date_str:
            parts.append(date_str)
        lines.append("")
        lines.append(f"Last build: {' · '.join(parts)}")

    # Not-ready hint
    if not ready:
        lines.append("")
        lines.append("Contact your admin to complete setup.")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ------------------------------------------------------------------
# /recent
# ------------------------------------------------------------------


async def recent_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent bot-triggered builds from local state."""
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    builds = ctx.recent_builds(count=5)

    if not builds:
        await update.message.reply_text("📭 No builds yet.")
        return

    app_name = _escape(ctx.config.app_name)
    lines = [f"📦 <b>Recent {app_name} Builds</b>\n"]
    for b in builds:
        result_icon = "✅" if b.result == "success" else "❌"
        short_hash = b.commit_hash[:7] if b.commit_hash else ""
        date_str = _format_date(b.completed_at) if b.completed_at else ""
        duration = _format_duration(b.triggered_at, b.completed_at)

        parts = [f"<code>{_escape(b.ref or 'unknown')}</code>"]
        if short_hash:
            parts.append(f"<code>{_escape(short_hash)}</code>")
        if date_str:
            parts.append(date_str)
        if duration:
            parts.append(duration)

        entry = " · ".join(parts)

        if b.drive_link:
            lines.append(
                f'• {result_icon} {entry}    <a href="{_escape(b.drive_link)}">Download</a>'
            )
        else:
            lines.append(f"• {result_icon} {entry}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ------------------------------------------------------------------
# /cancel
# ------------------------------------------------------------------


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel a pending build."""
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    pending = ctx.list_pending()

    if not pending:
        await update.message.reply_text("No build is currently in progress.")
        return

    # If a branch argument is provided, cancel that specific one
    target_branch = context.args[0] if context.args else None

    if target_branch is None and len(pending) > 1:
        # Multiple pending — list them for the user to pick
        lines = ["Multiple builds in progress:\n"]
        for rid, p in pending.items():
            started = _format_time(p.triggered_at)
            lines.append(f"• {_escape(p.ref)} (started {started})")
        lines.append("")
        lines.append("Use /cancel &lt;branch&gt; to cancel one.")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    # Find the build to cancel
    if target_branch:
        # Find by branch name — if multiple, cancel the most recent
        matches = [
            (rid, p)
            for rid, p in pending.items()
            if p.ref == target_branch
        ]
        if not matches:
            await update.message.reply_text(
                f"No build in progress for branch "
                f"<code>{_escape(target_branch)}</code>.",
                parse_mode="HTML",
            )
            return
        matches.sort(key=lambda x: x[1].triggered_at, reverse=True)
        request_id, build = matches[0]
    else:
        # Exactly one pending — cancel it
        request_id, build = next(iter(pending.items()))

    await ctx.cancel_pending(request_id)

    await update.message.reply_text(
        f"✅ Cancelled build for branch <code>{_escape(build.ref)}</code>.",
        parse_mode="HTML",
    )
