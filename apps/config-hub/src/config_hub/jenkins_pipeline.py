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
def _load_templates() -> tuple[dict[str, Template], dict[str, str]]:
    """Load and cache Groovy templates and snippet strings on first use."""
    return (
        {
            "pipeline": Template(
                (_TEMPLATE_DIR / "pipeline.groovy").read_text(encoding="utf-8")
            ),
            "checkout_private": Template(
                (_TEMPLATE_DIR / "checkout_private.groovy").read_text(encoding="utf-8")
            ),
            "checkout_public": Template(
                (_TEMPLATE_DIR / "checkout_public.groovy").read_text(encoding="utf-8")
            ),
        },
        {
            "properties": (_TEMPLATE_DIR / "properties.groovy").read_text(
                encoding="utf-8"
            ),
            "post_actions": (_TEMPLATE_DIR / "post_actions.groovy").read_text(
                encoding="utf-8"
            ),
            "extensions": (_TEMPLATE_DIR / "extensions.groovy").read_text(
                encoding="utf-8"
            ),
            "clone_opts": (_TEMPLATE_DIR / "clone_opts.groovy").read_text(
                encoding="utf-8"
            ),
        },
    )


def generate_jenkinsfile(
    repo_url: str,
    credentials_id: str,
    discard_builds: bool = True,
    clean_workspace: bool = False,
    shallow_clone: bool = True,
) -> str:
    """Generate a complete Jenkinsfile pipeline script.

    Parameters
    ----------
    repo_url:
        Git repository URL (HTTPS or SSH).
    credentials_id:
        Jenkins credentials ID for private repos.  When empty, the
        public-repo checkout template is used instead.
    discard_builds:
        Whether to configure build discarding to save space.
    clean_workspace:
        Whether to wipe workspace caches after the build finishes.
    shallow_clone:
        Whether to enable shallow git cloning to reduce clone size.
    """
    tpls, snippets = _load_templates()
    pipeline_tpl = tpls["pipeline"]
    private_tpl = tpls["checkout_private"]
    public_tpl = tpls["checkout_public"]

    # Build properties block
    properties_val = ""
    if discard_builds:
        properties_val = snippets["properties"]

    # Build post actions block
    post_actions_val = ""
    if clean_workspace:
        post_actions_val = snippets["post_actions"]

    # Build SCM options
    extensions_val = ""
    clone_opts_val = ""
    if shallow_clone:
        extensions_val = snippets["extensions"]
        clone_opts_val = snippets["clone_opts"]

    if credentials_id:
        checkout = private_tpl.safe_substitute(
            repo_url=repo_url, credentials_id=credentials_id, extensions=extensions_val
        )
    else:
        checkout = public_tpl.safe_substitute(
            repo_url=repo_url, clone_opts=clone_opts_val
        )

    return pipeline_tpl.safe_substitute(
        properties=properties_val, checkout=checkout, post_actions=post_actions_val
    )
