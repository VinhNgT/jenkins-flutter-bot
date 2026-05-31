---
trigger: model_decision
description: Build triggers, status polling streams, Google Drive OAuth flow, and async execution paradigms.
---

# Communication Flows

Triggered when developing cross-service messaging, webhook systems, or async integration pipelines.

---

## 1. Unified Build Trigger Pipeline
The Telegram build trigger acts as a highly decoupled state machine:
- **Trigger**: The whitelisted Telegram client transmits a trigger request containing branch and identifier metadata to `tg-jenkins-bot`.
- **Delegation**: The bot registers the active build in-memory and triggers the `build-manager` orchestrator.
- **VPN Execution & Poll**: `build-manager` brings up an isolated VPN connection via `agent-control`, schedules the parameterized pipeline build in Jenkins, and active-polls for completion.
- **Upload & Delivery**: Once complete, the orchestrator transfers the archived APK to `file-manager` for secure Google Drive storage, evicts old builds per retention plans, and posts an immutable download card to the chat.

---

## 2. Real-Time Service Status Streaming (SSE)
- **Aggregated SSE Stream**: Status signals (configured status, running state, and startup uptime stamps) from all Python microservices are proxied to `config-hub`.
- **MD5-Based Hashing Filters**: To avoid client re-rendering and optimize network traffic, the SSE server aggregates, serializes, and hashes status payloads using MD5. It transmits events down the socket solely when state changes occur.

---

## 3. Google Drive OAuth Callback
- **PKCE Flow States**: OAuth authorization states are held strictly in-memory by `file-manager` to minimize token leakage.
- **Dual-Flow Redirects**: Handled via browser callbacks or headless copy-paste entries.
- **Authentication Exemption Boundary**: The Caddy gateway must bypass authentication checks for the OAuth redirect callback path. This ensures accounts.google.com can successfully redirect browser context without credential stripping.

---

## 4. Concurrency & Async thread Executors
- **Asyncio Locking**: `BotManager` lifespans and startup/shutdown routines must synchronize using an `asyncio.Lock` to guarantee thread-safe status transitions.
- **Async wrappers for Blocking SDKs**: Heavily blocking external code blocks (like Google API SDKs) must be executed in a separate thread context using `asyncio.to_thread()`, wrapped inside clean async public facades.
