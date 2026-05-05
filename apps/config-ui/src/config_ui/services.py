"""HTTP client for bot and agent control APIs."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .settings import Settings

logger = logging.getLogger(__name__)


class ServiceClient:
    """Call bot and agent control endpoints over the internal network."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _service_url(self, service: str) -> str | None:
        if service == "bot":
            return self._settings.bot_control_url
        if service == "agent":
            return self._settings.agent_control_url
        raise ValueError(f"Unknown service: {service}")

    async def _control(
        self, service: str, action: str | None = None
    ) -> dict[str, Any]:
        url = self._service_url(service)
        if not url:
            return {
                "available": False,
                "running": False,
                "detail": "service URL not configured",
            }

        target = (
            f"{url}/control/status" if action is None else f"{url}/control/{action}"
        )
        method = "GET" if action is None else "POST"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.request(method, target)
                response.raise_for_status()
                data = response.json()
                data["available"] = True
                return data
        except Exception:
            logger.exception("Failed to reach %s at %s", service, target)
            return {
                "available": False,
                "running": False,
                "detail": f"Cannot reach {service} at {target}",
            }

    async def status(self, service: str) -> dict[str, Any]:
        """Get the current status of a service."""
        return await self._control(service)

    async def start(self, service: str) -> dict[str, Any]:
        """Start a service."""
        return await self._control(service, "start")

    async def stop(self, service: str) -> dict[str, Any]:
        """Stop a service."""
        return await self._control(service, "stop")

    async def restart(self, service: str) -> dict[str, Any]:
        """Restart a service."""
        return await self._control(service, "restart")
