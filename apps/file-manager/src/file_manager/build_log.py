"""Build log — records completed builds alongside stored artifacts.

The ``BuildLog`` tracks metadata for completed builds. Its persistence
strategy is determined by the storage backend:

- **Persistent** (Google Drive): records are saved to a JSON file on disk
  and survive service restarts.
- **Ephemeral** (in-memory): records exist only for the lifetime of the
  process — no disk I/O is performed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuildRecord:
    """Metadata for a completed build."""

    request_id: str
    branch: str
    commit_hash: str
    result: str  # "success" | "failure" | "timeout" | "cancelled"
    triggered_at: float
    completed_at: float
    download_url: str = ""
    file_id: str = ""


class BuildLog:
    """Completed build log with configurable persistence.

    When ``persistent=True``, records are saved to
    ``data_dir / "build_log.json"`` on every mutation.
    When ``persistent=False``, records are held in-memory only —
    the log starts empty on each process start.
    """

    def __init__(
        self,
        *,
        data_dir: Path,
        max_records: int = 5,
        persistent: bool = True,
    ) -> None:
        self._data_dir = data_dir
        self._max_records = max_records
        self._persistent = persistent
        self._log_path = data_dir / "build_log.json" if persistent else None
        self._records: list[BuildRecord] = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> list[BuildRecord]:
        if self._log_path is None or not self._log_path.exists():
            return []
        try:
            data = json.loads(self._log_path.read_text())
            return [BuildRecord(**entry) for entry in data]
        except Exception:
            logger.exception("Failed to load build log")
            return []

    def _save(self) -> None:
        if self._log_path is None:
            return
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = [asdict(r) for r in self._records]
        self._log_path.write_text(json.dumps(data))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        request_id: str,
        branch: str,
        commit_hash: str,
        result: str,
        triggered_at: float,
        completed_at: float,
        download_url: str = "",
        file_id: str = "",
    ) -> list[BuildRecord]:
        """Append a build record and enforce retention.

        Returns evicted records whose backend files should be deleted
        by the caller.
        """
        entry = BuildRecord(
            request_id=request_id,
            branch=branch,
            commit_hash=commit_hash,
            result=result,
            triggered_at=triggered_at,
            completed_at=completed_at,
            download_url=download_url,
            file_id=file_id,
        )
        self._records.append(entry)

        # Enforce retention — evict oldest records beyond the limit
        evicted: list[BuildRecord] = []
        while len(self._records) > self._max_records:
            evicted.append(self._records.pop(0))

        self._save()
        return evicted

    def recent(
        self, count: int = 10, *, success_only: bool = False
    ) -> list[BuildRecord]:
        """Return the most recent build records, newest first."""
        records = self._records
        if success_only:
            records = [r for r in records if r.result == "success"]
        return list(reversed(records[-count:]))

    def remove_by_file_id(self, file_id: str) -> None:
        """Remove any record referencing the given file ID."""
        before = len(self._records)
        self._records = [r for r in self._records if r.file_id != file_id]
        if len(self._records) != before:
            self._save()

    @property
    def file_ids(self) -> set[str]:
        """Return all file IDs referenced by build log records."""
        return {r.file_id for r in self._records if r.file_id}

    def reconcile(self, drive_file_ids: set[str]) -> tuple[list[BuildRecord], set[str]]:
        """Cross-reference the build log against actual Drive contents.

        Args:
            drive_file_ids: Set of file IDs that currently exist in Drive.

        Returns:
            A tuple of ``(stale_records, orphan_file_ids)``:

            - **stale_records** — build log entries whose ``file_id`` is no
              longer present in Drive. These are removed from the log.
            - **orphan_file_ids** — Drive files not referenced by any build
              log record. The caller should delete these.
        """
        # Identify stale records: log entries pointing to missing Drive files
        stale: list[BuildRecord] = []
        kept: list[BuildRecord] = []
        for record in self._records:
            if record.file_id and record.file_id not in drive_file_ids:
                stale.append(record)
            else:
                kept.append(record)

        # Identify orphan Drive files: present in Drive but not in any record
        tracked_ids = {r.file_id for r in kept if r.file_id}
        orphans = drive_file_ids - tracked_ids

        if stale:
            self._records = kept
            self._save()

        return stale, orphans

