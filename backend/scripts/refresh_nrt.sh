#!/usr/bin/env bash
# Background NRT refresh: probe FIRMS first, ingest only on a clean bill.
# Safe for cron/systemd: fails loud, never writes on product drift.
# Restart the API process after a successful run (in-process cache).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a

BBOX="${NRT_BBOX:--3.3,4.5,1.2,11.2}"
DATE="$(date -u +%F)"

cd "$ROOT/backend"
uv run python scripts/ingest_firms.py api --bbox="$BBOX" --date="$DATE" --check
uv run python scripts/ingest_firms.py api --bbox="$BBOX" --day-range 5 --date="$DATE"
echo "refresh ok for $DATE; restart the API process to drop the in-process cache"
