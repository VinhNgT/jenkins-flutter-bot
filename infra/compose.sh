#!/usr/bin/env bash
# Usage:
#   ./compose.sh [docker compose args]          — dev (build images locally)
#   ./compose.sh prod [docker compose args]     — prod (pull images from GHCR)
#   ./compose.sh edge [docker compose args]     — edge (pull edge images from GHCR)
#   ./compose.sh mock [docker compose args]     — mock (fake Jenkins for testing)
#
# Examples:
#   ./compose.sh up --build
#   ./compose.sh prod up -d
#   ./compose.sh prod pull
#   IMAGE_TAG=v1.2.3 ./compose.sh prod up -d
#   ./compose.sh edge up -d
#   ./compose.sh mock up -d --build
#   MOCK_BUILD_DELAY=5 ./compose.sh mock up -d --build

set -euo pipefail

if [[ "${1:-}" == "prod" ]]; then
  shift
  exec docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod.yml \
    "$@"
elif [[ "${1:-}" == "edge" ]]; then
  shift
  exec docker compose \
    -f docker-compose.yml \
    -f docker-compose.edge.yml \
    "$@"
elif [[ "${1:-}" == "mock" ]]; then
  shift
  exec docker compose \
    -f docker-compose.yml \
    -f docker-compose.mock.yml \
    "$@"
else
  exec docker compose "$@"
fi
