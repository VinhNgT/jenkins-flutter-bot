"""Tg-jenkins-bot — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .manager import BotManager
from .routers.callbacks import router as callbacks_router
from .routers.control import router as control_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage bot lifecycle on startup/shutdown."""
    try:
        await app.state.manager.start()
    except Exception:
        logger.exception("Bot not auto-started")

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error during shutdown")


def create_app() -> FastAPI:
    """Create the FastAPI app hosting callback and control routes."""
    app = FastAPI(title="tg-jenkins-bot", lifespan=lifespan)
    app.state.manager = BotManager()
    app.include_router(control_router)
    app.include_router(callbacks_router)
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
