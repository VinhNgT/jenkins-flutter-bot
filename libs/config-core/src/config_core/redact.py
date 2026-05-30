"""Unified secret redaction for logging and string output.

Provides a process-global ``SecretRedactor`` that scrubs registered secret
values from log output.  Services auto-register secrets via
``ServiceSettings.load()`` (for ``secret: True`` fields) and can manually
register ad-hoc values with ``register_secret()``.

Usage::

    from config_core import install_log_redaction, register_secret

    # At process start (in cli() / main), after logging.basicConfig():
    install_log_redaction()

    # Secrets from ServiceSettings are auto-registered on .load().
    # For ad-hoc secrets not in Pydantic models:
    register_secret(os.environ.get("SERVICE_AUTH_TOKEN", ""))
"""

from __future__ import annotations

import logging
import re

_REDACTED = "***"

# Don't redact very short values — they generate too many false positives
# in normal log text (e.g. "true", "8080").
_MIN_SECRET_LEN = 6


class SecretRedactor:
    """Process-global secret value registry and redaction engine.

    Holds a set of known secret strings and compiles a regex pattern
    (longest-first) to replace them with ``***``.  The pattern is
    lazily rebuilt whenever a new secret is registered.
    """

    def __init__(self) -> None:
        self._secrets: set[str] = set()
        self._pattern: re.Pattern[str] | None = None

    def clear(self) -> None:
        """Reset all registered secrets and the compiled pattern.

        Used by test fixtures to prevent secret accumulation across tests
        in the process-global singleton.
        """
        self._secrets.clear()
        self._pattern = None

    def register(self, value: str) -> None:
        """Add a secret value to the redaction set.

        Values shorter than ``_MIN_SECRET_LEN`` are ignored to avoid
        false positives in normal log text.
        """
        if not value or len(value) < _MIN_SECRET_LEN:
            return
        if value not in self._secrets:
            self._secrets.add(value)
            self._pattern = None  # Invalidate cached regex

    @property
    def pattern(self) -> re.Pattern[str] | None:
        """Lazily compiled regex matching all registered secrets."""
        if self._pattern is None and self._secrets:
            # Escape each secret for regex, longest first to avoid partial matches
            escaped = sorted(
                (re.escape(s) for s in self._secrets), key=len, reverse=True
            )
            self._pattern = re.compile("|".join(escaped))
        return self._pattern

    def redact(self, text: str) -> str:
        """Replace all registered secrets in *text* with ``***``."""
        p = self.pattern
        if p is None:
            return text
        return p.sub(_REDACTED, text)


# Module-level singleton — shared across the entire process.
_redactor = SecretRedactor()


def register_secret(value: str) -> None:
    """Register a secret value for automatic log redaction.

    Values shorter than 6 characters are silently ignored.
    """
    _redactor.register(value)


def redact(text: str) -> str:
    """Replace all registered secrets in *text* with ``***``."""
    return _redactor.redact(text)


def _redact_arg(value: object) -> object:
    """Redact a single log argument.

    String values are redacted directly.  Non-string values (e.g. lists,
    dicts passed as ``%s`` args) are stringified and checked — if a
    registered secret is found, the stringified form is returned with
    secrets replaced.  Primitives that cannot contain secrets are
    returned unchanged to avoid unnecessary ``str()`` conversions.
    """
    if isinstance(value, str):
        return _redactor.redact(value)
    # Primitives can never embed a secret substring.
    if isinstance(value, (int, float, bool, type(None))):
        return value
    # For complex types (list, dict, set, …), stringify and check.
    p = _redactor.pattern
    if p is None:
        return value
    text = str(value)
    if p.search(text):
        return p.sub(_REDACTED, text)
    return value


class RedactingLogFilter(logging.Filter):
    """Logging filter that scrubs registered secrets from all log output.

    Redacts both the format string (``record.msg``) and all arguments
    (``record.args``) — including non-string types like lists and dicts
    whose ``str()`` representation may embed secrets — so secret values
    are never written to disk.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if _redactor.pattern is None:
            return True

        # Redact the message template
        if isinstance(record.msg, str):
            record.msg = _redactor.redact(record.msg)

        # Redact arguments (both string and non-string)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: _redact_arg(v) for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(_redact_arg(a) for a in record.args)
        return True


def install_log_redaction() -> None:
    """Install the redacting filter on all root logger handlers.

    Filters on a *logger* only apply to records emitted directly by
    that logger — records propagated from child loggers skip parent
    logger filters entirely.  Installing on *handlers* ensures every
    log record is redacted regardless of which logger emitted it.

    Call once in each service's ``cli()`` entrypoint, **after**
    ``logging.basicConfig()``.
    """
    f = RedactingLogFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(f)
