"""Bot configuration resolved from declarative schema."""

from __future__ import annotations

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
        title="Allowed Chat IDs",
        description="Comma-separated list of chat IDs allowed to use the bot",
        json_schema_extra={
            "group": "Telegram",
            "help_html": (
                "You can find your chat ID by messaging"
                ' <a href="https://t.me/userinfobot" target="_blank"'
                ' rel="noopener">@userinfobot</a>. For groups, add the bot to the'
                " group and check the logs. Looks like <code>123456789</code> or"
                " <code>-100123456789</code>."
            ),
            "json_key": "telegram.allowed_chat_ids",
        },
    )
    admin_contact: str = Field(
        "an admin",
        title="Admin Contact",
        description="Shown to unauthorized users (e.g. '@username' or 'an admin')",
        json_schema_extra={"group": "Telegram", "json_key": "telegram.admin_contact"},
    )

    # Application
    app_name: str = Field(
        "My App",
        title="App Name",
        description="Name of the app being built (used in messages)",
        json_schema_extra={"group": "Application", "json_key": "bot.app_name"},
    )
    branch_list: list[str] = Field(
        default=["main", "develop"],
        title="Git Branches",
        description="Comma-separated list of branches to show in the build menu",
        json_schema_extra={"group": "Application", "json_key": "bot.branch_list"},
    )
    session_ttl: int = Field(
        60,
        title="Session TTL (seconds)",
        description="How long menu sessions stay active",
        json_schema_extra={"group": "Advanced", "json_key": "bot.session_ttl"},
    )

    # Project
    github_url: str = Field(
        "",
        title="GitHub Repository URL",
        description="Public web URL of the repository. Used to add a GitHub link to the bot's welcome message.",
        json_schema_extra={
            "group": "Project",
            "json_key": "project.github_url",
        },
    )

    # Advanced (deployment topology — configurable but rarely changed)
    bot_service_url: str = Field(
        title="Bot Service URL",
        description="Internal URL for this service's webhook endpoint",
        json_schema_extra={
            "group": "Advanced",
            "help_html": "Internal URL where this bot receives webhooks (e.g., <code>http://tg-jenkins-bot:9090</code>). Normally provided by the deployment environment.",
            "json_key": "bot.service_url",
        },
    )
    build_manager_url: str = Field(
        title="Build Manager URL",
        description="Internal URL of the build-manager service",
        json_schema_extra={
            "group": "Advanced",
            "help_html": "Internal URL of the build-manager service (e.g., <code>http://build-manager:9010</code>). Normally provided by the deployment environment.",
            "json_key": "bot.build_manager_url",
        },
    )

    @field_validator("branch_list", mode="before")
    @classmethod
    def parse_branch_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [b.strip() for b in v.split(",") if b.strip()]
        return v

    @field_validator("allowed_chat_ids", mode="before")
    @classmethod
    def parse_allowed_chat_ids(cls, v: Any) -> list[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @property
    def bot_callback_url(self) -> str:
        """Full callback URL that build-manager POSTs build results to."""
        return f"{self.bot_service_url.rstrip('/')}/callback/build-result"
