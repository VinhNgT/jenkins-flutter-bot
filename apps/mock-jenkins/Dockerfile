FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# This app (no shared libs needed — mock-jenkins is standalone)
COPY apps/mock-jenkins/pyproject.toml apps/mock-jenkins/
COPY apps/mock-jenkins/src apps/mock-jenkins/src

RUN uv sync --frozen --no-dev --no-editable --package mock-jenkins

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

CMD ["mock-jenkins"]
