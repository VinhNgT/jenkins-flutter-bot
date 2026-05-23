---
trigger: always_on
description: Core architectural reference — project identity, repo layout, service topology, and hard constraints.
---

# Jenkins Flutter Bot — AI Agent Guide

This is the core architectural reference for the **jenkins-flutter-bot** monorepo, which implements a microservice architecture. It loads on every interaction. For detailed guidance on specific topics, see the companion rule files.

---

## What This Project Is

A self-hosted microservice CI/CD ecosystem: a Telegram bot triggers Flutter builds on Jenkins and delivers APKs through Google Drive. Six containerized microservices coordinate over an internal Docker network.

**It is NOT a build system.** It is a thin orchestration layer around Jenkins. All cloning, compiling, and artifact packaging is delegated to a Jenkins pipeline running on a Flutter-capable agent.

---

## Repository Layout

The monorepo uses a **uv workspace** to manage its microservices, with two top-level directories for code:

- **`apps/`** — Six deployable Python applications, each with a Dockerfile, `pyproject.toml`, and `src/<package>/` layout.
- **`libs/`** — One shared workspace library consumed by the apps.
- **`infra/`** — Docker Compose files, Dockerfiles, and per-service environment file templates.
- **`scripts/`** — Developer utilities (env example generation, version tagging).

### Apps

| Directory | Package | Role |
|-----------|---------|------|
| `tg-jenkins-bot` | `tg_jenkins_bot` | Telegram bot — slash commands, webhook callback, notification rendering |
| `config-hub` | `config_hub` | Central operational hub — config proxy, service control, web dashboard |
| `build-manager` | `build_manager` | Build orchestration — Jenkins trigger, job/state tracking |
| `file-manager` | `file_manager` | Storage backend — Google Drive OAuth, APK upload/download |
| `agent-control` | `agent_control` | HTTP control wrapper for the Jenkins agent subprocess |
| `mock-jenkins` | `mock_jenkins` | Dev/test mock — simulates Jenkins + agent-control APIs |

### Libs

| Directory | Package | Role |
|-----------|---------|------|
| `config-core` | `config_core` | `BootstrapSettings` / `ServiceSettings` Pydantic bases, `get_frontend_schema()`, shared config I/O helpers |

### Naming Conventions

- **Directory names**: `kebab-case` (e.g., `tg-jenkins-bot`, `config-hub`).
- **Python packages**: `snake_case` matching the directory name (e.g., `tg_jenkins_bot`, `config_hub`).
- **Source layout**: All apps and libraries use PyPA `src` layout — code lives under `src/<package_name>/`.

---

## Architecture

### Service Topology

Six backend services (and two utility infra containers) on a shared Docker bridge network. Only Jenkins and config-hub are directly exposed to the host, while public Web App traffic is securely routed via the Caddy Ingress Gateway and Cloudflare Tunnel:

```mermaid
graph TD
    subgraph users["Users"]
        TU["Telegram User"]
        BA["Browser Admin"]
    end

    subgraph public["Public Boundary"]
        CF["cloudflared (Tunnel)"]
        GW["gateway (Caddy Ingress) :80"]
    end

    subgraph ops["Ops"]
        CH["config-hub :9000 ★"]
    end

    subgraph managed["Managed Services"]
        BOT["tg-jenkins-bot :9090"]
        BM["build-manager :9010"]
        FM["file-manager :9092"]
        AGT["agent-control :9091"]
    end

    JNK["jenkins :8080 ★"]

    TU -- Web App / HTTPS --> CF
    CF --> GW
    GW -- Proxy (/webapp) --> BOT
    BOT -- polling --> TU
    BA --> CH
    CH -. "configures & controls" .-> managed

    BOT -- trigger --> BM
    BM -- trigger --> JNK
    JNK -- dispatches --> AGT
    BM -- polls --> JNK
    BM -- upload --> FM
    BM -- callback --> BOT
```

### Service Roles

| Service | Port | Exposed | Role |
|---------|------|---------|------|
| `config-hub` | 9000 | Yes | Central operational hub — config proxy, service control, web dashboard |
| `jenkins` | 8080 | Yes | Standard Jenkins controller (dev/testing — can be external) |
| `tg-jenkins-bot` | 9090 | No | Telegram polling bot + FastAPI callback/control server |
| `agent-control` | 9091 | No | Jenkins inbound agent with Flutter/Android SDKs + control API |
| `file-manager` | 9092 | No | Storage backend — Google Drive OAuth, APK upload/download |
| `build-manager` | 9010 | No | Build orchestration — Jenkins trigger, job state tracking |
| `gateway` | 80 (internal) | No | Caddy Ingress Gateway — secure routing perimeter for public Web App endpoints |
| `cloudflared` | — | No | Cloudflare Tunnel — secure HTTPS tunnel connecting local gateway to Cloudflare |

### Design Principles

1. **Thin Trigger Layer** — The bot owns zero build logic. It delegates build requests to the build-manager, which triggers Jenkins via REST. All cloning, compiling, and packaging happens in the Jenkins pipeline.

