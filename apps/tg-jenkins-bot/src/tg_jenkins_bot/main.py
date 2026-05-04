"""Entry point — runs the FastAPI control/webhook server."""

from __future__ import annotations

import logging
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
    """Resolve listen port through the full config precedence chain."""
    return Config.resolve().bot_webhook_port


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage bot lifecycle on startup/shutdown."""
    config = Config.resolve()
    try:
        await app.state.manager.start(config)
    except Exception:
        logger.exception("Bot not auto-started")

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
