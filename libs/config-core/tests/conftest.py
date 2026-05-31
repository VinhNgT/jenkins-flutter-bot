"""Config-core test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect all config I/O to a temp directory."""
    monkeypatch.setenv("JTB_DATA_DIR", str(tmp_path))
    return tmp_path
