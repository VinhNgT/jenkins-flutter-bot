# 🤖 Telegram Jenkins Build Bot

A self-hosted Telegram bot that acts as a thin trigger layer for Jenkins CI/CD. It lets you trigger builds, tracks only the builds started through Telegram, and delivers resulting artifacts through Google Drive using credentials managed in the config UI dashboard.

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
- **Telegram Interface** — Trigger builds, check status, and receive Drive links directly from Telegram chat.
- **Google Drive Upload** — Use the config UI dashboard to complete Google OAuth through a browser callback, then upload artifacts to Google Drive and return a shareable link.
- **Chat Whitelist** — Restrict bot access to specific authorized Telegram chat IDs.
- **Bot-Scoped Tracking** — Only builds triggered by the bot are correlated back to Telegram users.
- **Thin Trigger Layer** — Minimal local state; relies on Jenkins for heavy lifting and build orchestration.

---

## Prerequisites

| Tool        | Version | Purpose                           |
| ----------- | ------- | --------------------------------- |
| **Python**  | ≥ 3.12  | Runtime                           |
| **uv**      | latest  | Package & virtualenv manager      |
| **Jenkins** | any     | A Jenkins server with a build job |

> [!NOTE]
> The heavy lifting (cloning, building) is done by your Jenkins server. This bot acts merely as a controller and notifier.

---

## Setup & API Keys

You need values from **three** external services: Telegram, Jenkins, and Google Cloud. The bot reads them from the config UI JSON file or from environment variables.

Collect this checklist before you start:

| Setting                | Required | Source                      | Notes                                               |
| ---------------------- | -------- | --------------------------- | --------------------------------------------------- |
| `TELEGRAM_BOT_TOKEN`   | Yes      | Telegram / @BotFather       | Bot API token                                       |
| `ALLOWED_CHAT_IDS`     | Yes      | Telegram chat metadata      | Comma-separated list of allowed chat IDs            |
| `JENKINS_URL`          | Yes      | Your Jenkins server         | Base URL only, no trailing job path                 |
| `JENKINS_USER`         | Yes      | Jenkins user directory      | Prefer a dedicated service account                  |
| `JENKINS_API_TOKEN`    | Yes      | Jenkins user security page  | Copy once when generated                            |
| `JENKINS_JOB_NAME`     | Yes      | Existing Jenkins job        | Current client expects a top-level job path segment |
| `JENKINS_JOB_ID`       | Usually  | Your own logical identifier | Usually set equal to `JENKINS_JOB_NAME`             |
| `GOOGLE_CLIENT_ID`     | Yes      | Google Cloud OAuth client   | Used by config UI Drive setup                       |
| `GOOGLE_CLIENT_SECRET` | Yes      | Google Cloud OAuth client   | Used by config UI Drive setup                       |
| `BOT_CALLBACK_HOST`    | Optional | Your deployment topology    | Defaults to `http://tg-bot:9090` in Docker          |
| `BOT_WEBHOOK_PORT`     | Optional | Your deployment topology    | Defaults to `9090`                                  |
| `CONFIG_UI_URL`        | Optional | Your deployment topology    | Public config UI URL shown in bot guidance          |
| `DRIVE_FOLDER_NAME`    | Optional | Your choice                 | Destination folder name in Google Drive             |

### 1. Telegram Bot Token

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and choose a name and username
3. Copy the token provided (e.g., `123456789:ABCdefGhI...`) — this is your `TELEGRAM_BOT_TOKEN`

> [!TIP]
> While chatting with @BotFather, send `/setcommands` and paste:
>
> ```
> start - Show help and available commands
> build - Build latest commit (or specify branch/hash)
> status - Current build status and config
> recent - Recent build history
> ```

### 2. Finding Your Telegram Chat ID

1. Add your bot to a group or start a private chat.
2. Send any message to the bot.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in your browser.
4. Look for `"chat":{"id":123456789}`. This number is your chat ID (groups will be negative). Add it to `ALLOWED_CHAT_IDS`.
5. If you want multiple chats to use the bot, store them as a comma-separated list such as `123456789,-100987654321`.

> [!TIP]
> `@userinfobot` or `@RawDataBot` can also reveal chat IDs without using `getUpdates`.

### 3. Jenkins URL, User, API Token, Job Name, and Job ID

The bot needs access to a Jenkins server to trigger builds and monitor status.

