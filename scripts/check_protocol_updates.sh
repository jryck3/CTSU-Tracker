#!/bin/bash
# Weekly check of the current CTSU protocol document for every study on the list.
# Needs the automation Chrome signed in with ID.me. If the session is signed
# out, this records that in logs/protocol_changes.md and opens the CTSU login.
set -u
cd "$(dirname "$0")/.."
WORKSPACE="$(cd ../.. && pwd)"
PY="$WORKSPACE/.venv/bin/python3"
mkdir -p logs

"$PY" scripts/refresh.py --no-save --skip-ctgov || echo "Public CTSU list refresh failed; checking the study list already on disk." >&2

PORT=$(bash "$WORKSPACE/tools/launch_chrome_debug.sh" "${CTSU_SESSION_KEY:-ctsu-9fa22944}" | tail -1)
err=$(mktemp)
set +e
"$PY" scripts/download_protocols.py --port "$PORT" 2>"$err"
code=$?
set -e
if [ -s "$err" ]; then
  cat "$err" >&2
fi
if [ "$code" -ne 0 ]; then
  stamp=$(date "+%Y-%m-%d %H:%M %Z")
  {
    echo ""
    echo "## $stamp"
    echo ""
    echo "Protocol check did not finish. Sign in with ID.me in the automation Chrome, then rerun scripts/check_protocol_updates.sh."
    echo ""
  } >> logs/protocol_changes.md
  if grep -q "Not signed in" "$err"; then
    "$PY" "$WORKSPACE/tools/chrome_browser.py" --port "$PORT" --focus open "https://ctsu.cancer.gov/" || true
  fi
fi
rm -f "$err"
exit "$code"
