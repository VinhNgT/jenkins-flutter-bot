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

The admin bot runs as a Telegram polling bot with **no HTTP server**. It is a pure **HTTP API client** to the `config-hub` service — no config volume mounts, no direct library dependencies on operational logic. All config, service control, and OAuth flows are handled by `config-hub`; the bot formats results for the Telegram UI.

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
