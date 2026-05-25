from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import Field
from config_core import ServiceSettings

_DEFAULT_CONFIG_PATH = Path("/app/data/agent.json")


class AgentSettings(ServiceSettings):
    """Jenkins inbound agent configuration."""

    config_path: ClassVar[Path] = _DEFAULT_CONFIG_PATH

    # ── Agent Connection ──
    agent_name: str = Field(
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

    # ── Advanced (deployment topology) ──
    jenkins_url: str = Field(
        title="Jenkins URL",
        description="Same Jenkins controller URL used for the agent's inbound connection",
        json_schema_extra={
            "group": "Agent Connection",
            "help_html": "URL of the Jenkins controller (e.g., <code>http://jenkins:8080</code> for internal, or <code>https://jenkins.yourdomain.com</code> if external).",
            "json_key": "agent.jenkins_url",
        },
    )

    web_socket: bool = Field(
        True,
        title="WebSocket Mode",
        description="WebSocket recommended; disable only for direct TCP tunnels",
        json_schema_extra={
            "group": "Advanced",
            "field_type": "select",
            "choices": [["true", "Enabled (default)"], ["false", "Disabled (TCP)"]],
            "json_key": "JENKINS_WEB_SOCKET",
        },
    )

    tunnel: str = Field(
        "",
        title="Tunnel",
        description="TCP tunnel endpoint (only when WebSocket is disabled)",
        json_schema_extra={
            "group": "Advanced",
            "json_key": "JENKINS_TUNNEL",
        },
    )

    # ── VPN ──
    vpn_enabled: bool = Field(
        False,
        title="Enable VPN",
        description="Connect to an OpenVPN server during builds (requires .ovpn file upload)",
        json_schema_extra={
            "group": "VPN",
            "field_type": "select",
            "choices": [["true", "Enabled"], ["false", "Disabled (default)"]],
            "json_key": "vpn.enabled",
        },
    )

