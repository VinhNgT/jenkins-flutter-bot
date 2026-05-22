"""Tests for HubClient — config-hub HTTP client."""

import pytest
import httpx

from tg_admin_bot.client import HubClient


def _hub_client(handler) -> HubClient:
    """Create a HubClient backed by MockTransport."""
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return HubClient("http://config-hub:9000", client=client)


# ---------------------------------------------------------------------------
# Service status
# ---------------------------------------------------------------------------


class TestServiceStatus:
    async def test_get_service_status(self):
        def handler(request: httpx.Request):
            assert "/api/services/status" in str(request.url)
            return httpx.Response(200, json={
                "bot": {"running": True},
                "agent": {"running": False},
            })

        client = _hub_client(handler)
        status = await client.get_service_status()
        assert status["bot"]["running"] is True
        assert status["agent"]["running"] is False
        await client.close()


# ---------------------------------------------------------------------------
# Service actions
# ---------------------------------------------------------------------------


class TestServiceAction:
    async def test_start(self):
        def handler(request: httpx.Request):
            assert request.method == "POST"
            assert "/api/services/bot/start" in str(request.url)
            return httpx.Response(200, json={"running": True})

        client = _hub_client(handler)
        result = await client.service_action("bot", "start")
        assert result["running"] is True
        await client.close()

    async def test_stop(self):
        def handler(request: httpx.Request):
            assert "/api/services/bot/stop" in str(request.url)
            return httpx.Response(200, json={"running": False})

        client = _hub_client(handler)
        result = await client.service_action("bot", "stop")
        assert result["running"] is False
        await client.close()


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------


class TestExportImport:
    async def test_export_tarball(self):
        def handler(request: httpx.Request):
            assert "/api/export/tarball" in str(request.url)
            return httpx.Response(200, content=b"fake-tarball-data")

        client = _hub_client(handler)
        data = await client.export_tarball()
        assert data == b"fake-tarball-data"
        await client.close()

    async def test_import_tarball(self):
        received_content_type = []

        def handler(request: httpx.Request):
            # Verify multipart upload
            content_type = request.headers.get("content-type", "")
            received_content_type.append(content_type)
            return httpx.Response(200, json={
                "applied": ["BOT_TOKEN → bot:telegram.bot_token"],
                "skipped_empty": [],
                "unrecognized": [],
            })

        client = _hub_client(handler)
        result = await client.import_tarball(b"tarball-data")
        assert len(result["applied"]) == 1
        assert "multipart" in received_content_type[0]
        await client.close()


# ---------------------------------------------------------------------------
# Jenkinsfile
# ---------------------------------------------------------------------------


class TestJenkinsfile:
    async def test_get_jenkinsfile(self):
        def handler(request: httpx.Request):
            assert "/api/jenkinsfile" in str(request.url)
            return httpx.Response(200, json={"content": "pipeline {}"})

        client = _hub_client(handler)
        result = await client.get_jenkinsfile()
        assert result["content"] == "pipeline {}"
        await client.close()


# ---------------------------------------------------------------------------
# Drive OAuth
# ---------------------------------------------------------------------------


class TestDriveOAuth:
    async def test_get_drive_status(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={"connected": True})

        client = _hub_client(handler)
        result = await client.get_drive_status()
        assert result["connected"] is True
        await client.close()

    async def test_save_drive_config(self):
        received = {}

        def handler(request: httpx.Request):
            import json
            received.update(json.loads(request.content))
            return httpx.Response(200, json={})

        client = _hub_client(handler)
        await client.save_drive_config("client-id-123", "client-secret-456")
        assert received["drive"]["client_id"] == "client-id-123"
        assert received["drive"]["client_secret"] == "client-secret-456"
        await client.close()

    async def test_exchange_drive_code(self):
        def handler(request: httpx.Request):
            assert "/api/drive/connect/exchange" in str(request.url)
            return httpx.Response(200)

        client = _hub_client(handler)
        await client.exchange_drive_code("auth-code-xyz", "cid", "csec")
        await client.close()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    async def test_connection_error_propagates(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        client = _hub_client(handler)
        with pytest.raises(httpx.ConnectError):
            await client.get_service_status()
        await client.close()

    async def test_non_200_raises(self):
        def handler(request: httpx.Request):
            return httpx.Response(500, text="Internal Server Error")

        client = _hub_client(handler)
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_service_status()
        await client.close()
