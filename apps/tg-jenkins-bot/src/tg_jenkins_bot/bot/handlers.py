"""Telegram handlers — keyboard buttons + slash commands.

Provides:
  - /start, /help — welcome message with persistent keyboard
  - /status — admin diagnostic (semi-technical, kept as-is)
  - 🔨 Build keyboard button — branch picker + build trigger
  - 📦 Recent keyboard button — recent builds with download links
  - Free-text handler for typed branch names during build sessions
"""

from __future__ import annotations

import html
import logging
import secrets
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from ..jenkins.client import JenkinsTriggerError
from .context import BotContext, PendingBuild, _format_duration, _format_elapsed

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent keyboard — shown on every reply
# ---------------------------------------------------------------------------

REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [["🔨 Build", "📦 Recent"]],
    resize_keyboard=True,
    is_persistent=True,
)


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
    msg = update.message or update.callback_query and update.callback_query.message
    if not msg or not update.effective_chat:
        return False

    chat_id = update.effective_chat.id
    if chat_id not in _get_ctx(context).config.allowed_chat_ids:
        if update.message:
            await update.message.reply_text(
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
    """Handle /start and /help commands — welcome message with keyboard."""
    if not update.message:
        return
    ctx = _get_ctx(context)
    app_name = _escape(ctx.config.app_name)
    await update.message.reply_text(
        f"👋 Hi! I'll build <b>{app_name}</b> and send you a download link "
        "when it's ready.\n"
        "\n"
        "Tap 🔨 Build to get started!",
        parse_mode="HTML",
        reply_markup=REPLY_KEYBOARD,
    )


# ---------------------------------------------------------------------------
# /status (semi-technical, admin-facing)
# ---------------------------------------------------------------------------


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
    stale_builds: list[tuple[str, PendingBuild]] = []
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

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=REPLY_KEYBOARD,
    )


# ---------------------------------------------------------------------------
# 🔨 Build keyboard button
# ---------------------------------------------------------------------------


async def keyboard_build_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle the 🔨 Build keyboard button — show branch picker."""
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    chat_id = update.effective_chat.id
    user = update.effective_user

    # Check Drive connection
    if not ctx.drive.is_connected():
        await update.message.reply_text(
            f"❌ Can't build right now — Google Drive isn't connected.\n"
            f"{ctx._admin_hint()}",
            parse_mode="HTML",
            reply_markup=REPLY_KEYBOARD,
        )
        return

    # Check session lock (group chats)
    existing = ctx.get_session(chat_id)
    if existing and user and existing.user_id != user.id:
        await update.message.reply_text(
            f"🔇 {_escape(existing.user_name)} is picking a branch right now.",
            parse_mode="HTML",
            reply_markup=REPLY_KEYBOARD,
        )
        return

    # Build inline keyboard from configured branch list
    branches = ctx.config.branch_list
    buttons: list[list[InlineKeyboardButton]] = []
    for branch in branches:
        label = branch[:40]
        data = f"build:branch:{branch[:40]}"
        buttons.append([InlineKeyboardButton(label, callback_data=data)])
    buttons.append(
        [InlineKeyboardButton("✏️ Type a name", callback_data="build:custom")]
    )

    msg = await update.message.reply_text(
        "🔨 Choose a version to build:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    # Start session (30s lock)
    user_name = (user.first_name if user else "Someone") or "Someone"
    user_id = user.id if user else 0
    ctx.start_session(chat_id, user_id, user_name, msg.message_id)


# ---------------------------------------------------------------------------
# 📦 Recent keyboard button
# ---------------------------------------------------------------------------


async def keyboard_recent_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle the 📦 Recent keyboard button — show recent builds."""
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    builds = ctx.recent_builds(count=5, success_only=True)

    if not builds:
        await update.message.reply_text(
            "📭 No successful builds yet.",
            reply_markup=REPLY_KEYBOARD,
        )
        return

    app_name = _escape(ctx.config.app_name)
    lines = [f"📦 <b>Recent {app_name} Builds</b>\n"]
    for b in builds:
        date_str = _format_date(b.completed_at) if b.completed_at else ""
        duration = _format_duration(b.triggered_at, b.completed_at)
        parts = [f"<code>{_escape(b.ref or 'unknown')}</code>"]
        if date_str:
            parts.append(date_str)
        if duration:
            parts.append(duration)
        entry = " · ".join(parts)

        if b.drive_link:
            lines.append(
                f'• ✅ {entry}    <a href="{_escape(b.drive_link)}">📲 Download</a>'
            )
        else:
            lines.append(f"• ✅ {entry}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=REPLY_KEYBOARD,
    )


# ---------------------------------------------------------------------------
# Free-text handler (typed branch names during build sessions)
# ---------------------------------------------------------------------------


