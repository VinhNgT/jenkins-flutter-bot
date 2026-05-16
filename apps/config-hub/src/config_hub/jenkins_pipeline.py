"""Jenkinsfile pipeline generator with self-documenting Groovy templates."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

# ---------------------------------------------------------------------------
# Groovy templates — loaded lazily from external .groovy files.
#
# Uses string.Template ($var substitution) so Groovy braces don't need
# escaping.  The template files are valid Groovy and can be edited with
# full IDE syntax support.
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _load_templates() -> tuple[Template, Template, Template]:
    """Load and cache Groovy templates on first use."""
    return (
        Template((_TEMPLATE_DIR / "pipeline.groovy").read_text()),
        Template((_TEMPLATE_DIR / "checkout_private.groovy").read_text()),
        Template((_TEMPLATE_DIR / "checkout_public.groovy").read_text()),
    )


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
    pipeline_tpl, private_tpl, public_tpl = _load_templates()

    if credentials_id:
        checkout = private_tpl.safe_substitute(
            repo_url=repo_url, credentials_id=credentials_id
        )
    else:
        checkout = public_tpl.safe_substitute(repo_url=repo_url)

    return pipeline_tpl.safe_substitute(checkout=checkout)

