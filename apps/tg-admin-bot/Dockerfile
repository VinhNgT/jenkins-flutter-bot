FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# Shared libraries
COPY libs/config-schema/pyproject.toml libs/config-schema/
COPY libs/config-schema/src libs/config-schema/src
COPY libs/stack-manager/pyproject.toml libs/stack-manager/
COPY libs/stack-manager/src libs/stack-manager/src

# This app
COPY apps/tg-admin-bot/pyproject.toml apps/tg-admin-bot/
COPY apps/tg-admin-bot/src apps/tg-admin-bot/src

RUN uv sync --frozen --no-dev --no-editable --package tg-admin-bot

FROM python:3.12-slim
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
CMD ["tg-admin-bot"]
