---
trigger: glob
globs: **/Dockerfile*, **/docker-compose*.yml, **/compose.sh
description: Docker volumes, networking, multi-stage build patterns, agent Dockerfile specifics, and CI/CD image pipeline.
---

# Docker & Infrastructure

Triggered when editing Dockerfiles, docker-compose files, or compose.sh. Covers volumes, networking, image build patterns, the flutter-agent's uv exception, and the CI/CD image release pipeline.

---

## Volumes

| Volume | Purpose | Mounted In |
|--------|---------|------------|
| `jenkins-data` | Jenkins home directory | `jenkins` |
| `bot-config` | Shared bot config + OAuth tokens | `config-ui`, `tg-bot` |
| `agent-config` | Agent configuration JSON | `config-ui`, `flutter-agent` |
| `ui-config` | UI configuration (Drive OAuth creds) | `config-ui` |
| `bot-data` | Runtime data (pending builds) | `tg-bot` |

---

## Network

All services share a single Docker bridge network (`jenkins`). Only two ports are exposed to the host:

| Port | Service | Host Exposure | Purpose |
|------|---------|---------------|---------|
| 8080 | jenkins | Exposed | Jenkins web UI |
| 9000 | config-ui | Exposed | Config dashboard + Drive OAuth callback |
| 9090 | tg-bot | Internal only | Webhook receiver + control API |
| 9091 | flutter-agent | Internal only | Agent control API |

Do not expose bot or agent ports to the host.

---

## Dev vs Production Compose

Two compose modes are provided via `compose.sh` in `infra/`:

```bash
./compose.sh [args]          # Dev — builds images locally from source
./compose.sh prod [args]     # Prod — pulls pre-built images from GHCR
```

**Dev mode** (`docker-compose.yml` only):
- Builds all images from local source on every `--build`
- Use for active development and testing changes

**Production mode** (`docker-compose.yml` + `docker-compose.prod.yml`):
- The prod override sets `build: null` and points each service to a GHCR image
- Images are pulled from `ghcr.io/vinhngt/jenkins-flutter-bot/<name>:<tag>`
- Defaults to `latest`; pin a release with `IMAGE_TAG=v1.2.3 ./compose.sh prod up -d`
- The `jenkins` service has **no** prod override — it's a dev/testing convenience only. Remove it from the stack for production deployments pointing at an external Jenkins.

`IMAGE_TAG` is a compose-invocation variable only — it is not set inside any container.

---

## CI/CD Image Pipeline

Defined in `.github/workflows/build-images.yml`. Triggers on version tags matching `v*.*.*`.

Three images are built and pushed to GHCR:

| Image | Platforms | Registry Path |
|-------|-----------|---------------|
| `tg-bot` | `linux/amd64`, `linux/arm64` | `ghcr.io/vinhngt/jenkins-flutter-bot/tg-bot` |
| `config-ui` | `linux/amd64`, `linux/arm64` | `ghcr.io/vinhngt/jenkins-flutter-bot/config-ui` |
| `flutter-agent` | `linux/amd64` only | `ghcr.io/vinhngt/jenkins-flutter-bot/flutter-agent` |

Each image is tagged with both the exact version (e.g., `v1.2.3`) and `latest`.

`flutter-agent` is `linux/amd64` only — Flutter does not support Android release builds on Linux ARM64.

**To release a new version:** push a `v*.*.*` tag. GitHub Actions handles the rest.

```bash
git tag v1.2.3
git push origin v1.2.3
```

---

## Docker Build Patterns

### tg-jenkins-bot and config-ui

Both follow the same two-stage pattern. Build context is the **repo root** for all services (required to access the shared `libs/config-schema/` library):

```dockerfile
# Stage 1: uv builder
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs/config-schema/pyproject.toml libs/config-schema/
COPY libs/config-schema/src libs/config-schema/src
COPY apps/<app-name>/pyproject.toml apps/<app-name>/
COPY apps/<app-name>/src apps/<app-name>/src
RUN uv sync --frozen --no-dev --no-editable --package <package-name>

# Stage 2: slim runtime (no uv, no build tools)
FROM python:3.12-slim
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
CMD ["<project-scripts-entry>"]
```

Key points:
- `uv sync --frozen` uses the lockfile for reproducible installs
- `--package <name>` installs only the target app + its workspace dependencies
- `--no-dev` excludes mypy, ruff, etc.
- `--no-editable` installs the package properly (not as an editable link)
- The final image has no `uv`, no build caches, no dev deps
- `.dockerignore` at repo root excludes `.git/`, `.venv/`, `__pycache__/`, etc.

### flutter-agent (Exception)

The flutter-agent uses a **two-stage build**: Stage 1 (`sdk-builder`) downloads Android and Flutter SDKs; Stage 2 copies the pre-built SDKs into a clean runtime image with `COPY --chown` to avoid duplicating multi-GB layers.

Key conventions:

- **`COPY --chown`** instead of `RUN chown -R` — prevents massive intermediate layer duplication
- **uv is kept in runtime** — the base image (`jenkins/inbound-agent:jdk21`) lacks Python 3.12, so uv manages both Python installation (`UV_PYTHON_INSTALL_DIR=/opt/uv-python`) and dependencies
- **`platform: linux/amd64`** is set in docker-compose — Flutter does not support Android release builds on Linux ARM64; x86_64 emulation is required on Apple Silicon hosts
- **Gradle memory tuning** via `GRADLE_OPTS` — daemon disabled, JVM heap capped, VFS watching disabled. See the Dockerfile comments for rationale.

The flutter-agent's Docker Compose build context is the **repo root** (`..` from `infra/`) — same as all other services, since all need access to the workspace root and shared library.

---

## Agent Subprocess Management

The `AgentManager` in agent-control wraps the Jenkins inbound agent as a child process:

- `start()` spawns `/usr/local/bin/jenkins-agent` via `subprocess.Popen`
- `stop()` sends `SIGTERM`, waits 5 seconds, then `SIGKILL` if the process hasn't exited
- `status()` uses `process.poll()` to check if the process is still running
- `start()` passes a **filtered environment** to the subprocess — only `JENKINS_URL`, `JENKINS_AGENT_NAME`, `JENKINS_SECRET`, `JENKINS_WEB_SOCKET`, and `JENKINS_TUNNEL` are forwarded, preventing duplicate CLI arguments from the entrypoint script
