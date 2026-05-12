"""Declarative schema for the file-manager configuration module."""

from __future__ import annotations

from config_schema import FieldDef, resolve_fields, serialize_schema  # noqa: F401

# ---------------------------------------------------------------------------
# Module metadata (rendered in the web UI config tab)
# ---------------------------------------------------------------------------

MODULE_TITLE = "File Storage Configuration"
MODULE_DESCRIPTION = (
    "Configures the storage backend used for uploading build artifacts."
    " The current implementation uses Google Drive — enter your OAuth"
    " credentials below, then connect via the dashboard."
)

# ---------------------------------------------------------------------------
# Storage field declarations
# ---------------------------------------------------------------------------

STORAGE_FIELDS: tuple[FieldDef, ...] = (
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
    FieldDef(
        key="drive.folder_name",
        env_var="DRIVE_FOLDER_NAME",
        attr="drive_folder_name",
        label="Drive Folder Name",
        group="Storage Settings",
        description="Drive folder for build artifacts (auto-created if missing)",
    ),
)

STORAGE_INFRA: tuple[FieldDef, ...] = ()

# Derived constants
STORAGE_SECRET_FIELDS = tuple(f.key for f in STORAGE_FIELDS if f.secret)
