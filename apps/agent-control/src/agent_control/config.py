"""Agent configuration resolved from declarative schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import AGENT_FIELDS, AGENT_INFRA, resolve_fields


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
        values = resolve_fields(AGENT_FIELDS + AGENT_INFRA, config_path)
        return cls(**values)
