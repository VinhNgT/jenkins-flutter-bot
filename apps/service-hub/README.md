# service-hub

Centralized configuration proxy and operational orchestrator for the Jenkins Flutter Bot microservice ecosystem. Serves as the single backend controller for all core configuration management, service control, OAuth flows, and pipeline generation.

## Features

- **Config CRUD** — proxies read, update, and deep-merge operations to the owning services via HTTP (`/control/config`)
- **Service Control** — starts, stops, restarts, and checks the status of all managed services via their `/control/*` APIs
- **Drive OAuth** — proxies headless code-exchange and token-exchange OAuth flows to file-manager
- **Config Export/Import** — tarball-based portable configuration transfer across the ecosystem
- **Jenkinsfile Generation** — renders customized Jenkins pipelines from the current build-manager configuration

## Architecture

Service-hub owns **zero domain schemas**. All config I/O is proxied to the owning services via HTTP:

```
service-hub (FastAPI)
    ├─ /api/config/*       Config CRUD (proxied to agent-control, file-manager, build-manager)
    ├─ /api/services/*     Service status and lifecycle control
    ├─ /api/drive/*        OAuth flows (proxied to file-manager)
    ├─ /api/export/*       Tarball export
    ├─ /api/import/*       Tarball import
    ├─ /api/jenkinsfile    Pipeline generation (from build-manager config)
    └─ /api/version        Version endpoint
```

Scope names map directly to their owning services:

| Scope | Service |
|-------|---------|
| `agent-control` | agent-control |
| `file-manager` | file-manager |
| `build-manager` | build-manager |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AGENT_CONTROL_URL` | Base URL of the agent-control API (default: `http://agent-control:9091`) |
| `FILE_MANAGER_URL` | Base URL of the file-manager API (default: `http://file-manager:9092`) |
| `BUILD_MANAGER_URL` | Base URL of the build-manager API (default: `http://build-manager:9010`) |

## Running

```bash
service-hub  # starts on port 9000
```

