"""Declarative schemas for Drive and Project configuration modules.

These schemas were previously split between config-ui (DRIVE_FIELDS) and
libs/stack-manager (PROJECT_FIELDS).  Stack-manager now owns both as the
central operational backend.
"""

from __future__ import annotations

from config_schema import FieldDef

# ---------------------------------------------------------------------------
# Drive configuration
# ---------------------------------------------------------------------------

DRIVE_MODULE_TITLE = "Google Drive Configuration"
DRIVE_MODULE_DESCRIPTION = (
    "Connects the bot to Google Drive so it can upload APKs and return"
    " shareable links in Telegram. Save your OAuth client credentials"
    " first, then click <strong>Connect Google Drive</strong> to authorize"
    " via a browser popup. Authorization is a one-time step — the token"
    " is stored in a shared volume."
)

DRIVE_FIELDS: tuple[FieldDef, ...] = (
    FieldDef(
        key="drive.client_id",
        env_var="DRIVE_CLIENT_ID",
        attr="drive_client_id",
        label="Drive Client ID",
        group="OAuth Credentials",
        description="OAuth 2.0 client ID from Google Cloud Console",
        help_html=(
            'Go to <a href="https://console.cloud.google.com/apis/credentials"'
            ' target="_blank" rel="noopener">Google Cloud Console → APIs'
            " &amp; Services → Credentials</a> → <strong>Create"
            " Credentials</strong> → <strong>OAuth client ID</strong>"
            " → Application type: <strong>Web application</strong>."
            " Add <code>http://&lt;your-host&gt;:9000/api/drive/oauth/callback</code>"
            " as an authorized redirect URI. Copy the Client ID."
        ),
        required=True,
    ),
    FieldDef(
        key="drive.client_secret",
        env_var="DRIVE_CLIENT_SECRET",
        attr="drive_client_secret",
        label="Drive Client Secret",
        group="OAuth Credentials",
        description="OAuth 2.0 client secret",
        help_html=(
            "Shown on the same credentials page as the Client ID."
            " Click the OAuth client you just created to view the secret."
        ),
        secret=True,
        required=True,
        field_type="password",
    ),
)

DRIVE_INFRA: tuple[FieldDef, ...] = ()

# Derived constants
DRIVE_SECRET_FIELDS = tuple(f.key for f in DRIVE_FIELDS if f.secret)

# ---------------------------------------------------------------------------
# Project configuration
# ---------------------------------------------------------------------------

PROJECT_MODULE_TITLE = "Project Configuration"
PROJECT_MODULE_DESCRIPTION = (
    "Project-wide settings shared across all services."
)

PROJECT_FIELDS: tuple[FieldDef, ...] = (
    FieldDef(
        key="project.github_url",
        env_var="PROJECT_GITHUB_URL",
        attr="project_github_url",
        label="GitHub URL",
        group="Repository",
        description="Link to the project's GitHub repository",
        help_html=(
            "The public URL of your GitHub repository."
            " This is displayed in the dashboard for quick access."
        ),
    ),
)

PROJECT_INFRA: tuple[FieldDef, ...] = ()
