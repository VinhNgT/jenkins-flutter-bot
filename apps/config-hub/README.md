# config-hub

Centralized configuration proxy and web dashboard for the Jenkins Flutter Bot ecosystem. Serves as the single entry point for all configuration management, service control, and UI tooling.

## Features

- **Web Dashboard** — serves the browser-based config UI via static files
- **Config CRUD** — proxies read, update, and merge operations to owning services via HTTP
- **Service Control** — start, stop, restart, and check status of all managed services via their `/control/*` APIs
- **Drive OAuth** — proxies browser-redirect and headless code-exchange flows to file-manager
- **Config Export/Import** — tarball-based portable configuration transfer
- **Jenkinsfile Generation** — renders customized Jenkins pipelines from current orchestrator config

## Architecture

Config-hub owns **zero domain schemas**. It proxies all config I/O to the owning service via HTTP:

```
config-hub (FastAPI + StaticFiles)
    ├─ /api/config/*       Config CRUD (proxied to bot, agent, file-manager, orchestrator)
    ├─ /api/services/*     Service control proxying
    ├─ /api/drive/*        OAuth flows (proxied to file-manager)
    ├─ /api/export/*       Tarball export
    ├─ /api/import/*       Tarball import
    ├─ /api/jenkinsfile    Pipeline generation
    ├─ /api/version        Version endpoint
    └─ /                   Web dashboard (SPA)
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `BOT_CONTROL_URL` | Base URL of the tg-bot control API |
| `AGENT_CONTROL_URL` | Base URL of the agent-control API |
| `FILE_MANAGER_URL` | Base URL of the file-manager control API |
| `ORCHESTRATOR_URL` | Base URL of the build-orchestrator control API |

## Running

```bash
config-hub  # starts on port 9000
```
