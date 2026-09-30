#!/usr/bin/env bash
# Parse the latest Shearwater Cloud export and publish the viewer to the
# divelog container. Only web/ and data/ are sent; raw/ never leaves this machine.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${DIVELOG_HOST:-root@192.168.200.124}"
DEST="/srv/divelog/"

usage() {
    cat <<EOF
Usage: scripts/deploy.sh [options] [DB]

Parse a Shearwater Cloud database export into data/, then sync web/ and data/
to the divelog web server.

Arguments:
  DB              Database export to parse (default: newest .db in raw/)

Options:
  -s, --skip-parse  Deploy data/ as it is, without running the parser
  -n, --dry-run     Show what would be sent; skip the parser and change nothing
  -h, --help        Show this help and exit

Environment:
  DIVELOG_HOST    SSH target to deploy to (default: root@192.168.200.124)

Examples:
  scripts/deploy.sh                   # parse newest export and deploy
  scripts/deploy.sh raw/export.db     # parse a specific export and deploy
  scripts/deploy.sh --dry-run         # preview the sync
EOF
}

parse=1
dry_run=0
db=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        -s|--skip-parse) parse=0 ;;
        -n|--dry-run) dry_run=1; parse=0 ;;
        -*) echo "Unknown option: $1" >&2; echo "Run 'scripts/deploy.sh --help' for usage." >&2; exit 2 ;;
        *)
            if [[ ${#db[@]} -gt 0 ]]; then
                echo "Only one DB can be given." >&2; exit 2
            fi
            db=("$1") ;;
    esac
    shift
done

cd "$ROOT"

if [[ $parse -eq 1 ]]; then
    echo "==> Parsing dives"
    python3 scripts/parse_dive.py "${db[@]}"
elif [[ ${#db[@]} -gt 0 ]]; then
    echo "Note: ignoring ${db[0]} because the parser is not running." >&2
fi

rsync_opts=(-az --delete --itemize-changes --chown=www-data:www-data --chmod=D755,F644)
note=""
if [[ $dry_run -eq 1 ]]; then
    rsync_opts+=(--dry-run)
    note=" (dry run)"
fi

echo "==> Syncing web/ and data/ to $HOST:$DEST$note"
rsync "${rsync_opts[@]}" -e "ssh -o SendEnv=-" web data "$HOST:$DEST"

if [[ $dry_run -eq 0 ]]; then
    url="http://${HOST#*@}/"
    status=$(curl -s -o /dev/null -w '%{http_code}' "${url}data/dives.json" || true)
    if [[ "$status" == "200" ]]; then
        echo "==> Done: $url"
    else
        echo "Warning: ${url}data/dives.json returned HTTP ${status:-no response}" >&2
        exit 1
    fi
fi
