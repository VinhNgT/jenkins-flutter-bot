---
trigger: model_decision
description: Build trigger flow, webhook protocol, OAuth implementations, async patterns, and service lifecycle.
---

# Communication Flows

Loaded at model discretion when the task involves service-to-service communication, build flows, OAuth, or async patterns.

---

## Build Trigger Flow

When a user sends `/build main` to the Telegram bot:

1. Bot generates a unique `request_id` via `secrets.token_hex()`
2. Bot POSTs to Jenkins `/buildWithParameters` with params: `BRANCH`, `BOT_CALLBACK_URL`, `BOT_REQUEST_ID`, `BOT_JOB_ID`
3. Bot stores a `PendingBuild(request_id → chat_id, ref)` in memory + persists to JSON
4. Bot replies "Build triggered" to the Telegram chat

The Jenkins pipeline runs on the flutter-agent. When it finishes:

5. Jenkins POSTs to `tg-bot:9090/webhook/build-complete` (multipart form)
6. Bot matches `request_id` to the pending build, uploads the APK to Google Drive
7. Bot sends the Drive download link to the original Telegram chat
8. Bot records the completed build in history (`data/build_history.json`)
9. Bot enforces `max_recent_builds` — evicts oldest entries and deletes their Drive files if needed

---

## Webhook Multipart Protocol

Jenkins POSTs to `/webhook/build-complete` with two multipart fields:

- **`metadata`**: JSON string containing `request_id`, `job_id`, `status`, `commit_hash`, and optionally `logs` (on failure only). Must be annotated with `Form()` in the FastAPI handler to correctly parse multipart form data.
- **`artifact`** (optional): the built APK file, present only on success

### Metadata JSON Schema

```json
{
  "request_id": "<128-bit hex token>",
  "job_id": "<jenkins job name>",
  "status": "success" | "failure",
  "commit_hash": "<full or short git hash>",
  "logs": "<last N lines of build output>"  // failure only, optional
}
```

The `logs` field is only sent on failure. The bot reads it via `metadata.get("logs", "")` and passes it to `_summarize_logs()` to extract the first meaningful error line for the Telegram notification.

### JSON Parsing — `strict=False`

The metadata JSON is parsed with `json.loads(metadata, strict=False)`. Jenkins pipelines may embed literal control characters (bare newlines, tabs) inside string values — e.g., when log output is inlined into the JSON. The `strict=False` flag allows these without raising a `JSONDecodeError`.

### Security Model

The `request_id` is a 128-bit random token (`secrets.token_hex(16)`) generated per build. It acts as the primary webhook authentication — only callers who know the exact token can trigger a Telegram notification. The token is:
- Logged **truncated** (first 8 chars) to prevent leakage via log aggregation
- Displayed truncated in Telegram messages
- Consumed on first use (one-time pop via `consume_pending()`)

### Validation Order

The handler validates metadata **before** writing any artifact to disk. This prevents disk exhaustion from unauthenticated callers:

1. Parse metadata JSON and extract `request_id`, `job_id`
2. Reject mismatched `job_id` — no file I/O occurs
3. Look up `request_id` in pending builds — reject if not found, no file I/O occurs
4. Only after validation: write artifact to temp file and process
5. Always clean up temporary files regardless of outcome

---

## Build Failure Notifications

When a build fails, the bot sends a Telegram message with a one-line error summary extracted from the `logs` metadata field using `_summarize_logs()`:

```python
def _summarize_logs(logs: str) -> str:
    """Extract the first meaningful error line from raw build logs."""
```

The function iterates through log lines and skips:
- Blank lines
- Lines starting with common boilerplate prefixes: `[INFO]`, `Downloading`, `Download`, `Note:`, `> Task`, `BUILD SUCCESSFUL`, `Picked up`, `Running `, `Starting `, `Cloning `, `Checking out`, `using credential`

The first non-skipped line is returned, capped at 200 characters. If no meaningful line is found, it returns `"No details available."`.

The Jenkinsfile is responsible for capturing and forwarding logs. The bot itself only summarizes — it never queries Jenkins for build logs.

---

## Config UI → Service Communication

The config-ui proxies control commands to services via HTTP:

```
Browser → POST /api/services/bot/restart → config-ui
    → POST http://tg-bot:9090/control/restart → tg-bot
    → Return status to browser
```

This pattern applies to both `bot` and `agent` services with `start`, `stop`, and `restart` actions.

### Schema Fetching

The config-ui fetches field definitions from each module to dynamically render config forms:

```
Browser → GET /api/config/schema → config-ui
    → GET http://tg-bot:9090/control/schema → bot schema
    → GET http://flutter-agent:9091/control/schema → agent schema
    → Merge with local UI schema
    → Return aggregated schemas to browser
```

If a service is down, its schema returns `null` and the frontend shows "Loading..." for that tab.

---

## Google Drive OAuth

OAuth is handled exclusively by config-ui via a **browser-redirect flow**. The bot never initiates OAuth — it only reads tokens from the shared volume.

### Flow

