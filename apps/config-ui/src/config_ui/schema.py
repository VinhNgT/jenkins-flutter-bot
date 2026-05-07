"""Declarative schema for the config-ui (Google Drive) configuration module.

This is the single source of truth for the UI-owned config fields.  It drives:
  - config_store.py constants  via field introspection
  - GET /api/config/schema     via serialize_schema()
  - Frontend rendering         via the serialized JSON
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Field definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldDef:
    """Declarative definition for a single configuration field."""

    key: str  # Dotted JSON key: "drive.client_id"
    env_var: str  # Env var fallback (unused for UI scope, kept for consistency)
    attr: str  # Python attribute name (unused for UI scope)
    label: str  # UI label: "Drive Client ID"
    group: str  # UI card grouping
    description: str = ""  # Short text below the label
    help_html: str = ""  # Rich HTML for ? popover
    default: str = ""  # Hardcoded default
    secret: bool = False  # Mask in UI, strip from API responses
    required: bool = False
    field_type: str = "text"  # "text", "password", "number", "select"
    choices: tuple[tuple[str, str], ...] = ()  # For select: (value, label)
    value_type: str = "str"  # "str", "int", "bool", "list[int]"


# ---------------------------------------------------------------------------
# UI field declarations
# ---------------------------------------------------------------------------

MODULE_TITLE = "Google Drive Configuration"
MODULE_DESCRIPTION = (
    "Connects the bot to Google Drive so it can upload APKs and return"
    " shareable links in Telegram. Save your OAuth client credentials"
    " first, then click <strong>Connect Google Drive</strong> to authorize"
    " via a browser popup. Authorization is a one-time step — the token"
    " is stored in a shared volume."
)

UI_FIELDS: tuple[FieldDef, ...] = (
    FieldDef(
        key="drive.client_id",
        env_var="",
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
        env_var="",
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

# ---------------------------------------------------------------------------
# Schema serialization (for GET /api/config/schema)
# ---------------------------------------------------------------------------

_BACKEND_ONLY_KEYS = {"attr", "value_type", "env_var"}


def serialize_schema(
    fields: tuple[FieldDef, ...],
    title: str,
    description: str,
) -> dict[str, Any]:
    """Serialize module schema to a JSON-ready dict for the HTTP endpoint."""
    return {
        "title": title,
        "description": description,
        "fields": [
            {k: v for k, v in asdict(f).items() if k not in _BACKEND_ONLY_KEYS}
            for f in fields
        ],
    }
