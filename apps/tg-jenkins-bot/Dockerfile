FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# Shared library
COPY libs/config-core/pyproject.toml libs/config-core/
COPY libs/config-core/src libs/config-core/src

# This app
COPY apps/tg-jenkins-bot/pyproject.toml apps/tg-jenkins-bot/
COPY apps/tg-jenkins-bot/src apps/tg-jenkins-bot/src

RUN uv sync --frozen --no-dev --no-editable --package tg-jenkins-bot

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

CMD ["tg-jenkins-bot"]
