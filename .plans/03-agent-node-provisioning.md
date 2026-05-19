# Task 03: Agent Node Provisioning API

Add an API-driven flow to auto-create Jenkins agent nodes and retrieve their
secrets, eliminating the most error-prone setup steps.

## Why

Currently, users must:
1. Open Jenkins UI → Manage Nodes → New Node → fill 5 exact fields → copy secret hex
2. Open config-hub → paste secret into the agent config form

This is 10+ clicks across two UIs with one manual copy-paste that must match
exactly. The API-driven flow replaces both steps with a single "Provision Agent"
button click in config-hub.

## Dependency

**Independent of** Task 01 (polling). Can be implemented in parallel.
**Independent of** Task 04 (agent optionality), but they complement each other.

## Scope

**Services:** `build-manager` (Jenkins API calls) + `config-hub` (orchestration + UI).
**Architecture:** Build-manager already has `JenkinsClient` with auth. All Jenkins
API logic stays in build-manager. Config-hub calls build-manager's new endpoint,
then pushes the secret to agent-control.

## Current State

### Build-manager

| File | Role |
|------|------|
| `apps/build-manager/src/build_manager/builds/jenkins_client.py` | Jenkins REST client — trigger, query, cancel |
| `apps/build-manager/src/build_manager/routers/builds.py` | Build API routes |

`JenkinsClient` already has Basic Auth configured. No node management methods exist.

### Config-hub

| File | Lines | Role |
|------|-------|------|
| `apps/config-hub/src/config_hub/manager.py` | 264 | ConfigHubManager — schema proxy, config CRUD |
| `apps/config-hub/src/config_hub/services.py` | 138 | ServiceClient — HTTP client for service control APIs |
| `apps/config-hub/src/config_hub/config.py` | 20 | HubBootstrap — env-only config (bot/agent/fm/bm URLs) |

`ConfigHubManager` already has `self.services` (ServiceClient) with access to
all services. It knows `BUILD_MANAGER_URL`.

### Agent-control

Config-hub already pushes config to agent-control via `PUT /control/config`
and starts it via `POST /control/start`. This flow is unchanged.

## Implementation Steps

### Step 1: Add node provisioning methods to `JenkinsClient`

**File:** `apps/build-manager/src/build_manager/builds/jenkins_client.py`

#### Add `_get_crumb()` — CSRF token helper

Jenkins requires a CSRF crumb for POST requests. Add a private helper:

```python
async def _get_crumb(self) -> dict[str, str]:
    """Fetch a Jenkins CSRF crumb for POST requests.

    Returns dict with crumb value and header field name.
    Raises httpx.HTTPStatusError if CSRF protection can't be queried.
    """
    url = f"{self.base_url}/crumbIssuer/api/json"
    resp = await self._client.get(url)
    resp.raise_for_status()
    data = resp.json()
    return {
        data["crumbRequestField"]: data["crumb"],
    }
```

#### Add `create_node()`

```python
async def create_node(
    self, agent_name: str, *, label: str = "flutter"
) -> bool:
    """Create a JNLP inbound agent node via the Jenkins REST API.

    Idempotent — checks if the node exists first.
    Returns True if created, False if already exists.

    Raises httpx.HTTPStatusError on API failure.
    """
    # Check if node already exists
    check_url = f"{self.base_url}/computer/{agent_name}/api/json?tree=displayName"
    resp = await self._client.get(check_url)
    if resp.status_code == 200:
        logger.info("Node '%s' already exists, skipping creation", agent_name)
        return False

    # Create the node
    crumb = await self._get_crumb()
    create_url = f"{self.base_url}/computer/doCreateItem"

    import json as json_mod
    node_config = json_mod.dumps({
        "name": agent_name,
        "nodeDescription": "Flutter build agent (auto-provisioned)",
        "numExecutors": 1,
        "remoteFS": "/home/jenkins/agent",
        "labelString": label,
        "mode": "EXCLUSIVE",
        "retentionStrategy": {
            "stapler-class": "hudson.slaves.RetentionStrategy$Always",
        },
        "nodeProperties": {"stapler-class-bag": "true"},
        "launcher": {
            "stapler-class": "hudson.slaves.JNLPLauncher",
            "workDirSettings": {
                "disabled": False,
                "workDirPath": "",
                "internalDir": "remoting",
                "failIfWorkDirIsMissing": False,
            },
        },
    })

    resp = await self._client.post(
        create_url,
        data={
            "name": agent_name,
            "type": "hudson.slaves.DumbSlave",
            "json": node_config,
        },
        headers=crumb,
    )
    resp.raise_for_status()
    logger.info("Created Jenkins node '%s' with label '%s'", agent_name, label)
    return True
```

