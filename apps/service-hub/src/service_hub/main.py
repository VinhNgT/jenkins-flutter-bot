"""Service Hub entry point — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from config_core import setup_service_logging

from .manager import ServiceHubManager
from .routers import config, drive, export, jenkinsfile, services, version

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage hub lifecycle on startup/shutdown."""
    await app.state.manager.start()

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error stopping manager")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="service-hub",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # --- Manager ---
    manager = ServiceHubManager()
    app.state.manager = manager

    # --- API routers ---
    app.include_router(config.router)
    app.include_router(services.router)
    app.include_router(export.router)
    app.include_router(drive.router)
    app.include_router(jenkinsfile.router)
    app.include_router(version.router)

    return app


def cli() -> None:
    """CLI entry point for the service-hub service."""
    setup_service_logging()
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9000,
    )
