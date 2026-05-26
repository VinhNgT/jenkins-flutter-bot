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


class RedactingLogFilter(logging.Filter):
    """Logging filter that scrubs registered secrets from all log output.

    Redacts both the format string (``record.msg``) and any string
    arguments (``record.args``) so secrets are never written to disk.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if _redactor.pattern is None:
            return True

        # Redact the message template
        if isinstance(record.msg, str):
            record.msg = _redactor.redact(record.msg)

        # Redact string arguments
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: _redactor.redact(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _redactor.redact(a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


def install_log_redaction() -> None:
    """Install the redacting filter on the root logger.

    Call once in each service's ``cli()`` entrypoint, **after**
    ``logging.basicConfig()``.  All loggers inherit from root, so
    every log statement across every module is automatically filtered.
    """
    logging.getLogger().addFilter(RedactingLogFilter())
