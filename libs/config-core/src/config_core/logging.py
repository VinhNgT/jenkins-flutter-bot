"""Shared logging setup for all JFB services.

Replaces the duplicated ``logging.basicConfig()`` + manual filter wiring
in every service's ``cli()`` entrypoint with a single function call.

The module also provides a thread-safe in-memory ring buffer that captures
formatted, redacted log lines. Services expose this buffer via
``/control/logs`` so that the Config Hub dashboard can display live logs
without requiring ``docker.sock`` access.

Usage::

    from config_core import setup_service_logging
    from config_core.logging import get_buffer_logs

    def cli() -> None:
        setup_service_logging()
        # ... service-specific filters if any ...
        uvicorn.run(create_app(), ...)
"""

from __future__ import annotations

import collections
import logging

from config_core.redact import install_log_redaction

_MAX_LOG_LINES = 1000

_log_buffer: collections.deque[str] = collections.deque(maxlen=_MAX_LOG_LINES)


class _RingBufferHandler(logging.Handler):
    """Logging handler that stores formatted lines in a bounded deque.

    Attached to the root logger by ``setup_service_logging()``, it captures
    every log record *after* formatting and redaction filters have run.
    The deque is thread-safe for single-producer / single-consumer access
    patterns, which matches the GIL-protected logging pipeline.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            _log_buffer.append(msg)
        except Exception:
            self.handleError(record)


def get_buffer_logs() -> list[str]:
    """Return a snapshot of the in-memory log ring buffer."""
    return list(_log_buffer)


def setup_service_logging() -> None:
    """Standard logging setup for all JFB services.

    Performs four things in order:

    1. Configures ``basicConfig`` with the project-standard format
    2. Suppresses noisy ``httpx`` debug/info logs
    3. Installs ``RedactingLogFilter`` on the root logger so all log
       output is automatically scrubbed of registered secrets
    4. Attaches a ``RingBufferHandler`` to the root logger to capture
       redacted log lines in memory for the ``/control/logs`` endpoint
    """
    log_format = "%(asctime)s [%(name)s] %(levelname)s — %(message)s"

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    install_log_redaction()

    # Attach the ring buffer handler with the same format so captured
    # lines are identical to what appears on stdout.
    handler = _RingBufferHandler()
    handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(handler)
