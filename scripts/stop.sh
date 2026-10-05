#!/usr/bin/env bash
# Stop the local viewer server started by scripts/start.sh.
set -euo pipefail

PORT="${DIVELOG_PORT:-8123}"

if fuser -k "$PORT/tcp" >/dev/null 2>&1; then
    echo "==> Stopped server on port $PORT"
else
    echo "Nothing is running on port $PORT"
fi
