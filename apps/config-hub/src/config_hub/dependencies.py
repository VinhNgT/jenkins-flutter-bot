"""Shared FastAPI dependencies for config-hub."""

from __future__ import annotations

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
    """Verify HTTP Basic Authentication if configured."""
    manager = request.app.state.manager
    username = manager.auth_username
    password = manager.auth_password

    # Bypassed if authentication is not configured in the environment
    if not username or not password:
        return

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
