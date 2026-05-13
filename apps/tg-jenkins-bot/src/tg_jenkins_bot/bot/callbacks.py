"""Inline button callback router for Telegram bot.

Dispatches ``CallbackQuery`` events based on ``callback_data`` prefix.
All interactive states (branch picker, cancel confirm, rebuild confirm)
are handled here via in-place message editing.

Entry points are /build and /recent slash commands (see handlers.py).
"""

from __future__ import annotations

import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .context import BotContext, _format_elapsed
from .handlers import _trigger_build

logger = logging.getLogger(__name__)


def _get_ctx(context: ContextTypes.DEFAULT_TYPE) -> BotContext:
    """Retrieve the shared BotContext from bot_data."""
    return context.bot_data["bot_context"]


def _escape(text: str) -> str:
    """Escape user-supplied text for safe inclusion in HTML messages."""
    return html.escape(text, quote=False)


# ---------------------------------------------------------------------------
# Main callback router
# ---------------------------------------------------------------------------


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch incoming callback queries by data prefix."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()  # Telegram requires this to dismiss the spinner

    data = query.data

    if data.startswith("build:branch:"):
        await _on_branch_selected(update, context, data)
    elif data == "build:custom":
        await _on_custom_branch(update, context)
    elif data.startswith("build:confirm_cancel_rebuild:"):
        await _on_confirm_cancel_rebuild(update, context, data)
    elif data.startswith("build:do_cancel_rebuild:"):
        await _on_do_cancel_rebuild(update, context, data)
    elif data.startswith("build:back_to_inprog:"):
        await _on_back_to_inprog(update, context, data)
    elif data.startswith("cancel:confirm:"):
        await _on_confirm_cancel(update, context, data)
    elif data.startswith("cancel:back:"):
        await _on_back_to_building(update, context, data)
    elif data.startswith("cancel:"):
        await _on_cancel(update, context, data)
    else:
        logger.warning("Unknown callback_data: %s", data)


# ---------------------------------------------------------------------------
# Branch selection
# ---------------------------------------------------------------------------


async def _on_branch_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """User tapped a branch button in the picker."""
    assert update.callback_query is not None
    ctx = _get_ctx(context)
    chat_id = update.effective_chat.id if update.effective_chat else 0

    branch = data.removeprefix("build:branch:")
    ctx.clear_session(chat_id)

    msg_id = (
        update.callback_query.message.message_id
        if update.callback_query.message
        else None
    )
    await _trigger_build(update, context, branch, msg_id)


async def _on_custom_branch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User tapped '✏️ Type a name' — switch session to awaiting_text."""
    assert update.callback_query is not None
    ctx = _get_ctx(context)
    chat_id = update.effective_chat.id if update.effective_chat else 0

    session = ctx.get_session(chat_id)
    if not session:
        try:
            await update.callback_query.edit_message_text(
                "⏳ Session expired. Tap 🔨 Build to try again."
            )
        except Exception:
            logger.exception("Failed to edit expired session message")
        return

    session.state = "awaiting_text"

    try:
        await update.callback_query.edit_message_text("✏️ Type the branch name:")
    except Exception:
        logger.exception("Failed to edit message for custom branch")


# ---------------------------------------------------------------------------
# Cancel-and-rebuild confirmation
# ---------------------------------------------------------------------------


async def _on_confirm_cancel_rebuild(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Two-step: show confirmation for 'Cancel and rebuild'."""
    assert update.callback_query is not None
    ref = data.removeprefix("build:confirm_cancel_rebuild:")

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Yes, do it",
                    callback_data=f"build:do_cancel_rebuild:{ref}",
                ),
                InlineKeyboardButton(
                    "↩️ Go back",
                    callback_data=f"build:back_to_inprog:{ref}",
                ),
            ],
        ]
    )

    try:
        await update.callback_query.edit_message_text(
            f"⚠️ Cancel the current build on <code>{_escape(ref)}</code>"
            " and start a new one?",
            parse_mode="HTML",
            reply_markup=buttons,
        )
    except Exception:
        logger.exception("Failed to show cancel-rebuild confirmation")


