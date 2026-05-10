---
trigger: glob
description: Python coding conventions, tooling, and project structure patterns.
globs: **/*.py
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

- **All FastAPI services** share `fastapi` + `uvicorn`. The `tg-admin-bot` is the exception — it uses only `python-telegram-bot[ext]` with no HTTP server.
- **All apps** depend on `config-schema` (shared library) for declarative config fields.
- **`config-ui` and `tg-admin-bot`** depend on `stack-manager` (shared library) for service control, Drive OAuth, env I/O, and Jenkinsfile generation.
- **Blocking I/O libraries** (e.g., `google-api-python-client`) are wrapped with `asyncio.to_thread()`. See `communication-flows.md` for details.

Check each app's `pyproject.toml` for the authoritative dependency list.

---

## Project Structure

### Service Apps

The three FastAPI service apps (`tg-jenkins-bot`, `config-ui`, `agent-control`) follow the same module pattern:

| Module | Role |
|--------|------|
| `main.py` | FastAPI app factory, lifespan, CLI entry |
| `schema.py` | `FieldDef` tuple declarations (imports from `config_schema`) |
| `config.py` | Typed frozen Config dataclass (delegates to `schema.py`) |
| `control.py` | Manager class + `/control/*` routes + `GET /control/schema` |

The bot additionally has sub-packages (`bot/`, `jenkins/`, `drive/`) for domain-specific logic.

### Admin Bot

`tg-admin-bot` is a standalone Telegram polling bot — no FastAPI, no schema, no control API. It uses `stack-manager` for all operational logic and `settings.py` for a flat `Settings` dataclass.

### Shared Libraries

Both live in `libs/` and use PyPA `src` layout:

- **`config-schema`** — `FieldDef` dataclass, `resolve_fields()`, `serialize_schema()`, `nested_get()`. The authoritative source for the config resolution algorithm.
- **`stack-manager`** — `ServiceClient`, `DriveOAuth`, config store I/O, env export/import, Jenkinsfile template generation. Re-exports public API from `__init__.py`.

---

## Coding Style

### Type Hints

All function signatures should have parameter types and return types. Use `from __future__ import annotations` to enable the `X | Y` union syntax everywhere.

### Data Classes

Use frozen dataclasses for value objects like `Config`, `AgentConfig`, `PendingBuild`, and `Settings`. This makes them hashable and prevents accidental mutation.

### State Management

Mutable state lives in manager classes (`BotManager`, `AgentManager`) attached to `app.state`. Avoid global mutable state at module level.

### Logging

Use `logging.getLogger(__name__)` consistently. No `print()` statements — the apps run as services where structured logging matters.

### File Organization

- One concern per module: `config.py`, `control.py`, `bot/handlers.py`, `jenkins/client.py`, etc.
- Use `TYPE_CHECKING` imports to avoid circular dependencies between modules.
- Each module that defines routes creates its own `APIRouter` — `main.py` just includes them.

---

## Error Handling

1. **Never suppress exceptions.** Every `except` block must log with a full traceback via `logger.exception()`. Never use `logger.info()` or `logger.warning()` inside an `except` block.
2. **Always include tracebacks.** Use `logger.exception()` — the standard Python idiom for logging caught exceptions with full stack traces.
3. **Keep services available.** FastAPI lifespan hooks and optional operations catch errors and continue so the control API stays up for retries. Webhook handlers return `{"status": "ignored"}` for unrecognized callbacks and always clean up temp files.
