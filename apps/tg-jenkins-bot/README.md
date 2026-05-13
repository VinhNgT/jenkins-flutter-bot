# 🤖 Telegram Jenkins Build Bot

A self-hosted Telegram bot that acts as a thin trigger layer for Jenkins CI/CD. It lets users trigger Flutter builds via slash commands, tracks only the builds started through Telegram, and delivers resulting APKs through Google Drive.

## Features

- **Jenkins Integration** — Triggers builds on the build-manager service via REST and receives webhook callbacks on completion.
- **Telegram Slash Commands** — `/build`, `/recent`, `/status`, `/help`, `/about` — native Telegram command interface.
- **Google Drive Upload** — Uploads build artifacts to Drive via the file-manager service and returns shareable per-file download links.
- **Chat Whitelist** — Restricts bot access to specific authorized Telegram chat IDs.
- **Bot-Scoped Tracking** — Only builds triggered by the bot are correlated back to Telegram users. No Jenkins metadata from manual triggers is ever exposed.

## How It Works

1. User sends `/build` → bot presents branch selection via inline keyboard
2. Bot requests a build from the build-manager, which triggers Jenkins with a unique `request_id`
3. Jenkins pipeline runs on the flutter-agent, then POSTs results back to the bot's webhook
4. Bot matches `request_id`, uploads APK to Drive via file-manager, sends the download link to Telegram
5. Bot enforces `max_recent_builds` retention — evicts oldest entries and cleans up Drive files

The bot owns zero build logic — all cloning, compiling, and packaging is delegated to the Jenkins pipeline.

## Telegram Interface

| Command | Action |
|---------|--------|
| `/build [ref]` | Trigger a build — presents branch picker, or builds `ref` directly if supplied |
| `/recent` | Show recent builds with download links |
| `/status` | Show service health and active builds |
| `/help` | Show usage instructions |
| `/about` | Show version and system info |

## Configuration

Configuration is managed through the **web dashboard** at http://localhost:9000 (preferred) or environment variables. See the [setup guide](../../docs/setup-guide.md) for details.

The config precedence chain is: `JSON (dashboard) > Environment Variable > .env file > Default`.

### Required Settings

| Setting | Source |
|---------|--------|
| Telegram Bot Token | [@BotFather](https://t.me/BotFather) |
| Allowed Chat IDs | Telegram chat metadata |
| App Name | Free text — shown in bot messages |

> Drive and Jenkins settings are managed in the **Google Drive** and **Build Manager** tabs of the config-hub dashboard respectively.

## Jenkins Pipeline

The bot triggers builds through the build-manager, which delegates to Jenkins. The web dashboard includes a **Jenkins Pipeline** tab that generates a customized Jenkinsfile based on your configuration — copy it into your Jenkins job.

The pipeline contract: the `post` block must POST a multipart form to `BOT_CALLBACK_URL` with a `metadata` JSON field (containing `request_id`, `job_id`, `status`, `commit_hash`) and an `artifact` file on success.

## Setup

📖 **See [docs/setup-guide.md](../../docs/setup-guide.md) for the complete walkthrough** — Jenkins setup, bot creation, Google Drive OAuth, and configuration.

## License

This project is private. All rights reserved.
