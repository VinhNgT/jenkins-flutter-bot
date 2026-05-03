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
| `python-dotenv` | tg-bot, agent-control | `.env` file loading |

### Package Manager

**uv** is the sole package manager. Key commands:

- `uv sync` — install dependencies into `.venv`
- `uv run <entrypoint>` — run within the managed venv
- `uv lock` — regenerate lockfile after dependency changes

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
├── uv.lock
└── src/<package_name>/
    ├── __init__.py
    ├── main.py             # FastAPI app factory, lifespan, CLI entry
    ├── config.py           # Config/settings resolution
    └── control.py          # Manager class + control routes
```

- **`pyproject.toml`** declares a `[project.scripts]` entry point used as the Docker `ENTRYPOINT`.
- **`main.py`** creates the FastAPI app via a factory function, wires up the lifespan, and includes routers.
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

## Error Handling Patterns

These are the current patterns. They work well but can be improved:

- **Config resolution** raises `KeyError` for missing required values. Callers catch and log.
- **FastAPI lifespan** catches startup failures and logs them, keeping the server running so the control API remains available for retries.
- **Webhook handlers** never crash on unexpected input — they return `{"status": "ignored"}` for unrecognized callbacks and always clean up temp files.
