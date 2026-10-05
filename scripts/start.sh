#!/usr/bin/env bash
# Start the local viewer server in the background.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${DIVELOG_PORT:-8123}"
URL="http://localhost:$PORT/web/"

if fuser "$PORT/tcp" >/dev/null 2>&1; then
    echo "Port $PORT is already in use; the server may already be running at $URL" >&2
    echo "Run scripts/stop.sh to stop it." >&2
    exit 1
fi

cd "$ROOT"
nohup python3 -m http.server "$PORT" >/dev/null 2>&1 &

for _ in {1..20}; do
    if curl -s -o /dev/null "$URL"; then
        echo "==> Serving at $URL"
        exit 0
    fi
    sleep 0.1
done

echo "Server did not respond on port $PORT" >&2
exit 1
