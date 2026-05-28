"""Tg-jenkins-bot — FastAPI app factory and CLI."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response

from config_core import setup_service_logging, verify_service_token

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


class _ScrubInitDataFilter(logging.Filter):
    """Redact init_data query params from uvicorn access logs.

    The SSE endpoint must receive init_data via query parameter because
    the EventSource API does not support custom headers. This filter
    prevents the full Telegram authentication payload (user IDs,
    signatures) from being written to disk in access logs.

    Note: This complements (but does not duplicate) the value-level
    RedactingLogFilter from config-core. That filter scrubs *known*
    secret values; this filter scrubs the *URL-encoded* initData
    parameter which contains ephemeral per-session payloads.
    """

    _pattern = re.compile(r"init_data=[^ \"]*")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(
                self._pattern.sub("init_data=<REDACTED>", str(a))
                if isinstance(a, str) and "init_data=" in a
                else a
                for a in record.args  # type: ignore[union-attr]
            )
        return True


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

    # ── Webapp SPA serving ────────────────────────────────────────
    # Vite builds the frontend into this directory with content-hashed
    # filenames (assets/index-[hash].js). Two-tier caching strategy:
    #   1. index.html → no-cache (revalidates, picks up new chunk hashes)
    #   2. assets/*.js/css → immutably cached (hash in filename)
    #
    # SPAStaticFiles intercepts 404s on the /webapp mount and returns
    # index.html, allowing the frontend router (wouter-preact) to
    # handle client-side routes like /webapp/build/active/<id>.
    static_dir = Path(__file__).parent / "webapp"
    _index_html = (static_dir / "index.html").read_text()

    class SPAStaticFiles(StaticFiles):
        """StaticFiles subclass that serves index.html for unknown paths.

        Enables History API routing for the Vite SPA. Requests for
        real files (JS, CSS, images) are served normally; all other
        paths receive the SPA entry point so the client-side router
        can resolve the route.
        """

        async def get_response(self, path: str, scope: dict) -> Response:  # type: ignore[override]
            try:
                return await super().get_response(path, scope)
            except (HTTPException, StarletteHTTPException) as exc:
                if exc.status_code == 404:
                    return await super().get_response("index.html", scope)
                raise

    @app.get("/webapp", response_class=HTMLResponse)
    async def serve_index_redirect() -> HTMLResponse:
        """Serve index.html for /webapp (no trailing slash)."""
        return HTMLResponse(content=_index_html)

    # Mount SPA static files — serves real assets and falls back to
    # index.html for client-side routes.
    app.mount(
        "/webapp", SPAStaticFiles(directory=str(static_dir), html=True), name="webapp"
    )

    # API routers — control + callbacks require service token auth,
    # webapp uses Telegram initData auth (different trust boundary).
    service_auth = [Depends(verify_service_token)]
    app.include_router(control_router, dependencies=service_auth)
    app.include_router(callbacks_router, dependencies=service_auth)
    app.include_router(webapp_router)
    return app


def cli() -> None:
    """CLI entry point for the tg-jenkins-bot service."""
    setup_service_logging()

    # Scrub Telegram init_data from access logs (URL-level redaction)
    logging.getLogger("uvicorn.access").addFilter(_ScrubInitDataFilter())

    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=9090,
    )

