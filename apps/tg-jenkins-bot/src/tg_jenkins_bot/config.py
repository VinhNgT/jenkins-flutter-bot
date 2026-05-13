"""Bot configuration resolved from declarative schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import BOT_FIELDS, BOT_INFRA, post_resolve, resolve_fields


@dataclass(frozen=True)
class Config:
    """Bot configuration resolved from config file, env, and defaults."""

    # Telegram
    telegram_token: str
    allowed_chat_ids: list[int]

    # Build Orchestrator
    orchestrator_url: str

    bot_service_url: str

    # Optional
    app_name: str
    branch_list: list[str]
    session_ttl: int
    build_timeout: int
    admin_contact: str
    github_url: str

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> Config:
        """Build config with priority: file > env > .env > defaults."""
        values = resolve_fields(BOT_FIELDS + BOT_INFRA, config_path)
        values = post_resolve(values)
        return cls(**values)

    @property
    def bot_webhook_port(self) -> int:
        """Listen port derived from bot_service_url."""
        from urllib.parse import urlparse

        return urlparse(self.bot_service_url).port or 9090

    @property
    def bot_callback_url(self) -> str:
        """Full callback URL that build-orchestrator POSTs build results to."""
        return f"{self.bot_service_url.rstrip('/')}/callback/build-result"
