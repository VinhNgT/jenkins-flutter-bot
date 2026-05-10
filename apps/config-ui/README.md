# 🖥️ Config UI Dashboard

A FastAPI web dashboard for managing the Jenkins Flutter Bot stack. Provides configuration CRUD, service control, Google Drive OAuth, environment file export, and Jenkinsfile generation — all through a browser interface.

## Features

- **Configuration Management** — Edit bot, agent, and Drive settings through dynamically rendered forms (generated from `FieldDef` schemas).
- **Service Control** — Start, stop, and restart the bot and agent services via internal HTTP control APIs.
- **Google Drive OAuth** — Browser-redirect OAuth flow with popup callback for connecting Drive.
- **Environment Export** — Generate and download production `.env` files and `oauth.json` for deployments without the config-ui.
- **Jenkins Pipeline** — Generate a customized Jenkinsfile from your current configuration.
- **Config Transfer** — Export/import full stack configuration as `.tar.gz` tarballs.

## How It Works

The dashboard fetches schemas from bot and agent services via HTTP, merges them with its local Drive schema, and renders forms dynamically. On save, it writes JSON config files to shared Docker volumes using `deep_merge()` to preserve untouched fields.

Secret fields are stripped before sending to the browser — existing values are preserved on save unless explicitly changed.

## Running

```bash
# Via Docker (recommended — part of the full stack)
cd infra && ./compose.sh up -d --build

# Local development
uv run --package config-ui config-ui
```

Open **http://localhost:9000** in your browser.

## Setup

📖 **See [docs/setup-guide.md](../../docs/setup-guide.md) for the complete walkthrough.**
