"""Bot configuration resolved from declarative schema."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from config_core import ServiceSettings

_DEFAULT_CONFIG_PATH = Path("/app/data/bot.json")


class BotConfig(ServiceSettings):
    """Bot configuration resolved from config file, env, and defaults."""

    # Telegram
    telegram_token: str = Field(
        "",
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
        default_factory=list,
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
        default_factory=lambda: ["main", "develop"],
        title="Git Branches",
        description="Comma-separated list of branches to show in the build menu",
        json_schema_extra={"group": "Application", "json_key": "bot.branch_list"},
    )
    session_ttl: int = Field(
        300,
        title="Session TTL (seconds)",
        description="How long menu sessions stay active",
        json_schema_extra={"group": "Application", "json_key": "bot.session_ttl"},
    )
    build_timeout: int = Field(
        1800,
        title="Build Timeout (seconds)",
        description="How long before a pending build is considered dead",
        json_schema_extra={"group": "Application", "json_key": "bot.build_timeout"},
    )

    # Project
    github_url: str = Field(
        "",
        title="GitHub Repository URL",
        description="Used to generate links to commits in Telegram messages",
        json_schema_extra={
            "group": "Project",
            "help_html": (
                "The public web URL of your GitHub repository."
                " Used only by the bot to make commit hashes clickable in Telegram."
                " Example: <code>https://github.com/my-org/my-repo</code>."
            ),
            "json_key": "project.github_url",
        },
    )

    # Infrastructure
    bot_service_url: str = Field("http://tg-bot:9090", json_schema_extra={"infra": True})
    build_manager_url: str = Field("http://build-manager:9010", json_schema_extra={"infra": True})

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

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> BotConfig:
        """Build config with priority: file > env > defaults."""
        return cls.load()

    @property
    def bot_callback_url(self) -> str:
        """Full callback URL that build-manager POSTs build results to."""
        return f"{self.bot_service_url.rstrip('/')}/callback/build-result"
