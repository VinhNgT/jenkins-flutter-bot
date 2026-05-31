"""Shared FastAPI dependencies for config-hub."""

from __future__ import annotations

import logging
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
    """Verify admin authentication — Telegram initData or Basic Auth in preview mode.

    Telegram initData is the primary authentication mechanism. Browser preview mode
    is enabled by ENABLE_BROWSER_PREVIEW and protected by Basic Auth.
    """
    manager = request.app.state.manager

    # EXEMPTION: The Google Drive OAuth callback endpoint must be accessible
    # without credentials. Modern browsers omit cached Basic Auth headers on
    # cross-origin redirects (e.g. coming back from accounts.google.com).
    # Since this endpoint only renders a static HTML completion shell and
    # performs no administrative actions, it is safe to exempt.
    if request.url.path == "/api/webapp-admin/drive/oauth/callback":
        return

    # --- 1. Telegram initData or Preview Authentication ---
    init_data = request.headers.get(_INIT_DATA_HEADER)

    if init_data:
        # Dev / preview bypass branch
        if init_data == "preview":
            if not manager.enable_browser_preview:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Browser preview is disabled in production",
                )

            # Require Basic Auth for preview mode
            if not credentials:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Basic"},
                )

            is_correct_username = secrets.compare_digest(
                credentials.username, manager.browser_auth_username or ""
            )
            is_correct_password = secrets.compare_digest(
                credentials.password, manager.browser_auth_password or ""
            )

            if is_correct_username and is_correct_password:
                return

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Basic"},
            )

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

        if not admin_ids:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin access not configured. Set ADMIN_TELEGRAM_USER_IDS.",
            )

        if user_id not in admin_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not authorized for admin access",
            )

        return

    # --- 2. Fail-closed (no initData) ---
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )
