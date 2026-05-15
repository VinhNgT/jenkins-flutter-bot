---
trigger: glob
description: Python coding conventions, tooling, and project structure patterns.
globs: "**/*.py"
---

# Coding Conventions

Triggered when editing Python files. Covers the Python stack, coding style, and project structure patterns used across all apps.

---

## Python Stack

- **Python 3.12+** — all apps declare `requires-python = ">=3.12"`.
- **`from __future__ import annotations`** at the top of every module for deferred type evaluation.

### Package Manager

**uv** is the sole package manager. The repo is a **uv workspace** — a single `uv.lock` at the root governs all members. Key commands:

- `uv sync` — install all workspace member dependencies into `.venv` (run from root)
- `uv run --package <name> <cmd>` — run within a specific package's environment
- `uv lock` — regenerate the root lockfile after dependency changes

### Dev Tools

| Tool | Purpose |
|------|---------|
| `mypy` | Static type checking (configured in `pyproject.toml`) |
| `ruff` | Linting + formatting |

### Key Dependency Patterns

- **All FastAPI services** share `fastapi` + `uvicorn`. The `tg-admin-bot` is the only exception — it uses only `python-telegram-bot[ext]` with no HTTP server.
- **All apps** depend on `config-core` (shared library) for `ServiceSettings` and config I/O helpers.
- **`tg-admin-bot`** is a pure HTTP client to `config-hub` — its primary dependencies are `httpx`, `python-telegram-bot`, and `config-core`.
- **Blocking I/O libraries** (e.g., `google-api-python-client`) are wrapped with `asyncio.to_thread()`. See `communication-flows.md` for details.

Check each app's `pyproject.toml` for the authoritative dependency list.

---

## Project Structure

### Service Apps

FastAPI service apps follow the official [Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/) structure:

| Module | Role |
|--------|------|
| `main.py` | FastAPI app factory, lifespan, CLI entry |
| `config.py` | Pydantic `ServiceSettings` subclass — field declarations + resolution |
| `manager.py` | Service lifecycle class — startup, shutdown, and domain resources |
| `dependencies.py` | Shared `Depends()` callables using `Annotated` type aliases |
| `routers/` | Route modules, each defining an `APIRouter` — no business logic |

This structure applies to all FastAPI services: `tg-jenkins-bot`, `agent-control`, `build-manager`, `file-manager`, `config-hub`, and `mock-jenkins`.

`config-hub` is an exception to the config pattern — it owns no schema and instead proxies config I/O to the owning services. `mock-jenkins` uses `pydantic-settings.BaseSettings` directly instead of `ServiceSettings`.

The bot additionally has sub-packages (`bot/`, `jenkins/`, `drive/`, `git/`) for domain-specific logic.

### Admin Bot

`tg-admin-bot` is a standalone Telegram polling bot — no FastAPI, no schema, no control API. It delegates all operations to the `config-hub` HTTP API via `httpx`, using `config.py` with an `AdminBotConfig(ServiceSettings)` class for its own infrastructure settings.

### Shared Library

One library lives in `libs/` using PyPA `src` layout:

- **`config-core`** — `ServiceSettings` Pydantic base class, `FieldDef` dataclass, `resolve_fields()`, `serialize_schema()`, `nested_get()`, `get_secret_keys()`, `read_masked_config()`, `save_config_with_merge()`.

---

## Coding Style

### Type Hints

All function signatures should have parameter types and return types. Use `from __future__ import annotations` to enable the `X | Y` union syntax everywhere.

### Data Classes vs Pydantic Models

- **Config classes** inherit from `ServiceSettings` (Pydantic) — see `config-and-secrets.md` for the pattern.
- **Value objects** like `PendingBuild` use frozen dataclasses — hashable and mutation-safe.
- Avoid global mutable state at module level; mutable state lives in manager classes attached to `app.state`.

### Logging

Use `logging.getLogger(__name__)` consistently. No `print()` statements — the apps run as services where structured logging matters.

### File Organization

- One concern per module: `config.py`, `manager.py`, `dependencies.py`, `routers/control.py`, etc.
- Use `TYPE_CHECKING` imports to avoid circular dependencies between modules.
- Each module that defines routes creates its own `APIRouter` — `main.py` just includes them.

### Dependency Injection

Route handlers receive shared resources via FastAPI's standard [dependency injection](https://fastapi.tiangolo.com/tutorial/dependencies/):

- Dependency callables live in `dependencies.py`, not in router files.
- Type aliases use `Annotated` for clean signatures: `ManagerDep = Annotated[Manager, Depends(get_manager)]`.
- Sub-dependencies chain from `ManagerDep` to add guard logic (e.g. HTTP 503 if a required resource is not running).
- Do not use middleware for dependency injection — use `Depends()`.

---

## Error Handling

Follows FastAPI's official [Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/) pattern.

### Manager Startup

Each service's `manager.py` defines a `StartupError` exception. The manager raises it on any failure — config missing, invalid credentials, subprocess crash — and **never logs**. The caller decides what to do:

1. **Global `@app.exception_handler(StartupError)`** registered in `create_app()` converts startup failures to HTTP 400 `{"detail": "..."}` responses. Control routes contain **no try/except boilerplate** — `StartupError` propagates naturally to the global handler.
2. **Lifespan is the single logging site.** Catches `StartupError` and logs with `logger.warning()` (no traceback — startup failures are expected when config isn't filled in yet). Never re-raises — the control API stays up for retries.
3. **Shutdown** failures use `logger.exception()` — they are always unexpected.

### Status Checks

`_is_configured()` methods catch config resolution failures and return `False` **without logging**. The config state is communicated via the `/control/status` response; logging it on every poll is noise.

### Service-to-Service HTTP

`ServiceClient` (config-hub) logs downstream HTTP failures with `logger.warning()` (no traceback) at the terminal catch site. The return value communicates the error to the caller. Full tracebacks are noise here because these failures are expected during initial setup.

### Terminal Catch Sites

Bot Telegram API handlers, Drive OAuth flows, and Jenkins client calls are **terminal catch sites** — the operation failed, we log it, and continue. These correctly use `logger.exception()` because there is no caller to propagate to. Do not change these.

