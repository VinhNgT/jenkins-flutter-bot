"""Bot context — shared state between Telegram handlers and webhook."""

from __future__ import annotations

import html
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from ..config import Config
    from ..drive.uploader import DriveUploader
    from ..git.remote import GitRemoteClient
    from ..jenkins.client import JenkinsClient

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert a display name to a safe filename prefix.

    'Tendoo Mall' -> 'tendoo-mall'
    'my_app'      -> 'my-app'
    """
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "build"




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
    """Tracks a build triggered via Telegram."""

    chat_id: int
    ref: str
    triggered_at: float
    queue_id: int | None = (
        None  # stored at trigger time; used to cancel via Jenkins API
    )
    message_id: int | None = None  # for editing the build message inline


@dataclass(frozen=True)
class TrackedBuild:
    """Record of a bot-triggered build, stored locally for /recent and Drive cleanup.

    All fields are captured at webhook time — the data originates from Jenkins
    (via webhook callback) but is persisted locally so the bot can serve
    /recent and /status even when Jenkins is unreachable.
    """

    request_id: str
    ref: str
    commit_hash: str
    result: str  # "success" or "failure"
    triggered_at: float
    completed_at: float
    drive_file_id: str = ""
    drive_link: str = ""


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


def _summarize_logs(logs: str, *, max_lines: int = 3) -> str:
    """Extract the first meaningful error lines from raw build logs.

    Skips blank lines and common boilerplate to find the most useful
    error messages for display in a Telegram notification.
    Returns up to `max_lines` meaningful lines.
    """
    skip_prefixes = (
        "[INFO]",
        "Downloading",
        "Download",
        "Note:",
        "> Task",
        "BUILD SUCCESSFUL",
        "Picked up",
        "Running ",
        "Starting ",
        "Cloning ",
        "Checking out",
        "using credential",
    )

    meaningful: list[str] = []
    for line in logs.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(prefix) for prefix in skip_prefixes):
            continue
        # Cap each line at 200 chars
        if len(stripped) > 200:
            stripped = stripped[:197] + "..."
        meaningful.append(stripped)
        if len(meaningful) >= max_lines:
            break

    return "\n".join(meaningful) if meaningful else "No details available."


class BotContext:
    """Shared context between Telegram handlers and the webhook server.

    Owns:
    - Pending build tracking (request_id → chat_id mapping)
    - Tracked build registry (enriched with webhook metadata for /recent)
    - Build result handling (Drive upload + Telegram notification)
    - Drive file retention enforcement (max_recent_builds)
    - Pending build validation against Jenkins (detect cancelled/deleted builds)
    """

    def __init__(
        self,
        config: Config,
        jenkins: JenkinsClient,
        drive: DriveUploader,
        bot: Bot | None,
        git_remote: GitRemoteClient | None = None,
    ) -> None:
        self.config = config
        self.jenkins = jenkins
        self.drive = drive
        self.bot = bot
        self.git_remote = git_remote
        self._pending_path = Path("data/pending_builds.json")
        self._pending: dict[str, PendingBuild] = self._load_pending()
        self._tracked_path = Path("data/tracked_builds.json")
        self._tracked: list[TrackedBuild] = self._load_tracked()
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
    # Pending build tracking (persisted to JSON)
    # ------------------------------------------------------------------

    @property
    def pending_count(self) -> int:
        """Number of pending builds currently tracked."""
        return len(self._pending)

    def _load_pending(self) -> dict[str, PendingBuild]:
        """Load pending builds from disk on startup."""
        if not self._pending_path.exists():
            return {}
        try:
            data = json.loads(self._pending_path.read_text())
            return {k: PendingBuild(**v) for k, v in data.items()}
        except Exception:
            logger.exception("Failed to load pending builds")
            return {}

    def _save_pending(self) -> None:
        """Persist pending builds to disk."""
        self._pending_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            k: {
                "chat_id": v.chat_id,
                "ref": v.ref,
                "triggered_at": v.triggered_at,
                "queue_id": v.queue_id,
                "message_id": v.message_id,
            }
            for k, v in self._pending.items()
        }
        self._pending_path.write_text(json.dumps(data))

    def add_pending(
        self,
        request_id: str,
        chat_id: int,
        ref: str,
        *,
        queue_id: int | None = None,
        message_id: int | None = None,
    ) -> None:
        """Track a Telegram-triggered build."""
        self._cleanup_expired()
        self._pending[request_id] = PendingBuild(
            chat_id=chat_id,
            ref=ref,
            triggered_at=time.time(),
            queue_id=queue_id,
            message_id=message_id,
        )
        self._save_pending()

    def get_pending(self, request_id: str) -> PendingBuild:
        """Look up a pending build by request_id. Raises KeyError if not found."""
        return self._pending[request_id]

    def list_pending(self) -> dict[str, PendingBuild]:
        """Return a snapshot of all pending builds."""
        self._cleanup_expired()
        return dict(self._pending)

    def consume_pending(self, request_id: str | None) -> PendingBuild | None:
        """Look up and remove a pending build. Returns None if not found."""
        if not request_id:
            return None
        self._cleanup_expired()
        result = self._pending.pop(request_id, None)
        if result:
            self._save_pending()
        return result

    async def cancel_pending(self, request_id: str) -> None:
        """Cancel a pending build — stop Jenkins and remove from tracking.

        Best-effort Jenkins cancellation: errors are logged but never
        propagated, so the bot-side tracking is always cleaned up.
        """
        pending = self._pending.pop(request_id, None)
        if not pending:
            return
        self._save_pending()

        # Attempt to cancel the Jenkins build
        if pending.queue_id is not None:
            try:
                await self.jenkins.cancel_build(pending.queue_id)
            except Exception:
                logger.exception(
                    "Failed to cancel Jenkins build (queue_id=%d)",
                    pending.queue_id,
                )

    def _cleanup_expired(self) -> list[tuple[str, PendingBuild]]:
        """Remove pending builds older than TTL. Returns expired builds."""
        timeout_seconds = self.config.build_timeout * 60
        if timeout_seconds <= 0:
            return []

        now = time.time()
        expired = [
            (request_id, pending)
            for request_id, pending in self._pending.items()
            if now - pending.triggered_at > timeout_seconds
        ]
        for request_id, _pending in expired:
            del self._pending[request_id]
        if expired:
            self._save_pending()
        return expired

    async def cleanup_expired_with_notification(self) -> None:
        """Remove expired pending builds and notify users about timeouts."""
        expired = self._cleanup_expired()
        if not expired or not self.bot:
            return

        timeout_min = self.config.build_timeout
        for _rid, pending in expired:
            try:
                app_name = _escape(self.config.app_name)
                text = (
                    f"⏰ <b>{app_name} build timed out</b>\n"
                    "\n"
                    f"The build on <code>{_escape(pending.ref)}</code>"
                    f" didn't complete within {timeout_min} minutes.\n"
                    f"{self._admin_hint()}"
                )
                # Edit the build message if we have one
                if pending.message_id:
                    try:
                        await self.bot.edit_message_text(
                            text,
                            chat_id=pending.chat_id,
                            message_id=pending.message_id,
                            parse_mode="HTML",
                        )
                    except Exception:
                        logger.exception("Failed to edit timed-out build message")
                # Always send a new message for mobile notification
                await self.bot.send_message(
                    pending.chat_id,
                    text,
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception("Failed to notify about timed-out build")

    # ------------------------------------------------------------------
    # Tracked build registry (persisted to JSON)
    # ------------------------------------------------------------------

    @property
    def tracked_count(self) -> int:
        """Number of tracked builds."""
        return len(self._tracked)

    def _load_tracked(self) -> list[TrackedBuild]:
        """Load tracked builds from disk on startup."""
        if not self._tracked_path.exists():
            return []
        try:
            data = json.loads(self._tracked_path.read_text())
            return [TrackedBuild(**entry) for entry in data]
        except Exception:
            logger.exception("Failed to load tracked builds")
            return []

    def _save_tracked(self) -> None:
        """Persist tracked builds to disk."""
        self._tracked_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "request_id": t.request_id,
                "ref": t.ref,
                "commit_hash": t.commit_hash,
                "result": t.result,
                "triggered_at": t.triggered_at,
                "completed_at": t.completed_at,
                "drive_file_id": t.drive_file_id,
                "drive_link": t.drive_link,
            }
            for t in self._tracked
        ]
        self._tracked_path.write_text(json.dumps(data))

    def track_build(
        self,
        request_id: str,
        *,
        ref: str,
        commit_hash: str,
        result: str,
        triggered_at: float,
        completed_at: float,
        drive_file_id: str = "",
        drive_link: str = "",
    ) -> None:
        """Record a bot-triggered build with all metadata from the webhook."""
        self._tracked.append(
            TrackedBuild(
                request_id=request_id,
                ref=ref,
                commit_hash=commit_hash,
                result=result,
                triggered_at=triggered_at,
                completed_at=completed_at,
                drive_file_id=drive_file_id,
                drive_link=drive_link,
            )
        )
        self._save_tracked()

    def recent_builds(
        self, count: int = 5, *, success_only: bool = False
    ) -> list[TrackedBuild]:
        """Return the most recent tracked builds, newest first.

        Served entirely from local state — always works, even when
        Jenkins is unreachable.
        """
        builds = self._tracked
        if success_only:
            builds = [b for b in builds if b.result == "success"]
        return list(reversed(builds[-count:]))

    def find_pending_for_branch(self, ref: str) -> tuple[str, PendingBuild] | None:
        """Find a pending build for the given branch.

        Returns ``(request_id, pending_build)`` or ``None``.
        """
        for request_id, pending in self._pending.items():
            if pending.ref == ref:
                return request_id, pending
        return None

    def last_successful_build_for_branch(self, ref: str) -> TrackedBuild | None:
        """Find the most recent successful tracked build for a branch."""
        for build in reversed(self._tracked):
            if build.ref == ref and build.result == "success":
                return build
        return None

    # ------------------------------------------------------------------
    # Pending build validation against Jenkins
    # ------------------------------------------------------------------

    async def validate_pending_builds(self) -> list[tuple[str, PendingBuild]]:
        """Cross-reference pending builds with Jenkins to detect stale entries.

        Checks if any pending builds have been cancelled or deleted on Jenkins
        by looking for completed builds matching our request_ids. Returns a list
        of (request_id, PendingBuild) tuples that were cleaned up.

        Gracefully returns an empty list if Jenkins is unreachable — the bot
        falls back to TTL-based cleanup in that case.
        """
        if not self._pending:
            return []

        try:
            jenkins_builds = await self.jenkins.get_builds(count=20)
        except Exception:
            logger.exception("Failed to validate pending builds against Jenkins")
            return []

        if not jenkins_builds:
            return []

        # Build a lookup: request_id → JenkinsBuild for completed builds
        completed_on_jenkins = {
            jb.request_id: jb
            for jb in jenkins_builds
            if not jb.building and jb.request_id
        }

        stale: list[tuple[str, PendingBuild]] = []
        for request_id, pending in list(self._pending.items()):
            if request_id in completed_on_jenkins:
                # Build completed on Jenkins but webhook never arrived
                stale.append((request_id, pending))
                del self._pending[request_id]

        if stale:
            self._save_pending()
            logger.info(
                "Cleaned up %d stale pending build(s) detected via Jenkins",
                len(stale),
            )

        return stale

    # ------------------------------------------------------------------
    # Drive file retention (max_recent_builds)
    # ------------------------------------------------------------------

    async def enforce_drive_limit(self) -> None:
        """Evict oldest tracked builds if count exceeds max_recent_builds.

        Deletes Drive files for evicted builds on a best-effort basis.
        Errors are logged but never propagated.
        """
        limit = self.config.max_recent_builds
        if limit <= 0 or len(self._tracked) <= limit:
            return

        to_evict = self._tracked[: len(self._tracked) - limit]
        self._tracked = self._tracked[len(self._tracked) - limit :]
        self._save_tracked()

        creds = self.drive.load_tokens()
        for build in to_evict:
            if not build.drive_file_id:
                continue
            try:
                if creds:
                    await self.drive.delete_file(creds, build.drive_file_id)
                logger.info(
                    "Evicted old build Drive file: %s",
                    build.drive_file_id,
                )
            except Exception:
                logger.exception(
                    "Failed to delete Drive file %s",
                    build.drive_file_id,
                )

    # ------------------------------------------------------------------
    # Build result handlers (called by webhook)
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
        metadata: dict,
        artifact_path: str,
        *,
        request_id: str = "",
    ) -> None:
        """Handle successful build — upload to Drive and notify user."""
        commit_hash = metadata.get("commit_hash", "")
        short_hash = commit_hash[:7]
        now = time.time()
        duration = _format_duration(pending.triggered_at, now)

        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            Path(artifact_path).unlink(missing_ok=True)
            return

        try:
            creds = self.drive.load_tokens()
            if not creds:
                app_name = _escape(self.config.app_name)
                text = (
                    f"⚠️ <b>{app_name} built successfully, but Google Drive"
                    f" isn't connected.</b>\n"
                    f"\n{self._admin_hint()}"
                )
                await self._edit_build_message(pending, text)
                await self.bot.send_message(
                    pending.chat_id,
                    text,
                    parse_mode="HTML",
                )
                # Still track the build even without Drive upload
                if request_id:
                    self.track_build(
                        request_id,
                        ref=pending.ref,
                        commit_hash=commit_hash,
                        result="success",
                        triggered_at=pending.triggered_at,
                        completed_at=now,
                    )
                return

            # Generate filename — slugify app_name for a clean, space-free prefix
            dt_now = datetime.now(timezone.utc)
            folder_name = self.config.drive_folder_name or "flutter-builds"
            file_prefix = _slugify(self.config.app_name)
            filename = (
                f"{file_prefix}-{dt_now.strftime('%Y%m%d-%H%M')}-{short_hash}.apk"
            )

            folder_id, _ = await self.drive.ensure_folder(creds, folder_name)
            file_id, drive_link = await self.drive.upload_file(
                artifact_path, filename, creds, folder_id
            )

            app_name = _escape(self.config.app_name)
            text = (
                f"✅ <b>{app_name} is ready!</b>\n"
                f"\n"
                f"Built from <code>{_escape(pending.ref)}</code> in {duration}."
            )
            download_button = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📲 Download APK", url=drive_link)],
                ]
            )

            # Edit the build message to "done" state
            await self._edit_build_message(pending, text, download_button)

            # Send a new message to trigger mobile notification
            await self.bot.send_message(
                pending.chat_id,
                text,
                parse_mode="HTML",
                reply_markup=download_button,
            )

            if request_id:
                self.track_build(
                    request_id,
                    ref=pending.ref,
                    commit_hash=commit_hash,
                    result="success",
                    triggered_at=pending.triggered_at,
                    completed_at=now,
                    drive_file_id=file_id,
                    drive_link=drive_link,
                )

            await self.enforce_drive_limit()

        except Exception:
            logger.exception("Failed to upload/notify for build %s", commit_hash)
            app_name = _escape(self.config.app_name)
            text = (
                f"⚠️ <b>{app_name} built successfully, but the file"
                f" couldn't be uploaded to Google Drive.</b>\n"
                f"\n{self._admin_hint()}"
            )
            await self._edit_build_message(pending, text)
            await self.bot.send_message(
                pending.chat_id,
                text,
                parse_mode="HTML",
            )

        finally:
            Path(artifact_path).unlink(missing_ok=True)

    async def on_build_failure(
        self,
        pending: PendingBuild,
        metadata: dict,
        *,
        request_id: str = "",
    ) -> None:
        """Handle failed build — notify user."""
        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            return

        commit_hash = metadata.get("commit_hash", "")
        now = time.time()

        app_name = _escape(self.config.app_name)
        text = (
            f"❌ <b>{app_name} build failed</b>\n"
            f"\n"
            f"Something went wrong on <code>{_escape(pending.ref)}</code>.\n"
            f"{self._admin_hint()}"
        )

        # Edit the build message to "failed" state
        await self._edit_build_message(pending, text)

        # Send a new message to trigger mobile notification
        await self.bot.send_message(
            pending.chat_id,
            text,
            parse_mode="HTML",
        )

        # Track failed builds too
        if request_id:
            self.track_build(
                request_id,
                ref=pending.ref,
                commit_hash=commit_hash,
                result="failure",
                triggered_at=pending.triggered_at,
                completed_at=now,
            )

    async def on_build_cancelled(
        self,
        pending: PendingBuild,
        *,
        by_user: bool = True,
    ) -> None:
        """Notify the build's chat that a build was cancelled."""
        if not self.bot:
            return

        text = f"🚫 Build on <code>{_escape(pending.ref)}</code> was cancelled."

        # Edit the build message to "cancelled" state
        await self._edit_build_message(pending, text)

        # Send a new message to trigger mobile notification
        await self.bot.send_message(
            pending.chat_id,
            text,
            parse_mode="HTML",
        )
