"""HTTP client for service control APIs on the internal network.

Proxies lifecycle, schema, and config operations to agent-control,
file-manager, and build-manager services.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class ServiceClient:
    """Call service control endpoints over the internal Docker network.

    Owns a persistent ``httpx.AsyncClient`` for connection reuse.
    Call :meth:`close` during shutdown to release resources.
    """

    def __init__(
        self,
        agent_url: str | None,
        file_manager_url: str | None = None,
        build_manager_url: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._agent_url = agent_url
        self._file_manager_url = file_manager_url
        self._build_manager_url = build_manager_url
        self._client = client or httpx.AsyncClient(timeout=5.0)

    async def close(self) -> None:
        """Shut down the underlying HTTP client."""
        await self._client.aclose()

    def _service_url(self, service: str) -> str | None:
        if service == "agent-control":
            return self._agent_url
        if service == "file-manager":
            return self._file_manager_url
        if service == "build-manager":
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
            response = await self._client.request(method, target)
            data = response.json()
            data["available"] = True
            if not response.is_success:
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
            response = await self._client.get(f"{url}/control/schema")
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
            response = await self._client.get(f"{url}/control/config")
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("Failed to fetch config from %s: %s", service, exc)
            return None

    async def get_config_unmasked(self, service: str) -> dict[str, Any] | None:
        """Fetch the unmasked config values from a service."""
        url = self._service_url(service)
        if not url:
            return None
        try:
            response = await self._client.get(
                f"{url}/control/config", params={"masked": "false"}
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("Failed to fetch unmasked config from %s: %s", service, exc)
            return None

    async def put_config(self, service: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Save config values to a service."""
        url = self._service_url(service)
        if not url:
            return {"status": "error", "detail": "service URL not configured"}
        try:
            response = await self._client.put(f"{url}/control/config", json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("Failed to save config to %s: %s", service, exc)
            return {"status": "error", "detail": f"Cannot reach {service}"}

    async def logs(self, service: str) -> dict[str, Any]:
        """Fetch recent log lines from a service's ring buffer."""
        url = self._service_url(service)
        if not url:
            return {"lines": [], "detail": "service URL not configured"}
        try:
            response = await self._client.get(f"{url}/control/logs")
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("Failed to reach %s logs at %s: %s", service, url, exc)
            return {"lines": [], "detail": f"Cannot reach {service}"}

    async def upload_vpn_file(self, content: bytes, filename: str) -> dict[str, Any]:
        """Proxy OpenVPN configuration file upload to agent-control."""
        url = self._service_url("agent-control")
        if not url:
            return {"status": "error", "detail": "Agent service not configured"}
        try:
            resp = await self._client.post(
                f"{url}/control/vpn/upload",
                files={"file": (filename, content)},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Failed to proxy VPN upload to agent: %s", exc)
            return {"status": "error", "detail": f"Cannot reach agent: {exc}"}

    async def vpn_status(self) -> dict[str, Any]:
        """Proxy VPN status check to agent-control."""
        url = self._service_url("agent-control")
        if not url:
            return {
                "uploaded": False,
                "size": 0,
                "connected": False,
                "available": False,
            }
        try:
            resp = await self._client.get(f"{url}/control/vpn/status")
            resp.raise_for_status()
            data = resp.json()
            data["available"] = True
            return data
        except Exception as exc:
            logger.warning("Failed to proxy VPN status to agent: %s", exc)
            return {
                "uploaded": False,
                "size": 0,
                "connected": False,
                "available": False,
                "detail": str(exc),
            }

    async def delete_vpn_file(self) -> dict[str, Any]:
        """Proxy VPN file deletion to agent-control."""
        url = self._service_url("agent-control")
        if not url:
            raise HTTPException(status_code=503, detail="Agent service not configured")
        try:
            resp = await self._client.delete(f"{url}/control/vpn/upload")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Failed to proxy VPN deletion to agent: %s", exc)
            raise HTTPException(status_code=500, detail=f"Cannot reach agent: {exc}")

    async def vpn_connect(self) -> dict[str, Any]:
        """Proxy VPN connect to agent-control."""
        url = self._service_url("agent-control")
        if not url:
            raise HTTPException(status_code=503, detail="Agent service not configured")
        try:
            resp = await self._client.post(f"{url}/control/vpn/connect")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Failed to proxy VPN connect to agent: %s", exc)
            raise HTTPException(status_code=500, detail=f"Cannot reach agent: {exc}")

    async def vpn_disconnect(self) -> dict[str, Any]:
        """Proxy VPN disconnect to agent-control."""
        url = self._service_url("agent-control")
        if not url:
            raise HTTPException(status_code=503, detail="Agent service not configured")
        try:
            resp = await self._client.post(f"{url}/control/vpn/disconnect")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Failed to proxy VPN disconnect to agent: %s", exc)
            raise HTTPException(status_code=500, detail=f"Cannot reach agent: {exc}")

    async def download_vpn_file(self) -> bytes | None:
        """Fetch the client.ovpn config file from agent-control."""
        url = self._service_url("agent-control")
        if not url:
            return None
        try:
            response = await self._client.get(f"{url}/control/vpn/download")
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.warning("Failed to fetch vpn file from agent: %s", e)
            return None
        except Exception as exc:
            logger.warning("Failed to fetch vpn file from agent: %s", exc)
            return None

    async def get_oauth_token(self) -> dict[str, Any] | None:
        """Fetch the OAuth tokens from file-manager."""
        url = self._service_url("file-manager")
        if not url:
            return None
        try:
            response = await self._client.get(f"{url}/api/auth/token")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.warning("Failed to fetch oauth token from file_manager: %s", e)
            return None
        except Exception as exc:
            logger.warning("Failed to fetch oauth token from file_manager: %s", exc)
            return None
