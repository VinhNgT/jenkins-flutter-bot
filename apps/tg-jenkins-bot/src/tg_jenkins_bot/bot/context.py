"""Bot context — Telegram-specific state shared between handlers.

This module manages the Telegram UI layer of the build lifecycle.
All build management (Jenkins, file storage, Git queries) is
delegated to the build-manager service via :class:`BuildClient`.

Owns:
  - Pending build tracking (request_id → chat_id/message_id mapping)
  - Build session management (interactive branch picker locking)
  - Telegram message formatting and editing
  - Build result notification rendering
"""

from __future__ import annotations

import html
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from ..config import BotSettings
    from ..build_client import BuildClient

logger = logging.getLogger(__name__)


@dataclass
class BuildSession:
    """Ephemeral session for the branch-picking phase.

    Prevents two users from using the build flow simultaneously
    in a group chat.  Not persisted — expires on restart.
    """

    chat_id: int
    user_id: int
    user_name: str
    message_id: int
    started_at: float
    state: str  # "picking" | "awaiting_text"


@dataclass(frozen=True)
class PendingBuild:
    """Tracks a build triggered via Telegram.

    This is a Telegram-side record that maps ``request_id`` to the
    originating chat and message for inline editing.  The canonical
    build state lives in the build-manager service.
    """

    request_id: str
    chat_id: int
    ref: str
    triggered_at: float
    message_id: int | None = None  # for editing the build message inline


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
    - Telegram-side pending build tracking (request_id → chat_id/message_id)
    - Build session management (interactive lock for branch picking)
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
        self._pending: dict[str, PendingBuild] = {}
        self._sessions: dict[int, BuildSession] = {}

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
    # Build session (interactive lock for branch picking)
    # ------------------------------------------------------------------

    def start_session(
        self,
        chat_id: int,
        user_id: int,
        user_name: str,
        message_id: int,
    ) -> BuildSession:
        """Start a new branch-picking session for a chat."""
        session = BuildSession(
            chat_id=chat_id,
            user_id=user_id,
            user_name=user_name,
            message_id=message_id,
            started_at=time.time(),
            state="picking",
        )
        self._sessions[chat_id] = session
        return session

    def get_session(self, chat_id: int) -> BuildSession | None:
        """Return the active session for a chat, or None if expired/missing."""
        session = self._sessions.get(chat_id)
        if session is None:
            return None
        if time.time() - session.started_at > self.config.session_ttl:
            del self._sessions[chat_id]
            return None
        return session

    def clear_session(self, chat_id: int) -> None:
        """Remove the session for a chat."""
        self._sessions.pop(chat_id, None)

    # ------------------------------------------------------------------
    # Pending build tracking (Telegram-side only)
    # ------------------------------------------------------------------

    @property
    def pending_count(self) -> int:
        """Number of pending builds currently tracked."""
        return len(self._pending)

    def add_pending(
        self,
        request_id: str,
        chat_id: int,
        ref: str,
        *,
        message_id: int | None = None,
    ) -> None:
        """Track a Telegram-triggered build."""
        self._pending[request_id] = PendingBuild(
            request_id=request_id,
            chat_id=chat_id,
            ref=ref,
            triggered_at=time.time(),
            message_id=message_id,
        )

    def get_pending(self, request_id: str) -> PendingBuild:
        """Look up a pending build by request_id. Raises KeyError if not found."""
        return self._pending[request_id]

    def list_pending(self) -> dict[str, PendingBuild]:
        """Return a snapshot of all pending builds."""
        return dict(self._pending)

    def consume_pending(self, request_id: str | None) -> PendingBuild | None:
        """Look up and remove a pending build. Returns None if not found."""
        if not request_id:
            return None
        return self._pending.pop(request_id, None)

    def find_pending_for_branch(self, ref: str) -> tuple[str, PendingBuild] | None:
        """Find a pending build for the given branch.

        Returns ``(request_id, pending_build)`` or ``None``.
        """
        for request_id, pending in self._pending.items():
            if pending.ref == ref:
                return request_id, pending
        return None

    # ------------------------------------------------------------------
    # Build result handlers (called by callback route)
    # ------------------------------------------------------------------

    async def _edit_build_message(
        self,
        pending: PendingBuild,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        """Edit the in-chat build message if we have its ID.

        Best-effort — failures are logged but never propagated.
        """
        if not self.bot or not pending.message_id:
            return
        try:
            await self.bot.edit_message_text(
                text,
                chat_id=pending.chat_id,
                message_id=pending.message_id,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except Exception:
            logger.exception("Failed to edit build message %d", pending.message_id)

    async def on_build_success(
        self,
        pending: PendingBuild,
        result: dict,
    ) -> None:
        """Handle successful build — notify user with download link."""
        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            return

        now = time.time()
        duration = _format_duration(pending.triggered_at, now)
        download_url = result.get("download_url", "")

        app_name = _escape(self.config.app_name)
        text = (
            f"✅ <b>{app_name} is ready!</b>\n"
            f"\n"
            f"Built from <code>{_escape(pending.ref)}</code> in {duration}."
        )

        reply_markup = None
        if download_url:
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📲 Download APK", url=download_url)]]
            )

        await self._edit_build_message(pending, text, reply_markup)
        await self.bot.send_message(
            pending.chat_id,
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    async def on_build_failure(
        self,
        pending: PendingBuild,
        result: dict,
    ) -> None:
        """Handle failed build — notify user."""
        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            return

        app_name = _escape(self.config.app_name)
        text = (
            f"❌ <b>{app_name} build failed</b>\n"
            f"\n"
            f"Something went wrong on <code>{_escape(pending.ref)}</code>.\n"
            f"{self._admin_hint()}"
        )

        await self._edit_build_message(pending, text)
        await self.bot.send_message(
            pending.chat_id,
            text,
            parse_mode="HTML",
        )

    async def on_build_timeout(
        self,
        pending: PendingBuild,
        result: dict,
    ) -> None:
        """Handle timed-out build — notify user."""
        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            return

        app_name = _escape(self.config.app_name)
        text = (
            f"⏰ <b>{app_name} build timed out</b>\n"
            f"\n"
            f"The build on <code>{_escape(pending.ref)}</code>"
            f" didn't complete in time.\n"
            f"{self._admin_hint()}"
        )

        await self._edit_build_message(pending, text)
        await self.bot.send_message(
            pending.chat_id,
            text,
            parse_mode="HTML",
        )

    async def on_build_cancelled(
        self,
        pending: PendingBuild,
    ) -> None:
        """Notify the build's chat that a build was cancelled."""
        if not self.bot:
            return

        text = f"🚫 Build on <code>{_escape(pending.ref)}</code> was cancelled."

        await self._edit_build_message(pending, text)
        await self.bot.send_message(
            pending.chat_id,
            text,
            parse_mode="HTML",
        )
