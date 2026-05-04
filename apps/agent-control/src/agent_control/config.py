"""Agent configuration resolved from config file, env, and defaults."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _nested_get(data: dict[str, Any], dotted_key: str) -> Any:
    """Read a dotted key from nested dict data."""
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


@dataclass(frozen=True)
class AgentConfig:
    """Jenkins inbound agent configuration."""

    jenkins_url: str
    agent_name: str
    secret: str
    web_socket: bool
    tunnel: str

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> AgentConfig:
        """Build config with priority: file > env > .env > defaults."""
        load_dotenv()

        resolved_path = config_path
        if resolved_path is None and os.environ.get("CONFIG_PATH"):
            resolved_path = Path(os.environ["CONFIG_PATH"])

        file_data: dict[str, Any] = {}
        if resolved_path and resolved_path.exists():
            file_data = json.loads(resolved_path.read_text())

        def get_value(
            file_key: str,
            env_key: str,
            *,
            default: str = "",
        ) -> str:
            file_value = _nested_get(file_data, file_key)
            if file_value not in (None, ""):
                return str(file_value)

            env_value = os.environ.get(env_key)
            if env_value not in (None, ""):
                return env_value

            return default

        web_socket_raw = get_value(
            "agent.web_socket",
            "JENKINS_WEB_SOCKET",
            default="true",
        )

        return cls(
            jenkins_url=get_value(
                "jenkins.url",
                "JENKINS_URL",
                default="http://jenkins:8080",
            ),
            agent_name=get_value(
                "agent.name",
                "JENKINS_AGENT_NAME",
                default="flutter-agent",
            ),
            secret=get_value(
                "agent.secret",
                "JENKINS_SECRET",
            ),
            web_socket=web_socket_raw.lower() not in {"0", "false", "no"},
            tunnel=get_value(
                "agent.tunnel",
                "JENKINS_TUNNEL",
                default="",
            ),
        )