#### Add `get_node_secret()`

```python
async def get_node_secret(self, agent_name: str) -> str:
    """Retrieve the JNLP secret for an agent node.

    Parses the secret from the slave-agent.jnlp XML response.

    Raises httpx.HTTPStatusError if the node doesn't exist.
    Raises ValueError if the secret can't be parsed.
    """
    url = f"{self.base_url}/computer/{agent_name}/slave-agent.jnlp"
    resp = await self._client.get(url)
    resp.raise_for_status()

    # Parse secret from JNLP XML: <argument>{hex_secret}</argument>
    import re
    match = re.search(r"<argument>([0-9a-f]{64})</argument>", resp.text)
    if not match:
        raise ValueError(
            f"Could not parse agent secret from JNLP response for '{agent_name}'"
        )
    return match.group(1)
```

### Step 2: Add provision endpoint to build-manager router

**File:** Create `apps/build-manager/src/build_manager/routers/agent.py` (new file)

Keeping this in a separate router from builds.py is cleaner — it's a different
domain (agent management vs build lifecycle).

```python
"""Agent provisioning routes — /api/agent/*."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..dependencies import CoordinatorDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ProvisionRequest(BaseModel):
    agent_name: str = "flutter-agent"
    label: str = "flutter"


@router.post("/provision")
async def provision_agent(
    coord: CoordinatorDep, body: ProvisionRequest
) -> dict[str, Any]:
    """Create a Jenkins agent node and return its secret.

    Idempotent — if the node already exists, just returns the secret.
    Config-hub calls this endpoint, then pushes the secret to agent-control.
    """
    if coord.jenkins is None:
        raise HTTPException(
            status_code=503,
            detail="Jenkins client not configured",
        )

    try:
        node_created = await coord.jenkins.create_node(
            body.agent_name, label=body.label
        )
        secret = await coord.jenkins.get_node_secret(body.agent_name)
    except Exception as exc:
        logger.exception("Agent provisioning failed")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to provision agent: {exc}",
        ) from exc

    return {
        "status": "ok",
        "agent_name": body.agent_name,
        "node_created": node_created,
        "secret": secret,
    }
```

Register this router in `main.py`:

```python
from .routers.agent import router as agent_router
# ...
app.include_router(agent_router)
```

### Step 3: Add provisioning orchestration to `ConfigHubManager`

**File:** `apps/config-hub/src/config_hub/manager.py`

Add `provision_agent()` method after the Jenkinsfile section (~line 263):

```python
# ------------------------------------------------------------------
# Agent provisioning
# ------------------------------------------------------------------

async def provision_agent(self, agent_name: str) -> dict[str, Any]:
    """Orchestrate agent provisioning via build-manager + agent-control.

    1. Call build-manager's provision endpoint (creates Jenkins node + gets secret)
    2. If agent-control is reachable: push config + start agent
    3. If agent-control is NOT reachable: return the secret for manual config

    Returns:
        {"status": "ok", "agent_name": ..., "node_created": bool,
         "agent_started": bool, "secret": str (only if agent-control unreachable)}
    """
    bm_url = self.services._build_manager_url
    if not bm_url:
        raise RuntimeError("Build manager URL not configured")

    # Step 1: Create node + get secret via build-manager
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{bm_url}/api/agent/provision",
            json={"agent_name": agent_name},
        )
        if resp.status_code != 200:
            detail = resp.json().get("detail", resp.text)
            raise RuntimeError(f"Provisioning failed: {detail}")
        provision_result = resp.json()

    secret = provision_result["secret"]
    node_created = provision_result["node_created"]

    # Step 2: Try to push config to agent-control
    agent_status = await self.services.status("agent")
    if agent_status.get("available"):
        # Agent-control is reachable — push config and start
        # Get Jenkins URL from build-manager config
        bm_config = await self.services.get_config("builds")
        jenkins_url = ""
        if bm_config:
            jenkins_url = bm_config.get("values", {}).get("jenkins", {}).get("url", "")

        agent_config = {
            "agent": {
                "name": agent_name,
                "secret": secret,
            },
        }
        if jenkins_url:
            agent_config["agent"]["jenkins_url"] = jenkins_url

        await self.services.put_config("agent", agent_config)
        await self.services.start("agent")

        return {
            "status": "ok",
            "agent_name": agent_name,
            "node_created": node_created,
            "agent_started": True,
        }
    else:
        # Agent-control not reachable — return secret for manual config
        return {
            "status": "ok",
            "agent_name": agent_name,
            "node_created": node_created,
            "agent_started": False,
            "secret": secret,
        }
```

