# tg-admin-bot

A headless Telegram bot for stack management — provides a fallback interface when the config-hub web dashboard is unavailable. All operational logic is delegated to the `config-hub` HTTP API via `httpx`.

## Features

- **Service Control** — start / stop / restart bot, agent, file-manager, and build-manager services
- **Status Monitoring** — check service availability and running state
- **Config Export** — generate and download config tarballs
- **Config Import** — upload and apply config tarballs
- **Jenkinsfile Generation** — on-demand pipeline script
- **Drive OAuth** — headless code-paste authorization flow

## Architecture

The admin bot is built as a FastAPI application running on internal port `9093`. The Telegram polling updater is wrapped in a lifespan manager (`AdminBotManager`) that starts and stops the background polling process in coordination with the FastAPI application lifecycle.

Key aspects of this architecture include:
- **FastAPI Lifespan** — The application utilizes standard FastAPI startup/shutdown lifespans to cleanly initialize and stop the Telegram bot updater.
- **Control endpoints** — Exposes `/control/*` endpoints (status, start, stop, restart) to align with the rest of the microservices in the stack.
- **HTTP API Client** — It remains a pure client to `config-hub` for retrieving config, performing system operations, and completing Drive OAuth, avoiding any direct database or volume dependencies on operational logic.


## Environment Variables

| Variable | Description |
|----------|-------------|
| `ADMIN_BOT_TOKEN` | Telegram bot token for the admin bot |
| `ADMIN_CHAT_ID` | Telegram chat ID authorized for admin commands |
| `CONFIG_HUB_URL` | Base URL of the config-hub API (default: `http://config-hub:9000`) |

## Usage

Send `/admin` in the authorized Telegram chat to open the inline keyboard control panel.

## Setup

Add `ADMIN_BOT_TOKEN` and `ADMIN_CHAT_ID` to `infra/.env`, then restart the stack:

```bash
cd infra && ./compose.sh up -d
```

The admin bot is optional — the stack runs fine without it.
