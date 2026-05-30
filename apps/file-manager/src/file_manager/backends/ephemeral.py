"""Ephemeral local filesystem storage backend.

Stores uploaded files in a container-local temporary directory.
Files are cleaned up on startup, graceful shutdown, and container destruction.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..storage import UploadResult

logger = logging.getLogger(__name__)


@dataclass
class EphemeralFile:
    """A file record representing a locally persisted ephemeral file."""

    filename: str
    file_path: Path
    created_at: float = field(default_factory=time.time)

    @property
    def data(self) -> bytes:
        """Read data from the file path on-demand (backward compatibility)."""
        try:
            return self.file_path.read_bytes()
        except FileNotFoundError:
            return b""


class EphemeralBackend:
    """Local filesystem storage backend implementing the ``StorageBackend`` protocol.

    Files are stored on disk and served via the download endpoint
    on the file-manager API (``GET /api/files/{file_id}/download``).
    """

    def __init__(
        self,
        *,
        base_url: str = "http://file-manager:9092",
        data_dir: Path | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._store: dict[str, EphemeralFile] = {}

        # Default to container-local temp dir to isolate from host persistent volumes
        if data_dir is not None:
            self._upload_dir = Path(data_dir) / "ephemeral_uploads"
        else:
            self._upload_dir = Path(tempfile.gettempdir()) / "ephemeral_uploads"

        self._wipe_dir()

    def _wipe_dir(self) -> None:
        """Completely wipe the uploads directory on initialization."""
        if self._upload_dir.exists():
            try:
                shutil.rmtree(self._upload_dir)
                logger.info("Wiped existing ephemeral uploads directory: %s", self._upload_dir)
            except Exception:
                logger.exception("Failed to wipe existing ephemeral uploads: %s", self._upload_dir)
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    async def upload(self, data: bytes, filename: str) -> UploadResult:
        """Store file on disk and return a download URL."""
        file_id = uuid4().hex[:12]
        safe_filename = Path(filename).name
        file_path = self._upload_dir / f"{file_id}_{safe_filename}"

        # Write to disk asynchronously using to_thread
        await asyncio.to_thread(file_path.write_bytes, data)

        self._store[file_id] = EphemeralFile(filename=safe_filename, file_path=file_path)
        download_url = f"{self._base_url}/api/files/{file_id}/download"
        logger.info(
            "Ephemeral upload: %s (%d bytes) -> %s",
            safe_filename,
            len(data),
            file_id,
        )
        return UploadResult(file_id=file_id, download_url=download_url)

    async def delete(self, file_id: str) -> None:
        """Remove a file from the memory index and delete its disk file."""
        removed = self._store.pop(file_id, None)
        if removed:
            logger.info("Ephemeral delete: %s (%s)", file_id, removed.filename)
            try:
                if removed.file_path.exists():
                    await asyncio.to_thread(removed.file_path.unlink)
            except Exception:
                logger.exception("Failed to delete file from disk: %s", removed.file_path)
        else:
            logger.warning("Ephemeral delete: %s not found (already removed)", file_id)

    async def is_connected(self) -> bool:
        """Ephemeral storage is always connected."""
        return True

    async def status(self) -> dict[str, Any]:
        """Return ephemeral storage status summary."""
        total_size = sum(
            f.file_path.stat().st_size
            for f in self._store.values()
            if f.file_path.exists()
        )
        return {
            "backend": "ephemeral",
            "connected": True,
            "configured": True,
            "file_count": len(self._store),
            "total_size_bytes": total_size,
        }

    def get(self, file_id: str) -> EphemeralFile | None:
        """Retrieve a stored file record by ID."""
        return self._store.get(file_id)

    async def cleanup(self) -> None:
        """Clean up all ephemeral uploads on shutdown."""
        logger.info("Graceful shutdown: cleaning up ephemeral uploads")
        if self._upload_dir.exists():
            try:
                shutil.rmtree(self._upload_dir)
            except Exception:
                logger.exception("Failed to delete ephemeral uploads on cleanup: %s", self._upload_dir)
        self._store.clear()

