"""Build Manager — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, Request
from starlette.responses import JSONResponse

from config_core import setup_service_logging, verify_service_token

from .manager import BuildManager, StartupError
from .routers.builds import router as builds_router
from .routers.control import router as control_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — initialise and tear down shared resources."""
    try:
        await app.state.manager.start()
    except StartupError:
        logger.warning(
            "Build manager not auto-started: %s",
            app.state.manager.status()["last_error"],
        )

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error stopping build manager")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # Only expose Swagger docs in dev mode — hidden in production.
    docs_url = "/api/docs" if os.environ.get("JFB_DEV_MODE") else None

    app = FastAPI(
        title="build-manager",
        docs_url=docs_url,
        lifespan=lifespan,
        dependencies=[Depends(verify_service_token)],
    )

    app.state.manager = BuildManager()

    @app.exception_handler(StartupError)
    async def handle_startup_error(
        request: Request, exc: StartupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(control_router)
    app.include_router(builds_router)

    return app


def cli() -> None:
    """CLI entry point for the build-manager service."""
    setup_service_logging()
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9010,
    )
