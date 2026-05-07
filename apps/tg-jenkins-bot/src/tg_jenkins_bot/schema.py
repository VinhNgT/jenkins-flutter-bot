"""Declarative schema for the Telegram bot configuration module.

This is the single source of truth for all bot config fields.  It drives:
  - Config.resolve()  via resolve_fields() + post_resolve()
  - GET /control/schema  via serialize_schema()
  - config-ui rendering  via the serialized JSON
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Field definition
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
OAUTH_TOKEN_PATH = DATA_DIR / "oauth.json"


@dataclass(frozen=True)
class FieldDef:
    """Declarative definition for a single configuration field."""

    key: str  # Dotted JSON key: "telegram.bot_token"
    env_var: str  # Env var fallback: "TELEGRAM_BOT_TOKEN"
    attr: str  # Python attribute on Config: "telegram_token"
    label: str  # UI label: "Bot Token"
    group: str  # UI card grouping: "Telegram"
    description: str = ""  # Short text below the label
    help_html: str = ""  # Rich HTML for ? popover
    default: str = ""  # Hardcoded default
    secret: bool = False  # Mask in UI, strip from API responses
    required: bool = False
    field_type: str = "text"  # "text", "password", "number", "select"
    choices: tuple[tuple[str, str], ...] = ()  # For select: (value, label)
    value_type: str = "str"  # "str", "int", "bool", "list[int]"


# ---------------------------------------------------------------------------
# Bot field declarations
# ---------------------------------------------------------------------------

MODULE_TITLE = "Telegram Bot Configuration"
MODULE_DESCRIPTION = (
    "Configures the Telegram bot that receives <code>/build</code> commands"
    " and delivers APK download links. Requires a Telegram bot token and a"
    " Jenkins server with a pipeline job ready to accept build triggers."
)

BOT_FIELDS: tuple[FieldDef, ...] = (
    # ── Telegram ──
    FieldDef(
        key="telegram.bot_token",
        env_var="TELEGRAM_BOT_TOKEN",
        attr="telegram_token",
        label="Bot Token",
        group="Telegram",
        description="Authentication token for the Telegram bot",
        help_html=(
            "Open Telegram → search for <strong>@BotFather</strong>"
            " → send <code>/newbot</code> → follow the prompts."
            " Copy the token it gives you."
        ),
        secret=True,
        required=True,
        field_type="password",
    ),
    FieldDef(
        key="telegram.allowed_chat_ids",
        env_var="ALLOWED_CHAT_IDS",
        attr="allowed_chat_ids",
        label="Allowed Chat IDs",
        group="Telegram",
        description="Users authorized to trigger builds",
        help_html=(
            "Send any message to your bot, then open"
            " <code>https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code>"
            " in a browser. Look for <code>\"chat\":{\"id\":…}</code>."
            " Comma-separate multiple IDs."
        ),
        required=True,
        value_type="list[int]",
    ),
    # ── Jenkins Connection ──
    FieldDef(
        key="jenkins.url",
        env_var="JENKINS_URL",
        attr="jenkins_url",
        label="Jenkins URL",
        group="Jenkins Connection",
        description="Internal Docker network URL (e.g. http://jenkins:8080)",
        required=True,
    ),
    FieldDef(
        key="jenkins.user",
        env_var="JENKINS_USER",
        attr="jenkins_user",
        label="Jenkins User",
        group="Jenkins Connection",
        description="Jenkins account with permission to trigger builds",
        required=True,
    ),
    FieldDef(
        key="jenkins.api_token",
        env_var="JENKINS_API_TOKEN",
        attr="jenkins_api_token",
        label="Jenkins API Token",
        group="Jenkins Connection",
        description="Token for triggering pipeline builds",
        help_html=(
            "In Jenkins: click your username (top-right) →"
            " <strong>Configure</strong> → <strong>API Token</strong>"
            " → <strong>Add new Token</strong> → copy the generated token."
        ),
        secret=True,
        required=True,
        field_type="password",
    ),
    FieldDef(
        key="jenkins.job_name",
        env_var="JENKINS_JOB_NAME",
        attr="jenkins_job_name",
        label="Pipeline Job Name",
        group="Jenkins Connection",
        description="Must match the pipeline job name in Jenkins",
        default="flutter-build",
    ),
    FieldDef(
        key="jenkins.job_id",
        env_var="JENKINS_JOB_ID",
        attr="jenkins_job_id",
        label="Jenkins Job ID",
        group="Jenkins Connection",
        description="URL-encoded job ID, visible in Jenkins URL as /job/<id>/",
        # Default is handled in post_resolve (defaults to job_name)
    ),
    # ── Build Settings ──
    FieldDef(
        key="bot.app_name",
        env_var="APP_NAME",
        attr="app_name",
        label="App Name",
        group="Build Settings",
        description='Display name shown in bot messages (e.g. "MyApp")',
        help_html=(
            'Name shown to users in bot messages, e.g. "MyApp".'
            " Defaults to the Drive folder name if not set,"
            ' then "your app".'
        ),
    ),
    FieldDef(
        key="drive.folder_name",
        env_var="DRIVE_FOLDER_NAME",
        attr="drive_folder_name",
        label="Drive Folder Name",
        group="Build Settings",
        description="Drive folder for APKs (auto-created if missing)",
    ),
    FieldDef(
        key="bot.max_recent_builds",
        env_var="MAX_RECENT_BUILDS",
        attr="max_recent_builds",
        label="Max Recent Builds",
        group="Build Settings",
        description="Build history limit (0 = unlimited)",
        default="0",
        field_type="number",
        value_type="int",
    ),
    FieldDef(
        key="bot.callback_url",
        env_var="BOT_CALLBACK_BASE_URL",
        attr="bot_callback_base_url",
        label="Bot Callback URL",
        group="Build Settings",
        description="Base URL where Jenkins POSTs build results (e.g. http://tg-bot:9090)",
        default="http://tg-bot:9090",
    ),
    FieldDef(
        key="bot.webhook_port",
        env_var="BOT_WEBHOOK_PORT",
        attr="bot_webhook_port",
        label="Bot Webhook Port",
        group="Build Settings",
        description="Port for the webhook receiver",
        default="9090",
        field_type="number",
        value_type="int",
    ),
    FieldDef(
        key="config_ui.url",
        env_var="CONFIG_UI_URL",
        attr="config_ui_url",
        label="Config UI URL",
        group="Build Settings",
        description="Host-facing URL for the config dashboard (shown in Telegram messages)",
    ),
)

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _nested_get(data: dict[str, Any], dotted_key: str) -> Any:
    """Read a value from a nested dict using a dotted key path."""
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _coerce(raw: Any, value_type: str) -> Any:
    """Convert a raw config value to its declared Python type."""
    if value_type == "str":
        return str(raw) if raw not in (None, "") else ""

    if value_type == "int":
        return int(raw) if raw not in (None, "") else 0

    if value_type == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() not in {"0", "false", "no", ""}

    if value_type == "list[int]":
        if isinstance(raw, list):
            return [int(v) for v in raw]
        if isinstance(raw, str) and raw:
            return [int(v.strip()) for v in raw.split(",") if v.strip()]
        return []

    return raw


def resolve_fields(
    fields: tuple[FieldDef, ...],
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Resolve config values with priority: file > env > .env > default."""
    load_dotenv()

    path = config_path
    if path is None and os.environ.get("CONFIG_PATH"):
        path = Path(os.environ["CONFIG_PATH"])

    file_data: dict[str, Any] = {}
    if path and path.exists():
        file_data = json.loads(path.read_text())

    values: dict[str, Any] = {}
    for f in fields:
        raw = _nested_get(file_data, f.key)
        if raw in (None, ""):
            raw = os.environ.get(f.env_var)
        if raw in (None, ""):
            raw = f.default
        values[f.attr] = _coerce(raw, f.value_type)

    return values


# ---------------------------------------------------------------------------
# Bot-specific post-resolution
# ---------------------------------------------------------------------------


def post_resolve(
    values: dict[str, Any], config_path: Path | None = None
) -> dict[str, Any]:
    """Apply bot-specific resolution logic after generic field resolution."""
    # app_name fallback: app_name → drive_folder_name → "your app"
    if not values.get("app_name"):
        values["app_name"] = values.get("drive_folder_name") or "your app"

    # job_id defaults to job_name
    if not values.get("jenkins_job_id"):
        values["jenkins_job_id"] = values.get("jenkins_job_name", "flutter-build")

    # oauth_token_path — keep tokens next to the config file when possible
    resolved_path = config_path
    if resolved_path is None and os.environ.get("CONFIG_PATH"):
        resolved_path = Path(os.environ["CONFIG_PATH"])

    if resolved_path is not None:
        values["oauth_token_path"] = resolved_path.parent / "oauth.json"
    else:
        values["oauth_token_path"] = OAUTH_TOKEN_PATH

    return values


# ---------------------------------------------------------------------------
# Schema serialization (for GET /control/schema)
# ---------------------------------------------------------------------------

# Fields excluded from the serialized schema — they are backend-only concerns.
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
