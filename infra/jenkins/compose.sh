#!/usr/bin/env bash
# Usage:
#   ./compose.sh [docker compose args]          — dev (build images locally)
#   ./compose.sh prod [docker compose args]     — prod (pull images from GHCR)
#
# Examples:
#   ./compose.sh up --build
#   ./compose.sh prod up -d
#   ./compose.sh prod pull
#   IMAGE_TAG=v1.2.3 ./compose.sh prod up -d

set -euo pipefail

if [[ "${1:-}" == "prod" ]]; then
  shift
  exec docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod.yml \
    "$@"
else
  exec docker compose "$@"
fi
