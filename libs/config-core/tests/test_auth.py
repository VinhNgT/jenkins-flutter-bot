"""Tests for inter-service bearer token authentication."""

from __future__ import annotations

import httpx
import pytest
from fastapi import Depends, FastAPI

from config_core.auth import get_service_auth_headers, verify_service_token


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with service token auth."""
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(verify_service_token)])
    async def protected() -> dict[str, str]:
        return {"status": "ok"}

    return app


class TestVerifyServiceToken:
    """Inbound token verification (FastAPI dependency)."""

    @pytest.fixture
    def app(self) -> FastAPI:
        return _make_app()

    @pytest.fixture
    async def client(self, app: FastAPI):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c

    async def test_no_token_configured_passes_through(
        self, client: httpx.AsyncClient, monkeypatch,
    ) -> None:
        """With no SERVICE_AUTH_TOKEN set, all requests pass."""
        monkeypatch.delenv("SERVICE_AUTH_TOKEN", raising=False)
        resp = await client.get("/protected")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_valid_token_passes(
        self, client: httpx.AsyncClient, monkeypatch,
    ) -> None:
        """Correct Bearer token returns 200."""
        monkeypatch.setenv("SERVICE_AUTH_TOKEN", "secret-token-123")
        resp = await client.get(
            "/protected",
            headers={"Authorization": "Bearer secret-token-123"},
        )
        assert resp.status_code == 200

    async def test_missing_header_returns_401(
        self, client: httpx.AsyncClient, monkeypatch,
    ) -> None:
        """No Authorization header → 401."""
        monkeypatch.setenv("SERVICE_AUTH_TOKEN", "secret-token-123")
        resp = await client.get("/protected")
        assert resp.status_code == 401
        assert "Missing" in resp.json()["detail"]

    async def test_wrong_token_returns_403(
        self, client: httpx.AsyncClient, monkeypatch,
    ) -> None:
        """Wrong Bearer token → 403."""
        monkeypatch.setenv("SERVICE_AUTH_TOKEN", "secret-token-123")
        resp = await client.get(
            "/protected",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 403
        assert "Invalid" in resp.json()["detail"]

    async def test_non_bearer_scheme_returns_401(
        self, client: httpx.AsyncClient, monkeypatch,
    ) -> None:
        """Authorization header without 'Bearer ' prefix → 401."""
        monkeypatch.setenv("SERVICE_AUTH_TOKEN", "secret-token-123")
        resp = await client.get(
            "/protected",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401


class TestGetServiceAuthHeaders:
    """Outbound header generation."""

    def test_returns_empty_when_no_token(self, monkeypatch) -> None:
        monkeypatch.delenv("SERVICE_AUTH_TOKEN", raising=False)
        assert get_service_auth_headers() == {}

    def test_returns_bearer_header_when_token_set(self, monkeypatch) -> None:
        monkeypatch.setenv("SERVICE_AUTH_TOKEN", "my-secret")
        headers = get_service_auth_headers()
        assert headers == {"Authorization": "Bearer my-secret"}
