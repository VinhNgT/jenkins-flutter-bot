# Jenkins Flutter Bot — Setup Guide

← [Back to README](../README.md)

Step-by-step instructions to get the full CI/CD stack running: a Telegram bot that triggers Flutter builds on Jenkins and delivers APKs through Google Drive.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1 — Clone & Start the Stack](#step-1--clone--start-the-stack)
- [Step 2 — Set Up Jenkins](#step-2--set-up-jenkins)
  - [2a. Initial Jenkins Setup](#2a-initial-jenkins-setup)
  - [2b. Create the Flutter Agent Node](#2b-create-the-flutter-agent-node)
  - [2c. Configure the Agent in Config Hub](#2c-configure-the-agent-in-config-hub)
  - [2d. Create a Jenkins API Token](#2d-create-a-jenkins-api-token)
  - [2e. Add Repository Credentials (Private Repos)](#2e-add-repository-credentials-private-repos)
  - [2f. Create the Pipeline Job](#2f-create-the-pipeline-job)
  - [2g. Save Jenkins Settings in Config Hub](#2g-save-jenkins-settings-in-config-hub)
- [Step 3 — Set Up the Telegram Bot](#step-3--set-up-the-telegram-bot)
- [Step 4 — Set Up Google Drive](#step-4--set-up-google-drive)
  - [4a. Create Google Cloud Credentials](#4a-create-google-cloud-credentials)
  - [4b. Save & Connect in Config Hub](#4b-save--connect-in-config-hub)
- [Step 5 — Start Services & Test](#step-5--start-services--test)
- [Troubleshooting](#troubleshooting)
- [Admin Bot Setup (Optional)](#admin-bot-setup-optional)

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

## Step 1 — Clone & Start the Stack

```bash
git clone https://github.com/VinhNgT/jenkins-flutter-bot.git
cd jenkins-flutter-bot/infra
./compose.sh up -d --build
```

<details>
<summary>Alternative: Production mode (pull pre-built images from GHCR)</summary>

```bash
cd infra
./compose.sh prod up -d                     # pull latest images
IMAGE_TAG=v1.2.3 ./compose.sh prod up -d     # pin a specific release
```

To release a new version, push a version tag — GitHub Actions handles building and pushing:

```bash
git tag v1.2.3
git push origin v1.2.3
```

> **Note:** The `jenkins` service has no pre-built image — it's a local development convenience. In production, remove the `jenkins` service from the compose stack and point `JENKINS_URL` to your external Jenkins instance.

</details>

This starts all seven services:

| Service          | URL                    | Purpose                                           |
| ---------------- | ---------------------- | ------------------------------------------------- |
| `jenkins`        | http://localhost:8080   | Jenkins controller (web UI)                       |
| `config-hub`     | http://localhost:9000   | Configuration dashboard and operational hub       |
| `tg-bot`         | Internal (:9090)       | Telegram bot + webhook receiver                   |
| `flutter-agent`  | Internal (:9091)       | Jenkins agent with Flutter/Android SDKs           |
| `file-manager`   | Internal (:9092)       | Google Drive OAuth and APK upload/download        |
| `build-manager`  | Internal (:9010)       | Jenkins build trigger and job state tracking      |
| `tg-admin-bot`   | Internal (polling)     | Headless admin bot (optional — needs `ADMIN_BOT_TOKEN`) |

> [!NOTE]
> The bot and agent won't fully start yet — that's expected. They need configuration first (Steps 2–4). Their control APIs remain available so config-hub can manage them.

Open **http://localhost:9000** — you'll use this dashboard throughout the remaining steps.

---

## Step 2 — Set Up Jenkins

### 2a. Initial Jenkins Setup

1. Open **http://localhost:8080** in your browser
2. Jenkins will ask for the initial admin password. Get it with:
   ```bash
   docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
   ```
3. Paste the password and click **Continue**
4. Choose **Install suggested plugins** and wait for installation
5. Create an admin user — you'll use this username and password in the next sub-steps

### 2b. Create the Flutter Agent Node

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
7. On the node status page, find the **secret token** (shown in the agent launch command, after `-secret`)

### 2c. Configure the Agent in Config Hub

Now switch to **config-hub** at http://localhost:9000:

1. Open the **Jenkins Agent** tab
2. Paste the **secret token** from the previous step into the **Agent Secret** field
3. Click **Save Agent Config**

> **Jenkins URL and Agent Name** are pre-configured in docker-compose and usually don't need to be changed via the UI.

### 2d. Create a Jenkins API Token

Back in Jenkins (http://localhost:8080):

1. Click your username (top-right) → **Configure**
2. Under **API Token**, click **Add new Token**
3. Give it a name (e.g., `tg-bot`) and click **Generate**
4. **Copy the token immediately** — it won't be shown again

### 2e. Add Repository Credentials (Private Repos)

If your Flutter project lives in a **private repository** (GitLab, GitHub, Bitbucket, etc.), Jenkins needs a Personal Access Token (PAT) to clone it. **Public repositories can skip to [2f](#2f-create-the-pipeline-job).**

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

### 2f. Create the Pipeline Job

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

5. Under **Pipeline**, paste a Jenkinsfile script.

   > **💡 Tip:** After completing the next sub-step ([2g](#2g-save-jenkins-settings-in-config-hub)), the config-hub dashboard has a **Jenkins Pipeline** tab that generates a customized Jenkinsfile based on your configuration. You can copy it directly into Jenkins.

   Alternatively, use this reference template:

   **For private repositories** (using the credential from [2e](#2e-add-repository-credentials-private-repos)):

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
                       def commitHash = ''
                       try {
                           commitHash = sh(script: 'git rev-parse --verify HEAD', returnStdout: true).trim()
                       } catch (e) {
                           commitHash = ''
                       }
                       def metadata = groovy.json.JsonOutput.toJson([
                           request_id : params.BOT_REQUEST_ID,
                           job_id     : params.BOT_JOB_ID,
                           status     : 'success',
                           commit_hash: commitHash,
                       ])

                       sh """
                           curl -X POST "${params.BOT_CALLBACK_URL}" \\
                               -F 'metadata=${metadata}' \\
                               -F "artifact=@${apkPath}"
                       """
                   }
               }
           }

           failure {
               script {
                   if (params.BOT_CALLBACK_URL) {
                       def commitHash = ''
                       try {
                           commitHash = sh(script: 'git rev-parse --verify HEAD', returnStdout: true).trim()
                       } catch (e) {
                           commitHash = ''
                       }
                       def logs = currentBuild.rawBuild.getLog(50).join('\n')
                       def metadata = groovy.json.JsonOutput.toJson([
                           request_id : params.BOT_REQUEST_ID,
                           job_id     : params.BOT_JOB_ID,
                           status     : 'failure',
                           commit_hash: commitHash,
                           logs       : logs,
                       ])

                       sh """
                           curl -X POST "${params.BOT_CALLBACK_URL}" \\
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
   >
   > `groovy.json.JsonOutput.toJson()` is used for metadata serialization — it correctly handles any special characters in commit hashes or log output. Do not use Groovy string interpolation to build JSON manually.

6. Click **Save**

### 2g. Save Jenkins Settings in Config Hub

Switch to **config-hub** at http://localhost:9000:

1. Open the **Build Manager** tab
2. Fill in the Jenkins fields:

   | Field             | Value                                            |
   | ----------------- | ------------------------------------------------ |
   | Jenkins URL       | `http://jenkins:8080` (internal Docker network)  |
   | Jenkins User      | Your Jenkins admin username (from [2a](#2a-initial-jenkins-setup)) |
   | Jenkins API Token | The token you just generated (from [2d](#2d-create-a-jenkins-api-token)) |
   | Pipeline Job Name | `flutter-build` (or the name from [2f](#2f-create-the-pipeline-job)) |
   | GitHub URL        | Your repository URL (used for commit links in messages) |

   > You can leave the other fields blank for now — we'll fill in Telegram and Drive in the next steps.

3. Click **Save**

---

## Step 3 — Set Up the Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts:
   - Choose a display name (e.g., "Flutter Build Bot")
   - Choose a username (e.g., `my_flutter_build_bot`)
3. BotFather will reply with your **bot token** — copy it
4. **Find your chat ID:**
   - Send any message to your new bot
   - Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   - Look for `"chat":{"id": XXXXXXXXX}` — this is your chat ID

   > [!TIP]
   > `@userinfobot` or `@RawDataBot` can also reveal chat IDs without using `getUpdates`.

5. **Register your bot's commands** with BotFather (recommended):
   - Send `/setcommands` to @BotFather
   - Select your bot, then paste:
     ```
     build - Trigger a Flutter build
     recent - Show recent builds with download links
     status - Current build status and service health
     help - Show usage instructions
     about - Show version and system info
     ```

Now enter these values in config-hub:

6. Open the **Telegram Bot** tab at http://localhost:9000
7. Fill in:

   | Field              | Value                                   |
   | ------------------ | --------------------------------------- |
   | Telegram Bot Token | The token from BotFather                |
   | Allowed Chat IDs   | Your chat ID(s), comma-separated        |

   You can also set these optional fields now:

   | Field              | Value                                   |
   | ------------------ | --------------------------------------- |
   | App Name           | Your app's display name (e.g., `Tendoo Mall`) — shown in bot messages |

8. Click **Save Bot Config**

---

## Step 4 — Set Up Google Drive

### 4a. Create Google Cloud Credentials

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

### 4b. Save & Connect in Config Hub

1. Open the **Google Drive** tab at http://localhost:9000
2. Paste the **Client ID** and **Client Secret** you just created
3. Click **Save Drive Config**
4. Click the **Connect Google Drive** button
5. A popup window will open — sign in with the Google account you added as a test user
6. Grant the requested permissions
7. The popup auto-closes on success and the dashboard shows "Connected"

> **Note:** Each APK upload gets its own unique, unguessable download link. The Drive folder itself stays private — the shared link only grants access to the specific file, not the entire build history.

---

## Step 5 — Start Services & Test

### Start the Bot and Agent

Use the **Service Control** section in the config-hub dashboard:

1. Click **Start** next to the **Agent** service — this connects the `flutter-agent` to Jenkins
2. Click **Start** next to the **Bot** service — this starts Telegram polling

Alternatively, restart the entire stack:

```bash
cd infra
docker compose restart
```

### Verify Everything is Connected

1. **Jenkins:** Go to http://localhost:8080 → Nodes — the `flutter-agent` should show as **online**
2. **Telegram:** Send `/status` to your bot — it should report service health and confirm the bot is ready

### Run Your First Build

1. Open your Telegram chat with the bot
2. Send `/build` — the bot presents a branch selection inline keyboard
3. Select a branch (or send `/build main` to trigger directly)
4. The bot replies with a "Building..." confirmation
5. Wait for Jenkins to complete the build (watch progress at http://localhost:8080)
6. On success, the bot uploads the APK to Google Drive and sends a download link
7. Send `/recent` to see your build history

🎉 **Setup complete!** You now have a fully functional CI/CD pipeline triggered from Telegram.

---

## Troubleshooting

### Container won't start / keeps restarting

```bash
# Check logs for a specific service
docker compose logs tg-bot
docker compose logs flutter-agent
docker compose logs config-hub
docker compose logs build-manager
docker compose logs file-manager
```

### Bot says "Google Drive setup required"

- Ensure you've entered the Drive Client ID and Secret in the **Google Drive** tab
- Click "Connect Google Drive" and complete the OAuth flow
- Make sure your Google account is added as a test user in the OAuth consent screen

### Agent shows as offline in Jenkins

- Verify the agent secret is correct in the **Jenkins Agent** tab
- Check the agent logs: `docker compose logs flutter-agent`
- Ensure the `JENKINS_AGENT_NAME` matches the node name in Jenkins (default: `flutter-agent`)

### Build triggers but Jenkins returns 403

- Verify Jenkins username and API token in the **Build Manager** tab
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
cd infra
docker compose down -v    # ⚠️ This deletes all volumes (config, data, Jenkins home)
docker compose up -d --build
```

---

## Admin Bot Setup (Optional)

The `tg-admin-bot` provides a Telegram-based fallback for stack management when the config-hub dashboard is unavailable.

1. Create a **separate** bot via @BotFather (not the same as the build bot)
2. Add both values to `infra/.env`:
   ```env
   ADMIN_BOT_TOKEN=your-admin-bot-token
   ADMIN_CHAT_ID=your-chat-id
   ```
3. Restart the stack: `cd infra && ./compose.sh up -d`

The admin bot supports: config view/edit, service control, headless Drive OAuth (code-paste flow), and config transfer (tarball export/import).

---

> For a system architecture overview, see the [main README](../README.md).
