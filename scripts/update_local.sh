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

protocol_code=0
if [ "${1:-}" = "--protocols" ]; then
  LOCK_PY="/usr/bin/python3"
  if "$LOCK_PY" scripts/ctsu_chrome_lock.py acquire $$ "ctsu-update-local" >/dev/null; then
    trap '"$LOCK_PY" scripts/ctsu_chrome_lock.py release $$' EXIT
    PORT=$(bash "$WORKSPACE/tools/launch_chrome_debug.sh" "${CTSU_SESSION_KEY:-ctsu-9fa22944}" | tail -1)
    "$PY" "$WORKSPACE/tools/chrome_browser.py" --port "$PORT" --focus open "https://www.ctsu.org/" >/dev/null 2>&1 || true
    "$PY" scripts/download_protocols.py --port "$PORT" --wait-minutes 60 || protocol_code=$?
    "$LOCK_PY" scripts/ctsu_chrome_lock.py release $$
    trap - EXIT
  else
    protocol_code=2
  fi
fi

"$PY" scripts/refresh.py --no-save
echo "Local dashboard: $(pwd)/dashboard/index.html"
exit "$protocol_code"
