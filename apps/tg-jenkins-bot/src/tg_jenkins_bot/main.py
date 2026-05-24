"""Tg-jenkins-bot — FastAPI app factory and CLI."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import version as pkg_version
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse

from .manager import BotManager, StartupError
from .routers.callbacks import router as callbacks_router
from .routers.control import router as control_router
from .routers.webapp import router as webapp_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage bot lifecycle on startup/shutdown."""
    try:
        await app.state.manager.start()
    except StartupError:
        logger.warning(
            "Bot not auto-started: %s", app.state.manager.status()["last_error"]
        )

    yield

    try:
        await app.state.manager.stop()
    except Exception:
        logger.exception("Error during shutdown")


def _compute_asset_hash(static_dir: Path) -> str:
    """Compute a short SHA-256 digest of the cacheable static assets.

    The hash covers the actual file contents of CSS/JS sub-resources
    referenced from index.html.  It changes if and only if any asset
    file changes — server restarts with identical code produce the same
    hash, so no unnecessary cache invalidation occurs.  This replaces
    the previous APP_VERSION-based cache-busting which was broken in
    development (always ``0.0.0-dev``).
    """
    h = hashlib.sha256()
    for name in ("style.css", "app.js", "tg-emulator.js"):
        h.update((static_dir / name).read_bytes())
    return h.hexdigest()[:8]


def create_app() -> FastAPI:
    """Create the FastAPI app hosting callback, control, and Web App routes."""
    app = FastAPI(title="tg-jenkins-bot", lifespan=lifespan)
    app.state.manager = BotManager()

    @app.exception_handler(StartupError)
    async def handle_startup_error(
        request: Request,
        exc: StartupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # ── Cache-busting for Telegram WebView ────────────────────────
    # APP_VERSION: package version for display only (UI fingerprint).
    try:
        _app_version = pkg_version("tg-jenkins-bot")
    except Exception:
        _app_version = "0.0.0-dev"

    # ASSET_HASH: content-based hash for ?v= query strings.
    # Changes only when actual CSS/JS file contents change — stable
    # across server restarts with identical code.
    static_dir = Path(__file__).parent / "webapp"
    _asset_hash = _compute_asset_hash(static_dir)
    _index_template = (static_dir / "index.html").read_text()

    @app.get("/webapp", response_class=HTMLResponse)
    @app.get("/webapp/", response_class=HTMLResponse)
    async def serve_index() -> HTMLResponse:
        """Serve index.html with content-hash cache-busting.

        Two-tier caching strategy:
        1. This HTML response uses Cache-Control: no-cache — the WebView
           always revalidates it (cheap 304 for a small file).
        2. Sub-resources (CSS/JS) use ?v=<asset_hash> in their URLs —
           cached aggressively, invalidated only when file content
           actually changes.
        """
        html = _index_template.replace(
            "{{APP_VERSION}}", _app_version
        ).replace("{{ASSET_HASH}}", _asset_hash)
        return HTMLResponse(
            content=html,
            headers={"Cache-Control": "no-cache"},
        )

    # Mount remaining static files (CSS, JS, assets/) — served as-is.
    # html=True is removed: index.html is now served by the explicit
    # route above. FastAPI evaluates routes before mounts, so GET
    # /webapp/ hits serve_index() first.
    app.mount(
        "/webapp", StaticFiles(directory=str(static_dir)), name="webapp"
    )

    # API routers
    app.include_router(control_router)
    app.include_router(callbacks_router)
    app.include_router(webapp_router)
    return app


def cli() -> None:
    """CLI entry point for the tg-jenkins-bot service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9090,
    )
