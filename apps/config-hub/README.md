# config-hub

Centralized configuration proxy and web dashboard for the Jenkins Flutter Bot microservice ecosystem. Serves as the single operational entry point for all configuration management, service control, OAuth flows, and UI tooling.

## Features

- **Web Dashboard** — browser-based SPA for configuring all services, managing Google Drive OAuth, and controlling service lifecycle
- **Config CRUD** — proxies read, update, and deep-merge operations to the owning service via HTTP (`/control/config`)
- **Service Control** — start, stop, restart, and check status of all managed services via their `/control/*` APIs
- **Drive OAuth** — proxies browser-redirect and headless code-exchange OAuth flows to file-manager
- **Config Export/Import** — tarball-based portable configuration transfer
- **Jenkinsfile Generation** — renders customized Jenkins pipelines from current build-manager config

## Architecture

Config-hub owns **zero domain schemas**. All config I/O is proxied to the owning service via HTTP:

```
config-hub (FastAPI + StaticFiles)
    ├─ /api/config/*       Config CRUD (proxied to bot, agent, file-manager, build-manager)
    ├─ /api/services/*     Service status and lifecycle control
    ├─ /api/drive/*        OAuth flows (proxied to file-manager)
    ├─ /api/export/*       Tarball export
    ├─ /api/import/*       Tarball import
    ├─ /api/jenkinsfile    Pipeline generation (from build-manager config)
    ├─ /api/version        Version endpoint
    └─ /                   Web dashboard (SPA)
```

UI scope names map to their owning services:

| Scope (UI) | Service |
|------------|---------|
| `bot` | tg-jenkins-bot |
| `agent` | agent-control |
| `file_manager` | file-manager |
| `builds` | build-manager |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `BOT_CONTROL_URL` | Base URL of the tg-bot control API (default: `http://tg-bot:9090`) |
| `AGENT_CONTROL_URL` | Base URL of the agent-control API (default: `http://flutter-agent:9091`) |
| `FILE_MANAGER_URL` | Base URL of the file-manager API (default: `http://file-manager:9092`) |
| `BUILD_MANAGER_URL` | Base URL of the build-manager API (default: `http://build-manager:9010`) |

## Running

```bash
config-hub  # starts on port 9000
```