1. Open Jenkins in your browser and copy the base URL (for example `http://192.168.1.50:8080`). This is `JENKINS_URL`.
2. Create or identify a dedicated Jenkins user for the bot.
3. Grant that user at least `Overall/Read`, `Job/Read`, and `Job/Build`. Some Jenkins setups also require `View/Read`.
4. Open the Jenkins user menu, go to **Security**, and create an **API Token**. Copy it immediately; this is `JENKINS_API_TOKEN`.
5. Copy the exact Jenkins job name that the bot should trigger. This becomes `JENKINS_JOB_NAME`.
6. Set `JENKINS_JOB_ID` to a stable identifier used only by the bot for callback scoping. In the common case, set it equal to `JENKINS_JOB_NAME` and keep it unchanged.

> [!IMPORTANT]
> The current Jenkins client builds URLs as `${JENKINS_URL}/job/${JENKINS_JOB_NAME}`. If your pipeline lives inside nested Jenkins folders, you will need to adapt the job path or the client implementation.

### 4. Google Cloud OAuth2 Client for Drive Uploads

This step is required to upload built artifacts to Google Drive and bypass Telegram file size limits.

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the **Google Drive API** under **APIs & Services -> Library**.
3. Configure the **OAuth consent screen**.
4. If the app is not published, add every Google account that will authorize Drive access as a **test user**.
5. Go to **Credentials -> Create Credentials -> OAuth 2.0 Client ID**.
6. Select **Web application** as the application type.
7. Add an **Authorized redirect URI** for the config UI callback.

   Local development example:

   ```text
   http://127.0.0.1:9000/api/drive/oauth/callback
   ```

   Deployed config UI example:

   ```text
   https://config.example.com/api/drive/oauth/callback
   ```

8. Copy the **Client ID** and **Client Secret**. These are `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
9. Save these values in the config UI dashboard before starting the Drive connection flow.

### 5. Bot Callback Host and Port

Jenkins must be able to call the bot back when a build finishes.

1. Set `BOT_CALLBACK_HOST` to the base URL Jenkins can reach for the bot service.
2. Do **not** append `/webhook/build-complete`; the bot adds that path automatically.
3. Use a host that is reachable from the Jenkins server, not just from your browser.
4. Keep `BOT_WEBHOOK_PORT=9090` unless you run the bot on a different port.

Examples:

```text
BOT_CALLBACK_HOST=http://192.168.1.50:9090
BOT_CALLBACK_HOST=http://tg-jenkins-bot:9090
```

### 6. Optional Values

Use these only when your deployment needs them:

| Setting                | When to use it                                                                         | How to get it                                                                        |
| ---------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `CONFIG_UI_URL`        | You want the bot to point users to the dashboard URL                                   | Use the full external URL of the config UI, for example `https://config.example.com` |
| `DRIVE_FOLDER_NAME`    | You want uploads grouped in a specific Drive folder                                    | Choose any folder name you want the uploader to create or reuse                      |
| `BOT_OAUTH_TOKEN_PATH` | You want the Drive OAuth token stored outside the default config directory             | Choose a writable path shared by the config UI and bot                               |

---

## Configuration

Configuration precedence is:

1. JSON config file written by the config UI
2. Process environment variables
3. `.env`
4. Built-in defaults

If you use the dashboard, its saved JSON config takes precedence over `.env`.

Copy `.env.example` to `.env` and fill in the values if you are not relying entirely on the config UI:

```env
# Required — Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-your-bot-token
ALLOWED_CHAT_IDS=123456789,-100987654321

# Required — Jenkins
JENKINS_URL=http://192.168.1.50:8080
JENKINS_USER=build-bot
JENKINS_API_TOKEN=your-jenkins-api-token
JENKINS_JOB_NAME=flutter-build
JENKINS_JOB_ID=flutter-build

# Required — Google Drive OAuth client for the config UI callback flow
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# Required — Bot Webhook
# Jenkins will POST build results to this address
BOT_CALLBACK_HOST=http://192.168.1.50:9090
BOT_WEBHOOK_PORT=9090

# Optional
# CONFIG_PATH=/app/config/bot.json
# CONFIG_UI_URL=http://localhost:9000
# BOT_OAUTH_TOKEN_PATH=/app/config/oauth.json
# DRIVE_FOLDER_NAME=flutter-builds
```

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/VinhNgT/jenkins-flutter-bot.git
cd jenkins-flutter-bot/apps/tg-jenkins-bot
```

### 2. Install dependencies & Run

```bash
uv sync
uv run tg-jenkins-bot
```

### 3. Connect Google Drive

1. Start the config UI dashboard or the full compose stack.
2. Open the dashboard and save your bot config, including `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
3. In the Google Drive setup panel, click the authorization button.
4. Sign in with a Google account that is listed as a test user in your GCP project.
5. Grant the requested permission (`drive.file` scope).
6. Google will redirect back to the config UI callback page automatically.
7. Wait for the dashboard to refresh and show that Drive is connected. No code copy and paste is required.
8. Return to Telegram and run `/status` to confirm the bot is ready.

