---
trigger: model_decision
description: Build trigger flow, webhook protocol, OAuth implementations, config transfer, async patterns, and service lifecycle.
---

# Communication Flows

Loaded at model discretion when the task involves service-to-service communication, build flows, OAuth, config transfer, or async patterns.

---

## Build Trigger Flow

The bot acts as a thin trigger layer. The full flow:

1. User requests a build via Telegram → bot generates a unique `request_id`
2. Bot POSTs to Jenkins `/buildWithParameters` with `BRANCH`, `BOT_CALLBACK_URL`, `BOT_REQUEST_ID`, `BOT_JOB_ID`
3. Bot stores a `PendingBuild` in memory + persists to JSON for crash recovery
4. Jenkins pipeline runs on the flutter-agent, then POSTs results back to the bot's webhook
5. Bot matches `request_id`, uploads APK to Drive, sends the link to Telegram
6. Bot enforces `max_recent_builds` retention — evicts oldest entries and deletes their Drive files

---

## Webhook Protocol

Jenkins POSTs to `/webhook/build-complete` as multipart form data with two fields:

- **`metadata`**: JSON string with `request_id`, `job_id`, `status`, `commit_hash`, and optionally `logs` (failure only)
- **`artifact`** (optional): the built APK file (success only)

### Security Model

The `request_id` is a 128-bit random token per build. It acts as webhook authentication — only callers who know the exact token can trigger a notification. Tokens are logged truncated, displayed truncated, and consumed on first use (one-time pop).

### Key Design Decisions

- **Validate before writing** — metadata is validated before any artifact is written to disk, preventing disk exhaustion from unauthenticated callers.
- **`json.loads(strict=False)`** — Jenkins pipelines may embed literal control characters in the JSON. The `strict=False` flag is intentional.
- **Failure logs** — the Jenkinsfile captures and forwards build logs. The bot only summarizes (extracts the first meaningful error line) — it never queries Jenkins for logs.

---

## Service Control

Both `stack-manager` and `tg-admin-bot` control services via `ServiceClient` from `stack-manager`:

```
Client → POST /control/{start|stop|restart} → target service
Client → GET /control/status → target service
Client → GET /control/schema → target service (returns fields + infra partitions)
```

If a service is down, its schema returns `null` and the stack-manager frontend shows "Loading..." for that tab.

---

## Google Drive OAuth

OAuth is handled by `DriveOAuth` in `stack-manager` via two mechanisms:

1. **Browser-redirect flow** — used by `stack-manager` (web dashboard with popup callback)
2. **Headless code-paste flow** — used by `tg-admin-bot` (no browser available)

Both flows produce the same `oauth.json` token file on the shared `bot-config` volume. The bot never initiates OAuth — it only reads and refreshes tokens.

### Key Design Decisions

- **`_pending_flow` is in-memory only** — the OAuth flow object contains PKCE state that can't be serialized. If the service restarts mid-flow, the flow is lost and must be restarted. This is by design.
- **Frontend-only "Connecting" state** — the stack-manager popup flow is tracked entirely by the frontend via a `<dialog>` modal. Do NOT add a backend `auth_pending` flag.
- **`OAUTHLIB_INSECURE_TRANSPORT`** — automatically set when the redirect URI uses `http://` (local/Docker development).

---

## Config Transfer

Both `stack-manager` and `tg-admin-bot` support symmetric config transfer via `stack-manager`:

- **Export**: packages all JSON configs + `oauth.json` + generated `.env` files into a `.tar.gz`
- **Import**: extracts a `.tar.gz`, writes configs, triggers automatic service restarts

Only `.tar.gz` imports are accepted — this prevents partial or inconsistent config states.

---

## Drive File Access

Each uploaded APK is made individually public — the Drive **folder** stays private. Key constraints:

- Per-file `anyone/reader` permission, set immediately after upload
- Do NOT set `anyone/reader` on the folder — this would expose the entire build history
- `delete_file()` cleans up both the file and its permissions atomically

---

## Build State Management

The bot maintains two slim registries:

- **Pending builds** — `dict[str, PendingBuild]` with TTL-based expiration and JSON persistence. Each `request_id` is consumed exactly once.
- **Tracked builds** — `list[TrackedBuild]` recording `request_id` + Drive file info. Used to filter Jenkins queries to bot-triggered builds only and to manage Drive file cleanup.

Jenkins owns all build metadata (status, duration, branch, commit). The bot's local state is limited to what it needs for webhook matching and Drive lifecycle.

---

## BotManager Lifecycle

- Uses an `asyncio.Lock` for safe concurrent start/stop from the control API
- On startup failure, the FastAPI server stays running — the control API remains available for retries
- `BotContext` with injected dependencies is stored in `Application.bot_data`

---

## Async I/O Pattern

Blocking I/O libraries (e.g., `google-api-python-client`) must be wrapped with `asyncio.to_thread()` in async code paths. Apply this pattern to any new blocking I/O added to async services.
