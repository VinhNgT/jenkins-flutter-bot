---
trigger: model_decision
description: Build trigger flow, polling-based completion detection, OAuth implementations, config transfer, async patterns, and service lifecycle.
---

# Communication Flows

Loaded at model discretion when the task involves service-to-service communication, build flows, OAuth, config transfer, or async patterns.

---

## Build Trigger Flow

The bot acts as a passive frontend and notification layer. All interactive build selections are handled in the Telegram Web App:

1. **User launches Web App** — Taps the `🚀 Build` MenuButtonWebApp to open the Telegram Mini App (served at `/webapp`). Private chats are disabled; the Web App must be launched from an authorized group chat.
2. **Retrieve Config** — Web App calls `GET /api/webapp/config` with `X-Telegram-Init-Data`. The bot's API validates the signature, verifies that it is not a private chat, and authorizes the chat ID against the whitelisted `allowed_chat_ids`.
3. **Establish Real-Time Active Build Stream** — The Web App establishes a Server-Sent Events (SSE) connection to `/api/webapp/stream` to receive real-time active build states. The backend only pushes down the wire when the store mutates, utilizing a 15-second keep-alive.
4. **Trigger Build** — User selects a branch option and clicks build. Web App calls `POST /api/webapp/trigger`.
5. **Trigger Build-Manager** — The bot requests a build from the build-manager (`POST /builds/trigger`) with `BRANCH`, `callback_url`, and a generated `request_id`.
6. **Register Active Build** — The bot registers the active build in the in-memory `ActiveBuildStore` (saving the user-configured `notify` option) and returns success to the Web App. To prevent group chat spam, no immediate starting build confirmation message is sent.
7. **Initiate VPN & Trigger Jenkins** — Build-manager initiates an OpenVPN connection via `agent-control`, triggers Jenkins (`POST /job/{name}/buildWithParameters`) with `BRANCH` and `BUILD_REQUEST_ID`, and registers the pending build.
8. **Jenkins Run** — Jenkins pipeline runs on the agent managed by `agent-control` and archives the resulting APK on success — **no outbound HTTP from the agent**.
9. **Poll & Forward** — Build-manager's poll worker detects build completion, downloads the artifact, and sends build metadata + artifact to file-manager via `POST /api/files/builds/record`. File-manager uploads to the storage backend: Google Drive or the local disk-persisted `ephemeral` storage (which persists files to a temporary directory on the local filesystem and wipes it completely on service startup). It then records the build in its build log, enforces retention, and returns the download URL. Build-manager forwards the result to the bot's webhook (`POST /callback/build-result`).
10. **Notify Chat** — If completion notifications are enabled (`notify=True` on the `ActiveBuild`), the bot delivers a success, failure, timeout, or cancellation notification containing the direct APK download link to the group chat. Messages are strictly **immutable** (send-only, fire-and-forget). The bot **never** edits or deletes its messages.
11. **Disconnect VPN** — Build-manager checks if the pending build queue is empty; if so, it triggers VPN disconnection via `agent-control`.
12. **Retrieve History** — Users can browse past successful builds on demand inside the Web App interface, which calls the `GET /api/webapp/recent` endpoint. The bot queries file-manager directly (`GET /api/files/builds/recent`) for completed build history (the Telegram chat remains clean of historical spam). Each build record contains `request_id`, custom branch `label`, `file_size`, and direct download URLs.

### Security & Access Model

- **HMAC-SHA256 Validation** — The bot validates the `X-Telegram-Init-Data` header signature using the bot's token (HMAC-SHA256) on every Web App API call to prevent unauthorized requests.
- **Allowed Group Filtering** — The bot extracts `chat.id` from the verified `initData` and enforces access control using the whitelisted `allowed_chat_ids`. Web App access from private chats (positive chat IDs) is strictly prohibited.
- **Creator-Only Cancellation** — When a cancel request is made via `POST /api/webapp/cancel`, the backend verifies that the Telegram user ID (`user.id`) matches the `triggered_by_id` stored for that active build, preventing unauthorized cancellation of builds triggered by other group members.
- **Correlation Token** — `BUILD_REQUEST_ID` is a 128-bit random token per build correlating the webhook callback back to the correct chat and active build.

---

## Service Control

`config-hub` controls services via `ServiceClient`:

```
Client → POST /control/{start|stop|restart} → target service
Client → GET /control/status → target service (polling status check)
Client → GET /control/stream → target service (SSE real-time status stream)
Client → GET /control/schema → target service
Client → GET/PUT /control/config → target service (read/write config)
```

The real-time status of all services is streamed to the config-hub frontend via a Server-Sent Events (SSE) stream at `/api/webapp-admin/services/stream`. The backend polls all managed service clients, serializes the aggregated status as a canonical JSON string, and hashes it using MD5. It only yields a new `ServerSentEvent` to the client if the resulting hash differs from the previously sent update, preventing redundant rendering and saving network bandwidth.

The `/control/status` response carries five fields:

| Field | Type | Meaning |
|-------|------|---------|
| `configured` | `bool` | Whether `Settings.load()` succeeds (all required fields present) |
| `running` | `bool` | Whether the managed subprocess/resource is active |
| `last_error` | `str | null` | Last runtime error from a `start()` attempt |
| `config_error` | `str | null` | Current config validation error (`null` when configured) |
| `started_at` | `float | null` | UNIX epoch timestamp of the last successful `start()` (for uptime display) |

