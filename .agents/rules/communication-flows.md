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

---

## Webhook Multipart Protocol

Jenkins POSTs to `/webhook/build-complete` with two multipart fields:

- **`metadata`**: JSON string containing `request_id`, `job_id`, `status`, `commit_hash`, etc.
- **`artifact`** (optional): the built APK file, present only on success

The webhook handler:
1. Validates `job_id` matches the bot's configured job — rejects mismatches
2. Looks up `request_id` in pending builds — `consume_pending()` is a pop (one-time use)
3. On match: uploads artifact to Drive, notifies Telegram
4. On no match: returns `{"status": "ignored"}` (the build wasn't triggered by this bot)
5. Always cleans up temporary artifact files regardless of outcome

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

---

## Pending Build Tracking

The bot tracks builds it triggered using an in-memory dict with JSON persistence:

- Stored as `dict[str, PendingBuild]` in `BotContext`
- Persisted to `data/pending_builds.json` for crash recovery
- TTL-based expiration (1 hour) via `_cleanup_expired()`
- `consume_pending()` is a pop — each `request_id` is consumed exactly once

---

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
