"""Config-hub test fixtures."""

from __future__ import annotations

import httpx
import pytest

from config_hub.config import HubBootstrap
from config_hub.dependencies import verify_admin_auth
from config_hub.main import create_app
from config_hub.manager import ConfigHubManager


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect all config I/O to a temp directory.
    """
    monkeypatch.setenv("JFB_DATA_DIR", str(tmp_path))


@pytest.fixture
def app():
    """Create a config-hub app with injected test config.

    Bypasses HubBootstrap.load() by providing a pre-built config
    with no real service URLs — all service calls will return
    'service URL not configured'.
    """
    test_config = HubBootstrap(
        bot_control_url=None,
        agent_control_url=None,
        file_manager_url=None,
        build_manager_url=None,
    )
    test_app = create_app()
    test_app.state.manager = ConfigHubManager(config=test_config)

    # Bypass authentication for testing by overriding verify_admin_auth dependency
    async def bypass_auth() -> None:
        pass

    test_app.dependency_overrides[verify_admin_auth] = bypass_auth
    return test_app


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

