"""Declarative schema for the file-manager configuration module."""

from __future__ import annotations


from functools import cache

from config_schema import ConfigRegistry

# ---------------------------------------------------------------------------
# Module metadata
# ---------------------------------------------------------------------------


@cache
def get_registry() -> ConfigRegistry:
    registry = ConfigRegistry(
        title="File Storage Configuration",
        description=(
            "Configures the storage backend used for uploading build artifacts."
            " The current implementation uses Google Drive — enter your OAuth"
            " credentials below, then connect via the dashboard."
        ),
    )

    # ---------------------------------------------------------------------------
    # Storage field declarations
    # ---------------------------------------------------------------------------

    registry.register_runtime(
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
    )

    registry.register_runtime(
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
    )

    registry.register_runtime(
        key="drive.folder_name",
        env_var="DRIVE_FOLDER_NAME",
        attr="drive_folder_name",
        label="Drive Folder Name",
        group="Storage Settings",
        description="Drive folder for build artifacts (auto-created if missing)",
    )

    # Note: file-manager currently has no infrastructure-only configuration fields.

    return registry