async def _on_do_cancel_rebuild(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Execute: cancel old build + trigger new one (force)."""
    assert update.callback_query is not None
    ref = data.removeprefix("build:do_cancel_rebuild:")
    msg_id = (
        update.callback_query.message.message_id
        if update.callback_query.message
        else None
    )
    await _trigger_build(update, context, ref, msg_id, force=True)


async def _on_back_to_inprog(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Restore the in-progress message (go back from confirm)."""
    assert update.callback_query is not None
    ctx = _get_ctx(context)
    ref = data.removeprefix("build:back_to_inprog:")

    match = ctx.find_pending_for_branch(ref)
    elapsed = ""
    if match:
        _, existing_pending = match
        elapsed = f" (started {_format_elapsed(existing_pending.triggered_at)})"

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

    try:
        await update.callback_query.edit_message_text(
            f"⚠️ A build is already running on <code>{_escape(ref)}</code>{elapsed}.",
            parse_mode="HTML",
            reply_markup=buttons,
        )
    except Exception:
        logger.exception("Failed to restore in-progress message")


# ---------------------------------------------------------------------------
# Cancel build
# ---------------------------------------------------------------------------


async def _on_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Two-step: show confirmation for cancelling a build."""
    assert update.callback_query is not None
    # data format: "cancel:<request_id>"
    request_id = data.removeprefix("cancel:")

    # Avoid double-processing confirm/back sub-routes
    if request_id.startswith("confirm:") or request_id.startswith("back:"):
        return

    ctx = _get_ctx(context)
    try:
        pending = ctx.get_pending(request_id)
    except KeyError:
        try:
            await update.callback_query.edit_message_text(
                "This build is no longer active."
            )
        except Exception:
            logger.exception("Failed to edit stale cancel button")
        return

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Yes, cancel it",
                    callback_data=f"cancel:confirm:{request_id}",
                ),
                InlineKeyboardButton(
                    "↩️ Go back",
                    callback_data=f"cancel:back:{request_id}",
                ),
            ],
        ]
    )

    try:
        await update.callback_query.edit_message_text(
            f"⚠️ Cancel the build on <code>{_escape(pending.ref)}</code>?",
            parse_mode="HTML",
            reply_markup=buttons,
        )
    except Exception:
        logger.exception("Failed to show cancel confirmation")


async def _on_confirm_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Execute: cancel the build via build-manager."""
    assert update.callback_query is not None
    request_id = data.removeprefix("cancel:confirm:")
    ctx = _get_ctx(context)

    pending = ctx.consume_pending(request_id)
    if not pending:
        try:
            await update.callback_query.edit_message_text(
                "This build is no longer active."
            )
        except Exception:
            logger.exception("Failed to edit stale cancel confirm")
        return

    # Cancel via build-manager (best-effort)
    try:
        await ctx.build_client.cancel_build(request_id)
    except Exception:
        logger.exception("Failed to cancel build via build-manager")

    try:
        await update.callback_query.edit_message_text(
            f"🚫 Build on <code>{_escape(pending.ref)}</code> was cancelled.",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Failed to edit message to cancelled state")


async def _on_back_to_building(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Restore the building message (go back from cancel confirm)."""
    assert update.callback_query is not None
    request_id = data.removeprefix("cancel:back:")
    ctx = _get_ctx(context)

    try:
        ctx.get_pending(request_id)
    except KeyError:
        try:
            await update.callback_query.edit_message_text(
                "This build is no longer active."
            )
        except Exception:
            logger.exception("Failed to edit stale cancel back")
        return

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

    try:
        await update.callback_query.edit_message_text(
            ctx._msg_building(),
            parse_mode="HTML",
            reply_markup=cancel_button,
        )
    except Exception:
        logger.exception("Failed to restore building message")
