# Stage 1: Build Python
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# Shared library
COPY libs/config-core/pyproject.toml libs/config-core/
COPY libs/config-core/src libs/config-core/src

# This app
COPY apps/service-hub/pyproject.toml apps/service-hub/
COPY apps/service-hub/src apps/service-hub/src

RUN uv sync --frozen --no-dev --no-editable --package service-hub


# Stage 2: Runtime
FROM python:3.12-slim

RUN adduser --system --no-create-home appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

USER appuser

CMD ["service-hub"]
