"""Jenkinsfile generator — produces a customized pipeline script."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template
from typing import Any

from config_schema import nested_get
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["jenkinsfile"])

# ---------------------------------------------------------------------------
# Groovy templates — loaded from external .groovy files at import time.
#
# Uses string.Template ($var substitution) so Groovy braces don't need
# escaping.  The template files are valid Groovy and can be edited with
# full IDE syntax support.
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_PIPELINE_TEMPLATE = Template((_TEMPLATE_DIR / "pipeline.groovy").read_text())
_CHECKOUT_PRIVATE = Template(
    (_TEMPLATE_DIR / "checkout_private.groovy").read_text()
)
_CHECKOUT_PUBLIC = Template(
    (_TEMPLATE_DIR / "checkout_public.groovy").read_text()
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_bot_config(config_path: Path | None) -> dict[str, Any]:
    """Read the bot config JSON file, returning {} if missing."""
    if config_path and config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except Exception:
            logger.exception("Failed to read bot config at %s", config_path)
    return {}


def _generate_jenkinsfile(repo_url: str, credentials_id: str) -> str:
    """Generate a complete Jenkinsfile pipeline script."""
    if credentials_id:
        checkout = _CHECKOUT_PRIVATE.substitute(
            repo_url=repo_url, credentials_id=credentials_id
        )
    else:
        checkout = _CHECKOUT_PUBLIC.substitute(repo_url=repo_url)

    return _PIPELINE_TEMPLATE.substitute(checkout=checkout)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/jenkinsfile")
async def get_jenkinsfile(request: Request) -> dict[str, Any]:
    """Generate a Jenkinsfile pipeline script from current bot config."""
    settings = request.app.state.settings
    bot_data = _read_bot_config(settings.bot_config_path)

    repo_url = nested_get(bot_data, "git.repo_url") or ""
    credentials_id = nested_get(bot_data, "jenkins.credentials_id") or ""

    warnings: list[str] = []
    if not repo_url:
        repo_url = "<YOUR_REPO_URL>"
        warnings.append(
            "Repository URL not configured — update it in the Bot config tab."
        )

    script = _generate_jenkinsfile(repo_url, credentials_id)

    return {"script": script, "warnings": warnings}
