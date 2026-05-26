FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# Shared library
COPY libs/config-core/pyproject.toml libs/config-core/
COPY libs/config-core/src libs/config-core/src

# This app
COPY apps/build-manager/pyproject.toml apps/build-manager/
COPY apps/build-manager/src apps/build-manager/src

RUN uv sync --frozen --no-dev --no-editable --package build-manager

FROM python:3.12-slim

RUN adduser --system --no-create-home appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

# Data directory needs write access for build state + JSON config
RUN mkdir -p /app/data && chown appuser /app/data

USER appuser

CMD ["build-manager"]
