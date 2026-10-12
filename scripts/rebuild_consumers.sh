#!/bin/bash
# Republish the three trackers from the CTSU protocol library.
#   CTSU:      commit data/protocol_briefs.json and data/protocol_library.json and push;
#              the push runs the page-only build in GitHub Actions.
#   Worldwide: build.py --briefs-only, commit, push; GitHub Pages serves docs/.
#   WVU:       enrich_details.py, commit, push, clasp push, then point the existing
#              web-app deployment at a new version so the /exec URL stays the same.
# Each tracker must pass scripts/publish_checks.py before anything is committed.
# Either Mac can run it; a publish lock keeps the two from publishing at once.
#
#   scripts/rebuild_consumers.sh [--if-stale] [--reason TEXT] [--no-push]
#
# --if-stale  republish only the trackers whose last publish used an older library.
# --no-push   build and check only. Nothing is committed, pushed, or deployed.
set -u
cd "$(dirname "$0")/.."
CTSU="$(pwd)"
PROJECTS="$(cd .. && pwd)"
WORKSPACE="$(cd ../.. && pwd)"
WW="$PROJECTS/Worldwide RT Trials"
WVU="$PROJECTS/WVU Trials Demo"
PY="$WORKSPACE/.venv/bin/python3"
SYS="/usr/bin/python3"
CLASP="$WVU/node_modules/.bin/clasp"
WVU_DEPLOYMENT="AKfycbwV3VELs_6p2oG_Ydd9qW63uuDF1T4vWTbEGhN4HFJyIGwuN-EpbD9CnCcwmFy7HU7kcg"
WVU_URL="https://script.google.com/macros/s/$WVU_DEPLOYMENT/exec"
STAMPS="protocols/.published_stamps.json"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

IF_STALE=0
PUSH=1
REASON="protocol library update"
while [ $# -gt 0 ]; do
  case "$1" in
    --if-stale) IF_STALE=1 ;;
    --no-push) PUSH=0 ;;
    --reason) REASON="${2:-$REASON}"; shift ;;
    *) echo "Unknown option $1" >&2; exit 64 ;;
  esac
  shift
done

HOST=$("$SYS" scripts/ctsu_chrome_lock.py host)
mkdir -p logs
exec >> "logs/publish.$HOST.log" 2>&1
echo ""
echo "== $(date "+%Y-%m-%d %H:%M %Z") on $HOST: $REASON"

FAILED=""
fail() {
  echo "FAILED: $1"
  FAILED="$FAILED $1"
}

if ! msg=$("$SYS" scripts/ctsu_chrome_lock.py acquire $$ "publish" --scope publish 2>&1); then
  echo "Skipped. $msg"
  exit 0
fi
trap '"$SYS" scripts/ctsu_chrome_lock.py release $$ --scope publish' EXIT

if [ ! -f "$STAMPS" ]; then
  echo '{}' > "$STAMPS"
fi

stamp_hash=$("$SYS" - << 'PY'
import json, sys
sys.path.insert(0, "scripts")
import protocol_library as lib
stamp = lib.library_stamp()
path = lib.ROOT / "data" / "protocol_library.json"
text = json.dumps(stamp, indent=1) + "\n"
if not path.exists() or path.read_text() != text:
    path.write_text(text)
print(stamp["hash"])
PY
)
if [ -z "$stamp_hash" ]; then
  echo "Could not read the protocol library."
  osascript -e 'display notification "Could not read the protocol library." with title "Tracker publish failed"' 2>/dev/null
  exit 1
fi
echo "Library $stamp_hash"

wvu_files_hash() {
  (cd "$WVU" && cat appsscript.json Code.gs Data.gs Index.html | shasum -a 256 | cut -c1-16)
}

published() {
  "$SYS" -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' "$STAMPS" "$1"
}

record() {
  "$SYS" - "$STAMPS" "$1" "$2" << 'PY'
import json, sys
path, key, value = sys.argv[1:]
data = json.load(open(path))
data[key] = value
json.dump(data, open(path, "w"), indent=1, sort_keys=True)
PY
}

needed() {
  [ "$IF_STALE" -eq 0 ] || [ "$(published "$1")" != "$stamp_hash" ]
}

# git_publish REPO_DIR MESSAGE PATH... : commit only PATHs, rebase on origin, push (one retry).
# Prints the pushed commit when it committed something, and nothing otherwise.
git_publish() {
  local dir="$1" message="$2"
  shift 2
  (
    cd "$dir" || exit 1
    committed=0
    git add -- "$@" || exit 1
    if git diff --cached --quiet -- "$@"; then
      echo "Nothing new to commit in $(basename "$dir")." >&2
    else
      git commit -q -m "$message" -- "$@" || exit 1
      committed=1
    fi
    for attempt in 1 2; do
      git pull -q --rebase --autostash >&2 || exit 1
      if git push -q >&2; then
        [ "$committed" -eq 1 ] && git rev-parse HEAD
        exit 0
      fi
      echo "Push attempt $attempt failed in $(basename "$dir")." >&2
    done
    exit 1
  )
}

