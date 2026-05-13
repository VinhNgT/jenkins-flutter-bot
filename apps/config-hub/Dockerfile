FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# Shared library
COPY libs/config-core/pyproject.toml libs/config-core/
COPY libs/config-core/src libs/config-core/src

# This app
COPY apps/config-hub/pyproject.toml apps/config-hub/
COPY apps/config-hub/src apps/config-hub/src

RUN uv sync --frozen --no-dev --no-editable --package config-hub

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

CMD ["config-hub"]
