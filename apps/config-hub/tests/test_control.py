"""Smoke tests for config-hub API endpoints."""


import json
from unittest.mock import patch

import pytest


def test_version_endpoint(client):
    """GET /api/version returns version info."""
    resp = client.get("/api/version")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data


def test_version_denormalization(client):
    """GET /api/version correctly denormalizes PEP 440 pre-release version strings."""
    with patch("config_hub.routers.version.version") as mock_version:
        # Dev pre-release
        mock_version.return_value = "0.3.2.dev2"
        resp = client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json() == {"version": "0.3.2-dev.2"}

        # RC pre-release
        mock_version.return_value = "1.0.0.rc12"
        resp = client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json() == {"version": "1.0.0-rc.12"}

        # Stable release (should remain unchanged)
        mock_version.return_value = "0.3.2"
        resp = client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json() == {"version": "0.3.2"}


def test_services_status(client):
    """GET /api/services/status returns status for all services."""
    resp = client.get("/api/services/status")
    assert resp.status_code == 200
    data = resp.json()
    # All services should be unavailable since no URLs are configured
    for service in ("bot", "agent", "file_manager", "builds"):
        assert data[service]["available"] is False


@pytest.mark.asyncio
async def test_services_stream_direct(client):
    """Test the SSE stream endpoint event generator directly."""
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request

    from config_hub.routers.services import stream_services_status

    mock_request = MagicMock(spec=Request)
    mock_request.is_disconnected = AsyncMock(return_value=False)

    app = client.app
    manager = app.state.manager

    # The endpoint is an async generator that yields ServerSentEvent
    gen = stream_services_status(request=mock_request, manager=manager)
    first_event = await gen.__anext__()

    assert first_event.event == "status"
    assert isinstance(first_event.data, dict)
    for service in ("bot", "agent", "file_manager", "builds"):
        assert first_event.data[service]["available"] is False


@pytest.mark.asyncio
async def test_services_stream_integration(client):
    """Full HTTP integration test for the services SSE /stream endpoint.

    Uses httpx.AsyncClient with ASGITransport to verify correct headers, response
    handling, and serialization.
    """
    from unittest.mock import AsyncMock, patch

    import httpx

    app = client.app

    # Track call count so is_disconnected returns False first, True second.
    call_count = 0

    async def fake_is_disconnected(self):
        nonlocal call_count
        call_count += 1
        return call_count > 1

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        with (
            patch("config_hub.routers.services.asyncio.sleep", new_callable=AsyncMock),
            patch("starlette.requests.Request.is_disconnected", fake_is_disconnected),
        ):
            resp = await async_client.get("/api/services/stream")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"

    body = resp.text
    data_lines = [
        line[len("data:") :].strip()
        for line in body.splitlines()
        if line.startswith("data:")
    ]
    assert len(data_lines) > 0
    payload = json.loads(data_lines[0])
    assert isinstance(payload, dict)
    for service in ("bot", "agent", "file_manager", "builds"):
        assert payload[service]["available"] is False
