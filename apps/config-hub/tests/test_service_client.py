"""Tests for ServiceClient — service URL routing and error handling."""

import httpx
import pytest

from config_hub.services import ServiceClient


def _service_client(handler) -> ServiceClient:
    """Create a ServiceClient backed by MockTransport."""
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return ServiceClient(
        bot_url="http://bot:9090",
        agent_url="http://agent:9091",
        file_manager_url="http://file-manager:9092",
        build_manager_url="http://builds:9010",
        client=client,
    )


# ---------------------------------------------------------------------------
# Service URL routing
# ---------------------------------------------------------------------------


class TestServiceUrlRouting:
    def test_known_services(self):
        sc = ServiceClient(
            bot_url="http://bot:9090",
            agent_url="http://agent:9091",
            file_manager_url="http://file-manager:9092",
            build_manager_url="http://builds:9010",
        )
        assert sc._service_url("bot") == "http://bot:9090"
        assert sc._service_url("agent") == "http://agent:9091"
        assert sc._service_url("file_manager") == "http://file-manager:9092"
        assert sc._service_url("builds") == "http://builds:9010"

    def test_unknown_service_raises(self):
        sc = ServiceClient(bot_url=None, agent_url=None)
        with pytest.raises(ValueError, match="Unknown service"):
            sc._service_url("nonexistent")


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------


class TestStatus:
    async def test_unconfigured_service(self):
        sc = ServiceClient(bot_url=None, agent_url=None)
        result = await sc.status("bot")
        assert result["available"] is False
        assert "not configured" in result["detail"]

    async def test_service_unreachable(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        sc = _service_client(handler)
        result = await sc.status("bot")
        assert result["available"] is False
        assert "Cannot reach" in result["detail"]

    async def test_service_ok(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={"running": True})

        sc = _service_client(handler)
        result = await sc.status("bot")
        assert result["available"] is True
        assert result["running"] is True

    async def test_service_error_response(self):
        """Service responds but with non-success status."""
        def handler(request: httpx.Request):
            return httpx.Response(400, json={"running": False, "detail": "bad config"})

        sc = _service_client(handler)
        result = await sc.status("bot")
        assert result["available"] is True
        assert "bad config" in str(result.get("detail", ""))


# ---------------------------------------------------------------------------
# start / stop / restart
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_start(self):
        def handler(request: httpx.Request):
            assert request.method == "POST"
            assert "/control/start" in str(request.url)
            return httpx.Response(200, json={"running": True})

        sc = _service_client(handler)
        result = await sc.start("bot")
        assert result["running"] is True

    async def test_stop(self):
        def handler(request: httpx.Request):
            assert "/control/stop" in str(request.url)
            return httpx.Response(200, json={"running": False})

        sc = _service_client(handler)
        result = await sc.stop("bot")
        assert result["running"] is False

    async def test_restart(self):
        def handler(request: httpx.Request):
            assert "/control/restart" in str(request.url)
            return httpx.Response(200, json={"running": True})

        sc = _service_client(handler)
        result = await sc.restart("bot")
        assert result["available"] is True


# ---------------------------------------------------------------------------
# schema()
# ---------------------------------------------------------------------------


class TestSchema:
    async def test_returns_parsed_json(self):
        schema = {"title": "Bot", "fields": [{"key": "token"}]}

        def handler(request: httpx.Request):
            return httpx.Response(200, json=schema)

        sc = _service_client(handler)
        result = await sc.schema("bot")
        assert result == schema

    async def test_unreachable_returns_none(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        sc = _service_client(handler)
        result = await sc.schema("bot")
        assert result is None

    async def test_error_returns_none(self):
        def handler(request: httpx.Request):
            return httpx.Response(500, text="Error")

        sc = _service_client(handler)
        result = await sc.schema("bot")
        assert result is None


# ---------------------------------------------------------------------------
# get_config / put_config
# ---------------------------------------------------------------------------


class TestConfigOps:
    async def test_get_config(self):
        def handler(request: httpx.Request):
            assert "/control/config" in str(request.url)
            return httpx.Response(200, json={"values": {"token": "abc"}})

        sc = _service_client(handler)
        result = await sc.get_config("bot")
        assert result["values"]["token"] == "abc"

    async def test_get_config_unreachable(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        sc = _service_client(handler)
        assert await sc.get_config("bot") is None

    async def test_put_config_proxies_payload(self):
        received = {}

        def handler(request: httpx.Request):
            import json
            received.update(json.loads(request.content))
            return httpx.Response(200, json={"status": "ok"})

        sc = _service_client(handler)
        result = await sc.put_config("bot", {"telegram": {"token": "new"}})
        assert result["status"] == "ok"
        assert received["telegram"]["token"] == "new"

    async def test_put_config_unreachable(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        sc = _service_client(handler)
        result = await sc.put_config("bot", {"key": "val"})
        assert result["status"] == "error"

    async def test_put_config_unconfigured(self):
        sc = ServiceClient(bot_url=None, agent_url=None)
        result = await sc.put_config("bot", {"key": "val"})
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    async def test_close(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={})

        sc = _service_client(handler)
        await sc.close()
        # Verify the client is closed (further requests would fail)
