"""Jenkinsfile generator route — delegates to stack_manager."""

from __future__ import annotations

import logging
from typing import Any

from config_schema import nested_get
from fastapi import APIRouter, Request
from stack_manager import generate_jenkinsfile, load_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["jenkinsfile"])


@router.get("/jenkinsfile")
async def get_jenkinsfile(request: Request) -> dict[str, Any]:
    """Generate a Jenkinsfile pipeline script from current bot config."""
    settings = request.app.state.settings
    bot_data = load_json(settings.bot_config_path)

    repo_url = nested_get(bot_data, "git.repo_url") or ""
    credentials_id = nested_get(bot_data, "jenkins.credentials_id") or ""

    warnings: list[str] = []
    if not repo_url:
        repo_url = "<YOUR_REPO_URL>"
        warnings.append(
            "Repository URL not configured — update it in the Bot config tab."
        )

    script = generate_jenkinsfile(repo_url, credentials_id)

    return {"script": script, "warnings": warnings}