async def text_branch_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle free-text input — only processes branch names during sessions."""
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    ctx = _get_ctx(context)
    chat_id = update.effective_chat.id
    session = ctx.get_session(chat_id)

    # Ignore if no active session or not in text-input mode
    if not session or session.state != "awaiting_text":
        return

    # Only the user who started the session can type a branch name
    if update.effective_user.id != session.user_id:
        return

    branch = (update.message.text or "").strip()
    if not branch:
        return

    ctx.clear_session(chat_id)

    # Trigger the build using the shared helper
    await _trigger_build(update, context, branch, session.message_id)


# ---------------------------------------------------------------------------
# Build trigger helper (shared by callback and text handlers)
# ---------------------------------------------------------------------------


async def _trigger_build(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ref: str,
    picker_message_id: int | None = None,
    *,
    force: bool = False,
) -> None:
    """Core build trigger logic — shared by branch picker and text input."""
    assert update.effective_chat is not None
    ctx = _get_ctx(context)
    config = ctx.config
    chat_id = update.effective_chat.id

    if not force:
        # Layer 1: Pending duplicate guard
        match = ctx.find_pending_for_branch(ref)
        if match:
            _, existing_pending = match
            elapsed = _format_elapsed(existing_pending.triggered_at)
            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 Cancel and rebuild",
                            callback_data=f"build:confirm_cancel_rebuild:{ref[:40]}",
                        )
                    ],
                ]
            )
            text = (
                f"⚠️ A build is already running on"
                f" <code>{_escape(ref)}</code>"
                f" (started {elapsed})."
            )
            if picker_message_id:
                try:
                    await context.bot.edit_message_text(
                        text,
                        chat_id=chat_id,
                        message_id=picker_message_id,
                        parse_mode="HTML",
                        reply_markup=buttons,
                    )
                except Exception:
                    logger.exception("Failed to edit picker to in-progress")
            elif update.message:
                await update.message.reply_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=buttons,
                )
            return

        # Layer 2: Commit comparison via GitLab API
        if config.commit_check_enabled and ctx.git_remote:
            last_build = ctx.last_successful_build_for_branch(ref)
            if last_build and last_build.commit_hash:
                remote_head = await ctx.git_remote.get_branch_head(ref)
                if remote_head and remote_head == last_build.commit_hash:
                    # Same commit — offer download or rebuild
                    buttons_list: list[list[InlineKeyboardButton]] = []
                    if last_build.drive_link:
                        buttons_list.append(
                            [
                                InlineKeyboardButton(
                                    "📲 Download APK",
                                    url=last_build.drive_link,
                                )
                            ]
                        )
                    buttons_list.append(
                        [
                            InlineKeyboardButton(
                                "🔄 Rebuild Anyway",
                                callback_data=f"build:confirm_rebuild:{ref[:40]}",
                            )
                        ]
                    )
                    dup_buttons = InlineKeyboardMarkup(buttons_list)
                    app_name = _escape(config.app_name)
                    text = (
                        f"📦 <b>{app_name}</b> is already up to date"
                        f" on <code>{_escape(ref)}</code>."
                    )
                    if picker_message_id:
                        try:
                            await context.bot.edit_message_text(
                                text,
                                chat_id=chat_id,
                                message_id=picker_message_id,
                                parse_mode="HTML",
                                reply_markup=dup_buttons,
                            )
                        except Exception:
                            logger.exception("Failed to edit picker to duplicate")
                    elif update.message:
                        await update.message.reply_text(
                            text,
                            parse_mode="HTML",
                            reply_markup=dup_buttons,
                        )
                    return
    else:
        # Force: cancel any pending build for this branch first
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
        error_text = f"❌ {_escape(exc.user_message)}"
        if picker_message_id:
            try:
                await context.bot.edit_message_text(
                    error_text,
                    chat_id=chat_id,
                    message_id=picker_message_id,
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception("Failed to edit picker to error")
        elif update.message:
            await update.message.reply_text(
                error_text,
                parse_mode="HTML",
            )
        return

    # Send/edit the building message with cancel button
    app_name = _escape(ctx.config.app_name)
    cancel_button = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data=f"cancel:{request_id}",
                )
            ],
        ]
    )
    building_text = (
        f"🔨 <b>Building {app_name}...</b>\n\nI'll let you know when it's ready."
    )

    if picker_message_id:
        try:
            await context.bot.edit_message_text(
                building_text,
                chat_id=chat_id,
                message_id=picker_message_id,
                parse_mode="HTML",
                reply_markup=cancel_button,
            )
            ctx.add_pending(
                request_id,
                chat_id,
                ref,
                queue_id=queue_id,
                message_id=picker_message_id,
            )
        except Exception:
            logger.exception("Failed to edit picker to building state")
            ctx.add_pending(request_id, chat_id, ref, queue_id=queue_id)
    elif update.message:
        msg = await update.message.reply_text(
            building_text,
            parse_mode="HTML",
            reply_markup=cancel_button,
        )
        ctx.add_pending(
            request_id,
            chat_id,
            ref,
            queue_id=queue_id,
            message_id=msg.message_id,
        )
    else:
        ctx.add_pending(request_id, chat_id, ref, queue_id=queue_id)
