"""Stack Manager settings — resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Immutable application settings resolved once at startup.

    Env vars:
        BOT_CONTROL_URL           — Base URL of the tg-bot control API
        AGENT_CONTROL_URL         — Base URL of the agent-control API
        FILE_MANAGER_CONTROL_URL  — Base URL of the file-manager API
        SM_SERVICE_URL            — This service's own external URL
        BOT_CONFIG_PATH           — Path to bot.json
        AGENT_CONFIG_PATH         — Path to agent.json
        DRIVE_CONFIG_PATH         — Path to drive.json
        BUILD_DATA_PATH           — Directory for build state persistence
    """

    bot_control_url: str | None
    agent_control_url: str | None
    file_manager_url: str | None
    sm_service_url: str
    bot_config_path: Path | None
    agent_config_path: Path | None
    drive_config_path: Path | None
    build_data_path: Path

    @classmethod
    def from_env(cls) -> Settings:
        """Resolve settings from environment variables."""

        def _path(env: str) -> Path | None:
            val = os.environ.get(env)
            return Path(val) if val else None

        return cls(
            bot_control_url=os.environ.get("BOT_CONTROL_URL") or None,
            agent_control_url=os.environ.get("AGENT_CONTROL_URL") or None,
            file_manager_url=os.environ.get("FILE_MANAGER_CONTROL_URL") or None,
            sm_service_url=os.environ.get("SM_SERVICE_URL", "http://localhost:9000"),
            bot_config_path=_path("BOT_CONFIG_PATH"),
            agent_config_path=_path("AGENT_CONFIG_PATH"),
            drive_config_path=_path("DRIVE_CONFIG_PATH"),
            build_data_path=Path(
                os.environ.get("BUILD_DATA_PATH", "data/builds")
            ),
        )
