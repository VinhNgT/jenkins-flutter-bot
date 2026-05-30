# mock-jenkins

Development-only mock that replaces the real Jenkins controller and flutter-agent
in the `infra/mock/docker-compose.yml` overlay.

## What It Does

Runs **two** FastAPI servers inside a single container:

| Port | Simulates | Key Endpoints |
|------|-----------|---------------|
| 8080 | Jenkins controller | `POST /job/{name}/buildWithParameters`, `GET /queue/item/{id}/api/json`, `GET /job/{name}/api/json`, `GET /job/{name}/{num}/api/json`, `GET /job/{name}/{num}/artifact/{path}`, `GET /crumbIssuer/api/json` |
| 9091 | Agent-control API | `GET /control/status`, `GET /control/schema`, `POST /control/start`, `POST /control/stop`, `POST /control/restart`, `GET /control/config`, `PUT /control/config` |

## Usage

Used exclusively via the mock compose overlay:

```bash
./compose.sh mock up -d --build
```

This replaces both the `jenkins` and `flutter-agent` services with a single
`mock-jenkins` container, enabling full end-to-end development without a real
Jenkins installation.

## Agent Config Lifecycle

The mock agent-control API uses the **real** `AgentSettings` schema from the
`agent-control` package. This means:

- The schema served to config-hub is always in sync — no hardcoded copies to drift.
- Config saves via `PUT /control/config` are persisted to the `mock-agent-data` volume.
- The agent secret is a required field — without it, the mock reports `configured: false`
  and `/control/start` returns an error, matching real agent-control behaviour.

## Build Simulation

When triggered, the mock simulates a build lifecycle:

1. Returns a queue item ID immediately
2. Transitions to a build number after a short delay
3. Marks the build as complete with a `SUCCESS` result and exposes a dummy APK via `GET /job/{name}/{num}/artifact/{path}`

Build-manager's poll worker detects completion by querying `GET /job/{name}/api/json`, then downloads the artifact directly from the mock. No outbound webhook is fired — the polling model is fully self-contained.
