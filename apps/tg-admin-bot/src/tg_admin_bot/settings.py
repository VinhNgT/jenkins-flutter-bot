"""Admin bot settings — resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Settings for the admin bot, resolved from environment variables.

    Env vars:
        ADMIN_BOT_TOKEN      — Telegram bot token for the admin bot
        ADMIN_CHAT_ID        — Telegram chat ID authorized for admin commands
        BOT_CONTROL_URL      — Base URL of the tg-bot control API
        AGENT_CONTROL_URL    — Base URL of the agent-control API
        BOT_CONFIG_PATH      — Path to bot.json
        AGENT_CONFIG_PATH    — Path to agent.json
        UI_CONFIG_PATH       — Path to ui.json (for Drive OAuth creds)
    """

    bot_token: str
    admin_chat_id: int
    bot_control_url: str | None
    agent_control_url: str | None
    bot_config_path: Path | None
    agent_config_path: Path | None
    ui_config_path: Path | None

    @classmethod
    def from_env(cls) -> Settings:
        """Resolve settings from environment variables."""
        token = os.environ.get("ADMIN_BOT_TOKEN", "")
        chat_id_str = os.environ.get("ADMIN_CHAT_ID", "0")
        try:
            chat_id = int(chat_id_str)
        except ValueError:
            chat_id = 0

        def _path(env: str) -> Path | None:
            val = os.environ.get(env)
            return Path(val) if val else None

        return cls(
            bot_token=token,
            admin_chat_id=chat_id,
            bot_control_url=os.environ.get("BOT_CONTROL_URL"),
            agent_control_url=os.environ.get("AGENT_CONTROL_URL"),
            bot_config_path=_path("BOT_CONFIG_PATH"),
            agent_config_path=_path("AGENT_CONFIG_PATH"),
            ui_config_path=_path("UI_CONFIG_PATH"),
        )
