#!/bin/bash
# Confirm a Pages build for SHA, then require the live manifest hash.
# Usage: wait_for_pages.sh owner/repo SHA MANIFEST_URL LOCAL_MANIFEST
set -eu
REPO="${1:?repo}"
SHA="${2:?sha}"
URL="${3:?manifest url}"
LOCAL="${4:?local manifest}"
expected="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["content_hash"])' "$LOCAL")"
built=""
for _ in $(seq 1 30); do
  line="$(gh api "repos/${REPO}/pages/builds?per_page=5" --jq ".[] | select(.commit[0:40]==\"${SHA}\") | .status" 2>/dev/null | head -n 1 || true)"
  if [ "$line" = "built" ]; then
    built=yes
    break
  fi
  if [ "$line" = "errored" ]; then
    echo "Pages build errored for ${SHA}" >&2
    exit 1
  fi
  sleep 20
done
if [ "$built" != "yes" ]; then
  echo "Pages build for ${SHA} did not finish" >&2
  exit 1
fi
live="$(curl -fsSL "$URL" | python3 -c 'import json,sys; print(json.load(sys.stdin)["content_hash"])')"
if [ "$live" != "$expected" ]; then
  echo "Live export hash ${live} does not match ${expected}" >&2
  exit 1
fi
echo "Live ${REPO} ${SHA} matches ${expected}"
