"""Stack Manager entry point — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .manager import StackManager
from .routes import config, drive, export, jenkinsfile, pages, services, version
from .settings import Settings

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATE_DIR = PACKAGE_DIR / "templates"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Stack Manager", docs_url="/api/docs")

    # --- Settings & Manager ---
    settings = Settings.from_env()
    manager = StackManager(settings)
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
    """CLI entry point for the stack-manager service."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=9000)
