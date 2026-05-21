"""Config-hub test fixtures."""

import os

import pytest
from fastapi.testclient import TestClient

from config_hub.config import HubBootstrap
from config_hub.manager import ConfigHubManager


@pytest.fixture(autouse=True)
def isolate_config(tmp_path):
    """Redirect all config I/O to a temp directory."""
    os.environ["JFB_DATA_DIR"] = str(tmp_path)
    yield
    os.environ.pop("JFB_DATA_DIR", None)


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
