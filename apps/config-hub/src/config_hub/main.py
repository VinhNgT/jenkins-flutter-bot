"""Config Hub entry point — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .manager import ConfigHubManager
from .routers import config, drive, export, jenkinsfile, pages, services, version

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATE_DIR = PACKAGE_DIR / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage hub lifecycle on startup/shutdown."""
    await app.state.manager.start()

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error stopping manager")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="config-hub", docs_url="/api/docs", lifespan=lifespan)

    # --- Manager ---
    manager = ConfigHubManager()
    app.state.manager = manager
    app.state.templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    # --- API routers ---
    app.include_router(config.router)
    app.include_router(services.router)
    app.include_router(export.router)
    app.include_router(drive.router)
    app.include_router(jenkinsfile.router)
    app.include_router(version.router)

    # --- Static files & SPA shell (must be after API routers) ---
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(pages.router)

    return app


def cli() -> None:
    """CLI entry point for the config-hub service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9000,
    )
