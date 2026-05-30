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
  - [2h. Optimize Jenkins for Bot-Only Operation (Storage & Resources)](#2h-optimize-jenkins-for-bot-only-operation-storage--resources)
- [Step 3 — Set Up the Telegram Bot](#step-3--set-up-the-telegram-bot)
- [Step 4 — Set Up Google Drive](#step-4--set-up-google-drive)
  - [4a. Create Google Cloud Credentials](#4a-create-google-cloud-credentials)
  - [4b. Save & Connect in Config Hub](#4b-save--connect-in-config-hub)
- [Step 5 — Start Services & Test](#step-5--start-services--test)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Requirement       | Minimum Version | Notes                                       |
| ----------------- | --------------- | ------------------------------------------- |
| Docker            | 24+             | With Docker Compose v2 (`docker compose`)   |
| Internet access   | —               | For pulling images and Google/Telegram APIs  |
| Telegram account  | —               | To create a bot via BotFather                |
| Google account    | —               | For Drive API OAuth credentials              |

> **First-time build warning:** The `agent-control` image (using `infra/agent/Dockerfile`) downloads Flutter SDK, Android SDK, and pre-caches artifacts during build. Expect the **first `docker compose build`** to take **15–30 minutes** depending on your internet speed. Subsequent builds use Docker layer caching.

> [!WARNING]
> **Apple Silicon (ARM64) users:** Flutter does not support building Android release APKs on Linux ARM64 hosts ([flutter#177936](https://github.com/flutter/flutter/issues/177936)). The `agent-control` service in `infra/docker-compose.yml` is set to `platform: linux/amd64` to force x86_64 emulation. Builds will be slower under emulation — for production CI/CD, use a native x86_64 server.

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

This starts all eight containers:

| Service          | URL                    | Purpose                                           |
| ---------------- | ---------------------- | ------------------------------------------------- |
| `jenkins`        | http://localhost:8080   | Jenkins controller (web UI)                       |
| `gateway`        | http://localhost:8880/webapp-admin | Ingress Gateway (proxies to config-hub) |
| `config-hub`     | Internal (:9000)       | Configuration dashboard and operational hub       |
| `tg-jenkins-bot` | Internal (:9090)       | Telegram bot + webhook receiver (publicly proxied to gateway:80) |
| `agent-control`  | Internal (:9091)       | Jenkins agent with Flutter/Android SDKs, OpenVPN management + control API |
| `file-manager`   | Internal (:9092)       | Google Drive OAuth, build log, and retention enforcement |
| `build-manager`  | Internal (:9010)       | Jenkins build trigger and job state tracking      |

> [!NOTE]
> The bot and agent won't fully start yet — that's expected. They need configuration first (Steps 2–4). Their control APIs remain available so config-hub can manage them.

Open **http://localhost:8880/webapp-admin** (proxied securely via the gateway) — you'll use this dashboard throughout the remaining steps.

### 1b. Config Hub Security (Basic Authentication)

By default, Config Hub operates with no authentication in development for rapid setup. To secure your configuration dashboard (especially when hosting publicly or in production):

1. Create or edit **`infra/env/config-hub.env`** and add your credentials:
   ```env
   CONFIG_HUB_AUTH_USERNAME=your_username
   CONFIG_HUB_AUTH_PASSWORD=your_secure_password
   ```
2. Restart the Config Hub container:
   ```bash
   ./compose.sh restart config-hub
   ```

Once configured, the web UI and APIs will prompt for standard HTTP Basic Authentication credentials.

> [!NOTE]
> The Google Drive OAuth callback endpoint (`/api/drive/oauth/callback`) is automatically exempted from Basic Auth. This prevents modern browsers from stripping authentication credentials on the redirect back from Google Accounts.

### 1c. Configuration Portability (Export & Import)

Config Hub provides symmetric configuration transfer under the **Export / Import** sidebar:
- **Export**: Generates a self-documenting unified `compose.env` file along with the JSON configurations of all running services packaged into a portable `.tar.gz` archive. The export routine can optionally package your active Google Drive OAuth tokens (`oauth.json`) and your current OpenVPN configuration (`client.ovpn`) if they exist.
- **Import**: Allows you to upload the `.tar.gz` package to fully restore the state of all services. Config Hub extracts the package, applies the Pydantic configurations to each service, writes the certificates, and automatically triggers service restarts.

This makes cloning configurations across dev, mock, and production environments exceptionally clean and fast.

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

Now switch to **config-hub** at http://localhost:8880/webapp-admin:

1. Open the **Jenkins Agent** tab
2. Paste the **secret token** from the previous step into the **Agent Secret** field
3. Click **Save Agent Config**

> **Jenkins URL and Agent Name** are pre-configured in docker-compose and usually don't need to be changed via the UI.

### 2d. Create a Jenkins API Token

Back in Jenkins (http://localhost:8080):

1. Click your username (top-right) → **Configure**
2. Under **API Token**, click **Add new Token**
3. Give it a name (e.g., `jenkins-flutter-bot` or `build-manager`) and click **Generate**
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
   | `BUILD_REQUEST_ID`| _(empty)_     | Correlation ID to match this build back to the Telegram request |

5. Under **Pipeline**, paste a Jenkinsfile script.

   > **💡 Tip:** After completing the next sub-step ([2g](#2g-save-jenkins-settings-in-config-hub)), the config-hub dashboard has a **Jenkins Pipeline** tab that generates a customized Jenkinsfile based on your configuration. You can select features like discarding old builds, cleaning workspaces, and shallow cloning, then copy the generated Groovy script directly into Jenkins.

   Alternatively, use this reference template:

   **For private repositories** (using the credential from [2e](#2e-add-repository-credentials-private-repos)):

   ```groovy
   pipeline {
       agent { label 'flutter' }

       parameters {
           // Branch to build — injected by the Telegram Web App
           string(name: 'BRANCH', defaultValue: 'main')

           // Correlation ID — injected automatically by the build-manager. Do NOT set manually.
           string(name: 'BUILD_REQUEST_ID', defaultValue: '')
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
               // Archive the resulting APK inside Jenkins.
               // Build-manager will poll for success, then download the archived file.
               archiveArtifacts artifacts: 'build/app/outputs/flutter-apk/*.apk'
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

   > **Adapt this pipeline** to your specific Flutter project. The key contract is the `archiveArtifacts` call in the success block. Build-manager's poll worker will detect completion and download the APK automatically. **The pipeline does not need to make any outbound HTTP calls.**

6. Click **Save**

### 2g. Save Jenkins Settings in Config Hub

Switch to **config-hub** at http://localhost:8880/webapp-admin:

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

### 2h. Optimize Jenkins for Bot-Only Operation (Storage & Resources)

Because the project delegates build compilation to Jenkins but manages **build history, download delivery, and file hosting** entirely within its own internal services and Google Drive, you can configure Jenkins for highly optimized, low-footprint operations. This prevents your Jenkins server's disk space from filling up over time.

Implement these optimizations in your Jenkins pipeline using the **integrated checkboxes in config-hub's "Jenkins Pipeline" tab**:

#### 1. Discard Old Builds Automatically
Since the bot immediately downloads the successful artifact and hosts it on Google Drive, and the build-manager tracks build logs/metadata locally, Jenkins does not need to store historical builds.
* Switch on the **Discard Old Builds** option in config-hub to limit the build history to **`1`** build.

#### 2. Clean Workspaces Post-Build
By default, Jenkins retains checked-out code and build caches on the agent's disk, which can grow to tens of gigabytes for Flutter/Android projects. Wipe this clean after every execution.
* Switch on the **Clean Workspace Post-Build** option in config-hub to clean workspace files after completion.

#### 3. Enable Shallow Clones (Speed & Space Optimization)
If your git history is large, downloading the entire repository history wastes time and disk space. Perform a shallow clone instead.
* Switch on the **Shallow Git Clone** option in config-hub to enable `--depth=1` shallow cloning.

#### 4. Restrict Node Concurrency
To ensure the `flutter-agent` build container isn't overwhelmed by multiple parallel builds:
* Go to **Manage Jenkins → Nodes → flutter-agent → Configure**.
* Set **Number of executors** to **`1`**.

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
     recent - Show recent builds with download links
     status - Current build status and service health
     help - Show usage instructions
     ```

Now enter these values in config-hub:

6. Open the **Telegram Bot** tab at http://localhost:8880/webapp-admin
7. Fill in:

   | Field              | Value                                   |
   | ------------------ | --------------------------------------- |
   | Telegram Bot Token | The token from BotFather                |
   | Allowed Chat IDs   | Your chat ID(s), comma-separated (optional, defaults to empty/unrestricted) |
   | Web App URL        | The public HTTPS URL where your bot service is accessible (e.g., `https://your-domain/webapp/`) |

   You can also set these optional fields:

   | Field              | Value                                   |
   | ------------------ | --------------------------------------- |
   | App Name           | Your app's display name (e.g., `Tendoo Mall`) — shown in bot messages |
   | Build Options      | JSON mapping of display label to git branch (e.g., `{"Stable Release": "main", "Testing Version": "develop"}`) |

8. Click **Save Bot Config**

> **💡 Web App Menu Button Setup:** The bot dynamically registers the native `🚀 Build` MenuButtonWebApp on startup using the configured `webapp_url`. You do not need to configure this manually in BotFather.

### 3b. Exposing the Web App via Cloudflare Tunnel (HTTPS)

Telegram Web Apps require a public **HTTPS** URL. An exceptionally secure, fast, and free way to obtain one without opening router ports or managing SSL certificates is **Cloudflare Tunnel** (`cloudflared`).

#### Method A — Running Cloudflared via Docker Compose (Recommended)


The `cloudflared` tunnel and a pre-configured **Caddy Ingress Gateway** are already integrated into `infra/docker-compose.yml`. The Ingress Gateway acts as a secure routing perimeter, exposing **only** the public Web App (`/webapp`) and its APIs (`/api/webapp`), while keeping all administrative and webhook paths completely isolated and closed to the public.

1. Open your Cloudflare Zero Trust Dashboard and go to **Networks → Tunnels**.
2. Click **Create a Tunnel**, choose **Cloudflared**, name it (e.g., `jenkins-flutter-bot`), and click **Save**.
3. Under **Install and run a connector**, select **Docker** and copy the **token** from the provided command (the long hash after `--token`).
4. Simply create or edit your **`infra/.env`** file and add your token:
   ```env
   CLOUDFLARE_TUNNEL_TOKEN=YOUR_CLOUDFLARE_TUNNEL_TOKEN
   ```
5. On the Cloudflare Tunnel page, click **Next** to go to **Route Traffic**.
6. Set up your public hostname:
   - **Public Hostname:** `bot.yourdomain.com` (or any subdomain of a domain managed by Cloudflare)
   - **Service Type:** `HTTP`
   - **URL:** `gateway:80` (routes directly through our secure Caddy Ingress Gateway)
7. Save the tunnel settings.

When you run your services, Docker Compose will automatically spin up the Caddy Ingress Gateway and the tunnel connector, linking them securely on the internal network.



#### Method B — Running Cloudflared on the Host

If you prefer to run the connector natively on your host machine:

1. Download and install `cloudflared` on your system.
2. Run the connector with your tunnel token:
   ```bash
   cloudflared tunnel --no-autoupdate run --token YOUR_CLOUDFLARE_TUNNEL_TOKEN
   ```
3. In the Cloudflare Tunnel configuration, route your public hostname to:
   - **Service Type:** `HTTP`
   - **URL:** `http://localhost:9090`

#### Finalizing the Setup
Once the tunnel is active, configure your `WEBAPP_URL` in **config-hub** (http://localhost:8880/webapp-admin):
- Set **Web App URL** to `https://bot.yourdomain.com/webapp/` (make sure it ends with `/webapp/` and uses `https`).
- Click **Save Bot Config** and restart the bot service. The bot will automatically register the `🚀 Build` MenuButtonWebApp pointing to your new Cloudflare domain!

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
   - **Authorized redirect URIs:** add `http://localhost:8880/api/webapp-admin/drive/oauth/callback`
   - Click **Create**
   - Copy the **Client ID** and **Client Secret**

### 4b. Save & Connect in Config Hub

1. Open the **Google Drive** tab at http://localhost:8880/webapp-admin
2. Paste the **Client ID** and **Client Secret** you just created
3. Click **Save Drive Config**
4. Click the **Connect Google Drive** button
5. A popup window will open — sign in with the Google account you added as a test user
6. Grant the requested permissions
7. The popup auto-closes on success and the dashboard shows "Connected"

> **Note:** Each APK upload gets its own unique, unguessable download link. The Drive folder itself stays private — the shared link only grants access to the specific file, not the entire build history.

> [!TIP]
> **Alternative Storage Backends (Dev/Testing):**
> If you do not want to set up Google Cloud/Google Drive OAuth credentials for local development or rapid testing, the file-manager service supports two alternative backends:
> - **`ephemeral`**: A local disk-persisted temporary directory storage backend. Uploaded APKs are stored in a temporary directory on the local filesystem and are served via an internal download endpoint. This temporary directory is completely wiped clean on every startup of the service to prevent memory or disk bloat. No external accounts or configurations are required.
> - **`log_only`**: A minimal dummy backend that logs upload and delete operations to the console and returns mock URLs without storing any files. Extremely useful for lightweight local testing or offline development.
>
> To use these, set the `STORAGE_BACKEND` environment variable in `infra/env/file-manager.env` to either `ephemeral` or `log_only` and restart the file-manager service.

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

> [!TIP]
> **Local WebApp Emulator for Development:**
> Both the `tg-jenkins-bot` webapp and the `config-hub` admin app include an integrated **Telegram WebApp Emulator** for rapid in-browser testing without relying on the physical Telegram client. When you access these apps in your browser locally (e.g. `http://localhost:8880/webapp/` or `http://localhost:8880/webapp-admin/`), the emulator provides a mock mobile UI container simulating custom theme styles, Main/Back button integration, and editable Telegram `initData` parameters.

### Run Your First Build

1. **Group Chat Only Requirement:** The Telegram Mini App is strictly prohibited in private 1-on-1 chats for collaborative security. Ensure your bot is added to an authorized group chat (one of the whitelisted IDs in `allowed_chat_ids`).
2. Tap the **🚀 Build** menu button in the authorized group chat to launch the Telegram Mini App. (Launching from a private chat will display a `private_chat_disabled` error page).
3. Select a configured branch or type a custom branch name, then tap **Trigger Build**.
4. The Mini App provides a **Real-Time Active Builds** dashboard using Server-Sent Events (SSE). You can monitor your build's status directly in the Mini App as it progresses:
   - Tapping **Cancel** stops the build in Jenkins and cleans up state immediately.
   - **Creator-Only Cancellation:** Only the user who originally triggered a specific build is authorized to cancel it. Other users will receive a `403 Forbidden` if they try.
5. The bot will also post a status message `🔨 Alice started a Stable Release build` to the group chat.
6. Watch the build progress on Jenkins (http://localhost:8080)
7. Upon successful completion, the bot posts a completely new `✅ MyApp Stable Release is ready!` message to the group chat containing the direct Google Drive **📥 Download APK** link.
8. **Recent Builds History:** Instead of spamming the chat with historical lists, you can view the 5 most recent completed builds and their download links natively inside the **Recent Builds** section at the bottom of the Mini App.

🎉 **Setup complete!** You now have a fully functional CI/CD pipeline triggered via Telegram Web Apps.

---

## Troubleshooting

### Container won't start / keeps restarting

```bash
# Check logs for a specific service
docker compose logs tg-jenkins-bot
docker compose logs agent-control
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
- Check the agent logs: `docker compose logs agent-control`
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

- Build-manager polls Jenkins REST API for build status. Ensure the Jenkins credentials and job name are configured correctly in the **Build Manager** tab.
- The pipeline MUST archive the APK (via `archiveArtifacts artifacts: 'build/app/outputs/flutter-apk/*.apk'`). Check that the archive pattern matches your APK output location.
- Verify that `tg-jenkins-bot` and `build-manager` are successfully communicating. Check logs:
  ```bash
  docker compose logs build-manager
  docker compose logs tg-jenkins-bot
  ```

### OAuth popup says "redirect_uri_mismatch"

- In Google Cloud Console, ensure the redirect URI is exactly: `http://localhost:8880/api/webapp-admin/drive/oauth/callback`
- The URI is case-sensitive and must include the full path

### Resetting everything

```bash
cd infra
docker compose down -v    # ⚠️ This deletes all volumes (config, data, Jenkins home)
docker compose up -d --build
```

---

> For a system architecture overview, see the [main README](../README.md).
