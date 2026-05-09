"""FastAPI app factory for the config-ui dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .drive import DriveOAuthManager
from .routes.config import router as config_router
from .routes.drive import router as drive_router
from .routes.jenkinsfile import router as jenkinsfile_router
from .routes.pages import router as pages_router
from .routes.services import router as services_router
from .services import ServiceClient
from .settings import Settings

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"


def _drive_token_path(bot_config_path: Path | None) -> Path:
    """Derive the OAuth token path from the bot config path."""
    if bot_config_path is not None:
        return bot_config_path.parent / "oauth.json"
    return Path("data/oauth.json")


def create_app() -> FastAPI:
    """Create and configure the config-ui FastAPI application."""
    app = FastAPI(title="config-ui")

    # --- Resolve settings and wire up shared state ---
    settings = Settings.from_env()
    app.state.settings = settings
    app.state.service_client = ServiceClient(settings)
    app.state.drive_oauth = DriveOAuthManager(
        _drive_token_path(settings.bot_config_path)
    )
    app.state.templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    # --- Include routers ---
    app.include_router(pages_router)
    app.include_router(config_router)
    app.include_router(drive_router)
    app.include_router(jenkinsfile_router)
    app.include_router(services_router)

    # Static files mounted last (acts as catch-all for /static/*)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
