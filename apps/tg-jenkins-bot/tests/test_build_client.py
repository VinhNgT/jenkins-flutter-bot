"""Tests for BuildClient — the bot's async HTTP client for build-manager and file-manager."""

import pytest
import httpx

from tg_jenkins_bot.build_client import BuildClient, BuildClientError, BuildResult


def _build_client(handler) -> BuildClient:
    """Create a BuildClient backed by MockTransport.

    The same mock transport handles both build-manager and file-manager
    requests — the test handler inspects the URL to route.
    """
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return BuildClient(
        "http://build-manager:9010",
        "http://file-manager:9092",
        client=client,
    )


# ---------------------------------------------------------------------------
# trigger_build
# ---------------------------------------------------------------------------


class TestTriggerBuild:
    async def test_success(self):
        def handler(request: httpx.Request):
            return httpx.Response(
                200, json={"request_id": "abc123", "status": "queued"}
            )

        client = _build_client(handler)
        result = await client.trigger_build("main", "http://bot/cb")
        assert result["request_id"] == "abc123"
        assert result["status"] == "queued"
        await client.close()

    async def test_success_with_app_name(self):
        import json

        payload = {}

        def handler(request: httpx.Request):
            nonlocal payload
            payload = json.loads(request.read())
            return httpx.Response(
                200, json={"request_id": "abc123", "status": "queued"}
            )

        client = _build_client(handler)
        result = await client.trigger_build("main", "http://bot/cb", app_name="My App")
        assert result["request_id"] == "abc123"
        assert result["status"] == "queued"
        assert payload["app_name"] == "My App"
        await client.close()

    async def test_connection_error(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        client = _build_client(handler)
        with pytest.raises(BuildClientError) as exc_info:
            await client.trigger_build("main", "http://bot/cb")
        assert "responding" in exc_info.value.user_message.lower()
        await client.close()

    async def test_non_200(self):
        def handler(request: httpx.Request):
            return httpx.Response(502, json={"detail": "Queue full"})

        client = _build_client(handler)
        with pytest.raises(BuildClientError) as exc_info:
            await client.trigger_build("main", "http://bot/cb")
        assert "Queue full" in exc_info.value.user_message
        await client.close()


# ---------------------------------------------------------------------------
# cancel_build
# ---------------------------------------------------------------------------


class TestCancelBuild:
    async def test_success(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={"status": "cancelled"})

        client = _build_client(handler)
        result = await client.cancel_build("req1")
        assert result["status"] == "cancelled"
        await client.close()

    async def test_error_returns_error_status(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        client = _build_client(handler)
        result = await client.cancel_build("req1")
        assert result["status"] == "error"
        await client.close()


# ---------------------------------------------------------------------------
# get_recent_builds (queries file-manager)
# ---------------------------------------------------------------------------


class TestGetRecentBuilds:
    async def test_parses_response(self):
        def handler(request: httpx.Request):
            return httpx.Response(
                200,
                json={
                    "builds": [
                        {
                            "request_id": "req1",
                            "branch": "main",
                            "commit_hash": "a" * 40,
                            "result": "success",
                            "triggered_at": 1.0,
                            "completed_at": 2.0,
                            "download_url": "https://example.com/file.apk",
                        }
                    ]
                },
            )

        client = _build_client(handler)
        builds = await client.get_recent_builds(count=5)
        assert len(builds) == 1
        assert isinstance(builds[0], BuildResult)
        assert builds[0].branch == "main"
        assert builds[0].download_url == "https://example.com/file.apk"
        await client.close()

    async def test_non_200_returns_empty(self):
        def handler(request: httpx.Request):
            return httpx.Response(500, text="Error")

        client = _build_client(handler)
        builds = await client.get_recent_builds()
        assert builds == []
        await client.close()

    async def test_network_error_returns_empty(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        client = _build_client(handler)
        builds = await client.get_recent_builds()
        assert builds == []
        await client.close()


# ---------------------------------------------------------------------------
# get_build_status
# ---------------------------------------------------------------------------


class TestGetBuildStatus:
    async def test_success(self):
        def handler(request: httpx.Request):
            return httpx.Response(200, json={"pending_count": 1})

        client = _build_client(handler)
        status = await client.get_build_status()
        assert status["pending_count"] == 1
        await client.close()

    async def test_fallback(self):
        def handler(request: httpx.Request):
            raise httpx.ConnectError("Connection refused")

        client = _build_client(handler)
        status = await client.get_build_status()
        assert status == {"pending_count": 0}
        await client.close()
