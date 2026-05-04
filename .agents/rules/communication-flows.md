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

- **`metadata`**: JSON string containing `request_id`, `job_id`, `status`, `commit_hash`, etc. Must be annotated with `Form()` in the FastAPI handler to correctly parse multipart form data.
- **`artifact`** (optional): the built APK file, present only on success

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

## Config UI → Service Control

The config-ui proxies control commands to services via HTTP:

```
Browser → POST /api/services/bot/restart → config-ui
    → POST http://tg-bot:9090/control/restart → tg-bot
    → Return status to browser
```

This pattern applies to both `bot` and `agent` services with `start`, `stop`, and `restart` actions.

---

## Google Drive OAuth

OAuth is handled exclusively by config-ui via a **browser-redirect flow**. The bot never initiates OAuth — it only reads tokens from the shared volume.

### Flow

1. Admin clicks "Connect Google Drive" in the config-ui dashboard
2. Config-ui's `DriveOAuthManager.start()` generates a consent URL with `/api/drive/oauth/callback` as the `redirect_uri`
3. Admin authorizes in a popup window → Google redirects back to config-ui's callback
4. Config-ui exchanges the authorization response for tokens via `exchange_callback()`
5. Tokens are saved to `oauth.json` on the shared `bot-config` volume
6. The callback page uses `window.opener.postMessage()` to signal the dashboard that auth completed, then auto-closes

### Token Consumption

The bot's `DriveUploader` only reads tokens — it calls `load_tokens()` to load credentials from `oauth.json`, refreshing the access token if expired. It never creates or exchanges OAuth flows.

### `_pending_flow` Statefulness

Config-ui stores the in-progress OAuth flow object in memory as `_pending_flow`. This object contains PKCE state that can't be serialized. If config-ui restarts between `start()` and `exchange_callback()`, the flow is lost and must be restarted from the dashboard. This is by design.

### HTTP Development

`DriveOAuthManager._allow_insecure_transport()` automatically sets `OAUTHLIB_INSECURE_TRANSPORT=1` when the redirect URI uses `http://`. No manual environment configuration is needed for local/Docker development.

---

## Pending Build Tracking

The bot tracks builds it triggered using an in-memory dict with JSON persistence:

- Stored as `dict[str, PendingBuild]` in `BotContext`
- Persisted to `data/pending_builds.json` for crash recovery
- TTL-based expiration (1 hour) via `_cleanup_expired()`
- `consume_pending()` is a pop — each `request_id` is consumed exactly once

---

## Build History Tracking

After a successful build upload and Telegram notification, the bot records a `CompletedBuild` entry:

- Stored as `list[CompletedBuild]` in `BotContext`
- Persisted to `data/build_history.json` for crash recovery
- Each entry tracks: `drive_file_id`, `drive_link`, `filename`, `ref`, `completed_at`
- Powers the `/recent` command (bot-scoped — only shows Telegram-triggered builds)

---

## Build History Cleanup

When `max_recent_builds > 0`, the bot enforces a retention limit after each successful build:

1. After `record_build()`, `enforce_history_limit()` is called
2. If history exceeds the limit, oldest entries are evicted
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
