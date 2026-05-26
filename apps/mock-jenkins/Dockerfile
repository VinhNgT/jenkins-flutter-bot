FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# Shared libs
COPY libs/config-core/pyproject.toml libs/config-core/
COPY libs/config-core/src libs/config-core/src

# Workspace dep: agent-control (for schema imports)
COPY apps/agent-control/pyproject.toml apps/agent-control/
COPY apps/agent-control/src apps/agent-control/src

# This app
COPY apps/mock-jenkins/pyproject.toml apps/mock-jenkins/
COPY apps/mock-jenkins/src apps/mock-jenkins/src

RUN uv sync --frozen --no-dev --no-editable --package mock-jenkins

FROM python:3.12-slim

RUN adduser --system --no-create-home appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

# Data directory for mock agent config
RUN mkdir -p /app/data && chown appuser /app/data

USER appuser

CMD ["mock-jenkins"]
