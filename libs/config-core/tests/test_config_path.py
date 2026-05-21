"""Smoke tests for config-core path resolution."""

import json
import os
from pathlib import Path
from typing import ClassVar

from config_core.schema import resolve_config_path, ServiceSettings


class _TestSettings(ServiceSettings):
    """Minimal settings subclass for testing."""

    config_path: ClassVar[Path] = Path("/app/data/test.json")

    example: str = "default"


def test_resolve_config_path_without_override():
    """Without JFB_DATA_DIR, paths pass through unchanged."""
    os.environ.pop("JFB_DATA_DIR", None)
    assert resolve_config_path(Path("/app/data/bot.json")) == Path("/app/data/bot.json")


def test_resolve_config_path_with_override(tmp_path):
    """With JFB_DATA_DIR, parent dir is replaced but filename preserved."""
    os.environ["JFB_DATA_DIR"] = str(tmp_path)
    result = resolve_config_path(Path("/app/data/bot.json"))
    assert result == tmp_path / "bot.json"


def test_service_settings_load_from_redirected_path(tmp_path):
    """ServiceSettings.load() reads from the redirected path."""
    config_file = tmp_path / "test.json"
    config_file.write_text(json.dumps({"example": "from_json"}))

    settings = _TestSettings.load()
    assert settings.example == "from_json"


def test_service_settings_load_defaults_when_no_file():
    """ServiceSettings.load() uses defaults when no config file exists."""
    settings = _TestSettings.load()
    assert settings.example == "default"
