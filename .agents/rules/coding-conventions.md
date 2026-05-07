---
trigger: glob
description: Python coding conventions, tooling, and project structure patterns.
globs: **/*.py
---

# Coding Conventions

Triggered when editing Python files. Covers the Python stack, coding style, and project structure patterns used across all three apps.

---

## Python Stack

- **Python 3.12+** — all apps declare `requires-python = ">=3.12"`.
- **`from __future__ import annotations`** at the top of every module for deferred type evaluation.

### Dependencies

| Package | Used By | Purpose |
|---------|---------|---------|
| `fastapi` + `uvicorn` | All apps | HTTP APIs and servers |
| `python-telegram-bot[ext]` | tg-bot | Telegram bot framework |
| `httpx` | tg-bot, config-ui | Async HTTP client |
| `google-api-python-client` | tg-bot | Google Drive API |
| `google-auth-oauthlib` | config-ui | OAuth2 browser-redirect flow |
| `python-multipart` | tg-bot | Multipart form parsing (webhook) |
| `python-dotenv` | config-schema (shared) | `.env` file loading |

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

---

## Project Structure

All three apps (`tg-jenkins-bot`, `config-ui`, `agent-control`) follow the same structure:

```
apps/<app-name>/
├── pyproject.toml          # deps, scripts, build config
└── src/<package_name>/
    ├── __init__.py
    ├── main.py             # FastAPI app factory, lifespan, CLI entry
    ├── schema.py           # Field declarations (imports FieldDef etc. from config_schema)
    ├── config.py           # Typed Config dataclass (delegates to schema.py)
    └── control.py          # Manager class + control routes + GET /control/schema
```

Shared infrastructure lives in `libs/config-schema/`:

```
libs/config-schema/
├── pyproject.toml
└── src/config_schema/
    ├── __init__.py         # Public API re-exports
    └── schema.py           # FieldDef, resolve_fields, serialize_schema, nested_get
```

- **`pyproject.toml`** declares a `[project.scripts]` entry point used as the Docker `ENTRYPOINT`.
- **`main.py`** creates the FastAPI app via a factory function, wires up the lifespan, and includes routers.
- **`schema.py`** (per-app) declares the module's `FieldDef` tuples. The shared `FieldDef` dataclass, `resolve_fields()`, and `serialize_schema()` live in `config_schema`.
- **Routers** are defined in their respective modules as `APIRouter` instances and included in `main.py`.

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
