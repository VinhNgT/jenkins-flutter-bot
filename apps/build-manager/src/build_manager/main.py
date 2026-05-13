"""Build Manager entry point — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .builds import routes as build_routes
from .control import BuildManager, control_router
from .settings import Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — initialise and tear down shared resources."""
    manager: BuildManager = app.state.manager
    try:
        manager.start()
    except Exception:
        logger.exception("Failed to start build manager on boot")
    yield
    try:
        await manager.stop()
    except Exception:
        logger.exception("Error stopping build manager")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Build Manager",
        docs_url="/api/docs",
        lifespan=_lifespan,
    )

    # --- Settings & Manager ---
    settings = Settings.from_env()
    manager = BuildManager(settings)
    app.state.manager = manager

    # Expose coordinator on app.state for build routes
    @app.middleware("http")
    async def _inject_coordinator(request, call_next):  # type: ignore[no-untyped-def]
        if manager.running:
            request.app.state.coordinator = manager.coordinator
        return await call_next(request)

    # --- Routers ---
    app.include_router(control_router)
    app.include_router(build_routes.router)

    return app


def cli() -> None:
    """CLI entry point for the build-manager service."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=9010)
