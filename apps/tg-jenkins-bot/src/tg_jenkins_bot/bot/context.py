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

from telegram import Bot

if TYPE_CHECKING:
    from ..config import Config
    from ..drive.uploader import DriveUploader
    from ..jenkins.client import JenkinsClient

logger = logging.getLogger(__name__)

PENDING_BUILD_TTL = 3600  # 1 hour


def _slugify(text: str) -> str:
    """Convert a display name to a safe filename prefix.

    'Tendoo Mall' -> 'tendoo-mall'
    'my_app'      -> 'my-app'
    """
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "build"


@dataclass(frozen=True)
class PendingBuild:
    """Tracks a build triggered via Telegram."""

    chat_id: int
    ref: str
    triggered_at: float
    queue_id: int | None = None  # stored at trigger time; used to cancel via Jenkins API


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


def _summarize_logs(logs: str) -> str:
    """Extract the first meaningful error line from raw build logs.

    Skips blank lines and common boilerplate to find the most useful
    error message for display in a Telegram notification.
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

    for line in logs.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(prefix) for prefix in skip_prefixes):
            continue
        # Return the first meaningful line, capped at 200 chars
        if len(stripped) > 200:
            return stripped[:197] + "..."
        return stripped

    return "No details available."


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
    ) -> None:
        self.config = config
        self.jenkins = jenkins
        self.drive = drive
        self.bot = bot
        self._pending_path = Path("data/pending_builds.json")
        self._pending: dict[str, PendingBuild] = self._load_pending()
        self._tracked_path = Path("data/tracked_builds.json")
        self._tracked: list[TrackedBuild] = self._load_tracked()

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
    ) -> None:
        """Track a Telegram-triggered build."""
        self._cleanup_expired()
        self._pending[request_id] = PendingBuild(
            chat_id=chat_id,
            ref=ref,
            triggered_at=time.time(),
            queue_id=queue_id,
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

    def _cleanup_expired(self) -> None:
        """Remove pending builds older than TTL."""
        now = time.time()
        expired = [
            request_id
            for request_id, pending in self._pending.items()
            if now - pending.triggered_at > PENDING_BUILD_TTL
        ]
        for request_id in expired:
            del self._pending[request_id]
        if expired:
            self._save_pending()

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

    def recent_builds(self, count: int = 5, *, success_only: bool = False) -> list[TrackedBuild]:
        """Return the most recent tracked builds, newest first.

        Served entirely from local state — always works, even when
        Jenkins is unreachable.
        """
        builds = self._tracked
        if success_only:
            builds = [b for b in builds if b.result == "success"]
        return list(reversed(builds[-count:]))

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

    async def on_build_success(
        self,
        pending: PendingBuild,
        metadata: dict,
        artifact_path: str,
        *,
        request_id: str = "",
    ) -> None:
        """Handle successful build — upload to Drive and notify user."""
        commit_hash = metadata.get("commit_hash", "unknown")
        short_hash = commit_hash[:7]
        now = time.time()
        started = _format_time(pending.triggered_at)
        finished = _format_time(now)
        duration = _format_duration(pending.triggered_at, now)

        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            Path(artifact_path).unlink(missing_ok=True)
            return

        try:
            creds = self.drive.load_tokens()
            if not creds:
                app_name = _escape(self.config.app_name)
                await self.bot.send_message(
                    pending.chat_id,
                    f"⚠️ <b>{app_name} built successfully, but Google Drive isn't connected.</b>\n"
                    "\n"
                    f"Branch:  <code>{_escape(pending.ref)}</code>\n"
                    f"Commit:  <code>{_escape(short_hash)}</code>\n"
                    "\n"
                    "Contact your admin to set up file delivery.",
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
            await self.bot.send_message(
                pending.chat_id,
                f"✅ <b>{app_name} is ready!</b>\n"
                "\n"
                f"Branch:  <code>{_escape(pending.ref)}</code>\n"
                f"Commit:  <code>{_escape(short_hash)}</code>\n"
                f"Built:   {started} → {finished} ({duration})\n"
                f"File:    <code>{_escape(filename)}</code>\n"
                "\n"
                f'📲 <a href="{_escape(drive_link)}">Download APK</a>',
                parse_mode="HTML",
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
            await self.bot.send_message(
                pending.chat_id,
                f"⚠️ <b>{app_name} built successfully, but the download couldn't be prepared.</b>\n"
                "\n"
                f"Branch:  <code>{_escape(pending.ref)}</code>\n"
                f"Commit:  <code>{_escape(short_hash)}</code>\n"
                "\n"
                "Contact your admin.",
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

        commit_hash = metadata.get("commit_hash", "unknown")
        short_hash = commit_hash[:7]
        logs = metadata.get("logs", "")
        error_summary = _escape(_summarize_logs(logs))
        now = time.time()
        started = _format_time(pending.triggered_at)
        finished = _format_time(now)

        app_name = _escape(self.config.app_name)
        await self.bot.send_message(
            pending.chat_id,
            f"❌ <b>{app_name} build failed</b>\n"
            "\n"
            f"Branch:  <code>{_escape(pending.ref)}</code>\n"
            f"Commit:  <code>{_escape(short_hash)}</code>\n"
            f"Time:    {started} → {finished}\n"
            "\n"
            f"Error: {error_summary}\n"
            "\n"
            "Contact your admin for the full log.",
            parse_mode="HTML",
        )

        # Track failed builds too so /recent shows them
        if request_id:
            self.track_build(
                request_id,
                ref=pending.ref,
                commit_hash=commit_hash,
                result="failure",
                triggered_at=pending.triggered_at,
                completed_at=now,
            )
