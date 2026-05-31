---
trigger: glob
description: Python coding conventions, tooling, and backend project structure principles.
globs: **/*.py
---

# Python conventions

Triggered when editing Python files. Outlines the architectural principles, microservice consistency standards, and structural patterns governing all backend applications.

---

## 1. Unified Stack & Dependency Management
- **Python 3.12+ & uv Workspace**: All member applications share a unified workspace, a single `uv.lock` at the root, and standard Ruff/MyPy configs.
- **FastAPI Standardization**: Every microservice must follow the same architectural conventions and design patterns. You must adhere to the latest industry standards and FastAPI best practices.
- **Top-Level Imports**: All module imports must reside strictly at the top of the file to prevent implicit side effects. Use `TYPE_CHECKING` guards solely to resolve circular dependencies.

---

## 2. Microservice Architecture (Bigger Applications)
All FastAPI services (`tg-jenkins-bot`, `agent-control`, `build-manager`, `file-manager`, `config-hub`, `mock-jenkins`) must consistently implement the official **Bigger Applications** layout:
- **`main.py`**: The central FastAPI application factory, lifecycle/lifespan context manager, and entry point.
- **`config.py`**: Declares Pydantic `ServiceSettings` (dashboard-controlled) or `BootstrapSettings` (env-only) configurations.
- **`manager.py`**: Standardized service lifecycle controller managing domain resources and clean startup/shutdown bounds.
- **`dependencies.py`**: Centralized dependency injection factories (`Depends()`) and type-annotated dependencies.
- **`routers/`**: Decoupled, dedicated routers containing no business logic (which belongs strictly inside domain components).

---

## 3. Structural Design Principles
- **Dependency Injection**: Route handlers must receive shared resources and manager singletons exclusively through standard FastAPI dependency injection, utilizing `Annotated` type dependencies in `dependencies.py`.
- **Stateless Domain Logic**: Manager classes attached to `app.state` hold persistent service lifespans and state. Do not maintain mutable module-level global states.
- **Error Propagation**:
  - **Graceful Lifespan Recovery**: Services must catch resource initialization issues (`StartupError`) gracefully at lifespan startup, logging a warning while keeping the control API functional for diagnostic/reconfiguration access.
  - **Global Exception Mapping**: Register clean FastAPI exception handlers at the application level to convert domain errors to client-friendly HTTP status responses without boilerplate try/except blocks inside routers.
  - **Buffered In-Memory Logging**: Use the standard logger. No raw `print()` statements are permitted.
