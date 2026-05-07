# 🏗️ Jenkins Flutter Bot — Setup Guide

Step-by-step instructions to get the full CI/CD stack running: a Telegram bot that triggers Flutter builds on Jenkins and delivers APKs through Google Drive.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1 — Clone the Repository](#step-1--clone-the-repository)
- [Step 2 — Start the Docker Stack](#step-2--start-the-docker-stack)
- [Step 3 — Set Up Jenkins](#step-3--set-up-jenkins)
  - [3a. Initial Jenkins Setup](#3a-initial-jenkins-setup)
  - [3b. Create the Flutter Agent Node](#3b-create-the-flutter-agent-node)
  - [3c. Connect the Agent Secret](#3c-connect-the-agent-secret)
  - [3d. Add Repository Credentials (Private Repos)](#3d-add-repository-credentials-private-repos)
  - [3e. Create the Pipeline Job](#3e-create-the-pipeline-job)
- [Step 4 — Create a Telegram Bot](#step-4--create-a-telegram-bot)
- [Step 5 — Set Up Google Drive OAuth](#step-5--set-up-google-drive-oauth)
  - [5a. Create Google Cloud Credentials](#5a-create-google-cloud-credentials)
  - [5b. Connect Google Drive](#5b-connect-google-drive)
- [Step 6 — Configure the Stack via Config UI](#step-6--configure-the-stack-via-config-ui)
- [Step 7 — Start the Bot and Agent](#step-7--start-the-bot-and-agent)
- [Step 8 — Test the Build Flow](#step-8--test-the-build-flow)
- [Troubleshooting](#troubleshooting)
- [Architecture Reference](#architecture-reference)

---

## Prerequisites

| Requirement       | Minimum Version | Notes                                       |
| ----------------- | --------------- | ------------------------------------------- |
| Docker            | 24+             | With Docker Compose v2 (`docker compose`)   |
| Internet access   | —               | For pulling images and Google/Telegram APIs  |
| Telegram account  | —               | To create a bot via BotFather                |
| Google account    | —               | For Drive API OAuth credentials              |

> **First-time build warning:** The `flutter-agent` image downloads Flutter SDK, Android SDK, and pre-caches artifacts during build. Expect the **first `docker compose build`** to take **15–30 minutes** depending on your internet speed. Subsequent builds use Docker layer caching.

> [!WARNING]
> **Apple Silicon (ARM64) users:** Flutter does not support building Android release APKs on Linux ARM64 hosts ([flutter#177936](https://github.com/flutter/flutter/issues/177936)). The `flutter-agent` service in `docker-compose.yml` is set to `platform: linux/amd64` to force x86_64 emulation. Builds will be slower under emulation — for production CI/CD, use a native x86_64 server.

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/VinhNgT/jenkins-flutter-bot.git
cd jenkins-flutter-bot
```

---

## Step 2 — Start the Docker Stack

```bash
cd infra/jenkins
docker compose up -d --build
```

This builds and starts all four services:

| Service          | URL                    | Purpose                                    |
| ---------------- | ---------------------- | ------------------------------------------ |
| `jenkins`        | http://localhost:8080   | Jenkins controller (web UI)                |
| `config-ui`      | http://localhost:9000   | Configuration dashboard                    |
| `tg-bot`         | Internal (:9090)       | Telegram bot + webhook receiver            |
| `flutter-agent`  | Internal (:9091)       | Jenkins agent with Flutter/Android SDKs    |

> **Note:** The bot and agent will fail to fully start at this point — that's expected. They need configuration first (Steps 3–6). Their FastAPI servers remain running so the config-ui can control them.

---

## Step 3 — Set Up Jenkins

### 3a. Initial Jenkins Setup

1. Open **http://localhost:8080** in your browser
2. Jenkins will ask for the initial admin password. Get it with:
   ```bash
   docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
   ```
3. Paste the password and click **Continue**
4. Choose **Install suggested plugins** and wait for installation
5. Create an admin user (remember these credentials — you'll need them for the bot)

### 3b. Create the Flutter Agent Node

1. Go to **Manage Jenkins → Nodes**
2. Click **New Node**
3. Enter the name: **`flutter-agent`** (must match the `JENKINS_AGENT_NAME` in docker-compose)
4. Select **Permanent Agent** and click **Create**
5. Configure the node:
   - **Remote root directory:** `/home/jenkins/agent`
   - **Labels:** `flutter` (optional, useful for restricting jobs)
   - **Usage:** "Only build jobs with label expressions matching this node"
   - **Launch method:** "Launch agent by connecting it to the controller"
6. Click **Save**

### 3c. Connect the Agent Secret

After saving the node, Jenkins will show the agent's **secret token**. You need this to connect the `flutter-agent` container.

1. On the node status page, find the secret token (shown in the agent launch command, after `-secret`)
2. Copy the secret — you'll enter it in the config-ui in [Step 6](#step-6--configure-the-stack-via-config-ui)

### 3d. Add Repository Credentials (Private Repos)

If your Flutter project lives in a **private repository** (GitLab, GitHub, Bitbucket, etc.), Jenkins needs a Personal Access Token (PAT) to clone it. Public repositories can skip this step.

#### Create a PAT on your Git hosting platform

**GitLab:**
1. Go to **User Settings → Access Tokens** (or **Project → Settings → Access Tokens** for project-scoped tokens)
2. Create a token with the **`read_repository`** scope
3. Set an expiration date and click **Create personal access token**
4. Copy the token immediately — it won't be shown again

**GitHub:**
1. Go to **Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Create a token with **Contents: Read-only** permission for your repository
3. Copy the token immediately

#### Store the PAT in Jenkins

1. Go to **Manage Jenkins → Credentials**
2. Select the appropriate credential scope (e.g., **(global)** under **System**)
3. Click **Add Credentials**
4. Fill in:
   - **Kind:** Username with password
   - **Username:** your Git hosting username (or any non-empty string for GitLab PATs)
   - **Password:** paste your PAT here
   - **ID:** `gitlab-credentials` (or any ID you'll reference in your pipeline)
   - **Description:** e.g., "GitLab PAT for flutter-app"
5. Click **Create**

> [!TIP]
> For GitLab PATs, the username field can be any non-empty string (e.g., `gitlab-ci-token`) — GitLab authenticates using only the token itself. For GitHub PATs, use your GitHub username.

> [!IMPORTANT]
> PATs expire. When a token expires, Jenkins builds will fail at the checkout stage. Set a calendar reminder to rotate the token before expiration and update the Jenkins credential.

### 3e. Create the Pipeline Job

1. From the Jenkins dashboard, click **New Item**
2. Enter the name: **`flutter-build`** (this is the default `JENKINS_JOB_NAME`)
3. Select **Pipeline** and click **OK**
4. Under **General**, check **This project is parameterized** and add these **String Parameters**:

   | Parameter Name    | Default Value | Description                                 |
   | ----------------- | ------------- | ------------------------------------------- |
   | `BRANCH`          | `main`        | Git branch or commit hash to build          |
   | `BOT_CALLBACK_URL`| _(empty)_     | Webhook URL the bot provides                |
   | `BOT_REQUEST_ID`  | _(empty)_     | Unique build tracking token                 |
   | `BOT_JOB_ID`      | _(empty)_     | Job identifier for routing callbacks        |

5. Under **Pipeline**, paste a Jenkinsfile script. Here's a reference template:

   **For private repositories** (using the credential from [Step 3d](#3d-add-repository-credentials-private-repos)):

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
               steps {
                   sh 'flutter pub get'
                   sh 'flutter build apk --release'
               }
           }
       }

       post {
           success {
               script {
                   if (params.BOT_CALLBACK_URL) {
                       def apkPath = 'build/app/outputs/flutter-apk/app-release.apk'
                       def commitHash = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                       def metadata = """{"request_id":"${params.BOT_REQUEST_ID}","job_id":"${params.BOT_JOB_ID}","status":"success","commit_hash":"${commitHash}"}"""

                       sh """
                           curl -X POST "${params.BOT_CALLBACK_URL}" \
                               -F 'metadata=${metadata}' \
                               -F "artifact=@${apkPath}"
                       """
                   }
               }
           }

           failure {
               script {
                   if (params.BOT_CALLBACK_URL) {
                       def commitHash = sh(script: 'git rev-parse HEAD || echo unknown', returnStdout: true).trim()
                       def metadata = """{"request_id":"${params.BOT_REQUEST_ID}","job_id":"${params.BOT_JOB_ID}","status":"failure","commit_hash":"${commitHash}"}"""

                       sh """
                           curl -X POST "${params.BOT_CALLBACK_URL}" \
                               -F 'metadata=${metadata}'
                       """
                   }
               }
           }
       }
   }
   ```

   **For public repositories** (no credentials needed):

   ```groovy
   // Replace the Checkout stage above with:
   stage('Clone') {
       steps {
           git branch: "${params.BRANCH}",
               url: 'https://github.com/YOUR_USER/YOUR_FLUTTER_PROJECT.git'
       }
   }
   ```

   > **Adapt this pipeline** to your specific Flutter project. The key contract is the `post` block — it must POST a multipart form to `BOT_CALLBACK_URL` with a `metadata` JSON field (and an `artifact` file on success). Replace the `url` and `credentialsId` with your own values.

6. Click **Save**

### Create a Jenkins API Token

The bot needs API credentials to trigger builds:

1. Click your username (top-right) → **Configure**
2. Under **API Token**, click **Add new Token**
3. Give it a name (e.g., `tg-bot`) and click **Generate**
4. **Copy the token immediately** — it won't be shown again
5. Note your Jenkins username — you'll need both in [Step 6](#step-6--configure-the-stack-via-config-ui)

---

## Step 4 — Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts:
   - Choose a display name (e.g., "Flutter Build Bot")
   - Choose a username (e.g., `my_flutter_build_bot`)
3. BotFather will reply with your **bot token** — copy it
4. **Find your chat ID:**
   - Send any message to your new bot
   - Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   - Look for `"chat":{"id": XXXXXXXXX}` — this is your chat ID
4. **Register your bot's commands** (optional but recommended):
   - In BotFather, send `/setcommands`
   - Select your bot, then paste:
     ```
     start - Show help and available commands
     build - Build latest commit (or specify branch)
     status - Current build status and service health
     recent - Recent build history with download links
     cancel - Cancel a build in progress
     ```
   - Multiple chat IDs can be allowed (comma-separated)

---

## Step 5 — Set Up Google Drive OAuth

### 5a. Create Google Cloud Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the **Google Drive API**:
   - Navigate to **APIs & Services → Library**
   - Search for "Google Drive API" and click **Enable**
4. Configure the **OAuth consent screen**:
   - Go to **APIs & Services → OAuth consent screen**
   - Choose **External** (or Internal if using Google Workspace)
   - Fill in the required fields (app name, user support email)
   - Add the scope: `https://www.googleapis.com/auth/drive.file`
   - Add your Google account as a **test user** (required while app is in "Testing" status)
   - Complete the wizard
5. Create **OAuth 2.0 credentials**:
   - Go to **APIs & Services → Credentials**
   - Click **Create Credentials → OAuth client ID**
   - Application type: **Web application**
   - **Authorized redirect URIs:** add `http://localhost:9000/api/drive/oauth/callback`
   - Click **Create**
   - Copy the **Client ID** and **Client Secret**

### 5b. Connect Google Drive

This is done after entering the credentials in the config-ui ([Step 6](#step-6--configure-the-stack-via-config-ui)).

---

## Step 6 — Configure the Stack via Config UI

Open **http://localhost:9000** in your browser. The dashboard has sections for bot configuration, agent configuration, and service control.

Fill in the following fields:

### Bot Configuration (Telegram Bot tab)

| Field                | Value                                            |
| -------------------- | ------------------------------------------------ |
| Telegram Bot Token   | The token from BotFather ([Step 4](#step-4--create-a-telegram-bot))                  |
| Allowed Chat IDs     | Your chat ID(s), comma-separated                  |
| Jenkins URL          | `http://jenkins:8080` (internal Docker network)   |
| Jenkins User         | Your Jenkins admin username                       |
| Jenkins API Token    | The API token from [Step 3](#create-a-jenkins-api-token)                        |
| Pipeline Job Name    | `flutter-build` (or your custom job name)         |
| Jenkins Job ID       | Same as Pipeline Job Name in the common case (e.g. `flutter-build`) |
| App Name             | _(optional)_ Your app's display name, e.g. `Tendoo Mall` — shown in bot messages |
| Drive Folder Name    | _(optional)_ e.g., `my-app-builds` (default: `flutter-builds`) |

Click **Save Bot Config**.

### Agent Configuration (Jenkins Agent tab)

| Field          | Value                                             |
| -------------- | ------------------------------------------------- |
| Agent Secret   | The secret from Jenkins node config ([Step 3c](#3c-connect-the-agent-secret))      |

> **Jenkins URL and Agent Name** are pre-configured in docker-compose and usually don't need to be changed via the UI.

Click **Save Agent Config**.

### Google Drive Credentials (Google Drive tab)

| Field               | Value                                                           |
| ------------------- | --------------------------------------------------------------- |
| Drive Client ID     | From Google Cloud ([Step 5a](#5a-create-google-cloud-credentials)) |
| Drive Client Secret | From Google Cloud ([Step 5a](#5a-create-google-cloud-credentials)) |

Click **Save Drive Config**.

### Connect Google Drive

After saving the Drive credentials:

1. Click the **Connect Google Drive** button in the config-ui
2. A popup window will open asking you to authorize with your Google account
3. Select your account and grant the requested permissions
4. The popup will auto-close on success and the dashboard will show "Connected"

---

## Step 7 — Start the Bot and Agent

Use the **Service Control** section in the config-ui dashboard:

1. Click **Start** next to the **Agent** service — this connects the `flutter-agent` to Jenkins
2. Click **Start** (or **Restart**) next to the **Bot** service — this starts Telegram polling

Alternatively, restart the entire stack to pick up all configuration:

```bash
cd infra/jenkins
docker compose restart
```

### Verify Everything is Connected

1. **Jenkins:** Go to http://localhost:8080 → Nodes — the `flutter-agent` should show as **online**
2. **Telegram:** Send `/status` to your bot — it should report:
   - Jenkins: ✅ (your job name)
   - Google Drive: ✅ (your folder name)
   - Headline: 🟢 Ready to build \<App Name\>

---

## Step 8 — Test the Build Flow

1. Open your Telegram chat with the bot
2. Send `/build main` (or `/build <branch-name>`)
3. The bot replies with a "Building..." confirmation including the branch and start time
4. Wait for Jenkins to complete the build (watch progress at http://localhost:8080)
5. On success, the bot uploads the APK to Google Drive and sends a download link
6. Send `/recent` to see your build history with download links
7. Use `/cancel` to stop a build in progress

---

## Troubleshooting

### Container won't start / keeps restarting

```bash
# Check logs for a specific service
docker compose logs tg-bot
docker compose logs flutter-agent
docker compose logs config-ui
```

### Bot says "Google Drive setup required"

- Ensure you've entered the Drive Client ID and Secret in config-ui
- Click "Connect Google Drive" and complete the OAuth flow
- Make sure your Google account is added as a test user in the OAuth consent screen

### Agent shows as offline in Jenkins

- Verify the agent secret is correct in config-ui
- Check the agent logs: `docker compose logs flutter-agent`
- Ensure the `JENKINS_AGENT_NAME` matches the node name in Jenkins (default: `flutter-agent`)

### Build triggers but Jenkins returns 403

- Verify Jenkins username and API token in config-ui
- Ensure the API token hasn't expired — generate a new one if needed
- Check that the Jenkins job name matches (`flutter-build` by default)

### Build fails at checkout ("authentication required" or 403)

- This means Jenkins can't clone the repository — usually a missing or expired PAT
- Verify the credential ID in your Jenkinsfile matches the one stored in Jenkins (e.g., `gitlab-credentials`)
- Check if the PAT has expired — generate a new one and update the credential in **Manage Jenkins → Credentials**
- Ensure the PAT has the correct scope (`read_repository` for GitLab, `Contents: Read-only` for GitHub)

### Build succeeds but no Telegram notification

- The `BOT_CALLBACK_URL` in the Jenkins pipeline must POST back to `http://tg-bot:9090/webhook/build-complete`
- Check bot logs for webhook errors: `docker compose logs tg-bot`
- Ensure the `request_id` and `job_id` are passed correctly in the pipeline's `post` block

### OAuth popup says "redirect_uri_mismatch"

- In Google Cloud Console, ensure the redirect URI is exactly: `http://localhost:9000/api/drive/oauth/callback`
- The URI is case-sensitive and must include the full path

### Resetting everything

```bash
cd infra/jenkins
docker compose down -v    # ⚠️ This deletes all volumes (config, data, Jenkins home)
docker compose up -d --build
```

---

## Architecture Reference

```
┌──────────────┐     ┌─────────────────────┐
│   Telegram   │     │      Browser        │
│    User      │     │      Admin          │
└──────┬───────┘     └──────────┬──────────┘
       │                        │
       │ (polling)              │ :9000
       ▼                        ▼
┌──────────────┐     ┌─────────────────────┐
│   tg-bot     │◄────│     config-ui       │
│   :9090      │     │     :9000           │
│  (internal)  │     │    (exposed)        │
└──────┬───────┘     └──────────┬──────────┘
       │                        │
       │ REST trigger           │ HTTP control
       ▼                        ▼
┌──────────────┐     ┌─────────────────────┐
│   jenkins    │────►│   flutter-agent     │
│   :8080      │     │   :9091             │
│  (exposed)   │     │  (internal)         │
└──────────────┘     └─────────────────────┘
```

**Data flow:**
1. User sends `/build` → bot triggers Jenkins via REST API
2. Jenkins runs the pipeline on `flutter-agent` (Flutter + Android SDKs)
3. Pipeline POSTs results back to bot via webhook
4. Bot uploads APK to Google Drive and notifies user on Telegram

**Configuration flow:**
- All configuration is managed through the config-ui dashboard (http://localhost:9000)
- Config-ui writes JSON files to shared Docker volumes
- Services read from these volumes on startup/restart

### Services & Ports

| Service         | Port | Exposed | Role                                                  |
| --------------- | ---- | ------- | ----------------------------------------------------- |
| `jenkins`       | 8080 | Yes     | Jenkins controller — dev/testing convenience          |
| `config-ui`     | 9000 | Yes     | Web dashboard for config, service control, Drive OAuth |
| `tg-bot`        | 9090 | No      | Telegram bot + build webhook receiver                  |
| `flutter-agent` | 9091 | No      | Jenkins agent with Flutter/Android + control API       |

> **Production note:** The bundled `jenkins` service is for development/testing. In production, point `JENKINS_URL` to an external Jenkins instance and remove the `jenkins` service from `docker-compose.yml`.
