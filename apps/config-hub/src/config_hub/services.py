"""HTTP client for service control APIs on the internal network.

Proxies lifecycle, schema, and config operations to bot, agent,
file-manager, and build-manager services.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ServiceClient:
    """Call service control endpoints over the internal Docker network.

    Decoupled from any framework — constructor takes raw URLs.
    """

    def __init__(
        self,
        bot_url: str | None,
        agent_url: str | None,
        file_manager_url: str | None = None,
        build_manager_url: str | None = None,
    ) -> None:
        self._bot_url = bot_url
        self._agent_url = agent_url
        self._file_manager_url = file_manager_url
        self._build_manager_url = build_manager_url

    def _service_url(self, service: str) -> str | None:
        if service == "bot":
            return self._bot_url
        if service == "agent":
            return self._agent_url
        if service == "file_manager":
            return self._file_manager_url
        if service == "builds":
            return self._build_manager_url
        raise ValueError(f"Unknown service: {service}")

    async def _control(self, service: str, action: str | None = None) -> dict[str, Any]:
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
                data = response.json()
                data["available"] = True
                if not response.is_success:
                    # Service responded but rejected the action (e.g. 400
                    # from a failed start). Preserve the error detail.
                    data.setdefault("detail", response.text)
                return data
        except Exception as exc:
            logger.warning("Failed to reach %s at %s: %s", service, target, exc)
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

    async def schema(self, service: str) -> dict[str, Any] | None:
        """Fetch the config field schema from a service."""
        url = self._service_url(service)
        if not url:
            return None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}/control/schema")
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning("Failed to fetch schema from %s: %s", service, exc)
            return None

    async def get_config(self, service: str) -> dict[str, Any] | None:
        """Fetch the current config values from a service."""
        url = self._service_url(service)
        if not url:
            return None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}/control/config")
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning("Failed to fetch config from %s: %s", service, exc)
            return None

    async def put_config(self, service: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Save config values to a service."""
        url = self._service_url(service)
        if not url:
            return {"status": "error", "detail": "service URL not configured"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.put(f"{url}/control/config", json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            logger.warning("Failed to save config to %s: %s", service, exc)
            return {"status": "error", "detail": f"Cannot reach {service}"}
