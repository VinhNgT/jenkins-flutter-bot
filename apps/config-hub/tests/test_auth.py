"""Tests for config-hub dual authentication (Telegram + Basic Auth).

Covers the verify_admin_auth dependency across all authentication paths:
Telegram initData (primary), Basic Auth (opt-in local), dev mode bypass,
and production fail-closed behavior.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse

import httpx
import time_machine

from config_hub.config import HubBootstrap
from config_hub.main import create_app
from config_hub.manager import ConfigHubManager

# Fixed test credentials
_TEST_TOKEN = "1234567890:ABCdefGhIjKlMnOpQrStUvWxYz"
_ADMIN_USER_ID = 42
_NON_ADMIN_USER_ID = 99999
_AUTH_DATE = 1748779200  # 2025-06-01 12:00:00 UTC


def _build_init_data(
    bot_token: str = _TEST_TOKEN,
    user_id: int = _ADMIN_USER_ID,
    auth_date: int = _AUTH_DATE,
) -> str:
    """Build a correctly-signed Telegram initData string for testing."""
    user_obj = json.dumps(
        {"id": user_id, "first_name": "Admin", "last_name": "User"},
        separators=(",", ":"),
    )
    params: dict[str, str] = {
        "user": user_obj,
        "auth_date": str(auth_date),
    }
    sorted_params = sorted(params.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    params["hash"] = computed_hash
    return urllib.parse.urlencode(params)


def _make_app(
    telegram_bot_token: str | None = None,
    admin_user_ids: list[int] | None = None,
    enable_browser_preview: bool = False,
    browser_auth_username: str | None = None,
    browser_auth_password: str | None = None,
):
    """Create a config-hub app with specific auth configuration."""
    config = HubBootstrap(
        bot_control_url=None,
        agent_control_url=None,
        file_manager_url=None,
        build_manager_url=None,
        telegram_bot_token=telegram_bot_token,
        admin_telegram_user_ids=admin_user_ids or [],
        enable_browser_preview=enable_browser_preview,
        browser_auth_username=browser_auth_username,
        browser_auth_password=browser_auth_password,
    )
    app = create_app()
    app.state.manager = ConfigHubManager(config=config)
    return app


# -- Endpoint used for auth testing --
# /api/webapp-admin/version is a lightweight auth-protected route.
_AUTH_ENDPOINT = "/api/webapp-admin/version"


class TestTelegramAuth:
    """Telegram initData as primary authentication."""

    @time_machine.travel("2025-06-01 12:00:00", tick=False)
    async def test_valid_admin_init_data_grants_access(self, monkeypatch) -> None:
        app = _make_app(
            telegram_bot_token=_TEST_TOKEN,
            admin_user_ids=[_ADMIN_USER_ID],
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            init_data = _build_init_data(user_id=_ADMIN_USER_ID)
            resp = await client.get(
                _AUTH_ENDPOINT,
                headers={"X-Telegram-Init-Data": init_data},
            )
            assert resp.status_code == 200
            assert "version" in resp.json()

    @time_machine.travel("2025-06-01 12:00:00", tick=False)
    async def test_non_admin_user_id_returns_403(self, monkeypatch) -> None:
        app = _make_app(
            telegram_bot_token=_TEST_TOKEN,
            admin_user_ids=[_ADMIN_USER_ID],
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            init_data = _build_init_data(user_id=_NON_ADMIN_USER_ID)
            resp = await client.get(
                _AUTH_ENDPOINT,
                headers={"X-Telegram-Init-Data": init_data},
            )
            assert resp.status_code == 403
            assert "not authorized" in resp.json()["detail"]

    @time_machine.travel("2025-06-01 12:00:00", tick=False)
    async def test_empty_admin_list_returns_503(self, monkeypatch) -> None:
        """When no admin IDs are configured, access is rejected with a 503."""
        app = _make_app(
            telegram_bot_token=_TEST_TOKEN,
            admin_user_ids=[],
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            init_data = _build_init_data(user_id=_NON_ADMIN_USER_ID)
            resp = await client.get(
                _AUTH_ENDPOINT,
                headers={"X-Telegram-Init-Data": init_data},
            )
            assert resp.status_code == 503
            assert "Admin access not configured" in resp.json()["detail"]

    @time_machine.travel("2025-06-01 12:00:00", tick=False)
    async def test_tampered_init_data_returns_401(self, monkeypatch) -> None:
        app = _make_app(
            telegram_bot_token=_TEST_TOKEN,
            admin_user_ids=[_ADMIN_USER_ID],
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            init_data = _build_init_data(user_id=_ADMIN_USER_ID)
            # Tamper: replace hash with garbage
            params = dict(urllib.parse.parse_qsl(init_data))
            params["hash"] = "a" * 64
            tampered = urllib.parse.urlencode(params)

            resp = await client.get(
                _AUTH_ENDPOINT,
                headers={"X-Telegram-Init-Data": tampered},
            )
            assert resp.status_code == 401
            assert "Invalid" in resp.json()["detail"]

    async def test_expired_init_data_returns_401(self, monkeypatch) -> None:
        app = _make_app(
            telegram_bot_token=_TEST_TOKEN,
            admin_user_ids=[_ADMIN_USER_ID],
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Build with auth_date 2 hours ago
            old_date = int(time.time()) - 7200
            init_data = _build_init_data(auth_date=old_date)
            resp = await client.get(
                _AUTH_ENDPOINT,
                headers={"X-Telegram-Init-Data": init_data},
            )
            assert resp.status_code == 401
            assert "expired" in resp.json()["detail"]

    async def test_no_bot_token_configured_returns_503(self, monkeypatch) -> None:
        """Telegram header present but no bot token configured → 503."""
        app = _make_app(telegram_bot_token=None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                _AUTH_ENDPOINT,
                headers={"X-Telegram-Init-Data": "some_data"},
            )
            assert resp.status_code == 503
            assert "TELEGRAM_BOT_TOKEN" in resp.json()["detail"]


class TestBrowserPreviewAuth:
    """Browser preview mode and basic auth verification."""

    async def test_preview_mode_disabled_returns_401(self, monkeypatch) -> None:
        app = _make_app(
            telegram_bot_token=_TEST_TOKEN,
            enable_browser_preview=False,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                _AUTH_ENDPOINT,
                headers={"X-Telegram-Init-Data": "preview"},
            )
            assert resp.status_code == 401
            assert "disabled" in resp.json()["detail"]

    async def test_preview_mode_enabled_valid_credentials_works(self, monkeypatch) -> None:
        app = _make_app(
            telegram_bot_token=_TEST_TOKEN,
            enable_browser_preview=True,
            browser_auth_username="admin",
            browser_auth_password="password123",
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                _AUTH_ENDPOINT,
                headers={"X-Telegram-Init-Data": "preview"},
                auth=("admin", "password123"),
            )
            assert resp.status_code == 200

    async def test_preview_mode_enabled_invalid_credentials_returns_401(self, monkeypatch) -> None:
        app = _make_app(
            telegram_bot_token=_TEST_TOKEN,
            enable_browser_preview=True,
            browser_auth_username="admin",
            browser_auth_password="password123",
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                _AUTH_ENDPOINT,
                headers={"X-Telegram-Init-Data": "preview"},
                auth=("admin", "wrong_password"),
            )
            assert resp.status_code == 401
            assert resp.headers["www-authenticate"] == "Basic"

    async def test_preview_mode_enabled_missing_credentials_returns_401(self, monkeypatch) -> None:
        app = _make_app(
            telegram_bot_token=_TEST_TOKEN,
            enable_browser_preview=True,
            browser_auth_username="admin",
            browser_auth_password="password123",
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                _AUTH_ENDPOINT,
                headers={"X-Telegram-Init-Data": "preview"},
            )
            assert resp.status_code == 401
            assert resp.headers["www-authenticate"] == "Basic"


class TestOAuthCallbackExemption:
    """Drive OAuth callback must bypass all auth."""

    async def test_oauth_callback_accessible_without_auth(
        self,
        monkeypatch,
    ) -> None:
        app = _make_app(
            enable_browser_preview=True,
            browser_auth_username="admin",
            browser_auth_password="password123",
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # The callback with an error param returns 400, not 401
            resp = await client.get(
                "/api/webapp-admin/drive/oauth/callback?error=access_denied",
            )
            assert resp.status_code == 400


class TestAPINamespacing:
    """Verify that old un-namespaced paths are gone."""

    async def test_old_version_path_returns_404(self, client) -> None:
        resp = await client.get("/api/version")
        assert resp.status_code == 404

    async def test_namespaced_version_path_works(self, client) -> None:
        resp = await client.get("/api/webapp-admin/version")
        assert resp.status_code == 200
        assert "version" in resp.json()

    async def test_old_config_path_returns_404(self, client) -> None:
        resp = await client.get("/api/config")
        assert resp.status_code == 404

    async def test_webapp_admin_spa_shell(self, client) -> None:
        """The /webapp-admin path serves the SPA HTML shell."""
        resp = await client.get("/webapp-admin")
        assert resp.status_code == 200
