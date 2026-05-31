"""Unit tests for the Telegram Web App API router."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Request
import httpx
import pytest

from tg_bot.bot.context import BotContext
from tg_bot.build_client import BuildClientError
from tg_bot.config import BotSettings
from tg_bot.main import create_app
from tg_bot.routers.webapp import stream_active_builds, WebAppUser


def _generate_valid_init_data(token: str, chat_id: int | None = None) -> str:
    """Generate a valid signed Telegram Web App initData string."""
    user = {"id": 67890, "first_name": "Alice", "username": "alice_tg"}
    init_params = {
        "user": json.dumps(user),
        "auth_date": str(int(time.time())),
        "query_id": "AAH6854",
    }
    if chat_id is not None:
        init_params["chat"] = json.dumps({"id": chat_id, "type": "group"})

    sorted_params = sorted(init_params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)

    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    sig = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    init_params["hash"] = sig
    return urllib.parse.urlencode(init_params)


def _generate_valid_init_data_with_start_param(token: str, start_param: str) -> str:
    """Generate a valid signed Telegram Web App initData string with start_param."""
    user = {"id": 67890, "first_name": "Alice", "username": "alice_tg"}
    init_params = {
        "user": json.dumps(user),
        "auth_date": str(int(time.time())),
        "query_id": "AAH6854",
        "start_param": start_param,
    }

    sorted_params = sorted(init_params.items())
    check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)

    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    sig = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    init_params["hash"] = sig
    return urllib.parse.urlencode(init_params)


@pytest.fixture
def mock_build_client():
    client = AsyncMock()
    client.trigger_build = AsyncMock(
        return_value={"request_id": "req-999", "status": "queued"}
    )
    client.cancel_build = AsyncMock(return_value={"status": "cancelled"})
    client.get_recent_builds = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.username = "test_bot"
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def app_with_mocks(mock_build_client, mock_bot):
    """Create app with mocked dependencies."""
    app = create_app()

    config = BotSettings(
        allowed_chat_ids=[-12345, -67890],
        app_name="TestApp",
        branches={"Stable Release": "main", "Testing Version": "develop"},
        bot_service_url="http://bot:9090",
        build_manager_url="http://build-manager:9010",
        file_manager_url="http://file-manager:9092",
        webapp_url="https://example.com/webapp",
    )

    ctx = BotContext(
        config=config,
        build_client=mock_build_client,
        bot=mock_bot,
    )

    # Replace manager and bot context
    app.state.manager._bot_context = ctx
    app.state.manager._config = config
    app.state.manager._build_client = mock_build_client

    return app


@pytest.fixture
async def test_client(app_with_mocks):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_mocks),
        base_url="http://test",
        follow_redirects=True,
    ) as c:
        yield c


async def test_webapp_config_preview_bypass(app_with_mocks, test_client) -> None:
    """Test standard config access using preview mode with credentials."""
    app_with_mocks.state.manager.bootstrap.enable_browser_preview = True
    app_with_mocks.state.manager.bootstrap.browser_auth_username = "preview_user"
    app_with_mocks.state.manager.bootstrap.browser_auth_password = "secret123"

    response = await test_client.get(
        "/api/webapp/config",
        headers={"X-Telegram-Init-Data": "preview"},
        auth=("preview_user", "secret123"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "TestApp"
    assert data["branches"] == [
        {"label": "Stable Release", "ref": "main"},
        {"label": "Testing Version", "ref": "develop"},
    ]



async def test_webapp_preview_bypass_rejected_when_disabled(app_with_mocks) -> None:
    """Test that preview bypass is rejected when ENABLE_BROWSER_PREVIEW is disabled."""
    app_with_mocks.state.manager.bootstrap.telegram_bot_token = "production_token_1234"
    app_with_mocks.state.manager.bootstrap.enable_browser_preview = False

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_mocks), base_url="http://test",
    ) as c:
        response = await c.get(
            "/api/webapp/config",
            headers={"X-Telegram-Init-Data": "preview"},
        )
        assert response.status_code == 401
        assert "disabled" in response.json()["detail"]


async def test_webapp_preview_bypass_valid_credentials_works(app_with_mocks) -> None:
    """Test that preview bypass works when ENABLE_BROWSER_PREVIEW is enabled and correct Basic Auth is provided."""
    app_with_mocks.state.manager.bootstrap.telegram_bot_token = "production_token_1234"
    app_with_mocks.state.manager.bootstrap.enable_browser_preview = True
    app_with_mocks.state.manager.bootstrap.browser_auth_username = "preview_user"
    app_with_mocks.state.manager.bootstrap.browser_auth_password = "secret123"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_mocks), base_url="http://test",
    ) as c:
        response = await c.get(
            "/api/webapp/config",
            headers={"X-Telegram-Init-Data": "preview"},
            auth=("preview_user", "secret123"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["app_name"] == "TestApp"


async def test_webapp_preview_bypass_invalid_credentials_returns_401(app_with_mocks) -> None:
    """Test that preview bypass is rejected with 401 when incorrect Basic Auth is provided."""
    app_with_mocks.state.manager.bootstrap.telegram_bot_token = "production_token_1234"
    app_with_mocks.state.manager.bootstrap.enable_browser_preview = True
    app_with_mocks.state.manager.bootstrap.browser_auth_username = "preview_user"
    app_with_mocks.state.manager.bootstrap.browser_auth_password = "secret123"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_mocks), base_url="http://test",
    ) as c:
        response = await c.get(
            "/api/webapp/config",
            headers={"X-Telegram-Init-Data": "preview"},
            auth=("preview_user", "wrong_pass"),
        )
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Basic"


async def test_webapp_preview_bypass_missing_credentials_returns_401(app_with_mocks) -> None:
    """Test that preview bypass is rejected with 401 when Basic Auth is missing."""
    app_with_mocks.state.manager.bootstrap.telegram_bot_token = "production_token_1234"
    app_with_mocks.state.manager.bootstrap.enable_browser_preview = True
    app_with_mocks.state.manager.bootstrap.browser_auth_username = "preview_user"
    app_with_mocks.state.manager.bootstrap.browser_auth_password = "secret123"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_mocks), base_url="http://test",
    ) as c:
        response = await c.get(
            "/api/webapp/config",
            headers={"X-Telegram-Init-Data": "preview"},
        )
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Basic"


async def test_webapp_stream_includes_triggered_by_id(app_with_mocks) -> None:
    """Verify that triggered_by_id is serialized in the stream response."""
    ctx = app_with_mocks.state.manager.bot_context

    class FakeResponse:
        status_code = 200
        async def aiter_lines(self):
            yield "event: builds"
            yield "data: [{\"request_id\": \"req-999\", \"branch\": \"main\", \"triggered_at\": 1700000000.0, \"triggered_by\": \"Alice\", \"triggered_by_id\": 67890, \"estimated_duration\": 120}]"
            yield ""

    class MockStreamContext:
        async def __aenter__(self):
            return FakeResponse()
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    ctx.build_client.stream_builds = MagicMock(return_value=MockStreamContext())

    mock_request = MagicMock(spec=Request)
    mock_request.is_disconnected = AsyncMock(return_value=False)

    user = WebAppUser(
        chat_id=-12345,
        user_id=12345,
        first_name="Alice",
        username="alice_tg",
    )

    gen = stream_active_builds(
        request=mock_request,
        manager=app_with_mocks.state.manager,
        user=user,
    )

    first_event = await gen.__anext__()
    assert first_event.event == "builds"
    assert len(first_event.data) == 1
    assert first_event.data[0]["triggered_by_id"] == 67890



async def test_webapp_config_real_hmac(test_client) -> None:
    """Test config access using valid HMAC signature."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=-12345)
    response = await test_client.get(
        "/api/webapp/config",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "TestApp"


async def test_webapp_config_invalid_hmac(test_client) -> None:
    """Test config access using invalid HMAC signature."""
    init_data = _generate_valid_init_data(token="WRONG-TOKEN", chat_id=-12345)
    response = await test_client.get(
        "/api/webapp/config",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert response.status_code == 401
    assert "Authentication failed" in response.json()["detail"]


async def test_webapp_config_unauthorized_chat(test_client) -> None:
    """Test config access from unauthorized chat."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=-99999)
    response = await test_client.get(
        "/api/webapp/config",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "group_not_authorized"
    assert "is not authorized" in detail["message"]
    assert detail["chat_id"] == -99999
    assert detail["bot_username"] == "test_bot"


async def test_webapp_config_real_hmac_query_param(test_client) -> None:
    """Test config access using valid HMAC signature via query parameter."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=-12345)
    response = await test_client.get(
        f"/api/webapp/config?init_data={urllib.parse.quote(init_data)}",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "TestApp"


async def test_webapp_config_invalid_hmac_query_param(test_client) -> None:
    """Test config access fails with invalid HMAC signature via query param."""
    init_data = _generate_valid_init_data(token="WRONG-TOKEN", chat_id=-12345)
    response = await test_client.get(
        f"/api/webapp/config?init_data={urllib.parse.quote(init_data)}",
    )
    assert response.status_code == 401
    assert "Authentication failed" in response.json()["detail"]


async def test_webapp_config_unauthorized_chat_query_param(test_client) -> None:
    """Test config access fails for unauthorized chat via query param."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=-99999)
    response = await test_client.get(
        f"/api/webapp/config?init_data={urllib.parse.quote(init_data)}",
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "group_not_authorized"


@pytest.mark.asyncio
async def test_webapp_stream_direct(app_with_mocks) -> None:
    """Test the SSE stream endpoint event generator directly."""
    ctx = app_with_mocks.state.manager.bot_context

    class FakeResponse:
        status_code = 200
        async def aiter_lines(self):
            yield "event: builds"
            yield "data: [{\"request_id\": \"req-stream-test\", \"branch\": \"main\", \"triggered_at\": 1700000000.0, \"triggered_by\": \"Alice\", \"triggered_by_id\": 67890, \"estimated_duration\": 120}]"
            yield ""
            yield "event: recent"
            yield "data: [{\"request_id\": \"req-recent-1\", \"branch\": \"main\", \"commit_hash\": \"abcdef0\", \"result\": \"success\", \"triggered_at\": 1715500000.0, \"completed_at\": 1715501000.0, \"download_url\": \"https://example.com/apk\", \"file_size\": 1024, \"build_number\": 1}]"
            yield ""

    class MockStreamContext:
        async def __aenter__(self):
            return FakeResponse()
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    ctx.build_client.stream_builds = MagicMock(return_value=MockStreamContext())

    mock_request = MagicMock(spec=Request)
    mock_request.is_disconnected = AsyncMock(return_value=False)

    user = WebAppUser(
        chat_id=-12345,
        user_id=12345,
        first_name="Alice",
        username="alice_tg",
    )

    gen = stream_active_builds(
        request=mock_request,
        manager=app_with_mocks.state.manager,
        user=user,
    )

    first_event = await gen.__anext__()

    assert first_event.event == "builds"
    assert isinstance(first_event.data, list)
    assert any(b["request_id"] == "req-stream-test" for b in first_event.data)

    second_event = await gen.__anext__()
    assert second_event.event == "recent"
    assert isinstance(second_event.data, list)
    assert len(second_event.data) == 1
    assert second_event.data[0]["request_id"] == "req-recent-1"


@pytest.mark.asyncio
async def test_webapp_stream_integration(app_with_mocks) -> None:
    ctx = app_with_mocks.state.manager.bot_context

    class FakeResponse:
        status_code = 200
        async def aiter_lines(self):
            yield "event: builds"
            yield "data: [{\"request_id\": \"req-integration\", \"branch\": \"main\", \"triggered_at\": 1700000000.0, \"triggered_by\": \"Alice\", \"triggered_by_id\": 67890, \"estimated_duration\": 120}]"
            yield ""

    class MockStreamContext:
        async def __aenter__(self):
            return FakeResponse()
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    ctx.build_client.stream_builds = MagicMock(return_value=MockStreamContext())

    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=-12345)

    # Track call count so is_disconnected returns False first, True second.
    call_count = 0

    async def fake_is_disconnected(self):
        nonlocal call_count
        call_count += 1
        return call_count > 3

    transport = httpx.ASGITransport(app=app_with_mocks)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with (
            patch("starlette.requests.Request.is_disconnected", fake_is_disconnected),
        ):
            resp = await client.get(
                f"/api/webapp/stream?init_data={urllib.parse.quote(init_data)}",
            )

    assert resp.status_code == 200

    # Verify SSE response headers
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"

    # Parse SSE wire format from the response body
    body = resp.text
    data_lines = [
        line[len("data:") :].strip()
        for line in body.splitlines()
        if line.startswith("data:")
    ]
    assert len(data_lines) > 0, f"No SSE data frames in response body:\n{body}"
    payload = json.loads(data_lines[0])
    assert isinstance(payload, list)
    assert any(b["request_id"] == "req-integration" for b in payload)


@pytest.mark.asyncio
async def test_webapp_stream_rejects_invalid_auth(app_with_mocks) -> None:
    """Verify the SSE /stream endpoint rejects invalid authentication."""


    bad_init_data = _generate_valid_init_data(token="WRONG-TOKEN", chat_id=-12345)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_mocks),
        base_url="http://test",
    ) as client:
        resp = await client.get(
            f"/api/webapp/stream?init_data={urllib.parse.quote(bad_init_data)}",
        )
        assert resp.status_code == 401
        assert "Authentication failed" in resp.json()["detail"]


async def test_webapp_trigger_build_happy_path(
    test_client, mock_build_client, mock_bot
) -> None:
    """Test successful build trigger from Web App."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=-12345)

    response = await test_client.post(
        "/api/webapp/trigger",
        headers={"X-Telegram-Init-Data": init_data},
        json={"branch": "main"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "request_id": "req-999"}

    # Verify build-manager call
    mock_build_client.trigger_build.assert_called_once_with(
        branch="main",
        callback_url="http://bot:9090/callback/build-result",
        app_name="TestApp",
        label="Stable Release",
        triggered_by="Alice",
        triggered_by_id=67890,
        notify=True,
        chat_id=-12345,
    )

    # No trigger notification — only build result notifications exist
    mock_bot.send_message.assert_not_called()


async def test_webapp_trigger_duplicate_blocked(
    test_client, mock_build_client
) -> None:
    """Test that starting a build on a branch already building is blocked."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=-12345)

    mock_build_client.trigger_build.side_effect = BuildClientError(
        detail="HTTP 409 Conflict: branch already building",
        user_message="Branch already building",
    )

    response = await test_client.post(
        "/api/webapp/trigger",
        headers={"X-Telegram-Init-Data": init_data},
        json={"branch": "main"},
    )

    assert response.status_code == 400
    assert "already in progress" in response.json()["detail"]
    mock_build_client.trigger_build.assert_called_once()


async def test_webapp_cancel_build_happy_path(
    test_client, mock_build_client
) -> None:
    """Test successful build cancellation from Web App."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=-12345)

    mock_build_client.get_pending_builds.return_value = {
        "req-999": {
            "branch": "main",
            "triggered_at": 1700000000.0,
            "label": "Stable Release",
            "triggered_by": "Alice",
            "triggered_by_id": 67890,
            "chat_id": -12345,
        }
    }

    response = await test_client.post(
        "/api/webapp/cancel",
        headers={"X-Telegram-Init-Data": init_data},
        json={"request_id": "req-999"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    # Verify build-manager cancel call
    mock_build_client.cancel_build.assert_called_once_with("req-999")


async def test_webapp_start_param_parsing(test_client, mock_build_client, mock_bot) -> None:
    """Test that chat_id is correctly extracted from start_param (deep link)."""
    init_data = _generate_valid_init_data_with_start_param(
        token="123456:test-token", start_param="-12345"
    )

    response = await test_client.post(
        "/api/webapp/trigger",
        headers={"X-Telegram-Init-Data": init_data},
        json={"branch": "main"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "request_id": "req-999"}

    # No trigger notification — only build result notifications exist
    mock_bot.send_message.assert_not_called()


async def test_webapp_trigger_build_notify_false(
    test_client, mock_build_client, mock_bot
) -> None:
    """Test that notify=false stores the build with notify=False."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=-12345)

    response = await test_client.post(
        "/api/webapp/trigger",
        headers={"X-Telegram-Init-Data": init_data},
        json={"branch": "main", "notify": False},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True

    # Verify trigger_build was called with notify=False
    mock_build_client.trigger_build.assert_called_once()
    assert mock_build_client.trigger_build.call_args[1]["notify"] is False

    # No messages sent
    mock_bot.send_message.assert_not_called()


async def test_webapp_private_chat_rejected_via_start_param(test_client) -> None:
    """Test that Web App triggers in private chats (positive chat IDs) are rejected."""
    init_data = _generate_valid_init_data_with_start_param(
        token="123456:test-token", start_param="67890"
    )

    response = await test_client.post(
        "/api/webapp/trigger",
        headers={"X-Telegram-Init-Data": init_data},
        json={"branch": "main"},
    )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "private_chat_disabled"
    assert "Private chats are disabled" in detail["message"]
    assert detail["bot_username"] == "test_bot"


async def test_webapp_private_chat_rejected_via_fallback(test_client) -> None:
    """Test that Web App triggers with no group context fall back to private user ID and are rejected."""
    # Generating without chat_id defaults to Alice's user.id 67890 (positive)
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=None)

    response = await test_client.post(
        "/api/webapp/trigger",
        headers={"X-Telegram-Init-Data": init_data},
        json={"branch": "main"},
    )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "private_chat_disabled"
    assert "Private chats are disabled" in detail["message"]
    assert detail["bot_username"] == "test_bot"


async def test_webapp_cancel_unauthorized_user_blocked(test_client, mock_build_client) -> None:
    """Test that cancelling a build triggered by someone else is blocked with HTTP 403."""
    init_data = _generate_valid_init_data(token="123456:test-token", chat_id=-12345)

    mock_build_client.get_pending_builds.return_value = {
        "req-999": {
            "branch": "main",
            "triggered_at": 1700000000.0,
            "label": "Stable Release",
            "triggered_by": "Bob",
            "triggered_by_id": 99999,
            "chat_id": -12345,
        }
    }

    # Alice (user_id 67890 in init_data) tries to cancel Bob's build
    response = await test_client.post(
        "/api/webapp/cancel",
        headers={"X-Telegram-Init-Data": init_data},
        json={"request_id": "req-999"},
    )

    assert response.status_code == 403
    assert (
        "Only the user who triggered the build can cancel it"
        in response.json()["detail"]
    )

    # Verify build is NOT cancelled
    mock_build_client.cancel_build.assert_not_called()


@pytest.mark.xfail(
    reason="Vite handles asset hashing via content-hashed filenames; "
           "the old {{APP_VERSION}}/{{ASSET_HASH}} template markers no longer exist",
    strict=True,
)
async def test_webapp_index_replaces_version_and_hash(test_client) -> None:
    """Test that served HTML has APP_VERSION and ASSET_HASH replaced."""
    response = await test_client.get("/webapp")
    assert response.status_code == 200

    html = response.text
    # Placeholders must be fully replaced — no raw template markers
    assert "{{APP_VERSION}}" not in html
    assert "{{ASSET_HASH}}" not in html

    # Cache-busting query strings should use the 8-char hex asset hash
    import re

    hash_matches = re.findall(r'\?v=([0-9a-f]{8})', html)
    assert len(hash_matches) >= 3, "Expected at least 3 ?v=<hash> occurrences (CSS + 2 JS)"
    # All query strings should use the same hash
    assert len(set(hash_matches)) == 1, "All asset hashes should be identical"


async def test_webapp_index_has_no_application_cache_control_headers(test_client) -> None:
    """Test that the index response has no application-level Cache-Control headers."""
    response = await test_client.get("/webapp")
    assert response.status_code == 200
    assert "cache-control" not in response.headers
