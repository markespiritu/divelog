#!/usr/bin/env bash
# Report whether the local viewer server is running.
set -euo pipefail

PORT="${DIVELOG_PORT:-8123}"
URL="http://localhost:$PORT/web/"

pids=$(fuser "$PORT/tcp" 2>/dev/null | xargs || true)

if [[ -z "$pids" ]]; then
    echo "Not running (nothing on port $PORT)"
    exit 1
fi

echo "==> Port $PORT in use by:"
ps -o pid=,etime=,args= -p "${pids// /,}" | sed 's/^/    /'

status=$(curl -s -o /dev/null -w '%{http_code}' "$URL" || true)
if [[ "$status" == "200" ]]; then
    echo "==> Viewer is up at $URL"
else
    echo "Warning: $URL returned HTTP ${status:-no response}" >&2
    exit 1
fi
