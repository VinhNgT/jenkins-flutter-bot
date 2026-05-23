# 🤖 Telegram Jenkins Build Bot

A self-hosted Telegram Web App and passive notification bot that acts as a thin trigger layer for Jenkins CI/CD. It lets users trigger Flutter builds via a Telegram Mini App, tracks only the builds started through Telegram, and delivers shareable download links for resulting APKs.

## Features

- **Mini App Build Trigger** — Taps a dedicated `🚀 Build` MenuButtonWebApp to launch a premium glassmorphic target branch selector Web App.
- **Passive Notification Channel** — The bot operates as a send-only passive announcer. No interactive messages, pickers, or message edits are performed.
- **HMAC Authentication** — Validates Telegram Web App data signatures to ensure only authorized Telegram sessions can interact with the APIs.
- **Chat Whitelist** — Restricts bot and Web App access to specific whitelisted Telegram chat IDs.
- **Bot-Scoped Tracking** — Only builds triggered by the bot are correlated back to Telegram users. No Jenkins metadata from manual triggers is ever exposed.

## How It Works

1. **User Opens Web App** — Taps `🚀 Build` inside the Telegram chat to launch the webview.
2. **API Verification** — The Web App requests configuration from `GET /api/webapp/config`. The bot validates the HMAC-SHA256 signature using its token, checks `allowed_chat_ids`, and returns branch configurations and active builds.
3. **Trigger Build** — User selects a branch and clicks Build. Web App calls `POST /api/webapp/trigger` to instruct the bot to request a build from the build-manager.
4. **Active Build Registration** — The bot posts a `"🔨 User started a Target build"` confirmation to the chat, registers the active build in `ActiveBuildStore`, and returns success to the Web App (which closes).
5. **Poll and Deliver** — The build-manager polls Jenkins for the build (tracked by `BUILD_REQUEST_ID`), uploads the compiled APK to Google Drive via file-manager, and forwards the results to the bot's webhook.
6. **immutable Success Notification** — The bot consumes the `ActiveBuild` from `ActiveBuildStore` and delivers a clean notification message containing the direct APK download link.

## Telegram Interface

| Command | Action |
|---------|--------|
| `/recent` | Show recent builds with download links |
| `/status` | Show service health and active builds |
| `/help` | Show usage instructions |

> **🚀 Build Button**: Dynamically registered next to the message input box on bot startup if `webapp_url` is configured.

## Configuration

Configuration is managed through the **web dashboard** at http://localhost:9000 (preferred) or environment variables. See the [setup guide](../../docs/setup-guide.md) for details.

The config precedence chain is: `JSON (dashboard) > Environment Variable > .env file > Default`.

### Required Settings

| Setting | Source |
|---------|--------|
| Telegram Bot Token | [@BotFather](https://t.me/BotFather) |
| Allowed Chat IDs | Telegram chat metadata |
| App Name | Free text — shown in bot messages |
| Web App URL | Public HTTPS URL mapping to the bot's `/webapp` static server |

## API & Static Server Layout

The bot FastAPI service mounts a static directory at `/webapp` serving `index.html` (the Mini App UI) and exposes these Web App endpoints under `/api/webapp`:

- `GET /api/webapp/config` — Returns target branches and active builds list.
- `POST /api/webapp/trigger` — Triggers a new build.
- `POST /api/webapp/cancel` — Cancels an active build.

### Preview Mode
When opened directly in a browser (where `window.Telegram.WebApp` is unavailable), the Web App operates in "Preview Mode" with simulated data to enable easy local development and validation.

## License

This project is private. All rights reserved.
