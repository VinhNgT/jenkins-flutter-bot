"""Inline button callback router for Telegram bot.

Dispatches ``CallbackQuery`` events based on ``callback_data`` prefix
**and** the tracked message's current state.  Every callback is validated
against the interaction tracker before being processed.  Invalid
transitions (double-taps, stale pickers, orphaned buttons) are rejected
at the router level — individual handlers never see them.

Entry points are /build and /recent slash commands (see handlers.py).
"""

from __future__ import annotations

import html
import logging

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
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
    """Dispatch incoming callback queries by data prefix + message state.

    Every callback is looked up in the interaction tracker.  If the
    message isn't tracked or is in the wrong state, the callback is
    rejected with an appropriate user-facing message.
    """
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()  # Telegram requires this to dismiss the spinner

    data = query.data
    ctx = _get_ctx(context)
    chat_id = update.effective_chat.id if update.effective_chat else 0
    msg_id = (
        query.message.message_id
        if query.message
        else 0
    )

    # Look up the message in the tracker
    tracked = ctx.tracker.get(chat_id, msg_id)

    # -- Branch picker actions (require state=picking) --

    if data.startswith("build:branch:"):
        if not tracked or tracked.state != "picking":
            await ctx.expire_picker(chat_id, msg_id)
            return
        # Atomic transition: picking → consumed.  Only one tap wins.
        if not ctx.tracker.transition(chat_id, msg_id, "picking", "consumed"):
            return  # another tap already won the race
        branch = data.removeprefix("build:branch:")
        await _trigger_build(update, context, branch, msg_id)
        # Clean up the consumed tracker entry — _trigger_build registers
        # a new "building" entry for this message_id if successful.
        # If _trigger_build showed a duplicate warning instead, the
        # consumed entry is just stale and will be ignored.
        return

    if data == "build:custom":
        if not tracked or tracked.state != "picking":
            await ctx.expire_picker(chat_id, msg_id)
            return
        # Atomic transition: picking → awaiting_text
        if not ctx.tracker.transition(chat_id, msg_id, "picking", "awaiting_text"):
            return
        try:
            await query.edit_message_text("✏️ Type the branch name:")
        except Exception:
            logger.exception("Failed to edit message for custom branch")
        return

    # -- Cancel build actions (require state=building) --

    if data.startswith("cancel:") and not data.startswith("cancel:confirm:") and not data.startswith("cancel:back:"):
        request_id = data.removeprefix("cancel:")
        if not tracked or tracked.state != "building":
            await _show_stale(query)
            return
        # Atomic transition: building → confirming_cancel
        if not ctx.tracker.transition(chat_id, msg_id, "building", "confirming_cancel"):
            return

        ref = tracked.data.get("ref", "unknown")
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
            await query.edit_message_text(
                f"⚠️ Cancel the build on <code>{_escape(ref)}</code>?",
                parse_mode="HTML",
                reply_markup=buttons,
            )
        except Exception:
            logger.exception("Failed to show cancel confirmation")
        return

    if data.startswith("cancel:confirm:"):
        request_id = data.removeprefix("cancel:confirm:")
        if not tracked or tracked.state != "confirming_cancel":
            await _show_stale(query)
            return
        # Atomic transition: confirming_cancel → done
        result = ctx.tracker.transition(chat_id, msg_id, "confirming_cancel", "done")
        if not result:
            return

        # Remove from tracker
        ctx.tracker.remove(chat_id, msg_id)

        # Cancel via build-manager (best-effort)
        try:
            await ctx.build_client.cancel_build(request_id)
        except Exception:
            logger.exception("Failed to cancel build via build-manager")

        ref = tracked.data.get("ref", "unknown")
        try:
            await query.edit_message_text(
                f"🚫 Build on <code>{_escape(ref)}</code> was cancelled.",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Failed to edit message to cancelled state")
        return

    if data.startswith("cancel:back:"):
        request_id = data.removeprefix("cancel:back:")
        if not tracked or tracked.state != "confirming_cancel":
            await _show_stale(query)
            return
        # Atomic transition: confirming_cancel → building
        if not ctx.tracker.transition(chat_id, msg_id, "confirming_cancel", "building"):
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
            await query.edit_message_text(
                ctx._msg_building(),
                parse_mode="HTML",
                reply_markup=cancel_button,
            )
        except Exception:
            logger.exception("Failed to restore building message")
        return

    # -- Cancel-and-rebuild actions --

    if data.startswith("build:confirm_cancel_rebuild:"):
        ref = data.removeprefix("build:confirm_cancel_rebuild:")
        # This button appears on untracked "duplicate warning" messages.
        # No state validation needed — the action is idempotent.
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
            await query.edit_message_text(
                f"⚠️ Cancel the current build on <code>{_escape(ref)}</code>"
                " and start a new one?",
                parse_mode="HTML",
                reply_markup=buttons,
            )
        except Exception:
            logger.exception("Failed to show cancel-rebuild confirmation")
        return

    if data.startswith("build:do_cancel_rebuild:"):
        ref = data.removeprefix("build:do_cancel_rebuild:")
        await _trigger_build(update, context, ref, msg_id, force=True)
        return

    if data.startswith("build:back_to_inprog:"):
        ref = data.removeprefix("build:back_to_inprog:")
        existing = ctx.find_building_for_branch(ref)
        elapsed = ""
        if existing:
            triggered_at = existing.data.get("triggered_at", existing.created_at)
            elapsed = f" (started {_format_elapsed(triggered_at)})"

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
            await query.edit_message_text(
                f"⚠️ A build is already running on <code>{_escape(ref)}</code>{elapsed}.",
                parse_mode="HTML",
                reply_markup=buttons,
            )
        except Exception:
            logger.exception("Failed to restore in-progress message")
        return

    logger.warning("Unknown callback_data: %s", data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------




async def _show_stale(query: CallbackQuery) -> None:
    """Edit a stale action button to 'no longer active'."""
    try:
        await query.edit_message_text(
            "This build is no longer active."
        )
    except Exception:
        pass

