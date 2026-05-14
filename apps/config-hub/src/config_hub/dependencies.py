"""Shared FastAPI dependencies for config-hub."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates

from .manager import ConfigHubManager


def get_manager(request: Request) -> ConfigHubManager:
    """Inject the config-hub manager from app state."""
    return request.app.state.manager


ManagerDep = Annotated[ConfigHubManager, Depends(get_manager)]


def get_templates(request: Request) -> Jinja2Templates:
    """Inject Jinja2 templates from app state."""
    return request.app.state.templates


TemplatesDep = Annotated[Jinja2Templates, Depends(get_templates)]
