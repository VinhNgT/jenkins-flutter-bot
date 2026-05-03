"""Entry point — runs the FastAPI control server for the Jenkins agent."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .config import AgentConfig
from .control import AgentManager, control_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage agent lifecycle on startup/shutdown."""
    try:
        config = AgentConfig.resolve()
        app.state.manager.start(config)
    except Exception as exc:
        logger.info("Agent not auto-started: %s", exc)

    yield

    app.state.manager.stop()


def create_app() -> FastAPI:
    """Create the FastAPI app hosting agent control routes."""
    app = FastAPI(title="agent-control", lifespan=lifespan)
    app.state.manager = AgentManager()
    app.include_router(control_router)
    return app


def cli() -> None:
    """CLI entry point."""
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9091,
    )
