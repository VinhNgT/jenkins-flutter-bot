"""Tests for env_io — export/import, tarball, env parsing edge cases."""

from __future__ import annotations

import io
import tarfile

from service_hub.env_io import (
    _needs_quoting,
    _serialize_value,
    _build_env_lines,
    _parse_env_content,
    build_export_tarball,
    generate_compose_env,
    import_tarball,
)


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


class TestBuildEnvLines:
    def test_basic_field_with_value(self):
        schema = _schema(
            _field_def("agent.name", "AGENT_NAME"),
        )
        config = {"agent": {"name": "my-agent"}}
        lines, warnings = _build_env_lines(schema, config, "Agent")
        text = "\n".join(lines)
        assert "AGENT_NAME=my-agent" in text
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


class TestParseEnvContent:
    def _lookup(self):
        return {
            "AGENT_NAME": _field_def("agent.name", "AGENT_NAME"),
        }

    def test_basic_parsing(self):
        """Verify env content is correctly parsed into the returned dict."""
        content = "AGENT_NAME=my-agent"
        ap, fmp, bu_p, applied, skipped, unrec, errors = _parse_env_content(
            content, self._lookup(), {}, {}
        )
        assert "agent" in ap
        assert ap["agent"]["name"] == "my-agent"
        assert len(applied) == 1
        assert errors == []

    def test_quoted_value(self):
        content = 'AGENT_NAME="value with spaces"'
        ap, *_ = _parse_env_content(content, self._lookup(), {}, {})
        assert ap["agent"]["name"] == "value with spaces"

    def test_comments_skipped(self):
        content = "# This is a comment\n\n# Another\nAGENT_NAME=my-agent"
        ap, *_ = _parse_env_content(content, self._lookup(), {}, {})
        assert ap["agent"]["name"] == "my-agent"

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
        content = "AGENT_NAME="
        _, _, _, applied, skipped, *_ = _parse_env_content(
            content, self._lookup(), {}, {}
        )
        assert len(skipped) == 1
        assert len(applied) == 0

    def test_export_prefix_handled(self):
        content = "export AGENT_NAME=my-agent"
        ap, *_ = _parse_env_content(content, self._lookup(), {}, {})
        assert ap["agent"]["name"] == "my-agent"


class TestTarball:
    def test_build_export_tarball(self):
        compose_env = "AGENT_NAME=my-agent\n"
        json_configs = {"agent-control": {"agent": {"name": "my-agent"}}}
        data = build_export_tarball(compose_env, json_configs)
        assert len(data) > 0

        # Verify tarball contents
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = tar.getnames()
            assert "compose.env" in names
            assert "data/agent.json" in names

    def test_build_export_tarball_with_oauth(self):
        oauth_token = {"access_token": "xyz"}
        data = build_export_tarball(
            "TOKEN=abc\n",
            {"agent-control": {"agent": {"name": "my-agent"}}},
            oauth_token=oauth_token,
        )
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = tar.getnames()
            assert "data/oauth.json" in names

    def test_build_export_tarball_no_oauth(self):
        data = build_export_tarball(
            "TOKEN=abc\n", {"agent-control": {"agent": {"name": "my-agent"}}}, oauth_token=None
        )
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = tar.getnames()
            assert "data/oauth.json" not in names

    def test_tarball_roundtrip(self):
        """Export → import → config files written with correct values."""
        agent_schema = _schema(
            _field_def("agent.name", "AGENT_NAME"),
        )
        file_manager_schema = _schema(
            _field_def("storage.backend", "STORAGE_BACKEND"),
        )

        compose_env = "AGENT_NAME=my-agent\nSTORAGE_BACKEND=google_drive\n"
        json_configs = {"agent-control": {}, "file-manager": {}}
        tarball = build_export_tarball(compose_env, json_configs)

        result = import_tarball(
            tarball,
            agent_schema=agent_schema,
            file_manager_schema=file_manager_schema,
        )

        assert len(result.applied) == 2
        assert result.parse_errors == []

        assert result.configs["agent-control"]["agent"]["name"] == "my-agent"
        assert result.configs["file-manager"]["storage"]["backend"] == "google_drive"

    def test_import_invalid_tarball(self):
        result = import_tarball(
            b"this is not a tarball",
            agent_schema=None,
        )
        assert len(result.parse_errors) == 1
        assert "tarball" in result.parse_errors[0].lower()

    def test_import_oauth_json(self):
        # Build tarball with oauth.json
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            oauth = b'{"access_token": "xyz"}'
            info = tarfile.TarInfo(name="data/oauth.json")
            info.size = len(oauth)
            tar.addfile(info, io.BytesIO(oauth))

        result = import_tarball(
            buf.getvalue(),
            agent_schema=None,
        )
        assert result.oauth_imported is True


class TestGenerateComposeEnv:
    def test_generates_compose_env(self):
        agent_schema = _schema(_field_def("name", "AGENT_NAME"))
        compose_env_str, warnings = generate_compose_env(
            agent_config={"name": "my-agent"},
            agent_schema=agent_schema,
        )
        assert "AGENT_NAME=my-agent" in compose_env_str
        assert warnings == []
