FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# Shared library (config-core dependency)
COPY libs/config-core/pyproject.toml libs/config-core/
COPY libs/config-core/src libs/config-core/src

# This app
COPY apps/tg-admin-bot/pyproject.toml apps/tg-admin-bot/
COPY apps/tg-admin-bot/src apps/tg-admin-bot/src

RUN uv sync --frozen --no-dev --no-editable --package tg-admin-bot

FROM python:3.12-slim
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
CMD ["tg-admin-bot"]
