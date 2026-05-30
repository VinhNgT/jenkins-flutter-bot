---
trigger: glob
description: Unified testing methodology for backend (pytest) and frontend (Vitest). Read before writing or modifying any test file, conftest, or test configuration.
globs: **/tests/**/*.py, **/conftest.py, **/*.test.ts, **/*.test.tsx, **/vitest.config.*, **/pyproject.toml
---

# Testing Conventions

Covers the unified testing methodology, infrastructure, and constraints for both the Python backend (pytest) and Preact frontends (Vitest).

---

## Philosophy

- **Every test file** must include `from __future__ import annotations`.
- **Tests live adjacent to source** — each app has a `tests/` directory at the package root; each frontend has a `__tests__/` directory inside `src/`.
- **Shared infrastructure is centralized** — the root `conftest.py` provides domain factories, HTTP mock fixtures, and Telegram test helpers. App-level conftest files are thin; duplicating root-level helpers is forbidden.
- **Environment isolation is mandatory** — tests never touch the real filesystem, network, or environment outside `tmp_path`. Config isolation uses `monkeypatch`, not raw `os.environ` mutation.
- **Async is the default** — `asyncio_mode = "auto"` is set globally. Do not add `@pytest.mark.asyncio` to individual tests.

---

## Backend Testing (pytest)

### Running Tests

```bash
# Full suite from the workspace root
uv run pytest

# Single package
uv run pytest apps/build-manager/

# With coverage
uv run pytest --cov --cov-report=term-missing
```

Configuration lives in the root `pyproject.toml` under `[tool.pytest.ini_options]`.

### Test File Layout

Each app's `tests/` directory mirrors the source structure:

| Source module | Test file |
|---------------|-----------|
| `manager.py` | `test_manager.py` |
| `config.py` | `test_config.py` |
| `builds/coordinator.py` | `test_coordinator.py` |
| `routers/control.py` | `test_control.py` |
| `routers/webapp.py` | `test_webapp.py` |

Group related tests in classes (e.g., `TestLifecycle`, `TestStatus`, `TestEdgeCases`) for organizational clarity.

### Shared Infrastructure (`conftest.py`)

A root-level `conftest.py` provides three categories of shared utilities:

#### 1. Domain Object Factories

Plain functions (not fixtures) that instantiate domain objects with realistic defaults. Callers override individual fields inline:

```python
build = pending_build_factory(branch="develop")
```

These use lazy imports internally to avoid hard-coupling to specific packages at import time. Every service's domain objects that appear in cross-service test data should have a factory here.

#### 2. HTTP Mocking (`mock_http_client`)

A fixture that creates `httpx.AsyncClient` instances backed by `httpx.MockTransport`. Clients are automatically closed after the test. Prefer this over `unittest.mock.patch` for HTTP dependencies — it exercises the real HTTP serialization path.

#### 3. Telegram Test Helpers

Full-stack helper functions for testing python-telegram-bot (PTB) handlers:

- `make_mock_bot()` — `AsyncMock` with all required PTB `Bot` attributes.
- `make_telegram_update()` / `make_callback_update()` — realistic `Update` payloads with proper `set_bot()` wiring and `BOT_COMMAND` entities.
- `make_handler_context()` — mock `ContextTypes.DEFAULT_TYPE` with `bot_data` wired.
- `make_test_application()` — fully-wired `Application` for integration tests via `process_update()`.

### App-Level Conftest

Each app's `tests/conftest.py` provides thin, service-specific fixtures:

- **`isolate_config`** (autouse) — redirects `JFB_DATA_DIR` to `tmp_path` using `monkeypatch.setenv()`.
- **`app`** — calls the service's `create_app()` factory.
- **`client`** — wraps the app in `httpx.AsyncClient(transport=httpx.ASGITransport(app))` for async route testing.

### Patterns & Conventions

#### Environment Isolation

Always use `monkeypatch` for environment variable manipulation. Never mutate `os.environ` directly — it is process-global and leaks between tests if teardown is skipped:

```python
@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    monkeypatch.setenv("JFB_DATA_DIR", str(tmp_path))
```

#### HTTP Client Testing

Use `httpx.AsyncClient` with `ASGITransport` for testing FastAPI routes. This is the official FastAPI async testing approach and properly handles async endpoints, SSE, and streaming:

```python
@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as client:
        yield client
```

All test functions using the client must be `async def` and all client calls must be `await`ed.

#### External Service Mocking

Mock external services (Jenkins, Google Drive, Telegram API) at the HTTP transport level using `httpx.MockTransport`, not by patching internal methods. This validates the full request serialization and response parsing path:

```python
def jenkins_handler(request: httpx.Request) -> httpx.Response:
    if "/buildWithParameters" in str(request.url):
        return httpx.Response(201, headers={"Location": ".../queue/item/42/"})
    return httpx.Response(404)

client = JenkinsClient(url="http://jenkins:8080", ..., client=httpx.AsyncClient(transport=httpx.MockTransport(jenkins_handler)))
```

