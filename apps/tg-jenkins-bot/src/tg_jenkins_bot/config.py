"""Bot configuration resolved from declarative schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field, field_validator
from config_core import ServiceSettings

_DEFAULT_CONFIG_PATH = Path("/app/data/bot.json")


class BotSettings(ServiceSettings):
    """Bot configuration resolved from config file, env, and defaults."""

    config_path: ClassVar[Path] = _DEFAULT_CONFIG_PATH

    # Telegram
    telegram_token: str = Field(
        title="Bot Token",
        description="Token from @BotFather",
        json_schema_extra={
            "group": "Telegram",
            "order": 1,
            "help_html": (
                'Message <a href="https://t.me/BotFather" target="_blank"'
                ' rel="noopener">@BotFather</a> with <code>/newbot</code> to get'
                " a token. It looks like <code>123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11</code>."
            ),
            "secret": True,
            "json_key": "telegram.bot_token",
        },
    )
    allowed_chat_ids: list[int] = Field(
        default_factory=list,
        title="Allowed Chat IDs",
        description="List of chat IDs allowed to use the bot",
        json_schema_extra={
            "group": "Telegram",
            "order": 2,
            "help_html": (
                "You can find your chat ID by messaging"
                ' <a href="https://t.me/userinfobot" target="_blank"'
                ' rel="noopener">@userinfobot</a>. For groups, add the bot to the'
                " group and check the logs. Looks like <code>123456789</code> or"
                " <code>-100123456789</code>."
            ),
            "json_key": "telegram.allowed_chat_ids",
            "field_type": "chat_id_list",
        },
    )
    admin_contact: str = Field(
        "an admin",
        title="Admin Contact",
        description="Shown to unauthorized users (e.g. '@username' or 'an admin')",
        json_schema_extra={"group": "Telegram", "order": 3, "json_key": "telegram.admin_contact"},
    )

    # Application
    app_name: str = Field(
        "My App",
        title="App Name",
        description="Name of the app being built (used in messages)",
        json_schema_extra={"group": "Application", "order": 1, "json_key": "bot.app_name"},
    )
    branches: dict[str, str] = Field(
        default={"Stable Release": "main", "Testing Version": "develop"},
        title="Build Options",
        description="Mapping of display label → git branch (e.g. 'Stable Release' → 'main')",
        json_schema_extra={
            "group": "Application",
            "order": 2,
            "json_key": "bot.branches",
            "field_type": "key_value",
        },
    )
    webapp_url: str = Field(
        title="Web App URL",
        description="Public HTTPS URL for the Telegram Web App (e.g. https://your-host/webapp/)",
        json_schema_extra={"group": "Application", "order": 3, "json_key": "bot.webapp_url"},
    )
    webapp_short_name: str = Field(
        "",
        title="Mini App Short Name",
        description=(
            "Short name of the Mini App registered with @BotFather via /newapp "
            "(e.g. 'builds'). When set, command buttons launch the app as a native "
            "Telegram Mini App panel in group chats via t.me/bot/shortname. "
            "Leave blank to fall back to a standard in-app browser button."
        ),
        json_schema_extra={"group": "Application", "order": 4, "json_key": "bot.webapp_short_name"},
    )

    @field_validator("webapp_url", mode="before")
    @classmethod
    def normalize_webapp_url(cls, v: Any) -> str:
        if not isinstance(v, str):
            return v
        v = v.strip()
        if not v:
            return v

        # 1. Normalize schema prefix (default to https:// if none exists)
        if not (v.startswith("http://") or v.startswith("https://")):
            v = f"https://{v}"

        # 2. Ensure it ends with /webapp/
        v = v.rstrip("/")
        if not v.endswith("/webapp"):
            v = f"{v}/webapp"

        return f"{v}/"

    # Project
    github_url: str = Field(
        "",
        title="GitHub Repository URL",
        description="Public web URL of the repository. Used to add a GitHub link to the bot's welcome message.",
        json_schema_extra={
            "group": "Project",
            "order": 1,
            "json_key": "project.github_url",
        },
    )

    # Advanced (deployment topology — configurable but rarely changed)
    bot_service_url: str = Field(
        title="Bot Service URL",
        description="Internal URL for this service's webhook endpoint",
        json_schema_extra={
            "group": "Advanced",
            "order": 1,
            "help_html": "Internal URL where this bot receives webhooks (e.g., <code>http://tg-jenkins-bot:9090</code>). Normally provided by the deployment environment.",
            "json_key": "bot.service_url",
        },
    )
    build_manager_url: str = Field(
        title="Build Manager URL",
        description="Internal URL of the build-manager service",
        json_schema_extra={
            "group": "Advanced",
            "order": 2,
            "help_html": "Internal URL of the build-manager service (e.g., <code>http://build-manager:9010</code>). Normally provided by the deployment environment.",
            "json_key": "bot.build_manager_url",
        },
    )
    file_manager_url: str = Field(
        title="File Manager URL",
        description="Internal URL of the file-manager service",
        json_schema_extra={
            "group": "Advanced",
            "order": 3,
            "help_html": "Internal URL of the file-manager service (e.g., <code>http://file-manager:9092</code>). Used to query build history.",
            "json_key": "bot.file_manager_url",
        },
    )

    @field_validator("branches", mode="before")
    @classmethod
    def parse_branches(cls, v: Any) -> dict[str, str]:
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return {}
            # Try to parse as JSON dict
            if v.startswith("{"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, dict):
                        return {str(k): str(val) for k, val in parsed.items()}
                except Exception:
                    pass
            # Comma-separated list fallback
            items = [b.strip() for b in v.split(",") if b.strip()]
            return {b: b for b in items}
        if isinstance(v, list):
            return {str(b): str(b) for b in v if b}
        return v

    @field_validator("allowed_chat_ids", mode="before")
    @classmethod
    def parse_allowed_chat_ids(cls, v: Any) -> list[int]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [int(x) for x in parsed]
                except Exception:
                    pass
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return v

    @property
    def bot_callback_url(self) -> str:
        """Full callback URL that build-manager POSTs build results to."""
        return f"{self.bot_service_url.rstrip('/')}/callback/build-result"
