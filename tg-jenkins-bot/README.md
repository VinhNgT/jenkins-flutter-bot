# 🤖 Telegram Jenkins Build Bot

A self-hosted Telegram bot that acts as a thin trigger layer for Jenkins CI/CD. It allows you to trigger builds, track status, and automatically upload resulting artifacts (APKs, etc.) to Google Drive via a secure Desktop OAuth flow.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Setup & API Keys](#setup--api-keys)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Telegram Bot Commands](#telegram-bot-commands)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Features

- **Jenkins Integration** — Seamlessly trigger builds on a Jenkins server and receive webhook callbacks when builds complete.
- **Telegram Interface** — Trigger builds, check status, and get download links directly from Telegram chat.
- **Google Drive Upload** — Connect via Desktop OAuth flow to securely upload artifacts to Google Drive and return a shareable link.
- **Chat Whitelist** — Restrict bot access to specific authorized Telegram chat IDs.
- **Thin Trigger Layer** — Minimal local state; relies on Jenkins for heavy lifting and build orchestration.

---

## Prerequisites

| Tool        | Version | Purpose                            |
| ----------- | ------- | ---------------------------------- |
| **Python**  | ≥ 3.11  | Runtime                            |
| **uv**      | latest  | Package & virtualenv manager       |
| **Jenkins** | any     | A Jenkins server with a build job  |

> [!NOTE]
> The heavy lifting (cloning, building) is done by your Jenkins server. This bot acts merely as a controller and notifier.

---

## Setup & API Keys

You need credentials from **three** external services: Telegram, Jenkins, and Google Cloud.

### 1. Telegram Bot Token

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and choose a name and username
3. Copy the token provided (e.g., `123456789:ABCdefGhI...`) — this is your `TELEGRAM_BOT_TOKEN`

> [!TIP]
> While chatting with @BotFather, send `/setcommands` and paste:
> ```
> start - Show help and available commands
> build - Build latest commit (or specify branch/hash)
> status - Current build status and config
> recent - Recent build history
> connect_drive - Connect Google Drive
> ```

### 2. Finding Your Telegram Chat ID

1. Add your bot to a group or start a private chat.
2. Send any message to the bot.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in your browser.
4. Look for `"chat":{"id":123456789}`. This number is your chat ID (groups will be negative). Add it to `ALLOWED_CHAT_IDS`.

### 3. Jenkins Configuration

The bot needs access to a Jenkins server to trigger builds and monitor status.

1. You need the **Jenkins URL** (e.g., `http://192.168.1.50:8080`).
2. Create or identify a **Jenkins User** with `Job/Build` and `Job/Read` permissions.
3. Generate an **API Token** for this user in Jenkins (User -> Configure -> Add new Token).
4. Identify the **Job Name** you want the bot to trigger.

### 4. Google Cloud OAuth2 Credentials (Desktop App)

This step is required to upload built artifacts to Google Drive and bypass Telegram file size limits.

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the **Google Drive API** under **APIs & Services -> Library**.
3. Configure the **OAuth consent screen** (External user type, add your email as a test user).
4. Go to **Credentials -> Create Credentials -> OAuth 2.0 Client ID**.
5. Select **Desktop app** as the application type.
6. Name it (e.g., `Build Bot Desktop`) and create it.
7. Copy the **Client ID** and **Client Secret** — these are your `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

---

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```env
# Required — Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-your-bot-token
ALLOWED_CHAT_IDS=123456789,-100987654321

# Required — Jenkins
JENKINS_URL=http://192.168.1.50:8080
JENKINS_USER=build-bot
JENKINS_API_TOKEN=your-jenkins-api-token
JENKINS_JOB_NAME=flutter-build

# Required — Google Drive OAuth (Desktop type client)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# Required — Bot Webhook
# Jenkins will POST build results to this address
BOT_CALLBACK_HOST=http://192.168.1.50:9090
BOT_WEBHOOK_PORT=9090

# Optional
# GITLAB_PAT=
# DRIVE_FOLDER_NAME=flutter-builds
```

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/VinhNgT/tg-jenkins-bot.git
cd tg-jenkins-bot
```

### 2. Install dependencies & Run

```bash
uv sync
uv run tg-jenkins-bot
```

### 3. Connect Google Drive

1. Send `/connect_drive` to your bot in Telegram.
2. The bot will reply with an authorization link. Click it.
3. Sign in with a Google account that is listed as a test user in your GCP project.
4. Grant the requested permission (`drive.file` scope).
5. The browser will redirect to a localhost URL that fails to load (e.g., `http://localhost/?state=...&code=4/0A...`).
6. Copy the `code=...` value from the URL bar (everything after `code=` up to any other `&`).
7. Send this code as a reply to the bot to complete the connection!

---

## Telegram Bot Commands

| Command           | Description                              |
| ----------------- | ---------------------------------------- |
| `/start`          | Show welcome message and command list    |
| `/build`          | Build latest commit on `main`            |
| `/build <branch>` | Build latest commit on a specific branch |
| `/build <hash>`   | Build a specific commit                  |
| `/status`         | Show build status and connections        |
| `/recent`         | List recent Jenkins builds               |
| `/connect_drive`  | Connect Google Drive via OAuth flow      |

---

## Project Structure

```text
tg-jenkins-bot/
├── pyproject.toml                   # Metadata, dependencies
├── uv.lock                          # Locked dependency versions
├── .env.example                     # Environment template
│
├── src/tg_jenkins_bot/
│   ├── main.py                      # Entry point (Telegram bot + webhook server)
│   ├── config.py                    # Configuration management
│   │
│   ├── bot/
│   │   └── handlers.py              # Telegram command handlers
│   │
│   ├── jenkins/
│   │   └── client.py                # Jenkins REST API wrapper & triggering
│   │
│   └── drive/
│       └── uploader.py              # Desktop OAuth flow & Drive uploads
│
└── data/                            # Runtime data (gitignored)
    └── config.json                  # Saved OAuth tokens
```

---

## Troubleshooting

### Bot doesn't respond to commands
- Verify `TELEGRAM_BOT_TOKEN` is correct.
- Check that your chat ID is in `ALLOWED_CHAT_IDS`.
- Look for errors in the terminal output.

### Jenkins builds aren't triggering
- Ensure `JENKINS_URL`, `JENKINS_USER`, and `JENKINS_API_TOKEN` are correct.
- Ensure the user has permissions to trigger `JENKINS_JOB_NAME`.

### Drive OAuth flow fails
- Ensure you created a **Desktop app** Client ID, not a Web application.
- Ensure your Google account is added as a **test user** in the OAuth consent screen.
- Ensure you copy only the `code` value, not the entire URL.

### Webhook not receiving callbacks
- Ensure `BOT_CALLBACK_HOST` is accessible from the Jenkins server.
- Verify `BOT_WEBHOOK_PORT` is not blocked by a firewall.ent screen

### "Cooldown active" message

- Default cooldown is 300 seconds (5 minutes)
- Reduce it via `COOLDOWN_SECONDS` or the Web UI config page
- Use `/status` to see remaining cooldown time

---

## License

This project is private. All rights reserved.
