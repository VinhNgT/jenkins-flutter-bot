"""Tests for env_io — export/import, tarball, env parsing edge cases."""

import io
import json
import tarfile

import pytest

from config_core.schema import ConfigDocument

from config_hub.env_io import (
    _needs_quoting,
    _serialize_value,
    _build_env_lines,
    _parse_env_content,
    _build_env_lookup,
    build_export_tarball,
    generate_env_files,
    import_tarball,
    ImportResult,
)
from config_hub.config_store import write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field_def(
    key: str,
    env_var: str,
    required: bool = False,
    secret: bool = False,
    default: str = "",
    value_type: str = "str",
    label: str = "",
) -> dict:
    return {
        "key": key,
        "env_var": env_var,
        "label": label or key.replace(".", " ").title(),
        "group": "General",
        "required": required,
        "secret": secret,
        "default": default,
        "value_type": value_type,
    }


def _schema(*fields) -> dict:
    return {"title": "Test", "description": "test schema", "fields": list(fields)}


# ---------------------------------------------------------------------------
# _needs_quoting / _serialize_value
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_no_quoting_simple(self):
        assert not _needs_quoting("hello")

    def test_quoting_with_spaces(self):
        assert _needs_quoting("hello world")

    def test_quoting_with_special_chars(self):
        assert _needs_quoting("value$var")
        assert _needs_quoting("it's")
        assert _needs_quoting('say "hi"')

    def test_serialize_none(self):
        assert _serialize_value(None, "str") == ""

    def test_serialize_bool_true(self):
        assert _serialize_value(True, "bool") == "true"

    def test_serialize_bool_false(self):
        assert _serialize_value(False, "bool") == "false"

    def test_serialize_list(self):
        assert _serialize_value([1, 2, 3], "list[int]") == "1,2,3"

    def test_serialize_string(self):
        assert _serialize_value("hello", "str") == "hello"


# ---------------------------------------------------------------------------
# _build_env_lines
# ---------------------------------------------------------------------------


class TestBuildEnvLines:
    def test_basic_field_with_value(self):
        schema = _schema(
            _field_def("telegram.bot_token", "TELEGRAM_BOT_TOKEN"),
        )
        config = {"telegram": {"bot_token": "abc123"}}
        lines, warnings = _build_env_lines(schema, config, "Bot")
        text = "\n".join(lines)
        assert "TELEGRAM_BOT_TOKEN=abc123" in text
        assert warnings == []

    def test_empty_required_field_warns(self):
        schema = _schema(
            _field_def("api_key", "API_KEY", required=True),
        )
        lines, warnings = _build_env_lines(schema, {}, "Service")
        text = "\n".join(lines)
        assert "API_KEY=" in text
        assert len(warnings) == 1

    def test_empty_optional_commented_out(self):
        schema = _schema(
            _field_def("name", "APP_NAME", default="MyApp"),
        )
        lines, _ = _build_env_lines(schema, {}, "Service")
        text = "\n".join(lines)
        assert "# APP_NAME=MyApp" in text

    def test_no_schema_warns(self):
        lines, warnings = _build_env_lines(None, {}, "Service")
        assert lines == []
        assert len(warnings) == 1


# ---------------------------------------------------------------------------
# _parse_env_content
# ---------------------------------------------------------------------------


class TestParseEnvContent:
    def _lookup(self):
        return {
            "BOT_TOKEN": _field_def("telegram.bot_token", "BOT_TOKEN"),
        }

    def test_basic_parsing(self):
        """Verify env content is correctly parsed into the returned dict."""
        content = "BOT_TOKEN=abc123"
        bp, ap, fmp, applied, skipped, unrec, errors = _parse_env_content(
            content, self._lookup(), {}, {}
        )
        assert "telegram" in bp
        assert bp["telegram"]["bot_token"] == "abc123"
        assert len(applied) == 1
        assert errors == []

    def test_quoted_value(self):
        content = 'BOT_TOKEN="value with spaces"'
        bp, _, _, applied, *_ = _parse_env_content(
            content, self._lookup(), {}, {}
        )
        assert bp["telegram"]["bot_token"] == "value with spaces"

    def test_comments_skipped(self):
        content = "# This is a comment\n\n# Another\nBOT_TOKEN=abc"
        bp, *_ = _parse_env_content(content, self._lookup(), {}, {})
        assert bp["telegram"]["bot_token"] == "abc"

    def test_invalid_syntax(self):
        content = "THIS IS NOT VALID"
        *_, errors = _parse_env_content(content, self._lookup(), {}, {})
        assert len(errors) == 1
        assert "invalid syntax" in errors[0]

    def test_unrecognized_env_var(self):
        content = "UNKNOWN_VAR=value"
        *_, unrec, errors = _parse_env_content(content, self._lookup(), {}, {})
        assert len(unrec) == 1
        assert "UNKNOWN_VAR" in unrec[0]

    def test_empty_value_skipped(self):
        content = "BOT_TOKEN="
        _, _, _, applied, skipped, *_ = _parse_env_content(
            content, self._lookup(), {}, {}
        )
        assert len(skipped) == 1
        assert len(applied) == 0

    def test_export_prefix_handled(self):
        content = "export BOT_TOKEN=abc123"
        bp, *_ = _parse_env_content(content, self._lookup(), {}, {})
        assert bp["telegram"]["bot_token"] == "abc123"


