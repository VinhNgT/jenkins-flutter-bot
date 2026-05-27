# Stage 1: Build frontend (Preact + Vite + TypeScript)
FROM node:22-slim AS frontend

WORKDIR /app/frontend
COPY apps/config-hub/frontend/package*.json ./
RUN npm ci
COPY apps/config-hub/frontend/ ./
RUN npm run build
# Output: ../src/config_hub/static/ (relative to frontend dir)

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
COPY apps/config-hub/pyproject.toml apps/config-hub/
COPY apps/config-hub/src apps/config-hub/src

# Overwrite static/ with Vite build output from Stage 1
COPY --from=frontend /app/src/config_hub/static apps/config-hub/src/config_hub/static

RUN uv sync --frozen --no-dev --no-editable --package config-hub

# Stage 3: Runtime
FROM python:3.12-slim

RUN adduser --system --no-create-home appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

USER appuser

CMD ["config-hub"]
