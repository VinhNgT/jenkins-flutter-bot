---
trigger: glob
description: Unified testing methodology for backend (pytest) and frontend (Vitest).
globs: **/tests/**/*.py, **/conftest.py, **/*.test.ts, **/*.test.tsx, **/vitest.config.*, **/pyproject.toml
---

# Testing Conventions

Triggered when writing or modifying tests. Defines the testing methodologies, hermetic execution bounds, and environment isolation principles.

---

## 1. Environment Isolation (Hermetic Execution)
- **Zero Real-World Mutations**: Tests must NEVER write to the physical filesystem, read real environment variables, or reach the real network. 
- **Dynamic File Isolation**: autouse `isolate_config` fixtures must intercept configurations and rewrite file target paths to temporary, test-local directories (`tmp_path`). Always use `monkeypatch` to isolate environment variables.

---

## 2. Backend Testing (pytest)
- **HTTP/Network Boundaries**: Use `httpx.MockTransport` at the HTTP transport boundary rather than mocking internal class functions. This exercises the entire request serialization and response parsing pipeline.
- **Dependency Injection Mocks**: Collaborate through constructor-injected arguments (`client: httpx.AsyncClient | None = None`). Avoid raw monkeypatching of internal method targets.
- **Time Control via time-machine**: Do not parameterize production clocks. Freeze or travel time using `time-machine` externally in test suites.
- **Default Async Execution**: Python testing operates globally in `asyncio_mode = "auto"`. Individual tests do not require explicit async annotations.

---

## 3. Frontend Testing (Vitest + JSDOM)
- **Vitest Setup**: Preact apps run in `jsdom` test environments using Vitest setup hooks (`defineConfig` imported from `vitest/config`).
- **Telegram SDK Simulation**: Preact hooks and components are tested against simulated WebApp contexts (spy models based on `emulator.ts`).
- **Isolation of Hook Timers**: Use Vitest fake timers (`vi.useFakeTimers()`) to verify hooks like `useNavigator()` which govern transition phases (push -> active -> pop -> delayed unmount -> idle) over time.
- **Mock Network Boundaries**: Mock `api.ts` clients using Vitest `vi.mock()` to isolate layout components from active HTTP networks.
