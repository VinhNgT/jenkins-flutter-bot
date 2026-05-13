"""Declarative schema for the Jenkins agent configuration module.

This is the single source of truth for all agent config fields.  It drives:
  - AgentConfig.resolve()  via resolve_fields()
  - GET /control/schema    via serialize_schema()
  - config-hub rendering    via the serialized JSON
"""

from __future__ import annotations


from functools import cache

from config_schema import ConfigRegistry

# ---------------------------------------------------------------------------
# Module metadata
# ---------------------------------------------------------------------------


@cache
def get_registry() -> ConfigRegistry:
    registry = ConfigRegistry(
        title="Jenkins Agent Configuration",
        description=(
            "Configures the Flutter build agent that connects to Jenkins as an"
            " inbound node. The agent runs inside Docker with Flutter and Android"
            " SDKs pre-installed. Obtain the agent secret from the node's status"
            " page in Jenkins after creating the node."
        ),
    )

    # ---------------------------------------------------------------------------
    # Agent field declarations
    # ---------------------------------------------------------------------------

    registry.register_runtime(
        key="agent.name",
        env_var="JENKINS_AGENT_NAME",
        attr="agent_name",
        label="Agent Name",
        group="Agent Connection",
        description="Must match the node name in Jenkins",
        help_html=(
            "Must exactly match the node name in Jenkins. Create the node:"
            " <strong>Manage Jenkins</strong> → <strong>Nodes</strong>"
            " → <strong>New Node</strong> → name it"
            " (e.g. <code>flutter-agent</code>)."
        ),
        default="flutter-agent",
    )

    registry.register_runtime(
        key="agent.secret",
        env_var="JENKINS_SECRET",
        attr="secret",
        label="Agent Secret",
        group="Agent Connection",
        description="Authentication secret from the Jenkins node",
        help_html=(
            "After creating the node in Jenkins, go to"
            " <strong>Nodes</strong> → click the agent name → the secret"
            " is shown on the status page under the connection command."
            " Copy the long hex string."
        ),
        secret=True,
        required=True,
        field_type="password",
    )

    # ---------------------------------------------------------------------------
    # Infrastructure fields (environment-specific, not portable)
    # ---------------------------------------------------------------------------

    registry.register_infra(
        env_var="JENKINS_URL",
        attr="jenkins_url",
        label="Jenkins URL",
        group="Agent Connection",
        description="Same Jenkins controller URL used for the agent's inbound connection",
        default="http://jenkins:8080",
    )

    registry.register_infra(
        env_var="JENKINS_WEB_SOCKET",
        attr="web_socket",
        label="WebSocket Mode",
        group="Agent Connection",
        description="WebSocket recommended; disable only for direct TCP tunnels",
        default="true",
        field_type="select",
        choices=(("true", "Enabled (default)"), ("false", "Disabled (TCP)")),
        value_type="bool",
    )

    registry.register_infra(
        env_var="JENKINS_TUNNEL",
        attr="tunnel",
        label="Tunnel",
        group="Agent Connection",
        description="TCP tunnel endpoint (only when WebSocket is disabled)",
    )

    return registry
