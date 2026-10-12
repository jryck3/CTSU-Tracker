#!/bin/bash
# Sunday check of the current CTSU protocol document for every study on the list.
# Either Mac can run it. It skips when the other Mac finished a full check in
# the last 12 hours or is running one now. It opens https://www.ctsu.org/ in the
# debugging automation Chrome and waits up to 60 minutes for the ID.me sign-in.
# It never types credentials, and Chrome stays open between sign-in and download.
# After downloads it refills the protocol briefs and publishes all three trackers.
#
#   scripts/check_protocol_updates.sh [--force]
set -u
cd "$(dirname "$0")/.."
WORKSPACE="$(cd ../.. && pwd)"
PY="$WORKSPACE/.venv/bin/python3"
LOCK_PY="/usr/bin/python3"
HOST=$("$LOCK_PY" scripts/ctsu_chrome_lock.py host)
LAST="protocols/.last_full_check.json"
mkdir -p logs
exec >> "logs/protocol_check.$HOST.log" 2>&1
echo ""
echo "== $(date "+%Y-%m-%d %H:%M %Z") on $HOST"

note() {
  {
    echo ""
    echo "## $(date "+%Y-%m-%d %H:%M %Z") ($HOST)"
    echo ""
    echo "$1"
    echo ""
  } >> logs/protocol_changes.md
}

if [ "${1:-}" != "--force" ] && [ -f "$LAST" ]; then
  recent=$("$LOCK_PY" - "$LAST" << 'PY'
import json, sys
from datetime import datetime, timezone
try:
    data = json.load(open(sys.argv[1]))
    age = datetime.now(timezone.utc) - datetime.fromisoformat(data["finished_at"])
    print("%s %d" % (data.get("host", "?"), age.total_seconds() // 3600) if age.total_seconds() < 12 * 3600 else "")
except Exception:
    print("")
PY
)
  if [ -n "$recent" ]; then
    echo "Skipped. ${recent% *} finished a full check ${recent#* } h ago."
    exit 0
  fi
fi

"$PY" scripts/refresh.py --no-save --skip-ctgov || echo "Public CTSU list refresh failed; checking the study list already on disk." >&2

if ! msg=$("$LOCK_PY" scripts/ctsu_chrome_lock.py acquire $$ "ctsu-full-check" 2>&1); then
  echo "$msg"
  note "Protocol check did not run on $HOST. $msg"
  exit 2
fi
trap '"$LOCK_PY" scripts/ctsu_chrome_lock.py release $$' EXIT

PORT=$(bash "$WORKSPACE/tools/launch_chrome_debug.sh" "${CTSU_SESSION_KEY:-ctsu-9fa22944}" | tail -1)
if [ -z "${PORT:-}" ]; then
  note "Protocol check did not run on $HOST. The automation Chrome did not start."
  exit 1
fi
"$PY" "$WORKSPACE/tools/chrome_browser.py" --port "$PORT" --focus open "https://www.ctsu.org/" >/dev/null 2>&1 || true

summary=$(mktemp)
"$PY" scripts/download_protocols.py --port "$PORT" --wait-minutes 60 --summary-json "$summary"
code=$?
if [ "$code" -eq 2 ]; then
  note "Protocol check did not run on $HOST. No ID.me sign-in within 60 minutes. Rerun scripts/check_protocol_updates.sh --force after signing in."
  rm -f "$summary"
  exit 2
fi
if [ "$code" -ne 0 ]; then
  note "Protocol check stopped with an error on $HOST. See logs/protocol_check.$HOST.log."
  rm -f "$summary"
  exit "$code"
fi

"$LOCK_PY" - "$LAST" "$HOST" << 'PY'
import json, sys
from datetime import datetime, timezone
json.dump({"host": sys.argv[2], "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
          open(sys.argv[1], "w"))
PY

changed=$("$LOCK_PY" -c 'import json,sys; s=json.load(open(sys.argv[1])); print(" ".join(sorted(set(s["downloaded"] + s["memos"]))))' "$summary")
rm -f "$summary"
"$LOCK_PY" scripts/ctsu_chrome_lock.py release $$
trap - EXIT

if [ -n "$changed" ]; then
  echo "New protocol versions: $changed"
  # shellcheck disable=SC2086
  "$PY" scripts/extract_protocol_briefs.py --only $changed
  bash scripts/rebuild_consumers.sh --reason "protocol check: $changed"
else
  echo "No protocol changed."
  bash scripts/rebuild_consumers.sh --if-stale --reason "protocol check"
fi
