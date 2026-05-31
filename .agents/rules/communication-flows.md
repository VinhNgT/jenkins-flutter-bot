---
trigger: model_decision
description: Build triggers, status polling streams, Google Drive OAuth flow, and async execution paradigms.
---

# Communication Flows

Triggered when developing cross-service messaging, webhook systems, or async integration pipelines.

---

## 1. Unified Build Trigger Pipeline
The Telegram build trigger acts as a highly decoupled state machine:
- **Trigger**: The whitelisted Telegram client transmits a trigger request containing branch and identifier metadata to `tg-bot`.
- **Delegation**: The bot validates the request and forwards the build trigger to `build-manager`, which tracks active builds persistently, manages duplicate validation, and publishes real-time state mutations.
- **VPN Execution & Poll**: `build-manager` brings up an isolated VPN connection via `agent-control`, schedules the parameterized pipeline build in Jenkins, and active-polls for completion.
- **Upload & Delivery**: Once complete, `build-manager` transfers the compiled APK and metadata record to `file-manager`. The `build-manager` operates statelessly with zero concern or knowledge of how files are handled, stored, or authenticated. The `file-manager` service itself handles storage, manages Google Drive OAuth credentials, and enforces old build retention policies, returning download urls to notify the bot.

---

## 2. Real-Time Service Status & Build Streaming (SSE)
- **Aggregated Service Status Stream**: Operational status signals (configured status, running state, and startup uptime stamps) from all Python microservices are proxied to `service-hub` and hashed using MD5. Events are transmitted only when the aggregated state changes.
- **Aggregated Build Status Stream**: The persistent source of truth for all build states is maintained in `build-manager`, which streams active and recently completed builds via Server-Sent Events (SSE). The `tg-bot` gateway hosts a stateless, secure proxy endpoint (`GET /api/webapp/stream`) that streams these real-time events to the Telegram client, replacing REST polling.
- **SHA-256 Deduplication Hashing**: To optimize bandwidth and avoid client re-renders, the build SSE server aggregates, serializes, and hashes build payloads using SHA-256, transmitting events down the socket solely when a state mutation occurs.

---

## 3. Google Drive OAuth Callback
- **PKCE Flow States**: OAuth authorization states are held strictly in-memory by `file-manager` to minimize token leakage.
- **Dual-Flow Redirects**: Handled via browser callbacks or headless copy-paste entries.
- **Authentication Exemption Boundary**: The Caddy gateway must bypass authentication checks for the OAuth redirect callback path. This ensures accounts.google.com can successfully redirect browser context without credential stripping.

---

## 4. Concurrency & Async thread Executors
- **Asyncio Locking**: `BotManager` lifespans and startup/shutdown routines must synchronize using an `asyncio.Lock` to guarantee thread-safe status transitions.
- **Async wrappers for Blocking SDKs**: Heavily blocking external code blocks (like Google API SDKs) must be executed in a separate thread context using `asyncio.to_thread()`, wrapped inside clean async public facades.
