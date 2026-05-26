# Stage 1: Build frontend (Preact + Vite + TypeScript)
FROM node:22-slim AS frontend

WORKDIR /app/frontend
COPY apps/tg-jenkins-bot/frontend/package*.json ./
RUN npm ci
COPY apps/tg-jenkins-bot/frontend/ ./
RUN npm run build
# Output: ../src/tg_jenkins_bot/webapp/ (relative to frontend dir)

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
COPY --from=frontend /app/src/tg_jenkins_bot/webapp apps/tg-jenkins-bot/src/tg_jenkins_bot/webapp

RUN uv sync --frozen --no-dev --no-editable --package tg-jenkins-bot

# Stage 3: Runtime
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

CMD ["tg-jenkins-bot"]