CTSU_SHA=""
WW_SHA=""

# CTSU
if needed ctsu; then
  if ! "$SYS" scripts/publish_checks.py briefs; then
    fail ctsu
  elif [ "$PUSH" -eq 1 ]; then
    if CTSU_SHA=$(git_publish "$CTSU" "Protocol briefs: $REASON." data/protocol_briefs.json data/protocol_library.json); then
      record ctsu "$stamp_hash"
      echo "CTSU pushed ${CTSU_SHA:-nothing new}"
    else
      fail ctsu
    fi
  fi
else
  echo "CTSU already published from this library."
fi

# Worldwide
if needed worldwide; then
  if ! (cd "$WW" && git pull -q --rebase --autostash); then
    fail worldwide
  elif ! (cd "$WW" && "$PY" build.py --briefs-only); then
    fail worldwide
  elif ! "$SYS" scripts/publish_checks.py worldwide "$WW"; then
    fail worldwide
  elif [ "$PUSH" -eq 1 ]; then
    if WW_SHA=$(git_publish "$WW" "Protocol briefs from the CTSU library: $REASON." docs/index.html data/trials.json config/protocol_schemas.json); then
      record worldwide "$stamp_hash"
      echo "Worldwide pushed ${WW_SHA:-nothing new}"
    else
      fail worldwide
    fi
  fi
else
  echo "Worldwide already published from this library."
fi

# WVU
if needed wvu || [ "$(published wvu_files)" != "$(wvu_files_hash)" ]; then
  if ! (cd "$WVU" && "$PY" enrich_details.py); then
    fail wvu
  elif ! "$SYS" scripts/publish_checks.py wvu "$WVU"; then
    fail wvu
  elif [ "$PUSH" -eq 1 ]; then
    files_hash=$(wvu_files_hash)
    if ! git_publish "$WVU" "Trial data from the CTSU library: $REASON." Data.gs data/trials.json research/payload_sha256.txt >/dev/null; then
      fail wvu
    elif [ "$(published wvu_files)" = "$files_hash" ]; then
      record wvu "$stamp_hash"
      echo "WVU Apps Script already has these files."
    elif ! (cd "$WVU" && "$CLASP" push --force); then
      fail wvu
    elif ! deployed=$(cd "$WVU" && "$CLASP" update-deployment "$WVU_DEPLOYMENT" --description "$REASON" --json); then
      fail wvu
    else
      record wvu "$stamp_hash"
      record wvu_files "$files_hash"
      echo "WVU deployed: $(echo "$deployed" | tr -d '\n ')"
      code=$(curl -sL -o /tmp/wvu_publish_check.html -w "%{http_code}" "$WVU_URL")
      if [ "$code" = "200" ] && grep -q "Also on the CTSU tracker" /tmp/wvu_publish_check.html; then
        echo "WVU page answers at $WVU_URL"
      else
        fail "wvu-page(HTTP $code)"
      fi
    fi
  fi
else
  echo "WVU already published from this library."
fi

# Wait for GitHub to build what was pushed.
if [ -n "$CTSU_SHA" ]; then
  for _ in $(seq 1 30); do
    run=$(gh run list -R jryck3/CTSU-Tracker -w refresh.yml -c "$CTSU_SHA" -L 1 --json status,conclusion -q '.[0] | "\(.status) \(.conclusion)"' 2>/dev/null)
    case "$run" in
      "completed success") echo "CTSU Action finished."; break ;;
      completed*) fail "ctsu-action($run)"; break ;;
    esac
    sleep 20
  done
  case "$run" in completed*) ;; *) fail "ctsu-action(not finished: ${run:-none})" ;; esac
fi
if [ -n "$WW_SHA" ]; then
  for _ in $(seq 1 30); do
    build=$(gh api repos/jryck3/worldwide-rt-trials/pages/builds/latest -q '"\(.status) \(.commit)"' 2>/dev/null)
    if [ "$build" = "built $WW_SHA" ]; then
      echo "Worldwide Pages built."
      break
    fi
    case "$build" in errored*) fail "worldwide-pages($build)"; break ;; esac
    sleep 20
  done
  case "$build" in "built $WW_SHA"|errored*) ;; *) fail "worldwide-pages(not built: ${build:-none})" ;; esac
fi

if [ -n "$FAILED" ]; then
  osascript -e "display notification \"Failed:$FAILED. See CTSU logs/publish.$HOST.log.\" with title \"Tracker publish failed\"" 2>/dev/null
  echo "Done with failures:$FAILED"
  exit 1
fi
echo "Done."
