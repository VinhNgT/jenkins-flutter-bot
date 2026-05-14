"""Mock Jenkins server — FastAPI app factory and CLI.

Simulates the Jenkins REST API for local development.
On trigger, spawns a background task that waits MOCK_BUILD_DELAY seconds,
then POSTs a webhook callback to BOT_CALLBACK_URL with a dummy APK.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .config import MockJenkinsConfig
from .manager import MockBuildManager
from .routers.jenkins import router as jenkins_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Mock Jenkins has no startup/shutdown resources — placeholder."""
    yield


def create_app() -> FastAPI:
    """Application factory for mock-jenkins."""
    config = MockJenkinsConfig()
    app = FastAPI(title="mock-jenkins", lifespan=lifespan)
    app.state.manager = MockBuildManager(config)
    app.include_router(jenkins_router)
    return app


def cli() -> None:
    """CLI entry point for the mock Jenkins server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    config = MockJenkinsConfig()
    logger.info(
        "Starting mock-jenkins on port %d (delay=%ds, failure_rate=%.0f%%)",
        config.mock_port,
        config.mock_build_delay,
        config.mock_failure_rate * 100,
    )
    uvicorn.run(create_app(), host="0.0.0.0", port=config.mock_port)
