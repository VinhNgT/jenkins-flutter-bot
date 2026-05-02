"""Entry point — runs the FastAPI control/webhook server."""

from __future__ import annotations

import logging
import os

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


def create_app() -> FastAPI:
    """Create the FastAPI app hosting webhook and control routes."""
    app = FastAPI(title="tg-jenkins-bot")
    app.state.manager = BotManager()
    app.include_router(control_router)
    app.include_router(webhook_router)

    @app.on_event("startup")
    async def startup() -> None:
        try:
            config = Config.resolve()
        except Exception as exc:
            logger.info("Bot not auto-started: %s", exc)
            return

        await app.state.manager.start(config)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await app.state.manager.stop()

    return app


def cli() -> None:
    """CLI entry point."""
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=_resolve_listen_port(),
    )
