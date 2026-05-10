"""Stack Manager settings — resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Immutable application settings resolved once at startup.

    Env vars:
        BOT_CONTROL_URL      — Base URL of the tg-bot control API
        AGENT_CONTROL_URL    — Base URL of the agent-control API
        BOT_CONFIG_PATH      — Path to bot.json
        AGENT_CONFIG_PATH    — Path to agent.json
        DRIVE_CONFIG_PATH    — Path to drive.json
        PROJECT_CONFIG_PATH  — Path to project.json
    """

    bot_control_url: str | None
    agent_control_url: str | None
    bot_config_path: Path | None
    agent_config_path: Path | None
    drive_config_path: Path | None
    project_config_path: Path | None

    @classmethod
    def from_env(cls) -> Settings:
        """Resolve settings from environment variables."""

        def _path(env: str) -> Path | None:
            val = os.environ.get(env)
            return Path(val) if val else None

        return cls(
            bot_control_url=os.environ.get("BOT_CONTROL_URL") or None,
            agent_control_url=os.environ.get("AGENT_CONTROL_URL") or None,
            bot_config_path=_path("BOT_CONFIG_PATH"),
            agent_config_path=_path("AGENT_CONFIG_PATH"),
            drive_config_path=_path("DRIVE_CONFIG_PATH"),
            project_config_path=_path("PROJECT_CONFIG_PATH"),
        )
