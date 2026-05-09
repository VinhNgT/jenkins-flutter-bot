"""Telegram command handlers — thin trigger layer for Jenkins builds."""

from __future__ import annotations

import html
import logging
import secrets
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from ..jenkins.client import JenkinsTriggerError
from .context import BotContext, _format_duration, _format_elapsed

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
            "❌ This chat isn't authorized.\n"
            f"Your Chat ID: <code>{chat_id}</code>\n"
            "\n"
            "Send this to your admin to request access.",
            parse_mode="HTML",
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
        "• /build --force — Force a fresh build (cancels any in-progress build)\n"
        "• /status — Bot status, active builds, and last build\n"
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

    # Parse arguments: support --force flag
    raw_args = list(context.args) if context.args else []
    force = "--force" in raw_args
    if force:
        raw_args.remove("--force")

    is_default = not raw_args
    ref = raw_args[0] if raw_args else "main"

    # Check Drive connection
    if not ctx.drive.is_connected():
        await update.message.reply_text(
            "❌ Google Drive isn't connected yet — I can't deliver the app.\n"
            f"{ctx._admin_hint()}",
            parse_mode="HTML",
        )
        return

    if not force:
        # ----------------------------------------------------------
        # Layer 1: Pending duplicate guard
        # ----------------------------------------------------------
        match = ctx.find_pending_for_branch(ref)
        if match:
            _, existing_pending = match
            await update.message.reply_text(
                f"⚠️ A build for <code>{_escape(ref)}</code>"
                f" is already in progress"
                f" (started {_format_elapsed(existing_pending.triggered_at)}).\n"
                "\n"
                f"Use /build {_escape(ref)} --force to cancel it and start a new build.",
                parse_mode="HTML",
            )
            return

        # ----------------------------------------------------------
        # Layer 2: Commit comparison via GitLab API
        # ----------------------------------------------------------
        if config.commit_check_enabled and ctx.git_remote:
            skipped = await _check_already_built(
                update, ctx, ref
            )
            if skipped:
                return
    else:
        # --force: cancel any pending build for this branch first
        match = ctx.find_pending_for_branch(ref)
        if match:
            old_rid, old_pending = match
            await ctx.cancel_pending(old_rid)
            await ctx.on_build_cancelled(old_pending, by_user=True)

    # Trigger Jenkins build
    request_id = secrets.token_hex(16)
    try:
        queue_id = await ctx.jenkins.trigger_build(
            branch=ref,
            callback_url=config.bot_callback_url,
            request_id=request_id,
            job_id=config.jenkins_job_name,
        )
    except JenkinsTriggerError as exc:
        await update.message.reply_text(
            f"❌ {_escape(exc.user_message)}",
            parse_mode="HTML",
        )
        return

    ctx.add_pending(request_id, chat_id, ref, queue_id=queue_id)

    app_name = _escape(ctx.config.app_name)
    started = _format_time(ctx.get_pending(request_id).triggered_at)
    branch_label = f"{_escape(ref)} (default)" if is_default else _escape(ref)
    await update.message.reply_text(
        f"🔨 <b>Building {app_name}...</b>\n"
        "\n"
        f"Branch:  <code>{branch_label}</code>\n"
        f"Started: {started}\n"
        "\n"
        "I'll notify you here when it's done.",
        parse_mode="HTML",
    )


