# stack-manager

Central operational hub for the Jenkins Flutter Bot ecosystem. Serves as both the web dashboard and the REST API backend for configuration management, service control, and Google Drive OAuth.

## Features

- **Web Dashboard** — serves the browser-based config UI via static files + Jinja2 templates
- **Config CRUD** — read, update, and merge configuration for all managed services
- **Service Control** — start, stop, restart, and check status of bot + agent via their `/control/*` APIs
- **Drive OAuth** — browser-redirect and headless code-exchange flows for Google Drive authorization
- **Config Export/Import** — tarball-based portable configuration transfer
- **Jenkinsfile Generation** — renders a customized Jenkins pipeline from current config
- **Unified Schema** — aggregates schemas from managed services with locally-owned Drive + Project fields

## Architecture

`stack-manager` is the **single source of truth** for all configuration volumes. It's the only service that directly reads and writes config JSON files. Other consumers interact via its HTTP API:

```
stack-manager (FastAPI + StaticFiles)
    ├─ /api/config/*       Config CRUD
    ├─ /api/services/*     Service control proxying
    ├─ /api/drive/*        OAuth flows
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
| `BOT_CONFIG_PATH` | Path to bot.json |
| `AGENT_CONFIG_PATH` | Path to agent.json |
| `DRIVE_CONFIG_PATH` | Path to drive.json |
| `PROJECT_CONFIG_PATH` | Path to project.json |

## Running

```bash
stack-manager  # starts on port 9000
```
