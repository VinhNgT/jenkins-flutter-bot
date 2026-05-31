# Stage 1: Build frontend (Preact + Vite + TypeScript)
FROM node:22-slim AS frontend

WORKDIR /app

COPY package.json ./
COPY libs/platform-core/package.json ./libs/platform-core/
COPY libs/tg-core-preact/package.json ./libs/tg-core-preact/
COPY libs/tg-ui-preact/package.json ./libs/tg-ui-preact/
COPY apps/tg-bot/frontend/package.json ./apps/tg-bot/frontend/
COPY apps/tg-bot/frontend-admin/package.json ./apps/tg-bot/frontend-admin/

RUN npm install --workspace=tg-bot-webapp --workspace=config-hub-frontend --include-workspace-root

COPY libs/platform-core/ ./libs/platform-core/
RUN npm run build --workspace=platform-core

COPY libs/tg-core-preact/ ./libs/tg-core-preact/
RUN npm run build --workspace=tg-core-preact

COPY libs/tg-ui-preact/ ./libs/tg-ui-preact/
RUN npm run build --workspace=tg-ui-preact

COPY apps/tg-bot/frontend/ ./apps/tg-bot/frontend/
RUN npm run build --workspace=tg-bot-webapp

COPY apps/tg-bot/frontend-admin/ ./apps/tg-bot/frontend-admin/
RUN npm run build --workspace=config-hub-frontend


# Stage 2: Build Python
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# Shared library
COPY libs/config-core/pyproject.toml libs/config-core/
COPY libs/config-core/src libs/config-core/src

# This app
COPY apps/tg-bot/pyproject.toml apps/tg-bot/
COPY apps/tg-bot/src apps/tg-bot/src

# Overwrite webapp/ and webapp-admin/ with Vite build output from Stage 1
COPY --from=frontend /app/apps/tg-bot/src/tg_bot/webapp apps/tg-bot/src/tg_bot/webapp
COPY --from=frontend /app/apps/tg-bot/src/tg_bot/webapp-admin apps/tg-bot/src/tg_bot/webapp-admin

RUN uv sync --frozen --no-dev --no-editable --package tg-bot

# Stage 3: Runtime
FROM python:3.12-slim

RUN adduser --system --no-create-home appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

# Data directory needs write access for JSON config
RUN mkdir -p /app/data && chown appuser /app/data

USER appuser

CMD ["tg-bot"]
