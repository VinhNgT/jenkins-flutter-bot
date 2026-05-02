"""Entry point — runs the FastAPI control/webhook server."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .config import Config
from .control import BotManager, control_router
from .jenkins.webhook import webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _resolve_listen_port() -> int:
    """Pick the HTTP listen port without requiring a fully valid config."""
    raw_port = os.environ.get("BOT_WEBHOOK_PORT", "9090")
    try:
        return int(raw_port)
    except ValueError:
        return 9090


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage bot lifecycle on startup/shutdown."""
    try:
        config = Config.resolve()
        await app.state.manager.start(config)
    except Exception as exc:
        logger.info("Bot not auto-started: %s", exc)

    yield

    await app.state.manager.stop()


def create_app() -> FastAPI:
    """Create the FastAPI app hosting webhook and control routes."""
    app = FastAPI(title="tg-jenkins-bot", lifespan=lifespan)
    app.state.manager = BotManager()
    app.include_router(control_router)
    app.include_router(webhook_router)
    return app


def cli() -> None:
    """CLI entry point."""
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=_resolve_listen_port(),
    )
