"""Jenkinsfile pipeline generator with self-documenting Groovy templates."""

from __future__ import annotations

from pathlib import Path
from string import Template

# ---------------------------------------------------------------------------
# Groovy templates — loaded from external .groovy files at import time.
#
# Uses string.Template ($var substitution) so Groovy braces don't need
# escaping.  The template files are valid Groovy and can be edited with
# full IDE syntax support.
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_PIPELINE_TEMPLATE = Template((_TEMPLATE_DIR / "pipeline.groovy").read_text())
_CHECKOUT_PRIVATE = Template((_TEMPLATE_DIR / "checkout_private.groovy").read_text())
_CHECKOUT_PUBLIC = Template((_TEMPLATE_DIR / "checkout_public.groovy").read_text())


def generate_jenkinsfile(repo_url: str, credentials_id: str) -> str:
    """Generate a complete Jenkinsfile pipeline script.

    Parameters
    ----------
    repo_url:
        Git repository URL (HTTPS or SSH).
    credentials_id:
        Jenkins credentials ID for private repos.  When empty, the
        public-repo checkout template is used instead.
    """
    if credentials_id:
        checkout = _CHECKOUT_PRIVATE.safe_substitute(
            repo_url=repo_url, credentials_id=credentials_id
        )
    else:
        checkout = _CHECKOUT_PUBLIC.safe_substitute(repo_url=repo_url)

    return _PIPELINE_TEMPLATE.safe_substitute(checkout=checkout)