# ---------------------------------------------------------------------------
# Tarball roundtrip
# ---------------------------------------------------------------------------


class TestTarball:
    def test_build_export_tarball(self):
        env_files = {"bot.env": "BOT_TOKEN=abc\n", "agent.env": "AGENT=xyz\n"}
        data = build_export_tarball(env_files)
        assert len(data) > 0

        # Verify tarball contents
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = tar.getnames()
            assert "env/bot.env" in names
            assert "env/agent.env" in names

    def test_build_export_tarball_with_oauth(self, tmp_path):
        oauth_path = tmp_path / "oauth.json"
        oauth_path.write_text('{"token": "xyz"}')

        data = build_export_tarball({"bot.env": "TOKEN=abc\n"}, oauth_token_path=oauth_path)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            assert "env/oauth.json" in tar.getnames()

    def test_build_export_tarball_no_oauth(self):
        data = build_export_tarball({"bot.env": "TOKEN=abc\n"}, oauth_token_path=None)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            assert "env/oauth.json" not in tar.getnames()

    def test_tarball_roundtrip(self, tmp_path):
        """Export → import → config files written with correct values."""
        bot_schema = _schema(
            _field_def("telegram.bot_token", "TELEGRAM_BOT_TOKEN"),
        )
        agent_schema = _schema(
            _field_def("agent.name", "AGENT_NAME"),
        )

        # Create env files
        env_files = {
            "bot.env": "TELEGRAM_BOT_TOKEN=secret_token\n",
            "agent.env": "AGENT_NAME=my-agent\n",
        }
        tarball = build_export_tarball(env_files)

        # Create config paths
        bot_path = tmp_path / "bot.json"
        agent_path = tmp_path / "agent.json"

        result = import_tarball(
            tarball,
            bot_schema=bot_schema,
            agent_schema=agent_schema,
            bot_config_path=bot_path,
            agent_config_path=agent_path,
        )

        assert len(result.applied) == 2
        assert result.parse_errors == []

        # Verify config files were actually written
        bot_config = json.loads(bot_path.read_text())
        assert bot_config["telegram"]["bot_token"] == "secret_token"

        agent_config = json.loads(agent_path.read_text())
        assert agent_config["agent"]["name"] == "my-agent"

    def test_import_invalid_tarball(self, tmp_path):
        result = import_tarball(
            b"this is not a tarball",
            bot_schema=None,
            agent_schema=None,
            bot_config_path=tmp_path / "bot.json",
            agent_config_path=tmp_path / "agent.json",
        )
        assert len(result.parse_errors) == 1
        assert "tarball" in result.parse_errors[0].lower()

    def test_import_oauth_json(self, tmp_path):
        # Build tarball with oauth.json
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            oauth = b'{"access_token": "xyz"}'
            info = tarfile.TarInfo(name="env/oauth.json")
            info.size = len(oauth)
            tar.addfile(info, io.BytesIO(oauth))

        oauth_dest = tmp_path / "oauth.json"
        result = import_tarball(
            buf.getvalue(),
            bot_schema=None,
            agent_schema=None,
            bot_config_path=None,
            agent_config_path=None,
            oauth_dest_path=oauth_dest,
        )
        assert result.oauth_imported is True
        assert oauth_dest.exists()
        assert json.loads(oauth_dest.read_text())["access_token"] == "xyz"


# ---------------------------------------------------------------------------
# generate_env_files
# ---------------------------------------------------------------------------


class TestGenerateEnvFiles:
    def test_generates_all_files(self):
        bot_schema = _schema(_field_def("token", "BOT_TOKEN"))
        agent_schema = _schema(_field_def("name", "AGENT_NAME"))
        files, warnings = generate_env_files(
            bot_config={"token": "abc"},
            agent_config={"name": "my-agent"},
            bot_schema=bot_schema,
            agent_schema=agent_schema,
        )
        assert "bot.env" in files
        assert "agent.env" in files
        assert "BOT_TOKEN=abc" in files["bot.env"]
        assert "AGENT_NAME=my-agent" in files["agent.env"]
