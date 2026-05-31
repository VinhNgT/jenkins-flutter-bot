"""Config Hub entry point — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config_core import setup_service_logging

from .dependencies import verify_admin_auth
from .manager import ConfigHubManager
from .routers import config, drive, export, jenkinsfile, pages, services, version

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
WEBAPP_DIR = PACKAGE_DIR / "webapp"
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
    app = FastAPI(
        title="config-hub",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # --- Manager ---
    manager = ConfigHubManager()
    app.state.manager = manager
    app.state.templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    # --- API routers ---
    auth_deps = [Depends(verify_admin_auth)]
    app.include_router(config.router, dependencies=auth_deps)
    app.include_router(services.router, dependencies=auth_deps)
    app.include_router(export.router, dependencies=auth_deps)
    app.include_router(drive.router, dependencies=auth_deps)
    app.include_router(jenkinsfile.router, dependencies=auth_deps)
    app.include_router(version.router, dependencies=auth_deps)

    # --- Static files & SPA shell (must be after API routers) ---
    app.include_router(pages.router)
    app.mount(
        "/webapp-admin",
        StaticFiles(directory=str(WEBAPP_DIR)),
        name="webapp-admin",
    )

    return app


def cli() -> None:
    """CLI entry point for the config-hub service."""
    setup_service_logging()
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9000,
    )
