"""Shared FastAPI dependencies for config-hub."""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from .manager import ConfigHubManager

security = HTTPBasic(auto_error=False)


def get_manager(request: Request) -> ConfigHubManager:
    """Inject the config-hub manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[ConfigHubManager, Depends(get_manager)]


def get_templates(request: Request) -> Jinja2Templates:
    """Inject Jinja2 templates from app state."""
    return request.app.state.templates


TemplatesDep = Annotated[Jinja2Templates, Depends(get_templates)]


async def verify_basic_auth(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    """Verify HTTP Basic Authentication if configured.

    Fail-closed in production: when credentials are not configured and
    ``JFB_DEV_MODE`` is not set, all requests are rejected with 503.
    This prevents a misconfigured deployment from exposing the admin
    dashboard without authentication.
    """
    manager = request.app.state.manager
    username = manager.auth_username
    password = manager.auth_password

    if not username or not password:
        # In dev mode, bypass auth for convenience
        if os.environ.get("JFB_DEV_MODE"):
            return
        # Production: reject — credentials must be configured
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication not configured. "
                "Set CONFIG_HUB_AUTH_USERNAME and CONFIG_HUB_AUTH_PASSWORD."
            ),
        )

    # EXEMPTION: The Google Drive OAuth callback endpoint must be accessible
    # without credentials. Modern browsers omit cached Basic Auth headers on
    # cross-origin redirects (e.g. coming back from accounts.google.com).
    # Since this endpoint only renders a static HTML completion shell and
    # performs no administrative actions, it is safe to exempt.
    if request.url.path == "/api/drive/oauth/callback":
        return

    # Enforce authentication if configured
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    is_correct_username = secrets.compare_digest(credentials.username, username)
    is_correct_password = secrets.compare_digest(credentials.password, password)

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
