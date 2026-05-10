# 🤖 Telegram Jenkins Build Bot

A self-hosted Telegram bot that acts as a thin trigger layer for Jenkins CI/CD. It lets users trigger Flutter builds, tracks only the builds started through Telegram, and delivers resulting APKs through Google Drive.

## Features

- **Jenkins Integration** — Trigger builds on Jenkins via REST API and receive webhook callbacks on completion.
- **Telegram Interface** — Keyboard-driven UI for triggering builds, checking status, and receiving Drive download links.
- **Google Drive Upload** — Uploads build artifacts to Drive and returns shareable per-file download links.
- **Chat Whitelist** — Restricts bot access to specific authorized Telegram chat IDs.
- **Bot-Scoped Tracking** — Only builds triggered by the bot are correlated back to Telegram users. No Jenkins metadata from manual triggers is ever exposed.

## How It Works

1. User taps **🔨 Build** → bot presents branch selection via inline keyboard
2. Bot triggers Jenkins with a unique `request_id` and stores a `PendingBuild`
3. Jenkins pipeline runs on the flutter-agent, then POSTs results to the bot's webhook
4. Bot matches `request_id`, uploads APK to Drive, sends the download link to Telegram
5. Bot enforces `max_recent_builds` retention — evicts oldest entries and cleans up Drive files

The bot owns zero build logic — all cloning, compiling, and packaging is delegated to the Jenkins pipeline.

## Telegram Interface

The bot uses a persistent two-button keyboard:

| Button | Action |
|--------|--------|
| **🔨 Build** | Start a new build — presents branch selection |
| **📦 Recent** | Show recent builds with download links |

Additional commands available via the menu button:

| Command | Description |
|---------|-------------|
| `/status` | Show service health and active builds |
| `/help` | Show usage instructions |
| `/about` | Show version and system info |

## Configuration

Configuration is managed through the **web dashboard** (preferred) or environment variables. See the [setup guide](../../docs/setup-guide.md) for details.

The config precedence chain is: `JSON (dashboard) > Environment Variable > .env file > Default`.

### Required Settings

| Setting | Source |
|---------|--------|
| Telegram Bot Token | [@BotFather](https://t.me/BotFather) |
| Allowed Chat IDs | Telegram chat metadata |
| Jenkins URL / User / API Token | Your Jenkins server |
| Pipeline Job Name | Existing Jenkins pipeline |
| Drive Client ID & Secret | Google Cloud Console (saved in dashboard Drive tab) |

## Jenkins Pipeline

The bot triggers Jenkins builds but does **not** manage the pipeline definition. The web dashboard includes a **Jenkins Pipeline** tab that generates a customized Jenkinsfile based on your configuration — copy it into your Jenkins job.

The pipeline contract: the `post` block must POST a multipart form to `BOT_CALLBACK_URL` with a `metadata` JSON field (containing `request_id`, `job_id`, `status`, `commit_hash`) and an `artifact` file on success.

## Setup

📖 **See [docs/setup-guide.md](../../docs/setup-guide.md) for the complete walkthrough** — Jenkins setup, bot creation, Google Drive OAuth, and configuration.

## License

This project is private. All rights reserved.
