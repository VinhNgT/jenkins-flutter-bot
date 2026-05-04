---
trigger: glob
globs: **/Dockerfile*, **/docker-compose.yml
description: Docker volumes, networking, multi-stage build patterns, and agent Dockerfile specifics.
---

# Docker & Infrastructure

Triggered when editing Dockerfiles or docker-compose.yml. Covers volumes, networking, image build patterns, and the flutter-agent's uv exception.

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

## Docker Build Patterns

### tg-jenkins-bot and config-ui

Both follow the same two-stage pattern:

```dockerfile
# Stage 1: uv builder
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# Stage 2: slim runtime (no uv, no build tools)
FROM python:3.12-slim
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["<project-scripts-entry>"]
```

Key points:
- `uv sync --frozen` uses the lockfile for reproducible installs
- `--no-dev` excludes mypy, ruff, etc.
- `--no-editable` installs the package properly (not as an editable link)
- The final image has no `uv`, no build caches, no dev deps

### flutter-agent (Exception)

The flutter-agent uses a **two-stage build**: Stage 1 (`sdk-builder`) downloads Android and Flutter SDKs; Stage 2 copies the pre-built SDKs into a clean runtime image with `COPY --chown` to avoid duplicating multi-GB layers.

Key conventions:

- **`COPY --chown`** instead of `RUN chown -R` — prevents massive intermediate layer duplication
- **uv is kept in runtime** — the base image (`jenkins/inbound-agent:jdk21`) lacks Python 3.12, so uv manages both Python installation (`UV_PYTHON_INSTALL_DIR=/opt/uv-python`) and dependencies
- **`platform: linux/amd64`** is set in docker-compose — Flutter does not support Android release builds on Linux ARM64; x86_64 emulation is required on Apple Silicon hosts
- **Gradle memory tuning** via `GRADLE_OPTS` — daemon disabled, JVM heap capped, VFS watching disabled. See the Dockerfile comments for rationale.

The flutter-agent's Docker Compose build context is the **repo root** (`../..` from `infra/jenkins/`) so the Dockerfile can access `apps/agent-control/`.

---

## Agent Subprocess Management

The `AgentManager` in agent-control wraps the Jenkins inbound agent as a child process:

- `start()` spawns `/usr/local/bin/jenkins-agent` via `subprocess.Popen`
- `stop()` sends `SIGTERM`, waits 5 seconds, then `SIGKILL` if the process hasn't exited
- `status()` uses `process.poll()` to check if the process is still running
- `start()` passes a **filtered environment** to the subprocess — only `JENKINS_URL`, `JENKINS_AGENT_NAME`, `JENKINS_SECRET`, `JENKINS_WEB_SOCKET`, and `JENKINS_TUNNEL` are forwarded, preventing duplicate CLI arguments from the entrypoint script
