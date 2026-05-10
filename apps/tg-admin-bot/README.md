# 🛡️ Telegram Admin Bot

A headless Telegram bot for stack management — provides a fallback interface when the config-ui web dashboard is unavailable. Uses `stack-manager` for all operational logic.

## Features

- **Configuration View/Edit** — View and modify bot, agent, and Drive settings via Telegram commands.
- **Service Control** — Start, stop, and restart the bot and agent services via `ServiceClient`.
- **Google Drive OAuth** — Headless code-paste flow for environments without a browser.
- **Config Transfer** — Export/import full stack configuration as `.tar.gz` tarballs via Telegram file messages.

## How It Works

The admin bot runs as a Telegram polling bot with no HTTP server. It shares the same config volumes as config-ui and uses `ServiceClient` from `stack-manager` for service control — identical to config-ui but through a Telegram interface.

Access is restricted to a single authorized admin chat ID (`ADMIN_CHAT_ID`).

## Configuration

| Variable | Source | Purpose |
|----------|--------|---------|
| `ADMIN_BOT_TOKEN` | @BotFather | Separate bot token (not the same as the build bot) |
| `ADMIN_CHAT_ID` | Telegram | Authorized admin chat ID |

Both are set via `infra/.env` and interpolated into `docker-compose.yml`.

## Running

The admin bot runs as part of the Docker Compose stack — no manual setup required beyond setting the two environment variables above.

```bash
# Set credentials in infra/.env
ADMIN_BOT_TOKEN=your-admin-bot-token
ADMIN_CHAT_ID=your-chat-id

# Start the stack
cd infra && ./compose.sh up -d --build
```
