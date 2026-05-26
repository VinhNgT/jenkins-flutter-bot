"""Shared logging setup for all JFB services.

Replaces the duplicated ``logging.basicConfig()`` + manual filter wiring
in every service's ``cli()`` entrypoint with a single function call.

Usage::

    from config_core import setup_service_logging

    def cli() -> None:
        setup_service_logging()
        # ... service-specific filters if any ...
        uvicorn.run(create_app(), ...)
"""

from __future__ import annotations

import logging
import os

from config_core.redact import install_log_redaction, register_secret


def setup_service_logging() -> None:
    """Standard logging setup for all JFB services.

    Performs four things in order:

    1. Configures ``basicConfig`` with the project-standard format
    2. Suppresses noisy ``httpx`` debug/info logs
    3. Installs ``RedactingLogFilter`` on the root logger so all log
       output is automatically scrubbed of registered secrets
    4. Registers ``SERVICE_AUTH_TOKEN`` for redaction (secrets from
       ``ServiceSettings`` are auto-registered when ``.load()`` runs)
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    install_log_redaction()
    register_secret(os.environ.get("SERVICE_AUTH_TOKEN", ""))
