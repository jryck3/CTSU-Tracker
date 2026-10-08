#!/bin/bash
# Pull the shared accrual history from GitHub and rebuild the local dashboard
# (dashboard/index.html), which adds protocol-on-file status. Pass --protocols
# to also check CTSU for amended protocol documents; that needs the automation
# Chrome running and signed in (see README.md).
set -euo pipefail
cd "$(dirname "$0")/.."
WORKSPACE="$(cd ../.. && pwd)"
PY="$WORKSPACE/.venv/bin/python3"

git pull --rebase --quiet || echo "git pull failed; building from the local copy of the history" >&2

if [ "${1:-}" = "--protocols" ]; then
  PORT=$(bash "$WORKSPACE/tools/launch_chrome_debug.sh" "${CTSU_SESSION_KEY:-ctsu-9fa22944}" | tail -1)
  "$PY" scripts/download_protocols.py --port "$PORT"
fi

"$PY" scripts/refresh.py --no-save
echo "Local dashboard: $(pwd)/dashboard/index.html"
