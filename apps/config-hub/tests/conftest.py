"""Config-hub test fixtures."""

from __future__ import annotations

import httpx
import pytest

from config_hub.config import HubBootstrap
from config_hub.main import create_app
from config_hub.manager import ConfigHubManager


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect all config I/O to a temp directory.

    Also sets JFB_DEV_MODE=true so the default no-auth-configured path
    falls through to the dev bypass instead of the production fail-closed
    503.  Individual tests that need production behaviour should override
    or unset JFB_DEV_MODE themselves.
    """
    monkeypatch.setenv("JFB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JFB_DEV_MODE", "true")


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
    return test_app


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
