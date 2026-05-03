"""Bot context — shared state between Telegram handlers and webhook."""

from __future__ import annotations

import json
import logging
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


@dataclass(frozen=True)
class PendingBuild:
    """Tracks a build triggered via Telegram."""

    chat_id: int
    ref: str
    triggered_at: float


class BotContext:
    """Shared context between Telegram handlers and the webhook server.

    Owns:
    - Pending build tracking (request_id → chat_id mapping)
    - Build result handling (Drive upload + Telegram notification)
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
            return {
                k: PendingBuild(**v)
                for k, v in data.items()
            }
        except Exception as exc:
            logger.warning("Failed to load pending builds: %s", exc)
            return {}

    def _save_pending(self) -> None:
        """Persist pending builds to disk."""
        self._pending_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            k: {
                "chat_id": v.chat_id,
                "ref": v.ref,
                "triggered_at": v.triggered_at,
            }
            for k, v in self._pending.items()
        }
        self._pending_path.write_text(json.dumps(data))

    def add_pending(self, request_id: str, chat_id: int, ref: str) -> None:
        """Track a Telegram-triggered build."""
        self._cleanup_expired()
        self._pending[request_id] = PendingBuild(
            chat_id=chat_id,
            ref=ref,
            triggered_at=time.time(),
        )
        self._save_pending()

    def consume_pending(self, request_id: str | None) -> PendingBuild | None:
        """Look up and remove a pending build. Returns None if not found."""
        if not request_id:
            return None
        self._cleanup_expired()
        result = self._pending.pop(request_id, None)
        if result:
            self._save_pending()
        return result

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
    # Build result handlers (called by webhook)
    # ------------------------------------------------------------------

    async def on_build_success(
        self,
        pending: PendingBuild,
        metadata: dict,
        artifact_path: str,
    ) -> None:
        """Handle successful build — upload to Drive and notify user."""
        commit_hash = metadata.get("commit_hash", "unknown")
        short_hash = commit_hash[:7]

        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            Path(artifact_path).unlink(missing_ok=True)
            return

        try:
            creds = self.drive.load_tokens()
            if not creds:
                ui_hint = ""
                if self.config.config_ui_url:
                    ui_hint = (
                        f"\nSet up Google Drive in the "
                        f"[config dashboard]({self.config.config_ui_url})."
                    )
                await self.bot.send_message(
                    pending.chat_id,
                    f"✅ Build successful (`{short_hash}`) but Google Drive "
                    f"is not connected.{ui_hint}",
                    parse_mode="Markdown",
                )
                return

            await self.bot.send_message(
                pending.chat_id,
                "☁️ Build complete! Uploading to Google Drive...",
            )

            # Generate filename
            now = datetime.now(timezone.utc)
            folder_name = self.config.drive_folder_name or "flutter-builds"
            filename = f"{folder_name}-{now.strftime('%Y%m%d-%H%M')}-{short_hash}.apk"

            folder_id = await self.drive.ensure_folder(creds, folder_name)
            file_id, drive_link = await self.drive.upload_file(
                artifact_path, filename, creds, folder_id
            )

            await self.bot.send_message(
                pending.chat_id,
                f"✅ Build successful!\n\n"
                f"📦 `{filename}`\n"
                f"🔗 [Download APK]({drive_link})",
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.exception("Failed to upload/notify for build %s", commit_hash)
            await self.bot.send_message(
                pending.chat_id,
                f"✅ Build succeeded (`{short_hash}`) but upload failed: {e}",
                parse_mode="Markdown",
            )

        finally:
            Path(artifact_path).unlink(missing_ok=True)

    async def on_build_failure(self, pending: PendingBuild, metadata: dict) -> None:
        """Handle failed build — notify user."""
        if not self.bot:
            logger.error("Cannot notify — bot instance is not available")
            return

        commit_hash = metadata.get("commit_hash", "unknown")
        short_hash = commit_hash[:7]
        logs = metadata.get("logs", "No logs available")

        await self.bot.send_message(
            pending.chat_id,
            f"❌ Build failed for `{short_hash}`\n\n"
            f"```\n{logs[:500]}\n```\n\n"
            f"Check Jenkins console for full logs.",
            parse_mode="Markdown",
        )
