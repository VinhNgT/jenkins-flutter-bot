"""Declarative schema for the Jenkins agent configuration module.

This is the single source of truth for all agent config fields.  It drives:
  - AgentConfig.resolve()  via resolve_fields()
  - GET /control/schema    via serialize_schema()
  - config-ui rendering    via the serialized JSON
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Field definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldDef:
    """Declarative definition for a single configuration field."""

    key: str  # Dotted JSON key: "agent.secret"
    env_var: str  # Env var fallback: "JENKINS_SECRET"
    attr: str  # Python attribute on AgentConfig: "secret"
    label: str  # UI label: "Agent Secret"
    group: str  # UI card grouping
    description: str = ""  # Short text below the label
    help_html: str = ""  # Rich HTML for ? popover
    default: str = ""  # Hardcoded default
    secret: bool = False  # Mask in UI, strip from API responses
    required: bool = False
    field_type: str = "text"  # "text", "password", "number", "select"
    choices: tuple[tuple[str, str], ...] = ()  # For select: (value, label)
    value_type: str = "str"  # "str", "int", "bool", "list[int]"


# ---------------------------------------------------------------------------
# Agent field declarations
# ---------------------------------------------------------------------------

MODULE_TITLE = "Jenkins Agent Configuration"
MODULE_DESCRIPTION = (
    "Configures the Flutter build agent that connects to Jenkins as an"
    " inbound node. The agent runs inside Docker with Flutter and Android"
    " SDKs pre-installed. Obtain the agent secret from the node's status"
    " page in Jenkins after creating the node."
)

AGENT_FIELDS: tuple[FieldDef, ...] = (
    FieldDef(
        key="jenkins.url",
        env_var="JENKINS_URL",
        attr="jenkins_url",
        label="Jenkins URL",
        group="Agent Connection",
        description="Same Jenkins controller URL used for the agent's inbound connection",
        default="http://jenkins:8080",
    ),
    FieldDef(
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
    ),
    FieldDef(
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
    ),
    FieldDef(
        key="agent.web_socket",
        env_var="JENKINS_WEB_SOCKET",
        attr="web_socket",
        label="WebSocket Mode",
        group="Agent Connection",
        description="WebSocket recommended; disable only for direct TCP tunnels",
        default="true",
        field_type="select",
        choices=(("true", "Enabled (default)"), ("false", "Disabled (TCP)")),
        value_type="bool",
    ),
    FieldDef(
        key="agent.tunnel",
        env_var="JENKINS_TUNNEL",
        attr="tunnel",
        label="Tunnel",
        group="Agent Connection",
        description="TCP tunnel endpoint (only when WebSocket is disabled)",
    ),
)

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _nested_get(data: dict[str, Any], dotted_key: str) -> Any:
    """Read a value from a nested dict using a dotted key path."""
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _coerce(raw: Any, value_type: str) -> Any:
    """Convert a raw config value to its declared Python type."""
    if value_type == "str":
        return str(raw) if raw not in (None, "") else ""

    if value_type == "int":
        return int(raw) if raw not in (None, "") else 0

    if value_type == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() not in {"0", "false", "no", ""}

    if value_type == "list[int]":
        if isinstance(raw, list):
            return [int(v) for v in raw]
        if isinstance(raw, str) and raw:
            return [int(v.strip()) for v in raw.split(",") if v.strip()]
        return []

    return raw


def resolve_fields(
    fields: tuple[FieldDef, ...],
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Resolve config values with priority: file > env > .env > default."""
    load_dotenv()

    path = config_path
    if path is None and os.environ.get("CONFIG_PATH"):
        path = Path(os.environ["CONFIG_PATH"])

    file_data: dict[str, Any] = {}
    if path and path.exists():
        file_data = json.loads(path.read_text())

    values: dict[str, Any] = {}
    for f in fields:
        raw = _nested_get(file_data, f.key)
        if raw in (None, ""):
            raw = os.environ.get(f.env_var)
        if raw in (None, ""):
            raw = f.default
        values[f.attr] = _coerce(raw, f.value_type)

    return values


# ---------------------------------------------------------------------------
# Schema serialization (for GET /control/schema)
# ---------------------------------------------------------------------------

_BACKEND_ONLY_KEYS = {"attr", "value_type", "env_var"}


def serialize_schema(
    fields: tuple[FieldDef, ...],
    title: str,
    description: str,
) -> dict[str, Any]:
    """Serialize module schema to a JSON-ready dict for the HTTP endpoint."""
    return {
        "title": title,
        "description": description,
        "fields": [
            {k: v for k, v in asdict(f).items() if k not in _BACKEND_ONLY_KEYS}
            for f in fields
        ],
    }
