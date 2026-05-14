"""Build Manager entry point — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .builds import routes as build_routes
from .control import BuildManager, control_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — initialise and tear down shared resources."""
    try:
        await app.state.manager.start()
    except Exception:
        logger.exception("Failed to start build manager on boot")

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error stopping build manager")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="build-manager",
        docs_url="/api/docs",
        lifespan=lifespan,
    )

    manager = BuildManager()
    app.state.manager = manager

    # Expose coordinator on app.state for build routes
    @app.middleware("http")
    async def _inject_coordinator(request, call_next):  # type: ignore[no-untyped-def]
        if manager.running:
            request.app.state.coordinator = manager.coordinator
        return await call_next(request)

    app.include_router(control_router)
    app.include_router(build_routes.router)

    return app


def cli() -> None:
    """CLI entry point for the build-manager service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9010,
    )
