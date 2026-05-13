"""Build state tracking — pending and completed build registries.

The ``BuildTracker`` is a frontend-agnostic state manager.  It tracks
which builds are pending (waiting for a webhook callback), which have
completed, and which frontend callback URLs should be notified.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingBuild:
    """A build that has been triggered but not yet completed."""

    request_id: str
    branch: str
    triggered_at: float
    queue_id: int | None = None
    frontend_callback_url: str = ""


@dataclass(frozen=True)
class CompletedBuild:
    """A build that has finished (success or failure)."""

    request_id: str
    branch: str
    commit_hash: str
    result: str  # "success" or "failure"
    triggered_at: float
    completed_at: float
    download_url: str = ""
    file_id: str = ""


class BuildTracker:
    """Manages in-flight and completed build state.

    State is persisted to JSON files so builds survive service restarts.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._pending_path = data_dir / "pending_builds.json"
        self._completed_path = data_dir / "completed_builds.json"
        self._pending: dict[str, PendingBuild] = self._load_pending()
        self._completed: list[CompletedBuild] = self._load_completed()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_pending(self) -> dict[str, PendingBuild]:
        if not self._pending_path.exists():
            return {}
        try:
            data = json.loads(self._pending_path.read_text())
            return {k: PendingBuild(**v) for k, v in data.items()}
        except Exception:
            logger.exception("Failed to load pending builds")
            return {}

    def _save_pending(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = {
            k: {
                "request_id": v.request_id,
                "branch": v.branch,
                "triggered_at": v.triggered_at,
                "queue_id": v.queue_id,
                "frontend_callback_url": v.frontend_callback_url,
            }
            for k, v in self._pending.items()
        }
        self._pending_path.write_text(json.dumps(data))

    def _load_completed(self) -> list[CompletedBuild]:
        if not self._completed_path.exists():
            return []
        try:
            data = json.loads(self._completed_path.read_text())
            return [CompletedBuild(**entry) for entry in data]
        except Exception:
            logger.exception("Failed to load completed builds")
            return []

    def _save_completed(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "request_id": c.request_id,
                "branch": c.branch,
                "commit_hash": c.commit_hash,
                "result": c.result,
                "triggered_at": c.triggered_at,
                "completed_at": c.completed_at,
                "download_url": c.download_url,
                "file_id": c.file_id,
            }
            for c in self._completed
        ]
        self._completed_path.write_text(json.dumps(data))

    # ------------------------------------------------------------------
    # Pending build operations
    # ------------------------------------------------------------------

    @staticmethod
    def generate_request_id() -> str:
        """Generate a unique request ID for a new build."""
        return uuid.uuid4().hex[:12]

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def add_pending(
        self,
        request_id: str,
        branch: str,
        *,
        queue_id: int | None = None,
        frontend_callback_url: str = "",
    ) -> PendingBuild:
        """Register a new pending build."""
        pending = PendingBuild(
            request_id=request_id,
            branch=branch,
            triggered_at=time.time(),
            queue_id=queue_id,
            frontend_callback_url=frontend_callback_url,
        )
        self._pending[request_id] = pending
        self._save_pending()
        return pending

    def get_pending(self, request_id: str) -> PendingBuild | None:
        """Look up a pending build by request_id."""
        return self._pending.get(request_id)

    def consume_pending(self, request_id: str) -> PendingBuild | None:
        """Remove and return a pending build.  Returns None if not found."""
        result = self._pending.pop(request_id, None)
        if result:
            self._save_pending()
        return result

    def list_pending(self) -> dict[str, PendingBuild]:
        """Return a snapshot of all pending builds."""
        return dict(self._pending)

    # ------------------------------------------------------------------
    # Completed build operations
    # ------------------------------------------------------------------

    def record_completed(
        self,
        request_id: str,
        *,
        branch: str,
        commit_hash: str,
        result: str,
        triggered_at: float,
        completed_at: float,
        download_url: str = "",
        file_id: str = "",
    ) -> CompletedBuild:
        """Record a completed build."""
        completed = CompletedBuild(
            request_id=request_id,
            branch=branch,
            commit_hash=commit_hash,
            result=result,
            triggered_at=triggered_at,
            completed_at=completed_at,
            download_url=download_url,
            file_id=file_id,
        )
        self._completed.append(completed)
        self._save_completed()
        return completed

    def recent_builds(
        self, count: int = 10, *, success_only: bool = False
    ) -> list[CompletedBuild]:
        """Return the most recent completed builds, newest first."""
        builds = self._completed
        if success_only:
            builds = [b for b in builds if b.result == "success"]
        return list(reversed(builds[-count:]))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of the build state."""
        return {
            "pending_count": self.pending_count,
            "completed_count": len(self._completed),
            "pending": {
                k: {"branch": v.branch, "triggered_at": v.triggered_at}
                for k, v in self._pending.items()
            },
        }
