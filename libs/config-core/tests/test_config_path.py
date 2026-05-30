"""Smoke tests for config-core path resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

from config_core.schema import ServiceSettings, resolve_config_path


class _TestSettings(ServiceSettings):
    """Minimal settings subclass for testing."""

    config_path: ClassVar[Path] = Path("/app/data/test.json")

    example: str = "default"


def test_resolve_config_path_without_override(monkeypatch) -> None:
    """Without JFB_DATA_DIR, paths pass through unchanged."""
    monkeypatch.delenv("JFB_DATA_DIR", raising=False)
    assert resolve_config_path(Path("/app/data/bot.json")) == Path("/app/data/bot.json")


def test_resolve_config_path_with_override(tmp_path, monkeypatch) -> None:
    """With JFB_DATA_DIR, parent dir is replaced but filename preserved."""
    monkeypatch.setenv("JFB_DATA_DIR", str(tmp_path))
    result = resolve_config_path(Path("/app/data/bot.json"))
    assert result == tmp_path / "bot.json"


def test_service_settings_load_from_redirected_path(tmp_path) -> None:
    """ServiceSettings.load() reads from the redirected path."""
    config_file = tmp_path / "test.json"
    config_file.write_text(json.dumps({"example": "from_json"}))

    settings = _TestSettings.load()
    assert settings.example == "from_json"


def test_service_settings_load_defaults_when_no_file() -> None:
    """ServiceSettings.load() uses defaults when no config file exists."""
    settings = _TestSettings.load()
    assert settings.example == "default"
