---
trigger: glob
globs: **/Dockerfile*, **/docker-compose*.yml, **/compose.sh, **/env/*.env*
description: Docker volumes, networking, build patterns, env file system, and CI/CD image pipeline.
---

# Docker & Infrastructure

Triggered when editing Dockerfiles, docker-compose files, compose.sh, or env files.

---

## Volumes

For the authoritative volume list, see `docker-compose.yml`. Key design decisions:

- Each service has its own isolated data volume — no volumes are shared between services.
- **`bot-data`** holds `tg-jenkins-bot` JSON config (interaction states are transient and held strictly in-memory).
- **`agent-data`** holds the `agent-control` JSON config.
- **`build-manager-data`** holds `build-manager` JSON config (pending builds are tracked in-memory only).
- **`storage-data`** holds Drive OAuth tokens, `build_log.json` (completed build records), and `file-manager` JSON config.
- **`jenkins-data`** holds Jenkins home — decoupled from all other services.
- **`mock-agent-data`** (mock mode only) holds the agent JSON config used by the mock `agent-control` server.
- Config crosses service boundaries via HTTP (`/control/config`), not via shared mounts.

---

## Network

All services share a single Docker bridge network. Only two ports are exposed to the host:

- **`jenkins:8080`** — Jenkins web UI (for local development)
- **`gateway:80`** — Caddy Ingress Gateway (mapped to `8880:80` in dev since port 80 requires root)

Bot (`tg-jenkins-bot` on `9090`), agent control (`agent-control` on `9091`), file-manager (`9092`), build-manager (`9010`), and config-hub (`9000`) ports are internal only. No service is exposed to the host directly except through the gateway.

The **Caddy Ingress Gateway** (`gateway` service) provides a unified routing perimeter on a single port. Path-based routing separates the two web apps: `/webapp*` routes to the bot, `/webapp-admin*` routes to config-hub. The gateway strips `Authorization` headers from non-LAN IPs on admin paths, preventing Basic Auth from working over the public internet while preserving Telegram `initData` auth (which uses a different header). Rate-limiting is applied to public endpoints. A **Cloudflare Tunnel** (`cloudflared` service) interfaces directly with `gateway:80` to expose endpoints over HTTPS.

Do not expose bot, agent-control, file-manager, or build-manager ports to the host.

---

## Per-Service Environment Files

Services consume optional per-service `.env` files via Compose `env_file:` with `required: false` (Compose v2.24+). These live in `infra/env/`.

Template files (`*.env.example`) are auto-generated from schemas via `scripts/gen_env_examples.py`. Regenerate after schema changes.

---

## Dev vs Production Compose

All Docker Compose configurations are organized into individual directories under `infra/` representing their respective environments. The `infra/compose.sh` script acts as a runner, automatically forwarding commands to the correct subdirectory using the `-f` flag (and optionally passing an `.env` file if it exists at `infra/.env`).

Five compose modes/directories are supported:

```bash
./compose.sh [args]          # Dev — runs from infra/docker-compose.yml (builds images locally from source)
./compose.sh prod [args]     # Prod — runs from infra/docker-compose.prod.yml (pulls stable images from GHCR)
./compose.sh hybrid [args]   # Hybrid — runs from infra/docker-compose.hybrid.yml (builds apps locally, pulls agent-control from GHCR)
./compose.sh mock [args]     # Mock — runs from infra/docker-compose.mock.yml (replaces agent-control & jenkins with mock-jenkins)
```

**Production mode** runs `infra/docker-compose.prod.yml`, which pulls images from GHCR. Pin a release with `IMAGE_TAG=v1.2.3 ./compose.sh prod up -d`.

**Hybrid mode** runs `infra/docker-compose.hybrid.yml`, building all five Python applications locally while pulling the heavy `agent-control` image from GHCR to save compile time.

**Mock mode** runs `infra/docker-compose.mock.yml`, replacing Jenkins and Agent Control with the lightweight `mock-jenkins` service for offline development and testing.

The `jenkins` service has **no** prod configuration — it's a dev/testing convenience only. In production, point `JENKINS_URL` to an external Jenkins and remove the local container.

---

## CI/CD Image Pipeline

Defined in `.github/workflows/build-images.yml`. Triggers on `v*.*.*` tags.

All apps are built and pushed to GHCR with both the exact version tag and `latest`. The `agent-control` (under `infra/agent/Dockerfile`) is `linux/amd64` only — Flutter does not support Android release builds on Linux ARM64.

**To release:** `git tag v1.2.3 && git push origin v1.2.3`.

---

## Docker Build Patterns

### Standard Apps (tg-jenkins-bot, config-hub, build-manager, file-manager, agent-control)

All follow a **two-stage pattern**: uv builder → slim runtime. Key conventions:

- Build context is the **repo root** (required to access `libs/`)
- `uv sync --frozen --no-dev --no-editable --package <name>` installs only the target app + transitive workspace dependencies
- The final image has no `uv`, no build caches, no dev deps
- The `[project.scripts]` entry in each app's `pyproject.toml` is the Docker `CMD`

### agent-control (Exception)

Two-stage build with fundamentally different concerns (using `infra/agent/Dockerfile` context): Stage 1 downloads multi-GB Android/Flutter SDKs; Stage 2 copies them into the runtime image.

Key conventions and the *why*:

- **`COPY --chown`** instead of `RUN chown -R` — prevents massive intermediate layer duplication when transferring multi-GB SDK directories
- **uv is kept in runtime** — the base image (`jenkins/inbound-agent`) lacks Python 3.12, so uv manages both Python installation and dependencies
- **`platform: linux/amd64`** in docker-compose — Flutter does not support Android release builds on Linux ARM64; x86_64 emulation is required on Apple Silicon hosts
- **Gradle memory tuning** — daemon disabled, JVM heap capped. See the Dockerfile comments for rationale.
- **OpenVPN Support** — the container requires the `NET_ADMIN` capability and access to the `/dev/net/tun` device to manage VPN connections.

### mock-jenkins (Dev Only)

A single container running two FastAPI servers:

- **Port 8080** — mock Jenkins API (build trigger, status)
- **Port 9091** — mock agent-control API (mirrors real `agent-control` `/control/*` endpoints)

The mock agent-control server uses the **real** `AgentSettings` schema from `agent-control` (not a hardcoded copy), so the schema served to config-hub is always in sync. Config is persisted to the `mock-agent-data` volume. Start/restart validate the config and fail if the agent secret is missing — matching real agent-control behaviour.

Exists only in `infra/docker-compose.mock.yml`. Never appears in prod or dev compose files.

---

## Agent Subprocess Management

The `AgentManager` wraps the Jenkins inbound agent as a child process:

- **Filtered environment** — only Jenkins-specific vars (`JENKINS_URL`, `JENKINS_AGENT_NAME`, `JENKINS_SECRET`, `JENKINS_WEB_SOCKET`, `JENKINS_TUNNEL`) are forwarded to the subprocess. This prevents the entrypoint script from receiving duplicate arguments via other env vars.
- **Graceful shutdown** — `SIGTERM` first, wait 5 seconds, then `SIGKILL`.
- **On failure, the FastAPI server stays running** — the control API remains available for retries.