If a service is down, its schema returns `null` and the config-hub frontend shows "Loading..." for that tab.

### Scope-to-Service Translation

The config-hub exposes UI scopes that map directly to internal service URLs (which point to their Docker containers). The mapping lives exclusively in `config-hub/manager.py:_SCOPE_TO_SERVICE`:

| UI Scope | Internal Service Client Name | Target Container / Service |
|----------|-----------------------------|----------------------------|
| `bot` | `bot` | `tg-jenkins-bot` |
| `agent` | `agent` | `agent-control` |
| `file_manager` | `file_manager` | `file-manager` |
| `builds` | `builds` | `build-manager` |

Unknown scopes are rejected with HTTP 404 — `save_scope()` raises `ValueError` for any scope not in the map.

Do not move or duplicate this mapping. Do not rename `file-manager` internals to `drive`.

---

## Google Drive OAuth

OAuth is handled by `file-manager` (`/api/auth/*`) via two mechanisms, both proxied through config-hub (`/api/webapp-admin/drive/*`):

1. **Browser-redirect flow** — used by the web dashboard (popup callback at `/api/webapp-admin/drive/oauth/callback`)
2. **Headless code-paste flow** — exchange manually-pasted auth code for tokens (manual fallback option)

Both flows produce the same stored token in file-manager's data volume. The bot never initiates OAuth — it only uploads files after a successful build.

### Auth Exemption for OAuth Callback
The Google Drive OAuth callback endpoint (`/api/webapp-admin/drive/oauth/callback`) is explicitly exempted from authentication. This is required because cross-origin redirects from accounts.google.com cannot carry authentication headers or initData. The exemption is safe as the endpoint only serves a static HTML shell that triggers parent window callback events, and carries out no administrative or write operations.

### Key Design Decisions

- **`_pending_flow` is in-memory only** — the OAuth flow object contains PKCE state that can't be serialized. If the service restarts mid-flow, the flow is lost and must be restarted. This is by design.
- **Frontend-only "Connecting" state** — the config-hub popup flow is tracked entirely by the frontend via a `<dialog>` modal. Do NOT add a backend `auth_pending` flag.
- **`OAUTHLIB_INSECURE_TRANSPORT`** — automatically set when the redirect URI uses `http://` (local/Docker development).

---

## Config Transfer

`config-hub` supports symmetric config transfer:

- **Export**: packages all JSON configs + generated `.env` files into a `.tar.gz`
- **Import**: extracts a `.tar.gz`, applies configs to each owning service via `PUT /control/config`, triggers service restarts

Only `.tar.gz` imports are accepted — this prevents partial or inconsistent config states.

OAuth tokens (`oauth.json`) and active OpenVPN client profiles (`client.ovpn`) can optionally be included in the config export/import `.tar.gz` packages to facilitate seamless migration and zero-manual-intervention environment setup, although by default OAuth tokens are environment-specific.

---

## Drive File Access

Each uploaded APK is made individually accessible — the Drive **folder** stays private. Key constraints:

- Per-file `anyone/reader` permission, set immediately after upload
- Do NOT set `anyone/reader` on the folder — this would expose the entire build history
- `delete_file()` cleans up both the file and its permissions atomically

---

## Build State Management

Build state is split across three services:

- **build-manager** — owns **pending builds** (in-flight) and poll workers. Manages build triggering, Jenkins polling, artifact downloading, and result forwarding. Completed builds are handed off to file-manager.
- **file-manager** — owns the **build log**: completed build records, download URL tracking, retention enforcement (`max_recent_builds` eviction with backend file cleanup), and Drive reconciliation on startup (cross-references the log against actual Drive contents to recover orphans and prune stale records). The build log is stored in a backend-specific database (`build_log_{backend_type}.json`) to prevent data cross-contamination when changing backends.
- **tg-jenkins-bot** — maintains active builds in-memory via `ActiveBuildStore` mapping `request_id -> ActiveBuild`. Used strictly to correlate webhook callback results back to the Telegram chat.

Jenkins owns all raw build metadata (status, duration, branch, commit). The bot queries build-manager for summaries — it never queries Jenkins directly for build info.

---

## Bot Manager Lifecycle

- **BotManager** (in `tg-jenkins-bot`) is defined in `manager.py` and injected into control routers via `ManagerDep`.
- The manager utilizes an `asyncio.Lock` for thread-safe concurrent `start()`, `stop()`, and `restart()` control operations.
- On startup failure (e.g. invalid bot tokens), the FastAPI wrapper stays running, meaning the control API remains available for retries and troubleshooting.
- Shared context (e.g., config, clients) is bound directly into `Application.bot_data` for accessibility within handler callbacks.

---

## Async I/O Pattern

Blocking I/O libraries (e.g., `google-api-python-client`) must be wrapped with `asyncio.to_thread()` in async code paths. The established convention is the `_sync` suffix pattern: the blocking implementation is a private `_method_sync()`, and the public async wrapper calls it via `to_thread()`. See `GoogleDriveBackend` for the canonical example (`_load_tokens_sync` → `load_tokens`, `_exchange_callback_sync` → `exchange_callback`, etc.).
