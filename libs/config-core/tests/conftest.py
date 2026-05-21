"""Config-core test fixtures."""

import os

import pytest


@pytest.fixture(autouse=True)
def isolate_config(tmp_path):
    """Redirect all config I/O to a temp directory."""
    os.environ["JFB_DATA_DIR"] = str(tmp_path)
    yield
    os.environ.pop("JFB_DATA_DIR", None)
