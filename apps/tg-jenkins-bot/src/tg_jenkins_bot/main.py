"""Tg-jenkins-bot — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse

from .manager import BotManager, StartupError
from .routers.callbacks import router as callbacks_router
from .routers.control import router as control_router
from .routers.webapp import router as webapp_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage bot lifecycle on startup/shutdown."""
    try:
        await app.state.manager.start()
    except StartupError:
        logger.warning(
            "Bot not auto-started: %s", app.state.manager.status()["last_error"]
        )

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error during shutdown")


def create_app() -> FastAPI:
    """Create the FastAPI app hosting callback, control, and Web App routes."""
    app = FastAPI(title="tg-jenkins-bot", lifespan=lifespan)
    app.state.manager = BotManager()

    @app.exception_handler(StartupError)
    async def handle_startup_error(
        request: Request,
        exc: StartupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # Mount static Web App files
    static_dir = Path(__file__).parent / "webapp"
    app.mount(
        "/webapp", StaticFiles(directory=str(static_dir), html=True), name="webapp"
    )

    # API routers
    app.include_router(control_router)
    app.include_router(callbacks_router)
    app.include_router(webapp_router)
    return app


def cli() -> None:
    """CLI entry point for the tg-jenkins-bot service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9090,
    )
