"""Tests for config_store — secret stripping, merging, and schema helpers."""

import json

import pytest

from config_hub.config_store import (
    load_json,
    write_json,
    strip_secrets,
    secrets_set,
    clean_secrets_from_payload,
    extract_secret_fields,
    extract_defaults,
    extract_required_fields,
    _nested_remove,
)


# ---------------------------------------------------------------------------
# load_json / write_json
# ---------------------------------------------------------------------------


class TestJsonIO:
    def test_load_json_missing_file(self, tmp_path):
        assert load_json(tmp_path / "nonexistent.json") == {}

    def test_load_json_none_path(self):
        assert load_json(None) == {}

    def test_load_json_existing(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text(json.dumps({"key": "value"}))
        assert load_json(f) == {"key": "value"}

    def test_write_json(self, tmp_path):
        f = tmp_path / "test.json"
        write_json(f, {"key": "value"})
        assert json.loads(f.read_text())["key"] == "value"

    def test_write_json_creates_parents(self, tmp_path):
        f = tmp_path / "sub" / "dir" / "test.json"
        write_json(f, {"nested": True})
        assert f.exists()

    def test_write_json_none_path_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            write_json(None, {"key": "value"})


# ---------------------------------------------------------------------------
# strip_secrets
# ---------------------------------------------------------------------------


class TestStripSecrets:
    def test_replaces_with_none(self):
        data = {"telegram": {"bot_token": "secret123"}}
        result = strip_secrets(data, ("telegram.bot_token",))
        assert result["telegram"]["bot_token"] is None

    def test_preserves_non_secrets(self):
        data = {"telegram": {"bot_token": "secret", "app_name": "MyApp"}}
        result = strip_secrets(data, ("telegram.bot_token",))
        assert result["telegram"]["app_name"] == "MyApp"

    def test_unset_secret_stays_none(self):
        data = {"telegram": {"app_name": "MyApp"}}
        result = strip_secrets(data, ("telegram.bot_token",))
        assert result == data


# ---------------------------------------------------------------------------
# secrets_set
# ---------------------------------------------------------------------------


class TestSecretsSet:
    def test_set_returns_length(self):
        data = {"telegram": {"bot_token": "abc123"}}
        result = secrets_set(data, ("telegram.bot_token",))
        assert result["telegram.bot_token"] == 8

    def test_unset_returns_false(self):
        data = {}
        result = secrets_set(data, ("telegram.bot_token",))
        assert result["telegram.bot_token"] is False

    def test_empty_string_returns_false(self):
        data = {"telegram": {"bot_token": ""}}
        result = secrets_set(data, ("telegram.bot_token",))
        assert result["telegram.bot_token"] is False


# ---------------------------------------------------------------------------
# clean_secrets_from_payload
# ---------------------------------------------------------------------------


class TestCleanSecrets:
    def test_removes_none_secrets(self):
        incoming = {"telegram": {"bot_token": None, "app_name": "Test"}}
        result = clean_secrets_from_payload(incoming, ("telegram.bot_token",))
        assert "bot_token" not in result.get("telegram", {})
        assert result["telegram"]["app_name"] == "Test"

    def test_removes_empty_string_secrets(self):
        incoming = {"telegram": {"bot_token": ""}}
        result = clean_secrets_from_payload(incoming, ("telegram.bot_token",))
        assert "bot_token" not in result.get("telegram", {})

    def test_preserves_real_values(self):
        incoming = {"telegram": {"bot_token": "new-token"}}
        result = clean_secrets_from_payload(incoming, ("telegram.bot_token",))
        assert result["telegram"]["bot_token"] == "new-token"


# ---------------------------------------------------------------------------
# Schema extractors
# ---------------------------------------------------------------------------


class TestSchemaExtractors:
    def _schema(self):
        return {
            "fields": [
                {"key": "telegram.bot_token", "secret": True, "required": True, "default": ""},
                {"key": "telegram.app_name", "secret": False, "required": False, "default": "MyApp"},
                {"key": "jenkins.url", "secret": False, "required": True, "default": ""},
            ]
        }

    def test_extract_secret_fields(self):
        result = extract_secret_fields(self._schema())
        assert result == ("telegram.bot_token",)

    def test_extract_secret_fields_none_schema(self):
        assert extract_secret_fields(None) == ()

    def test_extract_defaults(self):
        result = extract_defaults(self._schema())
        assert result["telegram.app_name"] == "MyApp"
        assert "telegram.bot_token" not in result  # empty default

    def test_extract_required_fields(self):
        result = extract_required_fields(self._schema())
        assert "telegram.bot_token" in result
        assert "jenkins.url" in result
        assert "telegram.app_name" not in result


# ---------------------------------------------------------------------------
# _nested_remove
# ---------------------------------------------------------------------------


class TestNestedRemove:
    def test_removes_deep_key(self):
        data = {"a": {"b": {"c": 1, "d": 2}}}
        _nested_remove(data, "a.b.c")
        assert data == {"a": {"b": {"d": 2}}}

    def test_removes_top_level_key(self):
        data = {"a": 1, "b": 2}
        _nested_remove(data, "a")
        assert data == {"b": 2}

    def test_missing_key_noop(self):
        data = {"a": 1}
        _nested_remove(data, "b.c.d")
        assert data == {"a": 1}

    def test_non_dict_intermediate_noop(self):
        data = {"a": "string"}
        _nested_remove(data, "a.b")
        assert data == {"a": "string"}
