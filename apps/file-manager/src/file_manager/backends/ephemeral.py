"""Ephemeral in-memory storage backend.

Stores uploaded files in a Python dictionary keyed by generated file ID.
Files exist only for the lifetime of the process — intended for mock/dev
environments where persistent storage is unnecessary.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..storage import UploadResult

logger = logging.getLogger(__name__)


@dataclass
class EphemeralFile:
    """A file stored in memory."""

    filename: str
    data: bytes
    created_at: float = field(default_factory=time.time)


class EphemeralBackend:
    """In-memory storage backend implementing the ``StorageBackend`` protocol.

    Files are stored in a dict and served via the download endpoint
    on the file-manager API (``GET /api/files/{file_id}/download``).
    """

    def __init__(self, *, base_url: str = "http://file-manager:9092") -> None:
        self._store: dict[str, EphemeralFile] = {}
        self._base_url = base_url.rstrip("/")

    async def upload(self, data: bytes, filename: str) -> UploadResult:
        """Store file in memory and return a download URL."""
        file_id = uuid4().hex[:12]
        self._store[file_id] = EphemeralFile(filename=filename, data=data)
        download_url = f"{self._base_url}/api/files/{file_id}/download"
        logger.info(
            "Ephemeral upload: %s (%d bytes) -> %s",
            filename,
            len(data),
            file_id,
        )
        return UploadResult(file_id=file_id, download_url=download_url)

    async def delete(self, file_id: str) -> None:
        """Remove a file from memory."""
        removed = self._store.pop(file_id, None)
        if removed:
            logger.info("Ephemeral delete: %s (%s)", file_id, removed.filename)
        else:
            logger.warning("Ephemeral delete: %s not found (already removed)", file_id)

    async def is_connected(self) -> bool:
        """Ephemeral storage is always connected."""
        return True

    async def status(self) -> dict[str, Any]:
        """Return ephemeral storage status summary."""
        total_size = sum(len(f.data) for f in self._store.values())
        return {
            "backend": "ephemeral",
            "connected": True,
            "configured": True,
            "file_count": len(self._store),
            "total_size_bytes": total_size,
        }

    def get(self, file_id: str) -> EphemeralFile | None:
        """Retrieve a stored file by ID (used by the download endpoint)."""
        return self._store.get(file_id)
