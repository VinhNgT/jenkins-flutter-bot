"""Mock agent-control server — emulates the flutter-agent's control API.

Serves the same /control/* endpoints that config-hub queries:
  - GET  /control/status  — reports agent as configured and running
  - GET  /control/schema  — returns the real agent schema (AGENT_FIELDS + AGENT_INFRA)
  - GET  /control/config  — returns empty config values (no file in mock mode)
  - PUT  /control/config  — no-op save (returns success without writing)
  - POST /control/start   — no-op, returns running status
  - POST /control/stop    — no-op, returns running status
  - POST /control/restart — no-op, returns running status
"""

from __future__ import annotations

import logging
import os
from typing import Any

import uvicorn
from fastapi import FastAPI

logger = logging.getLogger(__name__)

MOCK_AGENT_PORT = int(os.environ.get("MOCK_AGENT_PORT", "9091"))

# ---------------------------------------------------------------------------
# Hardcoded agent schema — mirrors agent_control.schema exactly.
#
# We inline the schema JSON rather than importing from agent-control so that
# mock-jenkins stays dependency-free from the real agent-control package.
# ---------------------------------------------------------------------------

_AGENT_SCHEMA: dict[str, Any] = {
    "title": "Jenkins Agent Configuration",
    "description": (
        "Configures the Flutter build agent that connects to Jenkins as an"
        " inbound node. The agent runs inside Docker with Flutter and Android"
        " SDKs pre-installed. Obtain the agent secret from the node's status"
        " page in Jenkins after creating the node."
    ),
    "fields": [
        {
            "key": "agent.name",
            "env_var": "JENKINS_AGENT_NAME",
            "label": "Agent Name",
            "group": "Agent Connection",
            "description": "Must match the node name in Jenkins",
            "help_html": (
                "Must exactly match the node name in Jenkins. Create the node:"
                " <strong>Manage Jenkins</strong> → <strong>Nodes</strong>"
                " → <strong>New Node</strong> → name it"
                " (e.g. <code>flutter-agent</code>)."
            ),
            "default": "flutter-agent",
            "required": False,
            "secret": False,
            "field_type": "text",
        },
        {
            "key": "agent.secret",
            "env_var": "JENKINS_SECRET",
            "label": "Agent Secret",
            "group": "Agent Connection",
            "description": "Authentication secret from the Jenkins node",
            "help_html": (
                "After creating the node in Jenkins, go to"
                " <strong>Nodes</strong> → click the agent name → the secret"
                " is shown on the status page under the connection command."
                " Copy the long hex string."
            ),
            "default": "",
            "required": True,
            "secret": True,
            "field_type": "password",
        },
    ],
    "infra": [
        {
            "key": "jenkins.url",
            "env_var": "JENKINS_URL",
            "label": "Jenkins URL",
            "group": "Agent Connection",
            "description": "Same Jenkins controller URL used for the agent's inbound connection",
            "default": "http://jenkins:8080",
            "required": False,
            "secret": False,
            "field_type": "text",
        },
        {
            "key": "agent.web_socket",
            "env_var": "JENKINS_WEB_SOCKET",
            "label": "WebSocket Mode",
            "group": "Agent Connection",
            "description": "WebSocket recommended; disable only for direct TCP tunnels",
            "default": "true",
            "required": False,
            "secret": False,
            "field_type": "select",
            "choices": [["true", "Enabled (default)"], ["false", "Disabled (TCP)"]],
        },
        {
            "key": "agent.tunnel",
            "env_var": "JENKINS_TUNNEL",
            "label": "Tunnel",
            "group": "Agent Connection",
            "description": "TCP tunnel endpoint (only when WebSocket is disabled)",
            "default": "",
            "required": False,
            "secret": False,
            "field_type": "text",
        },
    ],
}


# ---------------------------------------------------------------------------
# FastAPI agent control mock
# ---------------------------------------------------------------------------

agent_app = FastAPI(title="mock-agent-control")


def _status_response() -> dict[str, Any]:
    """Return a mock status that shows the agent as configured and running."""
    return {
        "configured": True,
        "running": True,
        "pid": 1,
        "last_error": None,
        "agent_name": os.environ.get("JENKINS_AGENT_NAME", "flutter-agent"),
    }


@agent_app.get("/control/status")
async def agent_status() -> dict[str, Any]:
    """Report the mock agent as running."""
    return _status_response()


@agent_app.get("/control/schema")
async def agent_schema() -> dict[str, Any]:
    """Return the agent config schema (identical to real agent-control)."""
    return _AGENT_SCHEMA


@agent_app.post("/control/start")
async def agent_start() -> dict[str, Any]:
    """No-op start — agent is always running in mock mode."""
    return _status_response()


@agent_app.post("/control/stop")
async def agent_stop() -> dict[str, Any]:
    """No-op stop — agent is always running in mock mode."""
    return _status_response()


@agent_app.get("/control/config")
async def agent_get_config() -> dict[str, Any]:
    """Return empty config — no file is written in mock mode."""
    # Secret keys from the inline schema that need secret_lengths tracking.
    secret_keys = [f["key"] for f in _AGENT_SCHEMA["fields"] if f.get("secret")]
    secret_lengths = {key: False for key in secret_keys}
    return {"values": {}, "secret_lengths": secret_lengths}


@agent_app.put("/control/config")
async def agent_put_config() -> dict[str, Any]:
    """No-op config save — mock mode has no persistent config file."""
    return {"status": "ok"}


@agent_app.post("/control/restart")
async def agent_restart() -> dict[str, Any]:
    """No-op restart — agent is always running in mock mode."""
    return _status_response()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def cli() -> None:
    """CLI entry point for the mock agent server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )
    logger.info("Starting mock-agent-control on port %d", MOCK_AGENT_PORT)
    uvicorn.run(agent_app, host="0.0.0.0", port=MOCK_AGENT_PORT)
