FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace root
COPY pyproject.toml uv.lock ./

# Shared library
COPY libs/config-schema/pyproject.toml libs/config-schema/
COPY libs/config-schema/src libs/config-schema/src

# This app
COPY apps/file-manager/pyproject.toml apps/file-manager/
COPY apps/file-manager/src apps/file-manager/src

RUN uv sync --frozen --no-dev --no-editable --package file-manager

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

CMD ["file-manager"]
