"""Declarative schema for the Drive configuration module.

Stack-manager owns the Drive OAuth field declarations used by the web UI.
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


