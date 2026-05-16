"""Storage configuration resolved from declarative schema."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from config_core import ServiceSettings

_DEFAULT_CONFIG_PATH = Path("/app/data/storage.json")


class StorageSettings(ServiceSettings):
    """Storage configuration resolved from config file, env, and defaults."""

    # OAuth credentials
    drive_client_id: str = Field(
        title="Drive Client ID",
        description="OAuth 2.0 client ID from Google Cloud Console",
        json_schema_extra={
            "group": "OAuth Credentials",
            "help_html": (
                'Go to <a href="https://console.cloud.google.com/apis/credentials"'
                ' target="_blank" rel="noopener">Google Cloud Console → APIs'
                " &amp; Services → Credentials</a> → <strong>Create"
                " Credentials</strong> → <strong>OAuth client ID</strong>"
                " → Application type: <strong>Web application</strong>."
                " Add <code>http://&lt;your-host&gt;:9000/api/drive/oauth/callback</code>"
                " as an authorized redirect URI. Copy the Client ID."
            ),
            "json_key": "drive.client_id",
        },
    )

    drive_client_secret: str = Field(
        title="Drive Client Secret",
        description="OAuth 2.0 client secret",
        json_schema_extra={
            "group": "OAuth Credentials",
            "help_html": (
                "Shown on the same credentials page as the Client ID."
                " Click the OAuth client you just created to view the secret."
            ),
            "secret": True,
            "field_type": "password",
            "json_key": "drive.client_secret",
        },
    )

    # Storage settings
    drive_folder_name: str = Field(
        "Flutter Builds",
        title="Drive Folder Name",
        description="Drive folder for build artifacts (auto-created if missing)",
        json_schema_extra={
            "group": "Storage Settings",
            "json_key": "drive.folder_name",
        },
    )
