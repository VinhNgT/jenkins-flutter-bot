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

- **All FastAPI services** share `fastapi` + `uvicorn` (including `tg-jenkins-bot` and `tg-admin-bot`).
- **All apps** depend on `config-core` (shared library) for `BootstrapSettings` / `ServiceSettings` and config I/O helpers.
- **`tg-admin-bot`** is also a standard FastAPI service; its primary dependencies are `fastapi`, `uvicorn`, `httpx`, `python-telegram-bot`, and `config-core`.
- **Blocking I/O libraries** (e.g., `google-api-python-client`) are wrapped with `asyncio.to_thread()`. See `communication-flows.md` for details.

Check each app's `pyproject.toml` for the authoritative dependency list.

---

## Project Structure

### Service Apps

FastAPI service apps follow the official [Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/) structure:

| Module | Role |
|--------|------|
| `main.py` | FastAPI app factory, lifespan, CLI entry |
| `config.py` | Pydantic `ServiceSettings` or `BootstrapSettings` subclass — field declarations + resolution |
| `manager.py` | Service lifecycle class — startup, shutdown, and domain resources |
| `dependencies.py` | Shared `Depends()` callables using `Annotated` type aliases |
| `routers/` | Route modules, each defining an `APIRouter` — no business logic |

This structure applies to all FastAPI services: `tg-jenkins-bot`, `tg-admin-bot`, `agent-control`, `build-manager`, `file-manager`, `config-hub`, and `mock-jenkins`.

`config-hub` and `tg-admin-bot` use `BootstrapSettings` (env-only, no JSON file) since they have no dashboard-editable config. `mock-jenkins` imports the real `AgentSettings` from `agent-control` for its mock agent-control server.

The bot additionally has sub-packages (`bot/`, `jenkins/`, `drive/`, `git/`) for domain-specific logic.

### Admin Bot

`tg-admin-bot` is implemented as a standard FastAPI application hosting control endpoints on port `9093`. It uses `config.py` with an `AdminBotBootstrap(BootstrapSettings)` class for its env-only settings, and wraps the Telegram polling updater in the `AdminBotManager` controlled via FastAPI's lifespan hooks. All administrative and operational requests are proxied via `HubClient` to the `config-hub` API.

### Shared Library

One library lives in `libs/` using PyPA `src` layout:

- **`config-core`** — `BootstrapSettings` and `ServiceSettings` Pydantic base classes, `get_frontend_schema()`, `ConfigDocument`, `get_secret_keys()`, `read_masked_config()`, `save_config_with_merge()`.

---

## Coding Style

### Type Hints

All function signatures should have parameter types and return types. Use `from __future__ import annotations` to enable the `X | Y` union syntax everywhere.

### Data Classes vs Pydantic Models

- **Config classes** inherit from `ServiceSettings` (Pydantic) — see `config-and-secrets.md` for the pattern.
- **Value objects and interactive states** use dataclasses (e.g. `TrackedMessage`) to cleanly encapsulate structured state. State transitions are managed atomically by dedicated tracker/manager classes (like `InteractionTracker`) to prevent race conditions.
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

`status()` methods attempt `Settings.load()` inline and capture the exception as `config_error`. This communicates both the `configured` boolean and the specific validation failure in a single `/control/status` response, **without logging** — logging it on every poll is noise.

### Service-to-Service HTTP

`ServiceClient` (config-hub) owns a persistent `httpx.AsyncClient` for connection reuse across dashboard polls and config proxying. It exposes a `close()` method called during `ConfigHubManager.stop()`. The client logs downstream HTTP failures with `logger.warning()` (no traceback) at the terminal catch site. The return value communicates the error to the caller. Full tracebacks are noise here because these failures are expected during initial setup.

### Terminal Catch Sites

Bot Telegram API handlers, Drive OAuth flows, and Jenkins client calls are **terminal catch sites** — the operation failed, we log it, and continue. These correctly use `logger.exception()` because there is no caller to propagate to. Do not change these.

---

## Testing Conventions

The repository uses **pytest** for both unit and integration tests across all workspace packages, configured globally in the root `pyproject.toml`.

### Shared Testing Infrastructure (`conftest.py`)

A centralized, root-level `conftest.py` provides shared testing utilities:

1. **Domain Object Factories** — Plain helper functions (not fixtures) to quickly instantiate mock data with realistic defaults. Use them inline with overrides:
   - `pending_build_factory(**overrides)` for build-manager builds
   - `completed_build_factory(**overrides)` for completed builds
   - `jenkins_build_factory(**overrides)` for Jenkins client responses
   - `tracked_message_factory(**overrides)` for Telegram interaction tracking
2. **HTTP Mocking** — The `mock_http_client` fixture registers custom transports to mock HTTP calls to external APIs without leaving the process boundary.
3. **Telegram Test Helpers** — Full-stack mock fixtures to test Telegram polling dispatch loops safely:
   - `make_mock_bot()` generates an `AsyncMock` pre-configured with the required attributes of `telegram.Bot` to satisfy PTB internals.
   - `make_telegram_update(...)` and `make_callback_update(...)` construct realistic, bot-attributed `telegram.Update` payloads so command and button callbacks can be integration-tested natively.
   - `make_handler_context(...)` mocks standard context objects to test standalone callback handlers in isolation.
   - `make_test_application(...)` builds fully-wired `Application` instances bound to a mock bot to allow end-to-end integration testing via `await app.process_update()`.

