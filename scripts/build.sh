#!/bin/bash
# Stock Investing Model - Docker Build Script
# Usage: ./scripts/build.sh [backend|web|all]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TARGET="${1:-all}"

build_backend() {
    echo "Building backend..."
    docker build -t stock-investing-backend "$PROJECT_ROOT/backend"
}

build_web() {
    echo "Building web..."
    docker build -t stock-investing-web "$PROJECT_ROOT/web"
}

case "$TARGET" in
    backend) build_backend ;;
    web)     build_web ;;
    all)
        build_backend
        build_web
        echo -e "\nBuild complete. Run: docker compose up"
        ;;
    *) echo "Usage: $0 [backend|web|all]"; exit 1 ;;
esac
