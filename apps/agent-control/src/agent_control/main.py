"""Agent-control — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from config_core import setup_service_logging

from .manager import AgentManager, StartupError
from .routers.control import router as control_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage agent lifecycle on startup/shutdown."""
    try:
        await app.state.manager.start()
    except StartupError:
        logger.warning("Agent not auto-started: %s", app.state.manager.status()["last_error"])

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error during shutdown")


def create_app() -> FastAPI:
    """Create the FastAPI app hosting agent control routes."""
    app = FastAPI(
        title="agent-control",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.manager = AgentManager()

    @app.exception_handler(StartupError)
    async def handle_startup_error(
        request: Request, exc: StartupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(control_router)
    return app


def cli() -> None:
    """CLI entry point for the agent-control service."""
    setup_service_logging()
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9091,
    )