#### Constructor Injection

Production classes accept optional collaborators in their constructors (e.g., `client: httpx.AsyncClient | None = None`). Tests inject mock-backed instances. Do not use `unittest.mock.patch` to replace internal attributes or properties — if a class is hard to test without patching internals, it needs a constructor parameter.

#### Time Control with `time-machine`

Time-dependent tests use `time-machine` to freeze or travel through time, replacing any need for clock injection parameters in production code. Production code calls `time.time()` or `time.monotonic()` directly — `time-machine` intercepts them transparently:

```python
import time_machine

@time_machine.travel("2025-01-15 12:00:00", tick=False)
async def test_build_timeout():
    store = ActiveBuildStore()
    store.add(build)
    # time is frozen at the specified instant
    assert not store.is_expired(build)
```

For tests that need to advance time mid-test, use the `travel()` context manager:

```python
async def test_expiry_after_advance():
    with time_machine.travel("2025-01-15 12:00:00", tick=False) as traveller:
        store = ActiveBuildStore()
        store.add(build)
        traveller.shift(timedelta(hours=2))
        assert store.is_expired(build)
```

#### Assertions

- Assert specific values, not truthiness — `assert result.branch == "main"`, not `assert result.branch`.
- Match exception messages with `pytest.raises(Error, match="...")` to verify the right error path.
- For HTTP routes, assert both status code and response body structure.

---

## Frontend Testing (Vitest)

### Stack

- **Vitest** — test runner, integrated with the Vite build pipeline via `vitest/config`.
- **`@testing-library/preact`** — component rendering, DOM queries, and `renderHook`.
- **`jsdom`** — browser environment for Vitest.

### Configuration

Both frontends use an identical Vitest setup pattern. The `defineConfig` import must come from `vitest/config` (not `vite`) to properly type the `test` property:

```ts
/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import preact from '@preact/preset-vite';

export default defineConfig({
  // ...existing vite config...
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],  // bot webapp only
    include: ['src/__tests__/**/*.test.{ts,tsx}'],
  },
});
```

The config-hub frontend omits `setupFiles` since it has no Telegram SDK dependency.

### Running Tests

```bash
cd apps/tg-jenkins-bot/frontend && npm test
cd apps/config-hub/frontend && npm test
```

### Test File Layout

Tests live in `src/__tests__/` mirroring the source structure:

```
frontend/src/
├── __tests__/
│   ├── setup.ts             # Telegram SDK mock (bot webapp only)
│   ├── hooks/
│   │   ├── useNavigator.test.ts
│   │   └── useMainButton.test.ts
│   ├── components/
│   │   └── ActiveBuilds.test.tsx
│   └── utils.test.ts        # pure utility tests (config-hub)
├── hooks/
├── components/
└── ...
```

### Patterns

#### Telegram SDK Mocking

The bot webapp uses a setup file (`src/__tests__/setup.ts`) that installs a `window.Telegram.WebApp` mock before all tests. The mock provides stubs for `MainButton`, `BackButton`, `CloudStorage`, `themeParams`, and `initDataUnsafe` — all with `vi.fn()` spies for assertion. The production emulator module (`emulator.ts`) serves as the canonical reference for realistic mock shapes.

#### Hook Testing

Test hooks in isolation using `@testing-library/preact`'s `renderHook`. For stateful hooks like `useNavigator`, use `vi.useFakeTimers()` and `vi.advanceTimersByTime()` to verify the full transition lifecycle (push → active → pop → delayed unmount → idle).

#### No Network in Unit Tests

Mock all `fetch` / API calls. The `api.ts` module in each frontend is the only network boundary — mock it at the module level with `vi.mock()`.

---

## Hard Constraints

1. **Do NOT duplicate root conftest helpers** in app-level test files. Import or use the fixture directly.
2. **Do NOT use `@pytest.mark.asyncio`** — `asyncio_mode = "auto"` handles it globally.
3. **Do NOT mutate `os.environ` directly** in tests — always use `monkeypatch`.
4. **Do NOT patch internal class attributes/properties** for test setup — use constructor injection. If a class cannot accept a mock collaborator, refactor it.
5. **Do NOT accept HTTP 500 in assertions** as a valid response — `assert resp.status_code in (400, 500)` masks real failures.
6. **Do NOT leave broken tests in the suite** — a red test suite blocks all other quality signals.
7. **Do NOT skip frontend tests** — both Preact apps require Vitest coverage alongside the backend.
8. **Do NOT use sync `TestClient`** for route testing — use `httpx.AsyncClient` with `ASGITransport`.
9. **Do NOT inject clock parameters** into production classes for testability — use `time-machine` to control time externally.
