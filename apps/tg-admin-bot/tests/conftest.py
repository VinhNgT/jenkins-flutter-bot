"""Tg-admin-bot test fixtures."""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolate_config(tmp_path):
    """Redirect all config I/O to a temp directory."""
    os.environ["JFB_DATA_DIR"] = str(tmp_path)
    yield
    os.environ.pop("JFB_DATA_DIR", None)


@pytest.fixture
def app():
    from tg_admin_bot.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)
