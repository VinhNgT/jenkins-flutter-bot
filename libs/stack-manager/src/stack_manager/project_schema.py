"""Project-owned configuration schema.

Declares PROJECT_FIELDS — the single canonical source for properties that
belong to the whole stack rather than any individual service.
"""

from __future__ import annotations

from config_schema import FieldDef

# ---------------------------------------------------------------------------
# Project field declarations
# ---------------------------------------------------------------------------

PROJECT_MODULE_TITLE = "Project Settings"
PROJECT_MODULE_DESCRIPTION = (
    "Project-wide properties shared across all services."
    " Changes here are reflected in both the Telegram bot messages"
    " and the config dashboard header."
)

PROJECT_FIELDS: tuple[FieldDef, ...] = (
    FieldDef(
        key="project.github_url",
        env_var="GITHUB_URL",
        attr="github_url",
        label="GitHub URL",
        group="General",
        description="Link shown in the /start message and config-ui header",
        help_html=(
            "URL to your project\u2019s GitHub (or any Git host) page."
            " Displayed as a hyperlink in the Telegram /start and /help messages"
            " and as a pill link in the config dashboard header."
            "<br><br>"
            "Leave empty to hide the link entirely."
        ),
        default="https://github.com/VinhNgT/jenkins-flutter-bot",
    ),
)

PROJECT_INFRA: tuple[FieldDef, ...] = ()
