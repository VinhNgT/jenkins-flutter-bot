"""Telegram handlers — slash commands + inline keyboards.

Provides:
  - /start, /help — welcome message
  - /build [ref] — branch picker or direct trigger if ref is supplied
  - /recent — recent builds with download links
  - /status — admin diagnostic (semi-technical, kept as-is)
  - Free-text handler for typed branch names during build sessions
"""

from __future__ import annotations

import html
import logging
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    LinkPreviewOptions,
)
from telegram.ext import ContextTypes

from ..build_client import BuildClientError
from .context import BotContext, _format_duration

logger = logging.getLogger(__name__)


def _bot_version() -> str:
    """Return the installed tg-jenkins-bot package version, or 'unknown'."""
    try:
        return _pkg_version("tg-jenkins-bot")
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
# JobQueue callbacks
# ---------------------------------------------------------------------------


async def _expire_picker_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback — proactively expire an idle picker.

    Delegates to :meth:`BotContext.expire_picker`, which is a no-op
    if the picker was already consumed (branch selected / build triggered).
    """
    job = context.job
    assert job is not None
    assert isinstance(job.data, dict)
    data: dict[str, int] = job.data
    ctx: BotContext = context.bot_data["bot_context"]
    await ctx.expire_picker(data["chat_id"], data["message_id"])


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
        "Use /build to trigger a build, or /recent to see past builds.\n"
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

    # Current pending builds
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
            ref = b.data.get("ref", "unknown")
            triggered_at = b.data.get("triggered_at", b.created_at)
            lines.append(
                f"  • <code>{_escape(ref)}</code>"
                f" (started {ctx.format_elapsed(triggered_at)})"
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
# /build [ref] command
# ---------------------------------------------------------------------------


async def build_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/build — show branch picker, or trigger directly if a ref is provided.

    Usage:
      /build          → shows the inline branch-picker keyboard
      /build main     → skips the picker and triggers main immediately
      /build feat/xyz → triggers the given branch directly
    """
    if not update.message or not update.effective_chat:
        return
    ctx = _get_ctx(context)

    if not await _ensure_authorized(update, context):
        return

    chat_id = update.effective_chat.id
    user = update.effective_user

    # If a branch name was supplied as an argument, trigger directly
    args = context.args or []
    if args:
        ref = " ".join(args).strip()
        if ref:
            await _trigger_build(update, context, ref)
            return

    # Check for active picker in this chat (one picker at a time)
    existing = ctx.has_active_picker(chat_id)
    if existing:
        if user and existing.user_id != user.id:
            picker_user = existing.data.get("user_name", "Someone")
            await update.message.reply_text(
                f"🔇 {_escape(picker_user)} is picking a branch right now.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                "☝️ You already have a branch picker open. "
                "Use it or wait for it to expire.",
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

    # Register picker with interaction tracker
    user_name = (user.first_name if user else "Someone") or "Someone"
    user_id = user.id if user else 0
    ctx.tracker.register(
        chat_id,
        msg.message_id,
        user_id,
        state="picking",
        data={"user_name": user_name},
    )

    # Schedule active expiry — proactively edit the picker to "expired"
    # when the TTL elapses. If the picker was already consumed (branch
    # selected, build triggered), expire_picker() is a safe no-op.
    if context.job_queue:
        context.job_queue.run_once(
            _expire_picker_job,
            when=ctx.tracker._picker_ttl,
            data={"chat_id": chat_id, "message_id": msg.message_id},
            name=f"expire_picker:{chat_id}:{msg.message_id}",
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

    # Find the awaiting_text picker for this chat
    picker = ctx.tracker.find_by_state(chat_id, "awaiting_text")
    if not picker:
        return

    # Only the user who started the session can type a branch name
    if update.effective_user.id != picker.user_id:
        return

    branch = (update.message.text or "").strip()
    if not branch:
        return

    # Remove the picker (session consumed)
    ctx.tracker.remove(chat_id, picker.message_id)

    # Trigger the build using the shared helper
    await _trigger_build(update, context, branch, picker.message_id)


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
    """Core build trigger logic — shared by branch picker and text input.

    Delegates the actual build trigger to the build-manager service via
    :class:`BuildClient`.  The bot only manages local Telegram state
    (interaction tracking, message editing).
    """
    assert update.effective_chat is not None
    ctx = _get_ctx(context)
    chat_id = update.effective_chat.id

    if not force:
        # Pending duplicate guard
        existing = ctx.find_building_for_branch(ref)
        if existing:
            triggered_at = existing.data.get("triggered_at", existing.created_at)
            elapsed = ctx.format_elapsed(triggered_at)
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
    else:
        # Force: cancel any pending build for this branch first
        existing = ctx.find_building_for_branch(ref)
        if existing:
            old_rid = existing.data.get("request_id", "")
            if old_rid:
                await ctx.build_client.cancel_build(old_rid)
            removed = ctx.tracker.remove(existing.chat_id, existing.message_id)
            if removed:
                await ctx.on_build_cancelled(removed)

    # Trigger build via build-manager
    try:
        result = await ctx.build_client.trigger_build(
            branch=ref,
            callback_url=ctx.config.bot_callback_url,
        )
    except BuildClientError as exc:
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

    request_id = result.get("request_id", "")

    # Send/edit the building message with cancel button
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
    building_text = ctx._msg_building()

    if picker_message_id:
        try:
            await context.bot.edit_message_text(
                building_text,
                chat_id=chat_id,
                message_id=picker_message_id,
                parse_mode="HTML",
                reply_markup=cancel_button,
            )
            ctx.tracker.register(
                chat_id,
                picker_message_id,
                user_id=0,
                state="building",
                data={
                    "ref": ref,
                    "request_id": request_id,
                    "triggered_at": ctx._clock(),
                },
            )
        except Exception:
            logger.exception("Failed to edit picker to building state")
    elif update.message:
        msg = await update.message.reply_text(
            building_text,
            parse_mode="HTML",
            reply_markup=cancel_button,
        )
        ctx.tracker.register(
            chat_id,
            msg.message_id,
            user_id=0,
            state="building",
            data={
                "ref": ref,
                "request_id": request_id,
                "triggered_at": ctx._clock(),
            },
        )
