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

- **`bot-config`** is mounted in both `stack-manager` and `tg-bot` at the same path (`/config/bot/`) so `oauth.json` is accessible from both containers. `tg-admin-bot` also mounts it.
- **`drive-config`** holds Drive OAuth client credentials (`drive.json`) — separate from bot config because Drive credentials are managed by `stack-manager` / `tg-admin-bot`, not by the bot itself.
- **`bot-data`** holds runtime state (pending builds, build history) — only mounted in `tg-bot`.
- Jenkins home data stays in its own volume, decoupled from all other services.

---

## Network

All services share a single Docker bridge network. Only two ports are exposed to the host:

- **`jenkins:8080`** — Jenkins web UI
- **`stack-manager:9000`** — Config dashboard + Drive OAuth callback

Bot (`9090`) and agent (`9091`) ports are internal only. `tg-admin-bot` has no HTTP server.

Do not expose bot or agent ports to the host.

---

## Per-Service Environment Files

Services consume optional per-service `.env` files via Compose `env_file:` with `required: false` (Compose v2.24+). These live in `infra/env/`.

Template files (`*.env.example`) are auto-generated from schemas via `scripts/gen_env_examples.py`. Regenerate after schema changes.

The `tg-admin-bot` uses `ADMIN_BOT_TOKEN` and `ADMIN_CHAT_ID` via `${VAR:-}` interpolation in `docker-compose.yml`, sourced from `infra/.env`.

---

## Dev vs Production Compose

Two compose modes via `compose.sh`:

```bash
./compose.sh [args]          # Dev — builds images locally from source
./compose.sh prod [args]     # Prod — pulls pre-built images from GHCR
```

**Production mode** overlays `docker-compose.prod.yml`, which replaces `build:` with `image:` pointing to GHCR. Pin a release with `IMAGE_TAG=v1.2.3 ./compose.sh prod up -d`.

The `jenkins` service has **no** prod override — it's a dev/testing convenience only. In production, point `JENKINS_URL` to an external Jenkins and remove the service.

---

## CI/CD Image Pipeline

Defined in `.github/workflows/build-images.yml`. Triggers on `v*.*.*` tags.

All apps are built and pushed to GHCR with both the exact version tag and `latest`. The `flutter-agent` is `linux/amd64` only — Flutter does not support Android release builds on Linux ARM64.

**To release:** `git tag v1.2.3 && git push origin v1.2.3`.

---

## Docker Build Patterns

### Standard Apps (tg-bot, stack-manager, tg-admin-bot)

All follow a **two-stage pattern**: uv builder → slim runtime. Key conventions:

- Build context is the **repo root** (required to access `libs/`)
- `uv sync --frozen --no-dev --no-editable --package <name>` installs only the target app + transitive workspace dependencies
- The final image has no `uv`, no build caches, no dev deps
- The `[project.scripts]` entry in each app's `pyproject.toml` is the Docker `CMD`

### flutter-agent (Exception)

Two-stage build with fundamentally different concerns: Stage 1 downloads multi-GB Android/Flutter SDKs; Stage 2 copies them into the runtime image.

Key conventions and the *why*:

- **`COPY --chown`** instead of `RUN chown -R` — prevents massive intermediate layer duplication when transferring multi-GB SDK directories
- **uv is kept in runtime** — the base image (`jenkins/inbound-agent`) lacks Python 3.12, so uv manages both Python installation and dependencies
- **`platform: linux/amd64`** in docker-compose — Flutter does not support Android release builds on Linux ARM64; x86_64 emulation is required on Apple Silicon hosts
- **Gradle memory tuning** — daemon disabled, JVM heap capped. See the Dockerfile comments for rationale.

---

## Agent Subprocess Management

The `AgentManager` wraps the Jenkins inbound agent as a child process:

- **Filtered environment** — only Jenkins-specific vars (`JENKINS_URL`, `JENKINS_AGENT_NAME`, `JENKINS_SECRET`, `JENKINS_WEB_SOCKET`, `JENKINS_TUNNEL`) are forwarded to the subprocess. This prevents the entrypoint script from receiving duplicate arguments via other env vars.
- **Graceful shutdown** — `SIGTERM` first, wait 5 seconds, then `SIGKILL`.
- **On failure, the FastAPI server stays running** — the control API remains available for retries.
