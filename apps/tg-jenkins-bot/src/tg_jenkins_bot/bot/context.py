"""Bot context — Telegram-specific state shared between handlers.

This module manages the Telegram UI layer of the build lifecycle.
All build management (Jenkins, file storage, Git queries) is
delegated to the build-manager service via :class:`BuildClient`.

Owns:
  - Interaction tracking (via :class:`InteractionTracker`)
  - Telegram message formatting and editing
  - Build result notification rendering
"""

from __future__ import annotations

import html
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from .tracker import InteractionTracker, TrackedMessage

if TYPE_CHECKING:
    from ..config import BotSettings
    from ..build_client import BuildClient

logger = logging.getLogger(__name__)


def _escape(text: str) -> str:
    """Escape user-supplied text for safe inclusion in HTML messages."""
    return html.escape(text, quote=False)


def _format_time(ts: float) -> str:
    """Format a Unix timestamp as HH:MM in UTC."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M")


def _format_duration(start: float, end: float) -> str:
    """Format a duration between two timestamps as human-readable string."""
    delta = int(end - start)
    if delta < 60:
        return f"{delta}s"
    minutes = delta // 60
    return f"{minutes} min"


def _format_elapsed(ts: float) -> str:
    """Format elapsed time since a timestamp as a human-readable string."""
    delta = int(time.time() - ts)
    if delta < 60:
        return "just now"
    minutes = delta // 60
    if minutes == 1:
        return "1 min ago"
    return f"{minutes} min ago"


class BotContext:
    """Shared context between Telegram handlers.

    Owns:
    - Interaction tracking — every interactive message has an explicit
      state managed by :class:`InteractionTracker`
    - Message formatting and editing helpers
    - Notification rendering for build results

    Delegates to :class:`BuildClient` for all build operations (trigger,
    cancel, recent builds, status).
    """

    def __init__(
        self,
        config: BotSettings,
        build_client: BuildClient,
        bot: Bot | None,
    ) -> None:
        self.config = config
        self.build_client = build_client
        self.bot = bot
        self.tracker = InteractionTracker(picker_ttl=config.session_ttl)

    # ------------------------------------------------------------------
    # Admin contact helper
    # ------------------------------------------------------------------

    def _admin_hint(self) -> str:
        """Return a 'contact your admin' string, personalised if configured."""
        contact = self.config.admin_contact
        if contact:
            return f"Contact your admin ({_escape(contact)})."
        return "Contact your admin."

    def _msg_building(self) -> str:
        """The 'build in progress' message shown while Jenkins is working."""
        app_name = _escape(self.config.app_name)
        return f"🔨 <b>Building {app_name}...</b>\n\nI'll let you know when it's ready."

    # ------------------------------------------------------------------
    # Convenience: chat-level picker lock
    # ------------------------------------------------------------------

    def has_active_picker(self, chat_id: int) -> TrackedMessage | None:
        """Check if there's an active picker in this chat.

        Returns the tracked picker message, or None.  Used by
        ``/build`` to enforce one picker per chat at a time.
        """
        picking = self.tracker.find_by_state(chat_id, "picking")
        if picking:
            return picking
        return self.tracker.find_by_state(chat_id, "awaiting_text")

    # ------------------------------------------------------------------
    # Convenience: build queries
    # ------------------------------------------------------------------

    def find_building_for_branch(self, ref: str) -> TrackedMessage | None:
        """Find an active build for a branch (any chat)."""
        for msg in self.tracker.list_by_state("building"):
            if msg.data.get("ref") == ref:
                return msg
        return None

    def list_building(self) -> list[TrackedMessage]:
        """All currently building messages."""
        return self.tracker.list_by_state("building")

    def consume_building(self, request_id: str) -> TrackedMessage | None:
        """Find and remove a building message by request_id.

        Atomic — only one caller gets the message.  Used by the
        webhook callback route to process build results.
        """
        msg = self.tracker.find_by_data("request_id", request_id)
        if msg and msg.state == "building":
            return self.tracker.remove(msg.chat_id, msg.message_id)
        return None

    # ------------------------------------------------------------------
    # Build result handlers (called by webhook callback route)
    # ------------------------------------------------------------------

    async def _edit_build_message(
        self,
        msg: TrackedMessage,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        """Edit the in-chat build message if we have its ID.

        Best-effort — failures are logged but never propagated.
        """
        if not self.bot:
            return
        try:
            await self.bot.edit_message_text(
                text,
                chat_id=msg.chat_id,
                message_id=msg.message_id,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except Exception:
            logger.exception("Failed to edit build message %d", msg.message_id)

    async def on_build_success(
        self,
        msg: TrackedMessage,
        result: dict,
    ) -> None:
        """Handle successful build — notify user with download link."""
        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            return

        triggered_at = msg.data.get("triggered_at", time.time())
        duration = _format_duration(triggered_at, time.time())
        download_url = result.get("download_url", "")
        ref = msg.data.get("ref", "unknown")

        app_name = _escape(self.config.app_name)
        text = (
            f"✅ <b>{app_name} is ready!</b>\n"
            f"\n"
            f"Built from <code>{_escape(ref)}</code> in {duration}."
        )

        reply_markup = None
        if download_url:
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📲 Download APK", url=download_url)]]
            )

        await self._edit_build_message(msg, text, reply_markup)
        await self.bot.send_message(
            msg.chat_id,
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    async def on_build_failure(
        self,
        msg: TrackedMessage,
        result: dict,
    ) -> None:
        """Handle failed build — notify user."""
        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            return

        ref = msg.data.get("ref", "unknown")
        app_name = _escape(self.config.app_name)
        text = (
            f"❌ <b>{app_name} build failed</b>\n"
            f"\n"
            f"Something went wrong on <code>{_escape(ref)}</code>.\n"
            f"{self._admin_hint()}"
        )

        await self._edit_build_message(msg, text)
        await self.bot.send_message(
            msg.chat_id,
            text,
            parse_mode="HTML",
        )

    async def on_build_timeout(
        self,
        msg: TrackedMessage,
        result: dict,
    ) -> None:
        """Handle timed-out build — notify user."""
        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            return

        ref = msg.data.get("ref", "unknown")
        app_name = _escape(self.config.app_name)
        text = (
            f"⏰ <b>{app_name} build timed out</b>\n"
            f"\n"
            f"The build on <code>{_escape(ref)}</code>"
            f" didn't complete in time.\n"
            f"{self._admin_hint()}"
        )

        await self._edit_build_message(msg, text)
        await self.bot.send_message(
            msg.chat_id,
            text,
            parse_mode="HTML",
        )

    async def on_build_cancelled(
        self,
        msg: TrackedMessage,
    ) -> None:
        """Notify the build's chat that a build was cancelled."""
        if not self.bot:
            return

        ref = msg.data.get("ref", "unknown")
        text = f"🚫 Build on <code>{_escape(ref)}</code> was cancelled."

        await self._edit_build_message(msg, text)
        await self.bot.send_message(
            msg.chat_id,
            text,
            parse_mode="HTML",
        )
