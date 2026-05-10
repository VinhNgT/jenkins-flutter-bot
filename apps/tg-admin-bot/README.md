# tg-admin-bot

A headless Telegram bot for stack management — provides a fallback interface when the web dashboard is unavailable. All operational logic is delegated to the `stack-manager` HTTP API via `httpx`.

## Features

- **Service Control** — start / stop bot and agent services
- **Status Monitoring** — check service availability
- **Config Export** — generate and download config tarballs
- **Config Import** — upload and apply config tarballs
- **Jenkinsfile Generation** — on-demand pipeline script
- **Drive OAuth** — headless code-paste authorization flow

## Architecture

The admin bot runs as a Telegram polling bot with no HTTP server. It is a pure **HTTP API client** to the `stack-manager` service — no direct library dependencies on operational logic. All config volumes, service control, and OAuth flows are handled by `stack-manager`; the bot formats results for the Telegram UI.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ADMIN_BOT_TOKEN` | Telegram bot token for the admin bot |
| `ADMIN_CHAT_ID` | Telegram chat ID authorized for admin commands |
| `STACK_MANAGER_URL` | Base URL of the stack-manager API (default: `http://stack-manager:9000`) |

## Usage

Send `/admin` in the authorized Telegram chat to open the inline keyboard control panel.