### Step 4: Add provision endpoint to config-hub router

**File:** `apps/config-hub/src/config_hub/routers/services.py` (existing router)

Or create a new `apps/config-hub/src/config_hub/routers/agent.py`.

```python
@router.post("/api/agent/provision")
async def provision_agent(request: Request) -> dict[str, Any]:
    """Provision a Jenkins agent node and configure agent-control.

    Creates the node in Jenkins, retrieves the JNLP secret, and
    (if agent-control is available) pushes the config and starts the agent.
    """
    body = await request.json()
    agent_name = body.get("agent_name", "flutter-agent")

    manager: ConfigHubManager = request.app.state.manager
    try:
        result = await manager.provision_agent(agent_name)
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

### Step 5: Add mock provisioning endpoints to mock-jenkins

**File:** `apps/mock-jenkins/src/mock_jenkins/routers/jenkins.py`

Mock the node creation and JNLP secret endpoints:

```python
# Track created nodes in the manager
# Add to MockBuildManager.__init__:
#   self.nodes: dict[str, str] = {}  # agent_name → secret

@router.get("/computer/{agent_name}/api/json")
async def node_info(
    manager: ManagerDep, agent_name: str, tree: str = ""
) -> dict[str, Any] | Response:
    """Check if a node exists."""
    if agent_name not in manager.nodes:
        return Response(status_code=404)
    return {"displayName": agent_name}


@router.post("/computer/doCreateItem")
async def create_node(
    manager: ManagerDep, request: Request, name: str = Query()
) -> Response:
    """Create a mock agent node."""
    import uuid
    if name in manager.nodes:
        return Response(status_code=400)  # Already exists
    manager.nodes[name] = uuid.uuid4().hex  # Generate a mock secret
    return Response(status_code=200)


@router.get("/computer/{agent_name}/slave-agent.jnlp")
async def jnlp_secret(
    manager: ManagerDep, agent_name: str
) -> Response:
    """Return mock JNLP XML with the agent secret."""
    secret = manager.nodes.get(agent_name)
    if secret is None:
        return Response(status_code=404)
    # Minimal JNLP XML that contains the secret
    jnlp = f"""<?xml version="1.0" encoding="UTF-8"?>
<jnlp>
  <application-desc>
    <argument>{secret}</argument>
    <argument>{agent_name}</argument>
  </application-desc>
</jnlp>"""
    return Response(content=jnlp, media_type="application/xml")
```

Add `nodes: dict[str, str] = field(default_factory=dict)` to `MockBuildManager.__init__`
or as an instance attribute.

### Step 6: Dashboard UI — "Provision Agent" button

**File:** Config-hub dashboard static files (HTML/JS)

This is a UI enhancement. The specific implementation depends on the dashboard
framework. Key behavior:

1. **Button placement:** In the Agent tab, above or alongside the existing config form
2. **On click:** `POST /api/agent/provision` with `{"agent_name": "flutter-agent"}`
3. **Success (agent started):** Show "✅ Agent provisioned and started"
4. **Success (no agent-control):** Show the secret with "Copy to clipboard" button
   and instructions for manual configuration
5. **Error:** Show the error message from the API response

## What Stays Unchanged

- Agent-control service code — no changes
- Agent-control `/control/config` and `/control/start` APIs — unchanged
- Config-hub schema/config proxy flow — unchanged
- Build-manager build flow — unchanged (provisioning is independent)

## Testing Checklist

- [ ] Provision with mock-jenkins → node created, secret returned
- [ ] Provision when node already exists → idempotent, secret still returned
- [ ] Provision with agent-control running → config pushed, agent started
- [ ] Provision without agent-control → secret returned in response
- [ ] CSRF crumb fetched and included in POST request
- [ ] Error handling — Jenkins unreachable, bad credentials, etc.
- [ ] Dashboard button shows appropriate feedback for each scenario

## Open Questions

1. **CSRF crumb handling** — Real Jenkins requires a crumb for POST requests.
   Test `_get_crumb()` + crumb header against a real Jenkins instance.
   Some older Jenkins versions may have CSRF disabled.

2. **JNLP secret XML parsing** — The regex `<argument>([0-9a-f]{64})</argument>`
   assumes a 64-char hex secret. Verify this format against real Jenkins JNLP
   responses. The secret might be shorter or longer in some versions.
