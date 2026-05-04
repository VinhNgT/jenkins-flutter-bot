---
trigger: always_on
description: Core architectural reference — project identity, repo layout, service topology, and hard constraints.
---

# Jenkins Flutter Bot — AI Agent Guide

This is the core architectural reference for the **jenkins-flutter-bot** monorepo. It loads on every interaction. For detailed guidance on specific topics, see the companion rule files.

---

## What This Project Is

A self-hosted CI/CD ecosystem: a Telegram bot triggers Flutter builds on Jenkins and delivers APKs through Google Drive. Four containerized services coordinate over an internal Docker network.

**It is NOT a build system.** It is a thin orchestration layer around Jenkins. All cloning, compiling, and artifact packaging is delegated to a Jenkins pipeline running on a Flutter-capable agent.

---

## Repository Layout

```text
jenkins-flutter-bot/
├── apps/                           Deployable Python applications
│   ├── tg-jenkins-bot/             Telegram bot — trigger layer + webhook receiver
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── src/tg_jenkins_bot/
│   │       ├── main.py             FastAPI entry point, lifespan hook
│   │       ├── config.py           Multi-layer config resolution
│   │       ├── control.py          BotManager lifecycle + /control/* API
│   │       ├── bot/
│   │       │   ├── context.py      Build tracking, history, Drive upload, notification
│   │       │   └── handlers.py     /start, /build, /status, /recent handlers
│   │       ├── jenkins/
│   │       │   ├── client.py       Jenkins REST API wrapper
│   │       │   └── webhook.py      POST /webhook/build-complete handler
│   │       └── drive/
│   │           └── uploader.py     Google Drive file ops (token read-only)
│   │
│   ├── config-ui/                  Web dashboard — configuration + service control
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── src/config_ui/
│   │       ├── app.py              Config CRUD, service control, Drive OAuth
│   │       ├── drive.py            DriveOAuthManager (browser-redirect flow)
│   │       ├── static/             Frontend assets (index.html, style.css, app.js)
│   │       └── templates/          Jinja2 templates (oauth_callback.html)
│   │
│   └── agent-control/              HTTP control wrapper for the Jenkins agent process
│       ├── pyproject.toml
│       └── src/agent_control/
│           ├── main.py             FastAPI app factory, lifespan, CLI entry
│           ├── config.py           AgentConfig resolution
│           └── control.py          AgentManager + /control/* routes
│
├── infra/                          Infrastructure & CI/CD
│   └── jenkins/
│       ├── docker-compose.yml      Stack orchestration (4 services; jenkins is dev-only)
│       ├── Dockerfile              Jenkins controller (dev/testing convenience)
│       ├── Dockerfile.flutter-agent  Multi-stage (SDKs + agent-control via uv)
│       └── .env.example            Reference env vars
│
└── .agents/rules/                  AI agent rules (these files)
```

### Naming Conventions

- **Directory names**: `kebab-case` (e.g., `tg-jenkins-bot`, `config-ui`, `agent-control`).
- **Python packages**: `snake_case` matching the directory name (e.g., `tg_jenkins_bot`, `config_ui`, `agent_control`).
- **Source layout**: All apps use PyPA `src` layout — code lives under `src/<package_name>/`.

---

## Architecture

### Service Topology

Four services on a shared Docker bridge network. Only Jenkins and config-ui are exposed to the host:

```
Telegram User → tg-bot:9090 (internal)
Browser Admin → config-ui:9000 (exposed) → tg-bot, flutter-agent
Jenkins UI    → jenkins:8080 (exposed) → flutter-agent:9091 (internal)
```

### Service Roles

| Service | Port | Exposed | Role |
|---------|------|---------|------|
| `tg-bot` | 9090 | No | Telegram polling bot + FastAPI webhook/control server |
| `config-ui` | 9000 | Yes | Web dashboard for config, service control, Drive OAuth |
| `jenkins` | 8080 | Yes | Standard Jenkins controller (dev/testing — can be external) |
| `flutter-agent` | 9091 | No | Jenkins inbound agent with Flutter/Android SDKs + control API |

### Design Principles

1. **Thin Trigger Layer** — The bot owns zero build logic. It triggers Jenkins via REST, registers a `request_id`, and waits for a webhook callback.

2. **HTTP Signal Architecture** — Services coordinate via internal HTTP control APIs (`/control/start`, `/control/stop`, `/control/restart`, `/control/status`). No Docker socket mounting.

3. **No Docker-out-of-Docker** — `docker.sock` is never mounted into any container. This is intentional for security and portability.

4. **FastAPI Everywhere** — All service APIs use FastAPI: the bot, config-ui, and agent-control.

5. **Bot-Scoped Tracking** — The bot only tracks builds it triggered. It maintains its own build history and state independently of Jenkins — it never queries Jenkins to reconstruct what it has already tracked locally.

6. **Consistent Packaging** — All three apps use uv with `src` layout, `pyproject.toml`, and `[project.scripts]` entry points. The flutter-agent Dockerfile keeps uv in runtime (exception — the base image lacks Python 3.12, so uv manages both Python and dependencies).

7. **Config-UI is Setup-Only** — The config-ui dashboard is a convenience for initial configuration and operational control. On first boot with missing configuration, services may depend on config-ui to provide settings via the web dashboard. Once configured, every service must auto-start independently on subsequent boots — resolving all configuration from env vars / `.env` files / JSON config without any dependency on config-ui. The only feature exclusive to config-ui is the Google Drive OAuth browser-redirect flow (one-time setup).

---

## Hard Constraints

These are architectural boundaries. Do not violate them.

1. **Do NOT mount `docker.sock`** into any container.
2. **Do NOT add build logic** to the Telegram bot — builds happen in Jenkins pipelines.
3. **Do NOT bypass the config precedence chain** — always use `Config.resolve()` / `AgentConfig.resolve()`.
4. **Do NOT expose bot or agent ports to the host** — only `jenkins:8080` and `config-ui:9000` are host-facing.
5. **Do NOT use synchronous blocking I/O** in async code paths without wrapping with `asyncio.to_thread()`.
6. **Do NOT store secrets in code or Dockerfiles** — use env vars, `.env`, or config-ui JSON files.
7. **Do NOT replace deep merge with full overwrite** in config save logic.
8. **Do NOT make the bot depend on Jenkins** beyond three interactions, all scoped to Telegram-triggered builds only: triggering builds (REST), checking their status (REST), and receiving their results (webhook callback). All bot-side state — build history, Drive file tracking, cleanup — is owned and persisted by the bot itself.

---

## Future Extensibility

The architecture supports these evolutions without structural changes:

- **External Jenkins** — the `jenkins` service in docker-compose is a **development/testing convenience**. In production, point `JENKINS_URL` to an external Jenkins instance and remove the `jenkins` service. The bot and agent are Jenkins-agnostic — they only need a reachable URL.
- **Multiple agents** — add more agent services with different `JENKINS_AGENT_NAME` values.
- **Additional build targets** — iOS, web, etc. The bot just needs the artifact file and metadata from the webhook.
- **Notification channels** — the `on_build_success` / `on_build_failure` handlers can extend to Slack, email, etc.
