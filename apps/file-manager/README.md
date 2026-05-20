# file-manager

Storage backend service for the Jenkins Flutter Bot. Manages Google Drive OAuth credentials, handles APK uploads, and returns shareable per-file download links. Designed to be storage-backend agnostic — currently implements Google Drive.

## Features

- **Google Drive Upload** — uploads APK artifacts and returns unique, unguessable file-scoped download links
- **OAuth Flow** — supports both browser-redirect (popup) and headless code-paste authorization
- **Token Lifecycle** — stores and refreshes OAuth tokens automatically
- **Config & Schema API** — exposes `/control/config` and `/control/schema` so config-hub can manage it

## How It Works

1. On first use, config-hub initiates the OAuth flow — user signs in via a browser popup
2. file-manager exchanges the auth code for tokens and stores them in `/app/data/oauth.json`
3. On each successful build, the build-manager instructs file-manager to upload the APK
4. file-manager creates a file-scoped shareable link and returns it to the caller

The Drive folder itself stays private — links grant access only to the specific file.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/status` | GET | OAuth connection status |
| `/api/auth/connect/start` | POST | Start browser-redirect OAuth flow (returns auth URL) |
| `/api/auth/connect/exchange` | POST | Headless code exchange (admin bot flow) |
| `/api/auth/callback` | GET | OAuth redirect callback |
| `/api/auth/disconnect` | DELETE | Revoke and delete stored token |
| `/api/files/upload` | POST | Upload a file and return a download link |
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
| Drive Folder Name | `drive.folder_name` | Folder name for uploads (default: `flutter-builds`) |

> The OAuth token is stored separately in the same data volume and is **not** part of the config export.

## Running

```bash
file-manager  # starts on port 9092
```
