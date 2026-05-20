# build-manager

Build orchestration service for the Jenkins Flutter Bot. Acts as the intermediary between the Telegram bot and Jenkins — manages build triggers, polls for completion, downloads build artifacts, and coordinates final callbacks.

## Features

- **Jenkins Trigger** — submits parameterized builds to Jenkins via REST API
- **Job State Tracking** — maintains a registry of in-progress and completed builds
- **Polling Completion Detection** — each triggered build gets a dedicated `asyncio` poll worker that queries Jenkins until `building == False`
- **Artifact Download** — on success, downloads the archived APK directly from Jenkins and delegates upload to file-manager
- **Branch Resolution** — queries the remote Git repository to resolve branch head commits before triggering
- **Config & Schema API** — exposes `/control/config` and `/control/schema` so config-hub can manage it

## How It Works

1. Telegram bot sends a `POST /builds/trigger` request with a branch and callback URL
2. build-manager triggers Jenkins via REST with `BRANCH` and `BUILD_REQUEST_ID` parameters
3. A per-build poll worker repeatedly queries the Jenkins API until the build finishes
4. On completion, build-manager downloads the archived APK from Jenkins, uploads it to file-manager, enforces `max_recent_builds` retention, and notifies the bot callback URL

The build-manager owns zero build logic — all cloning, compiling, and packaging is delegated to the Jenkins pipeline.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/builds/trigger` | POST | Trigger a new Jenkins build |
| `/builds/status` | GET | Get summary of active and recent builds |
| `/builds/recent` | GET | List recent completed builds |
| `/builds/pending` | GET | List in-flight builds |
| `/builds/{id}/cancel` | POST | Cancel a pending build |
| `/control/status` | GET | Service health |
| `/control/schema` | GET | Config field schema |
| `/control/config` | GET/PUT | Read/write config (deep merge) |

## Configuration

Config is stored at `/app/data/builds.json` inside the container (mounted from the `build-manager-data` volume).

### Runtime Fields (managed via the dashboard — Build Manager tab)

| Field | Key | Description |
|-------|-----|-------------|
| Jenkins URL | `jenkins.url` | Jenkins controller URL |
| Jenkins User | `jenkins.user` | Jenkins admin username |
| Jenkins API Token | `jenkins.api_token` | Jenkins API token (secret) |
| Jenkins Job Name | `jenkins.job_name` | Pipeline job name (default: `flutter-build`) |
| Jenkins Credentials ID | `jenkins.credentials_id` | Credential ID for private repo checkout |
| Git Repository URL | `git.repo_url` | Repository URL for branch resolution and commit links |

### Infrastructure Fields (set in docker-compose, not the dashboard)

| Variable | Default | Description |
|----------|---------|-------------|
| `FILE_MANAGER_URL` | `http://file-manager:9092` | File-manager URL for APK upload delegation |

### Advanced Fields (tunable via the dashboard — Build Manager tab)

| Field | Key | Default | Description |
|-------|-----|---------|-------------|
| Poll Interval | `builds.poll_interval` | 10 s | Seconds between Jenkins API checks while a build is running |
| Artifact Pattern | `builds.artifact_pattern` | `*.apk` | Glob pattern to match the archived build artifact |
| Build Timeout | `builds.build_timeout` | — | Max minutes before a build is declared timed out |
| Max Recent Builds | `builds.max_recent_builds` | 3 | How many completed builds to retain (oldest evicted with Drive cleanup) |

## Running

```bash
build-manager  # starts on port 9010
```
