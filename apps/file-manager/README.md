# file-manager

Storage backend service for the Jenkins Flutter Bot. Manages build artifact storage, build completion logs, retention enforcement, and Google Drive OAuth. Supports three storage backends: Google Drive (production), ephemeral in-memory storage (dev/mock), and log-only storage (dev/mock/minimal).

## Features

- **Build Log** — tracks completed build metadata (branch, commit, result, timestamps, download URLs, and APK file sizes) with configurable retention enforcement stored in backend-specific database files (`build_log_{backend_type}.json`).
- **Google Drive Upload** — uploads APK artifacts and returns unique, unguessable file-scoped download links
- **Ephemeral Storage** — in-memory storage backend for dev/mock environments (no Google Drive credentials required)
- **Log-Only Storage** — logs upload and delete operations without actually storing any data (useful for minimal setups or external storage testing)
- **Drive Reconciliation** — on startup, cross-references the build log against actual Drive contents to recover orphan files and prune stale records
- **Retention Enforcement** — evicts oldest build records and their backend files when the log exceeds `max_recent_builds`
- **OAuth Flow** — supports both browser-redirect (popup) and headless code-paste authorization
- **Token Lifecycle** — stores and refreshes OAuth tokens automatically
- **Config & Schema API** — exposes `/control/config` and `/control/schema` so config-hub can manage it

## How It Works

1. On first use, config-hub initiates the OAuth flow — user signs in via a browser popup
2. file-manager exchanges the auth code for tokens and stores them in `/app/data/oauth.json`
3. On each completed build, build-manager sends build metadata and artifact to file-manager via `POST /api/files/builds/record`
4. file-manager uploads to the storage backend, records the build in its log, enforces retention, and returns the download URL

The Drive folder itself stays private — links grant access only to the specific file.

In ephemeral mode (no Drive credentials), files are stored in memory and served via the download endpoint. No OAuth is required.

In log-only mode (`STORAGE_BACKEND=log_only`), operations are logged only, returning mock URLs. No files are stored or served.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/files/builds/record` | POST | Record a completed build, optionally uploading an artifact (and specifying `file_size` in bytes) |
| `/api/files/builds/recent` | GET | Return recent completed build records |
| `/api/files/{file_id}` | DELETE | Delete a single file and its build log record |
| `/api/files/cleanup` | POST | Batch delete files |
| `/api/files/{file_id}/download` | GET | Download from ephemeral storage (ephemeral mode only) |
| `/api/auth/status` | GET | OAuth connection status |
| `/api/auth/connect/start` | POST | Start browser-redirect OAuth flow (returns auth URL) |
| `/api/auth/connect/exchange` | POST | Headless code exchange (manual paste flow) |
| `/api/auth/callback` | GET | OAuth redirect callback |
| `/api/auth/disconnect` | DELETE | Revoke and delete stored token |
| `/control/status` | GET | Service health |
| `/control/schema` | GET | Config field schema |
| `/control/config` | GET/PUT | Read/write config (deep merge) |

## Configuration

Config is stored at `/app/data/storage.json` inside the container (mounted from the `storage-data` volume).

### Runtime Fields (managed via the dashboard — Google Drive tab)

| Field | Key | Description |
|-------|-----|-------------|
| Drive Client ID | `drive.client_id` | OAuth 2.0 Client ID from Google Cloud Console |
| Drive Client Secret | `drive.client_secret` | OAuth 2.0 Client Secret (secret) |
| Drive Folder Name | `drive.folder_name` | Folder name for uploads (default: `Flutter Builds`) |
| Max Recent Builds | `storage.max_recent_builds` | Number of completed build records to retain (default: 5) |

> The OAuth token is stored separately in the same data volume and is **not** part of the config export.

## Running

```bash
file-manager  # starts on port 9092
```
