"""build-manager test fixtures."""

from __future__ import annotations

import httpx
import pytest

from build_manager.main import create_app


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect all config I/O to a temp directory."""
    monkeypatch.setenv("JFB_DATA_DIR", str(tmp_path))


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
