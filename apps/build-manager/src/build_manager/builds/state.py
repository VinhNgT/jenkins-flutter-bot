"""Pending build state tracking.

The ``BuildTracker`` manages in-flight builds only. Completed build
history is owned by the file-manager service, which stores both
artifacts and their metadata.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
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
    app_name: str | None = None


class BuildTracker:
    """Manages in-flight build state.

    Pending builds are persisted to a JSON file so the tracker can
    detect and clear zombie builds from a previous process on startup.
    """

    def __init__(
        self,
        data_dir: Path,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._data_dir = data_dir
        self._clock = clock
        self._pending_path = data_dir / "pending_builds.json"
        self._pending: dict[str, PendingBuild] = self._load_pending()

        # On fresh startup, any persisted pending builds are zombies from a
        # previous crash — no poll tasks exist for them. Clear them so
        # pending_count returns to 0 and VPN disconnect is not blocked.
        self._clear_stale_pending()

    def _clear_stale_pending(self) -> None:
        """Remove all pending builds left over from a previous process."""
        if not self._pending:
            return
        for req_id, pending in self._pending.items():
            logger.warning(
                "Clearing stale pending build: request_id=%s branch=%s "
                "(leftover from previous process)",
                req_id,
                pending.branch,
            )
        self._pending.clear()
        self._save_pending()

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
                "app_name": v.app_name,
            }
            for k, v in self._pending.items()
        }
        self._pending_path.write_text(json.dumps(data))

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
        app_name: str | None = None,
    ) -> PendingBuild:
        """Register a new pending build."""
        pending = PendingBuild(
            request_id=request_id,
            branch=branch,
            triggered_at=self._clock(),
            queue_id=queue_id,
            frontend_callback_url=frontend_callback_url,
            app_name=app_name,
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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of the build state."""
        return {
            "pending_count": self.pending_count,
            "pending": {
                k: {"branch": v.branch, "triggered_at": v.triggered_at}
                for k, v in self._pending.items()
            },
        }
