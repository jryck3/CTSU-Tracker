#!/bin/bash
# Guards for tracker publishes. Source this file. Do not execute it.
# A scheduled publish uses the clean checkout named by TRACKER_CHECKOUT_ROOT
# in ~/.config/ai-workspace/machine.env. That directory is outside Syncthing.
# The Syncthing working tree is never the tree that gets committed or deployed.

tracker_machine_env() {
  local env_file="${HOME}/.config/ai-workspace/machine.env"
  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
  fi
}

assert_clean_repo() {
  local dir="$1"
  local dirty
  dirty="$(git -C "$dir" status --porcelain)"
  if [ -n "$dirty" ]; then
    echo "Refusing to publish ${dir}. The working tree is dirty:" >&2
    echo "$dirty" >&2
    return 1
  fi
}

require_publish_checkout() {
  local name="$1"
  local dir
  tracker_machine_env
  if [ -z "${TRACKER_CHECKOUT_ROOT:-}" ]; then
    echo "Refusing to publish. Set TRACKER_CHECKOUT_ROOT in ~/.config/ai-workspace/machine.env to a directory outside Syncthing with clean checkouts of the tracker repos." >&2
    return 1
  fi
  dir="${TRACKER_CHECKOUT_ROOT}/${name}"
  if [ ! -d "$dir/.git" ] && [ ! -f "$dir/.git" ]; then
    echo "Publish checkout is missing: $dir" >&2
    return 1
  fi
  assert_clean_repo "$dir" || return 1
  printf '%s\n' "$dir"
}

sync_publish_checkout() {
  local dir="$1"
  local branch
  assert_clean_repo "$dir" || return 1
  git -C "$dir" fetch --quiet origin || return 1
  branch="$(git -C "$dir" rev-parse --abbrev-ref HEAD)"
  if [ "$branch" != "main" ]; then
    echo "Refusing to publish ${dir} from branch ${branch}. The publish checkout must be on main." >&2
    return 1
  fi
  git -C "$dir" merge --ff-only origin/main || return 1
  git -C "$dir" rev-parse HEAD
}

git_pull_rebase_clean() {
  local dir="$1"
  if ! git -C "$dir" diff --quiet || ! git -C "$dir" diff --cached --quiet; then
    echo "Refusing to rebase ${dir}. Tracked changes are still uncommitted." >&2
    return 1
  fi
  git -C "$dir" pull --rebase --no-autostash
}

link_ctsu_library() {
  local synced="$1"
  local checkout="$2"
  if [ ! -e "$checkout/protocols" ] && [ -d "$synced/protocols" ]; then
    ln -s "$synced/protocols" "$checkout/protocols"
  fi
  mkdir -p "$checkout/data"
  if [ ! -e "$checkout/data/studies.json" ] && [ -f "$synced/data/studies.json" ]; then
    ln -s "$synced/data/studies.json" "$checkout/data/studies.json"
  fi
}
