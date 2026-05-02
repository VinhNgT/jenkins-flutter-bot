FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "config_ui.app:app", "--host", "0.0.0.0", "--port", "9000", "--app-dir", "/app/src"]
