"""Bot context — Telegram-specific state shared between handlers.

All build management (Jenkins, file storage, Git queries) is
delegated to the build-manager service via :class:`BuildClient`.
"""

from __future__ import annotations

import html
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .protocols import BotLike
from .store import ActiveBuildStore, ActiveBuild

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


class BotContext:
    """Shared context between Telegram handlers.

    Owns:
    - Active build store mapping request_id -> ActiveBuild
    - Notification rendering for build results

    Delegates to :class:`BuildClient` for all build operations (trigger,
    cancel, recent builds, status).
    """

    def __init__(
        self,
        config: BotSettings,
        build_client: BuildClient,
        bot: BotLike | None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.build_client = build_client
        self.bot = bot
        self._clock = clock
        self.store = ActiveBuildStore(clock=clock)

    # ------------------------------------------------------------------
    # Time formatting
    # ------------------------------------------------------------------

    def format_elapsed(self, ts: float) -> str:
        """Format elapsed time since *ts* as a human-readable string."""
        delta = int(self._clock() - ts)
        if delta < 60:
            return "just now"
        minutes = delta // 60
        if minutes == 1:
            return "1 min ago"
        return f"{minutes} min ago"

    # ------------------------------------------------------------------
    # Admin contact helper
    # ------------------------------------------------------------------

    def _admin_hint(self) -> str:
        """Return a 'contact your admin' string, personalised if configured."""
        contact = self.config.admin_contact
        if contact:
            return f"Contact your admin ({_escape(contact)})."
        return "Contact your admin."

    # ------------------------------------------------------------------
    # Convenience: build queries
    # ------------------------------------------------------------------

    def list_building(self) -> list[ActiveBuild]:
        """All currently active builds."""
        return self.store.list_active()

    def consume_building(self, request_id: str) -> ActiveBuild | None:
        """Find and remove an active build by request_id."""
        return self.store.consume(request_id)

    # ------------------------------------------------------------------
    # Build result handlers (called by webhook callback route)
    # ------------------------------------------------------------------

    async def on_build_success(self, build: ActiveBuild, result: dict) -> None:
        """Handle successful build — notify user with download link."""
        if not self.bot or not build.notify:
            return
        duration = _format_duration(build.triggered_at, self._clock())
        download_url = result.get("download_url", "")
        app_name = _escape(self.config.app_name)
        label = _escape(build.label)

        lines = [f"✅ <b>{app_name} {label} is ready!</b>", ""]
        lines.append(f"📦 Branch: <code>{_escape(build.ref)}</code>")
        commit = result.get("commit_hash", "")
        if commit:
            lines.append(f"🔖 Commit: <code>{_escape(commit[:7])}</code>")
        lines.append(f"⏱ Duration: {duration}")
        lines.append(f"👤 Triggered by: {_escape(build.triggered_by)}")
        text = "\n".join(lines) + "\n"

        # Telegram inline keyboard buttons require publicly-reachable HTTPS
        # URLs. Non-HTTPS URLs (e.g. internal Docker hostnames from the
        # ephemeral storage backend in mock/dev) are rejected by the
        # Telegram API. Only attach the download button when the URL is
        # valid for Telegram.
        reply_markup = None
        if download_url and download_url.startswith("https://"):
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📥 Download APK", url=download_url)]]
            )
        await self.bot.send_message(
            build.chat_id,
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    async def on_build_failure(self, build: ActiveBuild, result: dict) -> None:
        """Handle failed build — notify user."""
        if not self.bot or not build.notify:
            return
        app_name = _escape(self.config.app_name)
        label = _escape(build.label)
        duration = _format_duration(build.triggered_at, self._clock())

        lines = [f"❌ <b>{app_name} {label} build failed</b>", ""]
        lines.append(f"📦 Branch: <code>{_escape(build.ref)}</code>")
        commit = result.get("commit_hash", "")
        if commit:
            lines.append(f"🔖 Commit: <code>{_escape(commit[:7])}</code>")
        lines.append(f"⏱ Duration: {duration}")
        lines.append(f"👤 Triggered by: {_escape(build.triggered_by)}")
        lines.append("")
        lines.append(f"<i>{self._admin_hint()} for build logs.</i>")
        text = "\n".join(lines)

        await self.bot.send_message(build.chat_id, text, parse_mode="HTML")

    async def on_build_timeout(self, build: ActiveBuild, result: dict) -> None:
        """Handle timed-out build — notify user."""
        if not self.bot or not build.notify:
            return
        app_name = _escape(self.config.app_name)
        label = _escape(build.label)

        duration = _format_duration(build.triggered_at, self._clock())
        lines = [f"⏰ <b>{app_name} {label} build timed out</b>", ""]
        lines.append(f"📦 Branch: <code>{_escape(build.ref)}</code>")
        lines.append(f"⏱ Waited: {duration}")
        lines.append(f"👤 Triggered by: {_escape(build.triggered_by)}")
        lines.append("")
        lines.append(f"<i>The build exceeded its time limit. {self._admin_hint()}</i>")
        text = "\n".join(lines)

        await self.bot.send_message(build.chat_id, text, parse_mode="HTML")

    async def on_build_cancelled(
        self, build: ActiveBuild, cancelled_by: str | None = None
    ) -> None:
        """Handle cancelled build — notify user."""
        if not self.bot or not build.notify:
            return
        app_name = _escape(self.config.app_name)
        label = _escape(build.label)

        lines = [f"🛑 <b>{app_name} {label} build cancelled</b>", ""]
        lines.append(f"📦 Branch: <code>{_escape(build.ref)}</code>")
        if cancelled_by:
            lines.append(f"👤 Cancelled by: {_escape(cancelled_by)}")
        text = "\n".join(lines)

        await self.bot.send_message(build.chat_id, text, parse_mode="HTML")
