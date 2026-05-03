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

The flutter-agent uses `jenkins/inbound-agent:jdk21` as its base image, which lacks Python 3.12. Instead of a separate builder stage, **uv is kept in the runtime image** and handles both Python installation and dependency resolution:

```dockerfile
FROM jenkins/inbound-agent:jdk21
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# agent-control installed via uv directly in the runtime
WORKDIR /app
COPY apps/agent-control/pyproject.toml apps/agent-control/uv.lock ./
COPY apps/agent-control/src ./src
RUN uv sync --frozen --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH"
```

This is an intentional exception — the image already contains ~2GB of Flutter and Android SDKs, so uv's overhead is negligible. The trade-off is worth it for consistent packaging across all apps.

The flutter-agent's Docker Compose build context is the **repo root** (`../..` from `infra/jenkins/`) so the Dockerfile can access `apps/agent-control/`.

---

## Agent Subprocess Management

The `AgentManager` in agent-control wraps the Jenkins inbound agent as a child process:

- `start()` spawns `/usr/local/bin/jenkins-agent` via `subprocess.Popen`
- `stop()` sends `SIGTERM`, waits 5 seconds, then `SIGKILL` if the process hasn't exited
- `status()` uses `process.poll()` to check if the process is still running