2. **Centralized Operations** — `config-hub` is the single entry point for all configuration, service control, and Drive OAuth. It proxies `/control/*` calls to each owning service. Other API consumers interact via its HTTP API — no direct library dependencies or volume mounts needed.

3. **No Docker-out-of-Docker** — `docker.sock` is never mounted into any container. This is intentional for security and portability.

4. **FastAPI Everywhere** — All service APIs use FastAPI, structured per the official [Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/) pattern: `main.py` (app factory) → `dependencies.py` (`Depends` + `Annotated`) → `routers/` (`APIRouter` per domain). See `coding-conventions.md` for the module table.

5. **Jenkins-Synced, Bot-Scoped** — The bot tracks only builds it triggered. Build state is maintained in the build-manager; the bot's local state is limited to what it needs for callback matching. No information about non-bot-triggered builds is ever exposed to Telegram.

6. **uv Workspace** — Single `pyproject.toml` + `uv.lock` at the root. All members share a unified lockfile. Shared code lives in `libs/`. Dev tools are declared once at the workspace root. The flutter-agent Dockerfile keeps uv in runtime (exception — the base image lacks Python 3.12).

7. **Centralized Operational Hub** — `config-hub` (web dashboard + API) serves as the singular hub for editing configurations, initiating Google Drive OAuth connections, and monitoring individual container lifespans, eliminating secondary admin interfaces.

8. **Pydantic Configuration** — Two base classes from `config-core` partition the configuration by lifecycle: `BootstrapSettings` (env-only, hard crash at startup) for services with no dashboard-editable state (`config-hub`), and `ServiceSettings` (JSON > env, soft fail) for services whose config is editable via the web UI. All `ServiceSettings` fields are visible in the dashboard. Config is hardcoded to `/app/data/<service>.json` in each module — no path configuration needed.

9. **Scope = Service Name** — `config-hub` exposes UI scope names (`bot`, `agent`, `file_manager`, `builds`) that map directly to their `ServiceClient` service names. This mapping lives in `config-hub/manager.py:_SCOPE_TO_SERVICE` as a seam for future divergence. Unknown scopes are rejected with HTTP 404.

10. **No-Workaround Policy & Root Cause Resolution** — Workarounds or temporary band-aids that only mask symptoms instead of resolving core architectural problems are strictly forbidden. You must always address the *root cause* of bugs and mismatches. 
    If you are adding new features or fixing a bug and find that the current design or architecture is no longer a good fit, you have **explicit, unrestricted permission to rewrite the architecture** to ensure the code and system are as perfect and structural as possible.

11. **Refactor Notification Requirement** — While the user is open-minded and encourages structural rewrites to make the product perfect, you must notify the user, explain why the current architecture is a bad fit, and align on the rewrite plan before executing large-scale refactors.

---

## Hard Constraints

These are architectural boundaries. Do not violate them.

1. **Do NOT mount `docker.sock`** into any container.
2. **Do NOT add build logic** to the Telegram bot or config-hub — builds happen in Jenkins pipelines.
3. **Do NOT bypass the config precedence chain** — always use the service's own `ServiceSettings.load()` or `BootstrapSettings.load()` method.
4. **Do NOT expose bot, agent, file-manager, or build-manager ports to the host** — only `jenkins:8080` and `config-hub:9000` are host-facing.
5. **Do NOT use synchronous blocking I/O** in async code paths without wrapping with `asyncio.to_thread()`.
6. **Do NOT store secrets in code or Dockerfiles** — use env vars, `.env`, or service JSON config files.
7. **Do NOT replace deep merge with full overwrite** in config save logic.
8. **Do NOT leak non-bot build info to Telegram** — the bot strictly filters to its own triggered builds (matched by `BUILD_REQUEST_ID`). No build counts, build numbers, or metadata from manual Jenkins triggers may appear in Telegram messages.
9. **Do NOT rename `file-manager` internals to `drive`** — the service is storage-backend agnostic. The `drive` name appears only in user-facing labels (UI text, help strings) — the config scope key is `file_manager`.
10. **Do NOT use quick workarounds or temporary patches** — always fix structural root causes and rewrite components if necessary to maintain code perfection.

---

## Future Extensibility

The architecture supports these evolutions without structural changes:

- **External Jenkins** — the `jenkins` service in docker-compose is a **development/testing convenience**. In production, point `JENKINS_URL` to an external Jenkins instance and remove the `jenkins` service.
- **Multiple agents** — add more agent services with different `JENKINS_AGENT_NAME` values.
- **Additional storage backends** — file-manager is designed to support backends beyond Google Drive. Add a new backend under `file_manager/backends/`.
- **Additional build targets** — iOS, web, etc. The bot just needs the artifact file and metadata from the webhook.
- **Notification channels** — the build completion handlers can extend to Slack, email, etc.
- **Additional shared libraries** — add new packages under `libs/` and they are automatically picked up by the workspace via the `libs/*` member glob.
