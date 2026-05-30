"""Tests for secret redaction engine and log filter."""

from __future__ import annotations

import logging

from config_core.redact import (
    RedactingLogFilter,
    SecretRedactor,
    install_log_redaction,
    redact,
    register_secret,
    _redactor,
)


class TestSecretRedactor:
    """Unit tests for the SecretRedactor class."""

    def test_empty_redactor_is_passthrough(self) -> None:
        r = SecretRedactor()
        assert r.redact("no secrets here") == "no secrets here"

    def test_register_and_redact(self) -> None:
        r = SecretRedactor()
        r.register("my-api-key-123")
        assert r.redact("token is my-api-key-123 ok") == "token is *** ok"

    def test_ignores_short_values(self) -> None:
        """Values shorter than 6 chars are not redacted (too many false positives)."""
        r = SecretRedactor()
        r.register("abc")
        assert r.redact("value is abc here") == "value is abc here"

    def test_exactly_six_chars_is_registered(self) -> None:
        r = SecretRedactor()
        r.register("abcdef")
        assert r.redact("key=abcdef end") == "key=*** end"

    def test_empty_string_ignored(self) -> None:
        r = SecretRedactor()
        r.register("")
        assert r.pattern is None

    def test_multiple_secrets(self) -> None:
        r = SecretRedactor()
        r.register("secret-one-111")
        r.register("secret-two-222")
        result = r.redact("a=secret-one-111 b=secret-two-222")
        assert result == "a=*** b=***"

    def test_duplicate_registration_is_idempotent(self) -> None:
        r = SecretRedactor()
        r.register("my-secret-value")
        r.register("my-secret-value")
        assert r.redact("my-secret-value") == "***"

    def test_longest_match_wins(self) -> None:
        """When one secret is a substring of another, the longer one is matched."""
        r = SecretRedactor()
        r.register("secret")
        r.register("secret-extended")
        result = r.redact("val=secret-extended")
        assert result == "val=***"

    def test_clear_resets_state(self) -> None:
        r = SecretRedactor()
        r.register("my-secret-value")
        assert r.pattern is not None
        r.clear()
        assert r.pattern is None
        assert r.redact("my-secret-value") == "my-secret-value"

    def test_regex_special_chars_escaped(self) -> None:
        """Secrets with regex metacharacters are escaped properly."""
        r = SecretRedactor()
        r.register("secret+value(1)")
        assert r.redact("key=secret+value(1)") == "key=***"

    def test_pattern_lazy_rebuild(self) -> None:
        """Pattern is invalidated when a new secret is added."""
        r = SecretRedactor()
        r.register("first-secret")
        first_pattern = r.pattern
        r.register("second-secret")
        # Pattern should have been invalidated
        second_pattern = r.pattern
        assert first_pattern is not second_pattern


class TestModuleLevelAPI:
    """Tests for the module-level register_secret() and redact() functions."""

    def setup_method(self) -> None:
        _redactor.clear()

    def teardown_method(self) -> None:
        _redactor.clear()

    def test_register_and_redact_module_level(self) -> None:
        register_secret("global-secret-val")
        assert redact("token=global-secret-val") == "token=***"

    def test_redact_without_secrets_is_passthrough(self) -> None:
        assert redact("normal log line") == "normal log line"


class TestRedactingLogFilter:
    """Tests for the logging filter integration."""

    def setup_method(self) -> None:
        _redactor.clear()

    def teardown_method(self) -> None:
        _redactor.clear()

    def test_filter_redacts_message(self) -> None:
        register_secret("log-secret-abc")
        f = RedactingLogFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="auth: log-secret-abc", args=None, exc_info=None,
        )
        f.filter(record)
        assert record.msg == "auth: ***"

    def test_filter_redacts_string_args(self) -> None:
        register_secret("arg-secret-xyz")
        f = RedactingLogFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="token: %s", args=("arg-secret-xyz",), exc_info=None,
        )
        f.filter(record)
        assert record.args == ("***",)

    def test_filter_redacts_dict_args(self) -> None:
        register_secret("dict-secret-key")
        f = RedactingLogFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="%(token)s", args=None, exc_info=None,
        )
        # Set dict args after construction to bypass Python 3.14's
        # stricter LogRecord.__init__ validation of mapping args.
        record.args = {"token": "dict-secret-key"}
        f.filter(record)
        assert record.args == {"token": "***"}

    def test_filter_passthrough_without_secrets(self) -> None:
        """No registered secrets → filter is a no-op."""
        f = RedactingLogFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="clean message", args=None, exc_info=None,
        )
        assert f.filter(record) is True
        assert record.msg == "clean message"

    def test_filter_redacts_complex_args(self) -> None:
        """Non-string args (dicts, lists) whose str() contains a secret."""
        register_secret("nested-secret-val")
        f = RedactingLogFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="data: %s",
            args=({"key": "nested-secret-val"},),
            exc_info=None,
        )
        f.filter(record)
        # The dict arg should be stringified with the secret replaced
        assert "nested-secret-val" not in str(record.args)

    def test_filter_leaves_primitives_alone(self) -> None:
        """int/float/bool args are never converted to strings."""
        register_secret("irrelevant-secret")
        f = RedactingLogFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="count: %d, flag: %s",
            args=(42, True),
            exc_info=None,
        )
        f.filter(record)
        assert record.args == (42, True)


class TestInstallLogRedaction:
    """Tests for install_log_redaction()."""

    def test_installs_filter_on_root_handlers(self) -> None:
        root = logging.getLogger()
        # Add a temporary handler
        handler = logging.StreamHandler()
        root.addHandler(handler)
        try:
            initial_count = len(handler.filters)
            install_log_redaction()
            assert len(handler.filters) == initial_count + 1
            assert isinstance(handler.filters[-1], RedactingLogFilter)
        finally:
            root.removeHandler(handler)
