"""Config-UI entry point — FastAPI app factory and CLI."""

from __future__ import annotations

import logging

import uvicorn

from .app import create_app

logger = logging.getLogger(__name__)


def cli() -> None:
    """CLI entry point for the config-ui service."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=9000)
