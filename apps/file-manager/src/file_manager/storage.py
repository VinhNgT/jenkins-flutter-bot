"""Backend-agnostic storage protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class UploadResult:
    """Result of a successful file upload.

    Attributes:
        file_id:  Opaque identifier for later deletion.
        download_url:  Public URL for end-user download.
    """

    file_id: str
    download_url: str


class StorageBackend(Protocol):
    """Protocol that any storage backend must implement.

    All methods that perform I/O are async so callers never block.
    Implementations that wrap synchronous libraries (e.g. Google
    Drive) should use ``asyncio.to_thread()`` internally.
    """

    async def upload(self, file_path: str, filename: str) -> UploadResult:
        """Upload a file and return its ID + public URL."""
        ...

    async def delete(self, file_id: str) -> None:
        """Delete a previously uploaded file by its opaque ID."""
        ...

    async def is_connected(self) -> bool:
        """Return True if the backend is authenticated and reachable."""
        ...

    async def status(self) -> dict[str, Any]:
        """Return a JSON-serialisable status summary."""
        ...
