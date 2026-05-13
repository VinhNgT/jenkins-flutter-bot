FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# Shared library
COPY libs/config-schema/pyproject.toml libs/config-schema/
COPY libs/config-schema/src libs/config-schema/src

# This app
COPY apps/build-orchestrator/pyproject.toml apps/build-orchestrator/
COPY apps/build-orchestrator/src apps/build-orchestrator/src

RUN uv sync --frozen --no-dev --no-editable --package build-orchestrator

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

CMD ["build-orchestrator"]
