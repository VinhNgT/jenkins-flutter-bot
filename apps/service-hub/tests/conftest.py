"""Service-hub test fixtures."""

from __future__ import annotations

import httpx
import pytest

from service_hub.config import ServiceHubBootstrap
from service_hub.main import create_app
from service_hub.manager import ServiceHubManager


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect all config I/O to a temp directory."""
    monkeypatch.setenv("JTB_DATA_DIR", str(tmp_path))


@pytest.fixture
def app():
    """Create a service-hub app with injected test config."""
    test_config = ServiceHubBootstrap(
        agent_control_url=None,
        file_manager_url=None,
        build_manager_url=None,
    )
    test_app = create_app()
    test_app.state.manager = ServiceHubManager(config=test_config)
    return test_app


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
