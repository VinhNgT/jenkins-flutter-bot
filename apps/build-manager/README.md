# build-manager

Build orchestration service for the Jenkins Flutter Bot. Acts as the intermediary between the Telegram bot and Jenkins — manages build triggers, tracks job state, and coordinates webhook callbacks.

## Features

- **Jenkins Trigger** — submits parameterized builds to Jenkins via REST API
- **Job State Tracking** — maintains a registry of in-progress and completed builds
- **Webhook Coordination** — receives Jenkins build results and notifies the Telegram bot
- **Branch Resolution** — queries the remote Git repository to resolve branch head commits before triggering
- **Config & Schema API** — exposes `/control/config` and `/control/schema` so config-hub can manage it

## How It Works

1. Telegram bot sends a `POST /builds/trigger` request with a branch and callback URL
2. build-manager queues the job, triggers Jenkins via REST, and registers the `request_id`
3. Jenkins calls back to build-manager on completion (success or failure)
4. build-manager stores the result, uploads APK to Drive via file-manager (if successful), enforces `max_recent_builds` retention, and notifies the tg-bot webhook

The build-manager owns zero build logic — all cloning, compiling, and packaging is delegated to the Jenkins pipeline.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/builds/trigger` | POST | Trigger a new Jenkins build |
| `/builds/status` | GET | Get summary of active and recent builds |
| `/builds/recent` | GET | List recent completed builds |
| `/webhook/build-result` | POST | Jenkins build result callback |
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
| `SELF_URL` | `http://build-manager:9010` | This service's own URL (used as webhook callback base) |
| `FILE_MANAGER_URL` | `http://file-manager:9092` | File-manager URL for APK upload delegation |

## Running

```bash
build-manager  # starts on port 9010
```
