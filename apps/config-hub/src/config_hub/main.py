"""Config Hub entry point — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .manager import ConfigHubManager
from .routes import config, drive, export, jenkinsfile, pages, services, version
from .settings import Settings

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATE_DIR = PACKAGE_DIR / "templates"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — tear down shared resources on shutdown."""
    yield
    manager: ConfigHubManager = app.state.manager
    try:
        await manager.close()
    except Exception:
        logger.exception("Error closing manager")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Config Hub", docs_url="/api/docs", lifespan=_lifespan)

    # --- Settings & Manager ---
    settings = Settings.from_env()
    manager = ConfigHubManager(settings)
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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=9000)
