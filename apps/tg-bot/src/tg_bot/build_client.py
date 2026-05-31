"""Build service API client.

Provides typed async interfaces to the build-manager service. The bot
delegates build lifecycle operations and history queries to build-manager.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BuildClientError(Exception):
    """Raised when a build-manager API call fails.

    Carries a ``user_message`` suitable for Telegram display.
    """

    def __init__(self, detail: str, user_message: str) -> None:
        super().__init__(detail)
        self.user_message = user_message


class BuildClient:
    """Async HTTP client for build-manager APIs.

    Handles triggering, cancellation, active status tracking, and completed
    build log history.
    """

    def __init__(
        self,
        build_manager_url: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._build_url = build_manager_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def trigger_build(
        self,
        branch: str,
        callback_url: str,
        app_name: str | None = None,
        label: str = "",
        triggered_by: str = "",
        triggered_by_id: int = 0,
        notify: bool = True,
        chat_id: int = 0,
    ) -> dict[str, Any]:
        """Trigger a build via the build manager.

        Returns ``{request_id, status}`` on success.

        Raises ``BuildClientError`` on failure.
        """
        url = f"{self._build_url}/api/builds/trigger"
        try:
            payload = {
                "branch": branch,
                "callback_url": callback_url,
                "label": label,
                "triggered_by": triggered_by,
                "triggered_by_id": triggered_by_id,
                "notify": notify,
                "chat_id": chat_id,
            }
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

    def stream_builds(self) -> Any:
        """Return the async context manager for the build-manager stream."""
        url = f"{self._build_url}/api/builds/stream"
        return self._client.stream("GET", url, timeout=None)

    async def get_recent_builds(self, count: int = 5) -> list[dict[str, Any]]:
        """Fetch recent completed builds from build-manager."""
        url = f"{self._build_url}/api/builds/recent"
        try:
            resp = await self._client.get(url, params={"count": count})
            if resp.status_code != 200:
                logger.error("Failed to fetch recent builds: %d", resp.status_code)
                return []
            data = resp.json()
            return data.get("builds", [])
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

    async def get_pending_builds(self) -> dict[str, Any]:
        """Fetch full pending builds list with metadata from build-manager."""
        url = f"{self._build_url}/api/builds/pending"
        try:
            resp = await self._client.get(url)
            if resp.status_code != 200:
                return {}
            return resp.json().get("builds", {})
        except Exception:
            logger.exception("Failed to fetch pending builds")
            return {}
