"""Tests for config-core schema helpers — save/load, secret handling, coercion."""

import json
import os
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import Field, ValidationError

from config_core.schema import (
    ServiceSettings,
    format_validation_error,
    get_secret_keys,
    read_masked_config,
    save_config_with_merge,
    _coerce_payload_types,
)


# ---------------------------------------------------------------------------
# Test model (mirrors real ServiceSettings subclasses)
# ---------------------------------------------------------------------------


class _TestSettings(ServiceSettings):
    config_path: ClassVar[Path] = Path("/app/data/test.json")

    bot_token: str = Field(
        default="",
        json_schema_extra={"json_key": "telegram.bot_token", "secret": True},
    )
    app_name: str = Field(
        default="My App",
        json_schema_extra={"json_key": "telegram.app_name"},
    )
    timeout: int = Field(
        default=30,
        json_schema_extra={"json_key": "jenkins.timeout"},
    )
    enabled: bool = Field(
        default=True,
        json_schema_extra={"json_key": "flags.enabled"},
    )


class _RequiredSettings(ServiceSettings):
    """Settings with a required field (no default) for error formatting tests."""

    config_path: ClassVar[Path] = Path("/app/data/required.json")

    api_key: str = Field(
        json_schema_extra={"json_key": "api_key", "secret": True},
    )
    name: str = Field(
        json_schema_extra={"json_key": "name"},
    )


@pytest.fixture(autouse=True)
def isolate_config(tmp_path):
    """Redirect all config I/O to a temp directory."""
    os.environ["JFB_DATA_DIR"] = str(tmp_path)
    yield tmp_path
    os.environ.pop("JFB_DATA_DIR", None)


# ---------------------------------------------------------------------------
# get_secret_keys
# ---------------------------------------------------------------------------


def test_get_secret_keys():
    keys = get_secret_keys(_TestSettings)
    assert "telegram.bot_token" in keys
    assert "telegram.app_name" not in keys


def test_get_secret_keys_empty():
    """Model with no secret fields → empty list."""

    class _NoSecrets(ServiceSettings):
        config_path: ClassVar[Path] = Path("/app/data/nosecret.json")
        name: str = "default"

    assert get_secret_keys(_NoSecrets) == []


# ---------------------------------------------------------------------------
# save_config_with_merge
# ---------------------------------------------------------------------------


def test_save_preserves_existing(isolate_config):
    """Partial payload doesn't nuke existing keys."""
    config_path = Path("/app/data/test.json")
    resolved = isolate_config / "test.json"

    # Write existing config
    resolved.write_text(json.dumps({"telegram": {"app_name": "Old App", "bot_token": "secret123"}}))

    # Save only app_name — bot_token should be preserved
    save_config_with_merge(_TestSettings, config_path, {"telegram": {"app_name": "New App"}})

    result = json.loads(resolved.read_text())
    assert result["telegram"]["app_name"] == "New App"
    assert result["telegram"]["bot_token"] == "secret123"


def test_save_strips_empty_secrets(isolate_config):
    """None/empty secret not written to disk — preserves existing."""
    config_path = Path("/app/data/test.json")
    resolved = isolate_config / "test.json"

    # Existing config with a real secret
    resolved.write_text(json.dumps({"telegram": {"bot_token": "real-secret"}}))

    # Frontend sends None for the secret (masked) — it should NOT overwrite
    save_config_with_merge(_TestSettings, config_path, {"telegram": {"bot_token": None, "app_name": "Updated"}})

    result = json.loads(resolved.read_text())
    assert result["telegram"]["bot_token"] == "real-secret"
    assert result["telegram"]["app_name"] == "Updated"


def test_save_keeps_real_secret(isolate_config):
    """Non-empty secret is written to disk."""
    config_path = Path("/app/data/test.json")
    resolved = isolate_config / "test.json"

    save_config_with_merge(_TestSettings, config_path, {"telegram": {"bot_token": "new-token"}})

    result = json.loads(resolved.read_text())
    assert result["telegram"]["bot_token"] == "new-token"


def test_save_creates_file_from_scratch(isolate_config):
    """Saving to a non-existent file creates it."""
    config_path = Path("/app/data/test.json")
    resolved = isolate_config / "test.json"
    assert not resolved.exists()

    save_config_with_merge(_TestSettings, config_path, {"telegram": {"app_name": "Brand New"}})

    assert resolved.exists()
    result = json.loads(resolved.read_text())
    assert result["telegram"]["app_name"] == "Brand New"


# ---------------------------------------------------------------------------
# read_masked_config
# ---------------------------------------------------------------------------


def test_read_masked_hides_secrets(isolate_config):
    resolved = isolate_config / "test.json"
    resolved.write_text(json.dumps({"telegram": {"bot_token": "secret123", "app_name": "My App"}}))

    result = read_masked_config(_TestSettings, Path("/app/data/test.json"))

    assert result["values"]["telegram"]["bot_token"] is None
    assert result["values"]["telegram"]["app_name"] == "My App"


def test_read_masked_reports_lengths(isolate_config):
    resolved = isolate_config / "test.json"
    resolved.write_text(json.dumps({"telegram": {"bot_token": "secret123"}}))

    result = read_masked_config(_TestSettings, Path("/app/data/test.json"))

    assert result["secret_lengths"]["telegram.bot_token"] == len("secret123")


def test_read_masked_missing_file(isolate_config):
    """Graceful empty response when config file doesn't exist."""
    result = read_masked_config(_TestSettings, Path("/app/data/test.json"))

    assert result["values"] == {}
    assert result["secret_lengths"]["telegram.bot_token"] is False


def test_read_masked_unset_secret(isolate_config):
    """Unset secret reports False, not a length."""
    resolved = isolate_config / "test.json"
    resolved.write_text(json.dumps({"telegram": {"app_name": "Test"}}))

    result = read_masked_config(_TestSettings, Path("/app/data/test.json"))
    assert result["secret_lengths"]["telegram.bot_token"] is False


# ---------------------------------------------------------------------------
# _coerce_payload_types
# ---------------------------------------------------------------------------


def test_coerce_bool():
    payload = {"flags": {"enabled": "true"}}
    _coerce_payload_types(_TestSettings, payload)
    assert payload["flags"]["enabled"] is True


def test_coerce_bool_false():
    payload = {"flags": {"enabled": "false"}}
    _coerce_payload_types(_TestSettings, payload)
    assert payload["flags"]["enabled"] is False


def test_coerce_int():
    payload = {"jenkins": {"timeout": "42"}}
    _coerce_payload_types(_TestSettings, payload)
    assert payload["jenkins"]["timeout"] == 42


def test_coerce_skips_empty_string():
    payload = {"jenkins": {"timeout": ""}}
    _coerce_payload_types(_TestSettings, payload)
    assert payload["jenkins"]["timeout"] == ""


def test_coerce_already_correct_type():
    """Non-string values are left alone."""
    payload = {"jenkins": {"timeout": 42}}
    _coerce_payload_types(_TestSettings, payload)
    assert payload["jenkins"]["timeout"] == 42


# ---------------------------------------------------------------------------
# format_validation_error
# ---------------------------------------------------------------------------


def test_format_validation_error_missing_fields():
    try:
        _RequiredSettings(api_key="x")  # missing 'name'
        pytest.fail("Should have raised")
    except ValidationError as exc:
        msg = format_validation_error(exc)
        assert "Missing required fields" in msg or "name" in msg


def test_format_validation_error_non_pydantic():
    msg = format_validation_error(ValueError("something broke"))
    assert msg == "something broke"