---

## Jenkins Pipeline Setup

The bot triggers Jenkins builds but does **not** manage the pipeline definition. Configure your pipeline directly in Jenkins:

1. Create a new **Pipeline** job in Jenkins
2. Under "Pipeline", select **"Pipeline script"** (not "from SCM")
3. Paste the pipeline script below and customize `url` and `credentialsId`
4. The bot passes `BRANCH`, `BOT_CALLBACK_URL`, `BOT_REQUEST_ID`, and `BOT_JOB_ID` as build parameters — Jenkins handles everything else

<details>
<summary>Reference pipeline script</summary>

```groovy
pipeline {
    agent { label 'flutter' }
    parameters {
        string(name: 'BRANCH', defaultValue: 'main')
        string(name: 'BOT_CALLBACK_URL', defaultValue: '')
        string(name: 'BOT_REQUEST_ID', defaultValue: '')
        string(name: 'BOT_JOB_ID', defaultValue: '')
    }
    stages {
        stage('Checkout') {
            steps {
                checkout([$class: 'GitSCM',
                    branches: [[name: "*/${params.BRANCH}"]],
                    userRemoteConfigs: [[
                        url: 'https://gitlab.com/your-org/your-flutter-app.git',
                        credentialsId: 'gitlab-credentials'
                    ]]
                ])
            }
        }
        stage('Build APK') {
            steps { sh 'flutter build apk --release' }
        }
    }
    post {
        success {
            script {
                if (params.BOT_CALLBACK_URL) {
                    def commit = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                    def meta = [request_id: params.BOT_REQUEST_ID, job_id: params.BOT_JOB_ID,
                                status: 'success', commit_hash: commit,
                                build_number: env.BUILD_NUMBER, build_url: env.BUILD_URL]
                    writeJSON file: 'metadata.json', json: meta
                    retry(3) {
                        sh "curl -sf -X POST \"${params.BOT_CALLBACK_URL}\" " +
                           "-F 'metadata=@metadata.json;type=application/json' " +
                           "-F 'artifact=@build/app/outputs/flutter-apk/app-release.apk'"
                    }
                }
            }
        }
        failure {
            script {
                if (params.BOT_CALLBACK_URL) {
                    def commit = sh(script: 'git rev-parse HEAD || echo unknown', returnStdout: true).trim()
                    def meta = [request_id: params.BOT_REQUEST_ID, job_id: params.BOT_JOB_ID,
                                status: 'failed', commit_hash: commit,
                                build_number: env.BUILD_NUMBER, build_url: env.BUILD_URL,
                                logs: 'Check Jenkins console for details']
                    writeJSON file: 'metadata.json', json: meta
                    retry(3) {
                        sh "curl -sf -X POST \"${params.BOT_CALLBACK_URL}\" " +
                           "-F 'metadata=@metadata.json;type=application/json'"
                    }
                }
            }
        }
        always { cleanWs() }
    }
}
```

</details>

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

---

## Project Structure

```text
apps/tg-jenkins-bot/
├── pyproject.toml                   # Metadata, dependencies
├── uv.lock                          # Locked dependency versions
├── .env.example                     # Environment template
│
├── src/tg_jenkins_bot/
│   ├── main.py                      # FastAPI entry point for control and webhook routes
│   ├── control.py                   # Bot lifecycle and /control/* routes
│   ├── config.py                    # Configuration management
│   │
│   ├── bot/
│   │   ├── context.py               # Pending build tracking and Telegram delivery
│   │   └── handlers.py              # Telegram command handlers
│   │
│   ├── jenkins/
│   │   ├── client.py                # Jenkins REST API wrapper & triggering
│   │   └── webhook.py               # Build completion webhook handling
│   │
│   └── drive/
│       └── uploader.py              # Shared Drive token handling and uploads
│
└── data/                            # Runtime data (gitignored)
    └── ...                          # Local runtime artifacts when used outside compose
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

- Ensure the OAuth client is configured with the exact config UI callback URL.
- Ensure your Google account is added as a **test user** in the OAuth consent screen if the app is not published.
- Start the authorization flow from the config UI after saving `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
- If the callback page opens but the dashboard does not update, refresh the dashboard once and inspect the config-ui logs.

### Webhook not receiving callbacks

- Ensure `BOT_CALLBACK_HOST` is accessible from the Jenkins server.
- Verify `BOT_WEBHOOK_PORT` is not blocked by a firewall.


---

## License

This project is private. All rights reserved.
