"""Tg-admin-bot — FastAPI app factory and CLI.

Wraps the Telegram polling bot inside a FastAPI lifespan, matching
the standard service pattern used by all other services in the stack.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from .manager import AdminBotManager, StartupError
from .routers.control import router as control_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage admin bot lifecycle on startup/shutdown."""
    try:
        await app.state.manager.start()
    except StartupError:
        logger.warning(
            "Admin bot not auto-started: %s",
            app.state.manager.status()["last_error"],
        )

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error during shutdown")


def create_app() -> FastAPI:
    """Create the FastAPI app hosting control routes."""
    app = FastAPI(title="tg-admin-bot", lifespan=lifespan)
    app.state.manager = AdminBotManager()

    @app.exception_handler(StartupError)
    async def handle_startup_error(
        request: Request, exc: StartupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(control_router)
    return app


def cli() -> None:
    """CLI entry point for the admin bot service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    uvicorn.run(create_app(), host="0.0.0.0", port=9093)
