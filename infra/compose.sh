#!/usr/bin/env bash
# Usage:
#   ./compose.sh [docker compose args]          — dev (build images locally)
#   ./compose.sh prod [docker compose args]     — prod (pull images from GHCR)
#   ./compose.sh hybrid [docker compose args]   — hybrid (build locally, pull agent from GHCR)
#   ./compose.sh mock [docker compose args]     — mock (fake Jenkins for testing)
#
# Examples:
#   ./compose.sh up --build
#   ./compose.sh prod up -d
#   ./compose.sh prod pull
#   IMAGE_TAG=v1.2.3 ./compose.sh prod up -d
#   ./compose.sh hybrid up -d --build
#   ./compose.sh mock up -d --build
#   MOCK_BUILD_DELAY=5 ./compose.sh mock up -d --build

set -euo pipefail

# Always run from the directory where the script is located
cd "$(dirname "$0")"

# Automatically load compose.env if it exists
if [ -f "compose.env" ]; then
    set -a
    source compose.env
    set +a
fi

# Pass --env-file if it exists, so docker-compose itself also gets the vars
ENV_ARGS=()
if [ -f "compose.env" ]; then
    ENV_ARGS=("--env-file" "compose.env")
fi

# Determine target compose file
COMPOSE_FILE="docker-compose.yml"
if [[ "${1:-}" =~ ^(prod|hybrid|mock)$ ]]; then
  COMPOSE_FILE="docker-compose.$1.yml"
  shift
fi

exec docker compose "${ENV_ARGS[@]}" -f "$COMPOSE_FILE" "$@"
