#!/bin/bash
# Exercises the publish guard against a temporary git repo.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
. "$ROOT/scripts/publish_tree.sh"

if grep -n -- '--autostash' "$ROOT/scripts/rebuild_consumers.sh" "$ROOT/../WVU Trials Demo/scripts/monday_check.sh"; then
  echo "autostash is still present" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git -C "$tmp" init -q -b main
echo "one" > "$tmp/file.txt"
git -C "$tmp" add file.txt
GIT_AUTHOR_NAME="publish-test" GIT_AUTHOR_EMAIL="publish-test@example.com" \
  GIT_COMMITTER_NAME="publish-test" GIT_COMMITTER_EMAIL="publish-test@example.com" \
  git -C "$tmp" commit -q -m "start"
assert_clean_repo "$tmp"
echo "two" >> "$tmp/file.txt"
if assert_clean_repo "$tmp"; then
  echo "dirty tree was accepted" >&2
  exit 1
fi
echo "publish guard ok"
