"""tg-bot test fixtures."""

from __future__ import annotations

import httpx
import pytest

from tg_bot.main import create_app


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect all config I/O to a temp directory and mock bootstrap settings."""
    monkeypatch.setenv("JFB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("ADMIN_TELEGRAM_USER_IDS", "[123456,789012]")
    monkeypatch.setenv("SERVICE_HUB_URL", "http://service-hub:9000")


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
