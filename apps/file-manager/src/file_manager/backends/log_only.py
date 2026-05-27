"""Log-only storage backend.

A dummy storage backend that only logs upload and delete operations
without actually storing any data. Used for testing or minimal setups
where files are not needed.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from ..storage import UploadResult

logger = logging.getLogger(__name__)


class LogOnlyBackend:
    """Storage backend that only logs operations."""

    async def upload(self, data: bytes, filename: str) -> UploadResult:
        """Log upload and return a fake download URL."""
        file_id = uuid4().hex[:12]
        download_url = f"log-only://{file_id}/{filename}"
        logger.info(
            "Log-only upload: %s (%d bytes) -> %s",
            filename,
            len(data),
            file_id,
        )
        return UploadResult(file_id=file_id, download_url=download_url)

    async def delete(self, file_id: str) -> None:
        """Log delete operation."""
        logger.info("Log-only delete: %s", file_id)

    async def is_connected(self) -> bool:
        """Log-only storage is always connected."""
        return True

    async def status(self) -> dict[str, Any]:
        """Return log-only storage status summary."""
        return {
            "backend": "log_only",
            "connected": True,
            "configured": True,
        }
