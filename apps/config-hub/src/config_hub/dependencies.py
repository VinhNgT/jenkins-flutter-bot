"""Shared FastAPI dependencies for config-hub."""

from __future__ import annotations

import logging
import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from config_core import verify_init_data

from .manager import ConfigHubManager

logger = logging.getLogger(__name__)

security = HTTPBasic(auto_error=False)

_INIT_DATA_HEADER = "X-Telegram-Init-Data"


def get_manager(request: Request) -> ConfigHubManager:
    """Inject the config-hub manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[ConfigHubManager, Depends(get_manager)]


def get_templates(request: Request) -> Jinja2Templates:
    """Inject Jinja2 templates from app state."""
    return request.app.state.templates


TemplatesDep = Annotated[Jinja2Templates, Depends(get_templates)]


async def verify_admin_auth(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    """Verify admin authentication — Telegram initData or Basic Auth.

    Telegram initData is the primary authentication mechanism. Basic Auth
    is disabled by default and only activated when credentials are
    explicitly configured. The Caddy gateway strips the Authorization
    header from non-local requests, so Basic Auth only works from the
    same local network even when configured.

    Checks in order:
    1. X-Telegram-Init-Data header → validate HMAC, check admin user ID
    2. Basic Auth credentials (opt-in) → username/password check
    3. JFB_DEV_MODE bypass → allow unauthenticated access in dev
    4. Reject with 401/403 (fail-closed)
    """
    manager = request.app.state.manager

    # EXEMPTION: The Google Drive OAuth callback endpoint must be accessible
    # without credentials. Modern browsers omit cached Basic Auth headers on
    # cross-origin redirects (e.g. coming back from accounts.google.com).
    # Since this endpoint only renders a static HTML completion shell and
    # performs no administrative actions, it is safe to exempt.
    if request.url.path == "/api/webapp-admin/drive/oauth/callback":
        return

    # --- 1. Telegram initData authentication (primary) ---
    init_data = request.headers.get(_INIT_DATA_HEADER)
    if init_data:
        # Dev mode preview bypass
        if init_data == "preview" and os.environ.get("JFB_DEV_MODE"):
            return

        bot_token = manager.telegram_bot_token
        if not bot_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Telegram authentication not configured. "
                    "Set TELEGRAM_BOT_TOKEN on config-hub."
                ),
            )

        try:
            data = verify_init_data(init_data, bot_token)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Telegram initData: {e}",
            )

        # Check admin whitelist
        user = data.get("user", {})
        user_id = user.get("id") if isinstance(user, dict) else None
        admin_ids = manager.admin_telegram_user_ids

        if admin_ids and user_id not in admin_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not authorized for admin access",
            )

        return

    # --- 2. Basic Auth (opt-in, local network only) ---
    username = manager.auth_username
    password = manager.auth_password

    if username and password and credentials:
        is_correct_username = secrets.compare_digest(credentials.username, username)
        is_correct_password = secrets.compare_digest(credentials.password, password)

        if is_correct_username and is_correct_password:
            return

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    # --- 3. Dev mode bypass ---
    if os.environ.get("JFB_DEV_MODE"):
        return

    # --- 4. Fail-closed ---
    # Prompt for Basic Auth if it's configured, otherwise generic 401
    if username and password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )
