"""Agent-control — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .manager import AgentManager
from .routers.control import router as control_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage agent lifecycle on startup/shutdown."""
    try:
        await app.state.manager.start()
    except Exception:
        logger.exception("Agent not auto-started")

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error during shutdown")


def create_app() -> FastAPI:
    """Create the FastAPI app hosting agent control routes."""
    app = FastAPI(title="agent-control", lifespan=lifespan)
    app.state.manager = AgentManager()
    app.include_router(control_router)
    return app


def cli() -> None:
    """CLI entry point for the agent-control service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9091,
    )
