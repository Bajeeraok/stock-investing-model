#!/bin/bash
# Stock Investing Model - Dev mode (hot reload)
# Usage: ./scripts/dev.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "Starting dev environment with hot reload..."
echo "Backend: changes auto-restart | Web: Next.js hot-reloads"
docker compose -f docker-compose.dev.yml up --build
