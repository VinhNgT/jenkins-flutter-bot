"""Config-hub test fixtures."""

import os

import pytest
from fastapi.testclient import TestClient

from config_hub.config import HubBootstrap
from config_hub.manager import ConfigHubManager


@pytest.fixture(autouse=True)
def isolate_config(tmp_path):
    """Redirect all config I/O to a temp directory.

    Also sets JFB_DEV_MODE=true so the default no-auth-configured path
    falls through to the dev bypass instead of the production fail-closed
    503.  Individual tests that need production behaviour should override
    or unset JFB_DEV_MODE themselves.
    """
    os.environ["JFB_DATA_DIR"] = str(tmp_path)
    os.environ["JFB_DEV_MODE"] = "true"
    yield
    os.environ.pop("JFB_DATA_DIR", None)
    os.environ.pop("JFB_DEV_MODE", None)


@pytest.fixture
def app():
    """Create a config-hub app with injected test config.

    Bypasses HubBootstrap.load() by providing a pre-built config
    with no real service URLs — all service calls will return
    'service URL not configured'.
    """
    from config_hub.main import create_app

    test_config = HubBootstrap(
        bot_control_url=None,
        agent_control_url=None,
        file_manager_url=None,
        build_manager_url=None,
    )
    test_app = create_app()
    # Replace the manager with one using injected config
    test_app.state.manager = ConfigHubManager(config=test_config)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)
