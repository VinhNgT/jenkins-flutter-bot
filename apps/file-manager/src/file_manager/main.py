"""File-manager — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, Request
from starlette.responses import JSONResponse

from config_core import setup_service_logging, verify_service_token

from .manager import StorageManager, StartupError
from .routers import auth, files
from .routers.control import router as control_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage storage manager lifecycle on startup/shutdown."""
    try:
        await app.state.manager.start()
    except StartupError:
        logger.warning(
            "StorageManager not auto-started: %s",
            app.state.manager.status()["last_error"],
        )

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error during shutdown")


def create_app() -> FastAPI:
    """Create the FastAPI app hosting file and auth routes."""
    app = FastAPI(
        title="file-manager",
        lifespan=lifespan,
        dependencies=[Depends(verify_service_token)],
    )
    app.state.manager = StorageManager()

    @app.exception_handler(StartupError)
    async def handle_startup_error(
        request: Request, exc: StartupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # --- API routers ---
    app.include_router(control_router)
    app.include_router(files.router)
    app.include_router(auth.router)

    return app


def cli() -> None:
    """CLI entry point for the file-manager service."""
    setup_service_logging()
    uvicorn.run(create_app(), host="0.0.0.0", port=9092)
