#!/usr/bin/env bash
# Usage:
#   ./compose.sh [docker compose args]          — dev (build images locally)
#   ./compose.sh prod [docker compose args]     — prod (pull images from GHCR)
#   ./compose.sh edge [docker compose args]     — edge (pull edge images from GHCR)
#   ./compose.sh hybrid [docker compose args]   — hybrid (build locally, pull agent from GHCR)
#   ./compose.sh mock [docker compose args]     — mock (fake Jenkins for testing)
#
# Examples:
#   ./compose.sh up --build
#   ./compose.sh prod up -d
#   ./compose.sh prod pull
#   IMAGE_TAG=v1.2.3 ./compose.sh prod up -d
#   ./compose.sh edge up -d
#   ./compose.sh hybrid up -d --build
#   ./compose.sh mock up -d --build
#   MOCK_BUILD_DELAY=5 ./compose.sh mock up -d --build

set -euo pipefail

# Always run from the directory where the script is located
cd "$(dirname "$0")"

ENV_ARGS=()
if [[ -f .env ]]; then
  ENV_ARGS+=(--env-file .env)
fi

# Determine target environment directory
ENV_NAME="dev"
if [[ "${1:-}" =~ ^(prod|edge|hybrid|mock)$ ]]; then
  ENV_NAME="$1"
  shift
fi

exec docker compose "${ENV_ARGS[@]}" -f "$ENV_NAME/docker-compose.yml" "$@"
