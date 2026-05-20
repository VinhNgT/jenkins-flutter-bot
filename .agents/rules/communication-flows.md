---
trigger: model_decision
description: Build trigger flow, polling-based completion detection, OAuth implementations, config transfer, async patterns, and service lifecycle.
---

# Communication Flows

Loaded at model discretion when the task involves service-to-service communication, build flows, OAuth, config transfer, or async patterns.

---

## Build Trigger Flow

The bot acts as a thin trigger layer. The full flow:

1. User sends `/build` (or `/build <ref>`) → bot shows branch picker or triggers directly
2. Bot requests a build from the build-manager (`POST /builds/trigger`) with `BRANCH`, `callback_url`, and a generated `request_id`
3. Build-manager triggers Jenkins (`POST /buildWithParameters`) with `BRANCH` and `BUILD_REQUEST_ID`, and registers the pending build
4. Build-manager spawns a **per-build poll worker** (`asyncio` task) that periodically queries the Jenkins REST API
5. Bot stores a `PendingBuild` in memory (request_id → chat_id/message_id for inline editing)
6. Jenkins pipeline runs on the flutter-agent and calls `archiveArtifacts` on success — **no outbound HTTP from the agent**
7. Poll worker detects `building == False` for the matching `BUILD_REQUEST_ID`, downloads the artifact directly from Jenkins (`GET /job/{name}/{number}/artifact/{path}`), uploads it to file-manager, enforces `max_recent_builds` retention, and forwards the result to the bot's callback URL
8. Bot matches `request_id` and sends the download link to the originating Telegram chat

If the poll worker's elapsed time exceeds `build_timeout`, build-manager records a `timeout` completion and notifies the bot's callback URL.

### Security Model

The `BUILD_REQUEST_ID` is a 128-bit random token per build. It correlates the poll worker to the originating Telegram request. Tokens are logged truncated, displayed truncated, and consumed on first use (one-time pop).

---

## Service Control

`config-hub` and `tg-admin-bot` control services via `ServiceClient` in `config-hub`:

```
Client → POST /control/{start|stop|restart} → target service
Client → GET /control/status → target service
Client → GET /control/schema → target service
Client → GET/PUT /control/config → target service (read/write config)
```

The `/control/status` response carries four fields:

| Field | Type | Meaning |
|-------|------|---------|
| `configured` | `bool` | Whether `Settings.load()` succeeds (all required fields present) |
| `running` | `bool` | Whether the managed subprocess/resource is active |
| `last_error` | `str \| null` | Last runtime error from a `start()` attempt |
| `config_error` | `str \| null` | Current config validation error (`null` when configured) |
| `started_at` | `float \| null` | UNIX epoch timestamp of the last successful `start()` (for uptime display) |

If a service is down, its schema returns `null` and the config-hub frontend shows "Loading..." for that tab.

### Scope-to-Service Translation

The config-hub exposes UI scopes that map directly to internal service names. The mapping lives exclusively in `config-hub/manager.py:_SCOPE_TO_SERVICE`:

| UI Scope | Internal Service |
|----------|-----------------|
| `bot` | `bot` |
| `agent` | `agent` |
| `file_manager` | `file_manager` |
| `builds` | `builds` |

Unknown scopes are rejected with HTTP 404 — `save_scope()` raises `ValueError` for any scope not in the map.

Do not move or duplicate this mapping. Do not rename `file-manager` internals to `drive`.

---

## Google Drive OAuth

OAuth is handled by `file-manager` (`/api/auth/*`) via two mechanisms, both proxied through config-hub (`/api/drive/*`):

1. **Browser-redirect flow** — used by the web dashboard (popup callback at `http://<host>:9000/api/drive/oauth/callback`)
2. **Headless code-paste flow** — used by `tg-admin-bot` (no browser available)

Both flows produce the same stored token in file-manager's data volume. The bot never initiates OAuth — it only uploads files after a successful build.

### Key Design Decisions

- **`_pending_flow` is in-memory only** — the OAuth flow object contains PKCE state that can't be serialized. If the service restarts mid-flow, the flow is lost and must be restarted. This is by design.
- **Frontend-only "Connecting" state** — the config-hub popup flow is tracked entirely by the frontend via a `<dialog>` modal. Do NOT add a backend `auth_pending` flag.
- **`OAUTHLIB_INSECURE_TRANSPORT`** — automatically set when the redirect URI uses `http://` (local/Docker development).

---

## Config Transfer

Both `config-hub` and `tg-admin-bot` support symmetric config transfer:

- **Export**: packages all JSON configs + generated `.env` files into a `.tar.gz`
- **Import**: extracts a `.tar.gz`, applies configs to each owning service via `PUT /control/config`, triggers service restarts

Only `.tar.gz` imports are accepted — this prevents partial or inconsistent config states.

OAuth tokens are **not** included in config exports — they are environment-specific and must be re-authorized after import.

---

## Drive File Access

Each uploaded APK is made individually accessible — the Drive **folder** stays private. Key constraints:

- Per-file `anyone/reader` permission, set immediately after upload
- Do NOT set `anyone/reader` on the folder — this would expose the entire build history
- `delete_file()` cleans up both the file and its permissions atomically

---

## Build State Management

Build state is split across two services:

- **build-manager** — maintains the authoritative build registry: in-progress and completed builds, Jenkins job metadata, Drive file links. Owns build completion detection (per-build poll worker `asyncio` tasks), artifact download, and retention enforcement (`max_recent_builds` eviction with Drive file cleanup). The poll worker queries Jenkins at configurable intervals and downloads the artifact directly from the Jenkins archive upon success.
- **tg-bot** — maintains `PendingBuild` records (in-memory only) keyed by `request_id`. Each record maps a `request_id` to a Telegram `chat_id` and `message_id` for inline message editing. These are consumed on callback receipt.

Jenkins owns all raw build metadata (status, duration, branch, commit). The bot queries build-manager for summaries — it never queries Jenkins directly for build info.

---

## BotManager Lifecycle

- Defined in `manager.py`, injected into routes via `ManagerDep` from `dependencies.py`
- Uses an `asyncio.Lock` for safe concurrent start/stop from the control API
- On startup failure, the FastAPI server stays running — the control API remains available for retries
- `BotContext` with injected dependencies is stored in `Application.bot_data`

---

## Async I/O Pattern

Blocking I/O libraries (e.g., `google-api-python-client`) must be wrapped with `asyncio.to_thread()` in async code paths. The established convention is the `_sync` suffix pattern: the blocking implementation is a private `_method_sync()`, and the public async wrapper calls it via `to_thread()`. See `GoogleDriveBackend` for the canonical example (`_load_tokens_sync` → `load_tokens`, `_exchange_callback_sync` → `exchange_callback`, etc.).
