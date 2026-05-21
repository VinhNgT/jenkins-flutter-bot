"""HTTP client for config-hub API.

Extracts all config-hub HTTP operations from handlers into a reusable,
injectable class.  Tests can provide an ``httpx.AsyncClient`` with a
``MockTransport`` to avoid real network calls.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class HubClient:
    """Async HTTP client for the config-hub API.

    All operational methods correspond to config-hub REST endpoints used
    by the admin bot's Telegram handlers.
    """

    def __init__(self, base_url: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # -- Service status & control --

    async def get_service_status(self) -> dict[str, Any]:
        """Fetch aggregated service status from config-hub."""
        resp = await self._client.get(f"{self._base_url}/api/services/status")
        resp.raise_for_status()
        return resp.json()

    async def service_action(self, service: str, action: str) -> dict[str, Any]:
        """Start/stop/restart a managed service."""
        resp = await self._client.post(
            f"{self._base_url}/api/services/{service}/{action}"
        )
        resp.raise_for_status()
        return resp.json()

    # -- Export / Import --

    async def export_tarball(self) -> bytes:
        """Download the config tarball from config-hub."""
        resp = await self._client.get(
            f"{self._base_url}/api/export/tarball", timeout=30.0
        )
        resp.raise_for_status()
        return resp.content

    async def import_tarball(self, raw: bytes) -> dict[str, Any]:
        """Upload a config tarball to config-hub."""
        resp = await self._client.post(
            f"{self._base_url}/api/import/tarball",
            files={"file": ("config.tar.gz", raw, "application/gzip")},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    # -- Jenkinsfile --

    async def get_jenkinsfile(self) -> dict[str, Any]:
        """Fetch generated Jenkinsfile from config-hub."""
        resp = await self._client.get(f"{self._base_url}/api/jenkinsfile")
        resp.raise_for_status()
        return resp.json()

    # -- Drive OAuth --

    async def get_drive_status(self) -> dict[str, Any]:
        """Fetch Google Drive OAuth status."""
        resp = await self._client.get(f"{self._base_url}/api/drive/status")
        resp.raise_for_status()
        return resp.json()

    async def save_drive_config(
        self, client_id: str, client_secret: str
    ) -> None:
        """Save Drive OAuth credentials via config-hub."""
        await self._client.put(
            f"{self._base_url}/api/config/file_manager",
            json={"drive": {"client_id": client_id, "client_secret": client_secret}},
        )

    async def exchange_drive_code(
        self, code: str, client_id: str, client_secret: str
    ) -> None:
        """Exchange a Drive OAuth code for tokens via config-hub."""
        resp = await self._client.post(
            f"{self._base_url}/api/drive/connect/exchange",
            json={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