async def _check_already_built(
    update: Update,
    ctx: BotContext,
    ref: str,
) -> bool:
    """Check if the branch HEAD matches the last successful build.

    Returns True if the build was blocked (user shown existing download),
    False if the build should proceed.
    """
    assert update.message is not None
    assert ctx.git_remote is not None

    last_build = ctx.last_successful_build_for_branch(ref)
    if not last_build or not last_build.commit_hash:
        return False

    remote_head = await ctx.git_remote.get_branch_head(ref)
    if not remote_head:
        # API failed — proceed with build (fail-open)
        return False

    if remote_head != last_build.commit_hash:
        # New commits exist — proceed with build
        return False

    # Same commit — offer existing download
    short_hash = last_build.commit_hash[:7]
    duration_ago = _format_elapsed(last_build.completed_at)

    lines = [
        f"📦 <code>{_escape(ref)}</code> is already at the latest"
        f" version (<code>{_escape(short_hash)}</code>,"
        f" built {duration_ago}).",
    ]
    if last_build.drive_link:
        lines.append("")
        lines.append(
            f'📲 <a href="{_escape(last_build.drive_link)}">Download APK</a>'
        )
    lines.append("")
    lines.append(
        f"Use /build {_escape(ref)} --force to rebuild anyway."
    )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )
    return True


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
                await ctx.on_build_cancelled(stale_pending, by_user=False)
            except Exception:
                logger.exception("Failed to notify about cancelled build")

    # Check for expired builds and notify (best-effort)
    try:
        await ctx.cleanup_expired_with_notification()
    except Exception:
        logger.exception("Failed to clean up expired builds")

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

    lines = [headline, ""]

    # Service status
    if jenkins_ok:
        lines.append("Jenkins       ✅  Connected")
    else:
        lines.append("Jenkins       ❌  Not responding")

    if drive_ok:
        lines.append("Google Drive  ✅  Connected")
    else:
        lines.append("Google Drive  ❌  Setup required")

    # Pending builds
    if pending:
        lines.append("")
        lines.append("In progress:")
        for p in pending.values():
            lines.append(
                f"  • <code>{_escape(p.ref)}</code>"
                f" (started {_format_elapsed(p.triggered_at)})"
            )

    # Last successful build — from local tracked data
    recent = ctx.recent_builds(count=1, success_only=True)
    if recent:
        b = recent[0]
        short_hash = b.commit_hash[:7] if b.commit_hash else ""
        date_str = _format_date(b.completed_at) if b.completed_at else ""
        parts = [f"✅ {_escape(b.ref or 'unknown')}"]
        if short_hash:
            parts.append(f"<code>{_escape(short_hash)}</code>")
        if date_str:
            parts.append(date_str)
        lines.append("")
        lines.append(f"Last build: {' · '.join(parts)}")

    # Not-ready hint
    if not ready:
        lines.append("")
        lines.append(ctx._admin_hint())

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

    builds = ctx.recent_builds(count=5, success_only=True)

    if not builds:
        await update.message.reply_text("📭 No successful builds yet.")
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
            lines.append(
                f"• <code>{_escape(p.ref)}</code>"
                f" (started {_format_elapsed(p.triggered_at)})"
            )
        lines.append("")
        lines.append("Use /cancel &lt;branch&gt; to cancel one.")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    if target_branch is None and len(pending) == 1:
        # Single pending — show confirmation prompt instead of cancelling
        request_id, build = next(iter(pending.items()))
        await update.message.reply_text(
            f"Cancel the build for <code>{_escape(build.ref)}</code>"
            f" (started {_format_elapsed(build.triggered_at)})?\n"
            "\n"
            f"Use /cancel {_escape(build.ref)} to confirm.",
            parse_mode="HTML",
        )
        return

    # Find the build to cancel (target_branch is set — both None branches returned above)
    assert target_branch is not None
    matches = [(rid, p) for rid, p in pending.items() if p.ref == target_branch]
    if not matches:
        # No match — show available branches
        lines = [
            f"No build in progress for <code>{_escape(target_branch)}</code>.",
            "",
            "Active builds:",
        ]
        for rid, p in pending.items():
            lines.append(
                f"  • <code>{_escape(p.ref)}</code>"
                f" (started {_format_elapsed(p.triggered_at)})"
            )
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
        )
        return

    matches.sort(key=lambda x: x[1].triggered_at, reverse=True)
    request_id, build = matches[0]

    await ctx.cancel_pending(request_id)

    # Notify the chat about the cancellation
    await ctx.on_build_cancelled(build, by_user=True)

    await update.message.reply_text(
        f"✅ Cancelled build for branch <code>{_escape(build.ref)}</code>.",
        parse_mode="HTML",
    )