1. Admin clicks "Connect Google Drive" in the config-ui dashboard
2. Config-ui's `DriveOAuthManager.start()` generates a consent URL with `/api/drive/oauth/callback` as the `redirect_uri`
3. A popup window opens (`window.open()` — **without `noopener`**, so the callback page can reach `window.opener`)
4. Admin authorizes in the popup → Google redirects back to config-ui's callback
5. Config-ui exchanges the authorization response for tokens via `exchange_callback()`
6. Tokens are saved to `oauth.json` on the shared `bot-config` volume
7. The callback page uses `window.opener.postMessage()` to signal the dashboard that auth completed, then auto-closes

### Frontend "Connecting" State

The "Connecting" state is managed **entirely by the frontend** — there is no `auth_pending` backend flag. The dashboard shows a `<dialog>` modal (spinner + Cancel button) that:
- Opens before `window.open()` so the user always sees it first
- Polls `popup.closed` at 500ms intervals with an `oauthCompleted` guard flag to avoid race conditions
- Closes automatically when the popup closes (either from success, Cancel button, or user closing the tab)
- Suppresses the Escape key (`cancel` event `preventDefault()`) to prevent accidental dismissal

Do NOT add a backend `auth_pending` property to `DriveOAuthManager` — the design intentionally keeps this state in the frontend only.

### Token Consumption

The bot's `DriveUploader` only reads tokens — it calls `load_tokens()` to load credentials from `oauth.json`, refreshing the access token if expired. It never creates or exchanges OAuth flows.

### `_pending_flow` Statefulness

Config-ui stores the in-progress OAuth flow object in memory as `_pending_flow`. This object contains PKCE state that can't be serialized. If config-ui restarts between `start()` and `exchange_callback()`, the flow is lost and must be restarted from the dashboard. This is by design.

### HTTP Development

`DriveOAuthManager._allow_insecure_transport()` automatically sets `OAUTHLIB_INSECURE_TRANSPORT=1` when the redirect URI uses `http://`. No manual environment configuration is needed for local/Docker development.

---

## Google Drive File Access

Each uploaded APK is made individually public by calling `permissions().create()` on the **file** (not the folder) with `{"type": "anyone", "role": "reader"}` immediately after upload:

- The Drive folder itself is **private** — it cannot be browsed by someone who finds a single download link
- Each file gets its own unique, random 33-character file ID — effectively unguessable
- The `webViewLink` returned by the upload API is the canonical download link sent to Telegram
- `delete_file()` cleans up both the file and its permissions atomically

Do NOT set `anyone/reader` on the folder — this would expose the entire build history to anyone with the folder link.

---

## Pending Build Tracking

The bot tracks builds it triggered using an in-memory dict with JSON persistence:

- Stored as `dict[str, PendingBuild]` in `BotContext`
- Persisted to `data/pending_builds.json` for crash recovery
- TTL-based expiration (1 hour) via `_cleanup_expired()`
- `consume_pending()` is a pop — each `request_id` is consumed exactly once

---

## Tracked Build Registry

After a webhook completes (success or failure), the bot records a slim `TrackedBuild` entry:

- Stored as `list[TrackedBuild]` in `BotContext`
- Persisted to `data/tracked_builds.json` for crash recovery
- Each entry tracks only: `request_id`, `drive_file_id`, `drive_link`
- Used to filter Jenkins queries (match `BOT_REQUEST_ID`) and manage Drive file cleanup
- Jenkins owns all build metadata (status, duration, branch, commit)

---

## Jenkins Build Queries

The bot queries Jenkins REST API for live build details, strictly filtered to its own triggered builds:

- `JenkinsClient.get_builds(count)` fetches recent builds with parameters via `GET /job/{name}/api/json?tree=builds[...]`
- `BotContext.get_recent_builds()` filters Jenkins results by matching `BOT_REQUEST_ID` against the local `TrackedBuild` registry
- `BotContext.get_active_builds()` returns only currently-building bot-triggered builds
- Drive download links are merged from local `TrackedBuild` records (Jenkins doesn't know about Drive)
- No Jenkins build numbers, non-bot build counts, or other metadata from manual triggers are ever exposed to Telegram

---

## Drive File Cleanup

When `max_recent_builds > 0`, the bot enforces a Drive file retention limit after each successful build:

1. After `track_build()`, `enforce_drive_limit()` is called
2. If the tracked list exceeds the limit, oldest entries are evicted
3. Drive files for evicted builds are deleted (best-effort via `DriveUploader.delete_file()`)
4. Errors during deletion are logged but never propagated — user notification is never blocked

## BotManager Lifecycle

The `BotManager` class owns the Telegram `Application` lifecycle:

- Uses an `asyncio.Lock` for safe concurrent start/stop from the control API
- Builds a `BotContext` with injected dependencies (`JenkinsClient`, `DriveUploader`)
- Stores `BotContext` in `Application.bot_data` so handlers can access it
- On startup failure, the FastAPI server stays running — the control API remains available for retries

---

## Async I/O Pattern

The Google Drive API client library is synchronous. All Drive operations are wrapped with `asyncio.to_thread()` to avoid blocking the FastAPI event loop:

```python
async def upload_file(self, ...) -> tuple[str, str]:
    return await asyncio.to_thread(self._upload_file_sync, ...)
```

Apply this same pattern to any new blocking I/O added to async services.
