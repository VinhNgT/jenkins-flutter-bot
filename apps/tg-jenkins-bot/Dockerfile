# Stage 1: Build frontend (Preact + Vite + TypeScript)
FROM node:22-slim AS frontend

WORKDIR /app

COPY package.json ./
COPY libs/platform-core/package.json ./libs/platform-core/
COPY libs/tg-core-preact/package.json ./libs/tg-core-preact/
COPY libs/tg-ui-preact/package.json ./libs/tg-ui-preact/
COPY apps/tg-jenkins-bot/frontend/package.json ./apps/tg-jenkins-bot/frontend/

RUN npm install --workspace=tg-jenkins-bot-webapp --include-workspace-root

COPY libs/platform-core/ ./libs/platform-core/
RUN npm run build --workspace=platform-core

COPY libs/tg-core-preact/ ./libs/tg-core-preact/
RUN npm run build --workspace=tg-core-preact

COPY libs/tg-ui-preact/ ./libs/tg-ui-preact/
RUN npm run build --workspace=tg-ui-preact

COPY apps/tg-jenkins-bot/frontend/ ./apps/tg-jenkins-bot/frontend/
RUN npm run build --workspace=tg-jenkins-bot-webapp


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
COPY apps/tg-jenkins-bot/pyproject.toml apps/tg-jenkins-bot/
COPY apps/tg-jenkins-bot/src apps/tg-jenkins-bot/src

# Overwrite webapp/ with Vite build output from Stage 1
COPY --from=frontend /app/apps/tg-jenkins-bot/src/tg_jenkins_bot/webapp apps/tg-jenkins-bot/src/tg_jenkins_bot/webapp

RUN uv sync --frozen --no-dev --no-editable --package tg-jenkins-bot

# Stage 3: Runtime
FROM python:3.12-slim

RUN adduser --system --no-create-home appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

# Data directory needs write access for JSON config
RUN mkdir -p /app/data && chown appuser /app/data

USER appuser

CMD ["tg-jenkins-bot"]
