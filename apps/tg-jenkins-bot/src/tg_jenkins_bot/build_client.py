"""Build service API clients.

Provides typed async interfaces to both the build-manager and
file-manager services. The bot delegates build lifecycle operations
to build-manager (trigger, cancel, status) and queries file-manager
directly for completed build history.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from config_core import get_service_auth_headers

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuildResult:
    """A completed build returned by the file-manager build log."""

    request_id: str
    branch: str
    commit_hash: str
    result: str  # "success" | "failure" | "timeout" | "cancelled"
    triggered_at: float
    completed_at: float
    download_url: str = ""
    file_size: int = 0
    build_number: int = 0


class BuildClientError(Exception):
    """Raised when a build-manager API call fails.

    Carries a ``user_message`` suitable for Telegram display.
    """

    def __init__(self, detail: str, user_message: str) -> None:
        super().__init__(detail)
        self.user_message = user_message


class BuildClient:
    """Async HTTP client for build-manager and file-manager APIs.

    Build lifecycle (trigger, cancel, status) goes to build-manager.
    Completed build history goes to file-manager.
    """

    def __init__(
        self,
        build_manager_url: str,
        file_manager_url: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._build_url = build_manager_url.rstrip("/")
        self._file_url = file_manager_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            timeout=30.0, headers=get_service_auth_headers()
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def trigger_build(
        self, branch: str, callback_url: str, app_name: str | None = None
    ) -> dict[str, Any]:
        """Trigger a build via the build manager.

        Returns ``{request_id, status}`` on success.

        Raises ``BuildClientError`` on failure.
        """
        url = f"{self._build_url}/api/builds/trigger"
        try:
            payload = {"branch": branch, "callback_url": callback_url}
            if app_name:
                payload["app_name"] = app_name
            resp = await self._client.post(
                url,
                json=payload,
            )
        except Exception as exc:
            logger.exception("Failed to reach build-manager for trigger")
            raise BuildClientError(
                detail=f"Connection failed: {exc}",
                user_message=(
                    "The build server isn't responding. Try again in a few minutes."
                ),
            ) from exc

        if resp.status_code == 200:
            return resp.json()

        try:
            detail = resp.json().get("detail", resp.text[:200])
        except Exception:
            detail = resp.text[:200] or f"HTTP {resp.status_code}"
        raise BuildClientError(
            detail=f"HTTP {resp.status_code}: {detail}",
            user_message=detail,
        )

    async def cancel_build(self, request_id: str) -> dict[str, str]:
        """Cancel a pending build via the build manager."""
        url = f"{self._build_url}/api/builds/{request_id}/cancel"
        try:
            resp = await self._client.post(url)
            return resp.json()
        except Exception:
            logger.exception("Failed to cancel build via build-manager")
            return {"status": "error"}

    async def get_recent_builds(self, count: int = 5) -> list[BuildResult]:
        """Fetch recent completed builds from file-manager."""
        url = f"{self._file_url}/api/files/builds/recent"
        try:
            resp = await self._client.get(url, params={"count": count})
            if resp.status_code != 200:
                logger.error("Failed to fetch recent builds: %d", resp.status_code)
                return []
            data = resp.json()
            return [
                BuildResult(
                    request_id=b.get("request_id", ""),
                    branch=b.get("branch", ""),
                    commit_hash=b.get("commit_hash", ""),
                    result=b.get("result", ""),
                    triggered_at=b.get("triggered_at", 0),
                    completed_at=b.get("completed_at", 0),
                    download_url=b.get("download_url", ""),
                    file_size=b.get("file_size", 0),
                    build_number=b.get("build_number", 0),
                )
                for b in data.get("builds", [])
            ]
        except Exception:
            logger.exception("Failed to fetch recent builds")
            return []

    async def get_build_status(self) -> dict[str, Any]:
        """Fetch build manager status (pending builds only)."""
        url = f"{self._build_url}/api/builds/status"
        try:
            resp = await self._client.get(url)
            if resp.status_code != 200:
                return {"pending_count": 0}
            return resp.json()
        except Exception:
            logger.exception("Failed to fetch build status")
            return {"pending_count": 0}
