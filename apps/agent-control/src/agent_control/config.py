"""Agent configuration resolved from declarative schema."""

from __future__ import annotations

from pathlib import Path
from pydantic import Field
from config_core import ServiceSettings

# Default config file path inside the container. Can be overridden via the
# CONFIG_PATH environment variable for local development outside Docker.
_DEFAULT_CONFIG_PATH = Path("/app/data/agent.json")


class AgentConfig(ServiceSettings):
    """Jenkins inbound agent configuration."""

    # ── Agent Connection ──
    agent_name: str = Field(
        "flutter-agent",
        title="Agent Name",
        description="Must match the node name in Jenkins",
        json_schema_extra={
            "group": "Agent Connection",
            "help_html": (
                "Must exactly match the node name in Jenkins. Create the node:"
                " <strong>Manage Jenkins</strong> → <strong>Nodes</strong>"
                " → <strong>New Node</strong> → name it"
                " (e.g. <code>flutter-agent</code>)."
            ),
            "json_key": "agent.name",
        },
    )

    secret: str = Field(
        "",
        title="Agent Secret",
        description="Authentication secret from the Jenkins node",
        json_schema_extra={
            "group": "Agent Connection",
            "help_html": (
                "After creating the node in Jenkins, go to"
                " <strong>Nodes</strong> → click the agent name → the secret"
                " is shown on the status page under the connection command."
                " Copy the long hex string."
            ),
            "secret": True,
            "field_type": "password",
            "json_key": "agent.secret",
        },
    )

    # ── Infra ──
    jenkins_url: str = Field(
        "http://jenkins:8080",
        title="Jenkins URL",
        description="Same Jenkins controller URL used for the agent's inbound connection",
        json_schema_extra={
            "group": "Agent Connection",
            "infra": True,
        },
    )

    web_socket: bool = Field(
        True,
        title="WebSocket Mode",
        description="WebSocket recommended; disable only for direct TCP tunnels",
        json_schema_extra={
            "group": "Agent Connection",
            "field_type": "select",
            "choices": [["true", "Enabled (default)"], ["false", "Disabled (TCP)"]],
            "infra": True,
            "json_key": "JENKINS_WEB_SOCKET",
        },
    )

    tunnel: str = Field(
        "",
        title="Tunnel",
        description="TCP tunnel endpoint (only when WebSocket is disabled)",
        json_schema_extra={
            "group": "Agent Connection",
            "infra": True,
            "json_key": "JENKINS_TUNNEL",
        },
    )

    @classmethod
    def resolve(cls, config_path: Path | None = None) -> AgentConfig:
        """Build config with priority: file > env > defaults."""
        return cls.load()
