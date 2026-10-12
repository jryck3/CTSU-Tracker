#!/usr/bin/env python3
"""Locks for the CTSU automation Chrome profile and for publishing.

Two layers:
- A per-machine lock file outside the synced workspace. A dead pid is replaced.
  A live pid, including the older protocol_check.pid, keeps the lock.
- A synced marker in protocols/ so the other Mac does not start the same work.
  Syncthing copies it within seconds. A marker from another host older than
  MARKER_MAX_AGE is treated as stale.

Scopes: "chrome" (CTSU downloads, the default) and "publish" (rebuild_consumers.sh).

    ctsu_chrome_lock.py acquire PID LABEL [--scope publish]
    ctsu_chrome_lock.py release PID [--scope publish]
    ctsu_chrome_lock.py status [--scope publish]
    ctsu_chrome_lock.py host
"""
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LOCAL_DIR = Path.home() / "Library/Application Support/wvu-trial-tracker"
LEGACY = LOCAL_DIR / "protocol_check.pid"
PROTOCOLS = Path(__file__).resolve().parents[1] / "protocols"
MARKER_MAX_AGE = 3 * 60 * 60

SCOPES = {
    "chrome": (LOCAL_DIR / "ctsu_chrome.lock", PROTOCOLS / ".download_running.json"),
    "publish": (LOCAL_DIR / "publish.lock", PROTOCOLS / ".publish_running.json"),
}


def this_host():
    try:
        name = subprocess.run(
            ["scutil", "--get", "LocalHostName"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    return name or socket.gethostname().split(".")[0]


def alive(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def read_lock(lock):
    data = read_json(lock)
    if not isinstance(data, dict):
        return None
    try:
        pid = int(data.get("pid") or 0)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    return {"pid": pid, "label": str(data.get("label") or "ctsu-chrome")}


def legacy_pid():
    try:
        pid = int((LEGACY.read_text() or "").strip() or 0)
    except (OSError, ValueError):
        return 0
    return pid if alive(pid) else 0


def local_holder(scope):
    lock, _marker = SCOPES[scope]
    if scope == "chrome":
        old = legacy_pid()
        if old:
            return {"pid": old, "label": "wvu-protocol-request"}
    owner = read_lock(lock)
    if owner and alive(owner["pid"]):
        return owner
    return None


def remote_holder(scope):
    """The other Mac's marker, if it is recent enough to respect."""
    _lock, marker = SCOPES[scope]
    data = read_json(marker)
    if not isinstance(data, dict) or data.get("host") in (None, "", this_host()):
        return None
    try:
        started = datetime.fromisoformat(str(data.get("started_at")))
    except ValueError:
        return None
    age = (datetime.now(timezone.utc) - started).total_seconds()
    if age > MARKER_MAX_AGE:
        return None
    return {"host": data["host"], "label": data.get("label") or scope, "age_min": int(age // 60)}


def write_marker(scope, pid, label):
    _lock, marker = SCOPES[scope]
    if not marker.parent.is_dir():
        return
    payload = {
        "host": this_host(),
        "pid": pid,
        "label": label,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tmp = marker.with_name(marker.name + ".tmp")
    tmp.write_text(json.dumps(payload) + "\n")
    tmp.replace(marker)


def clear_marker(scope, pid):
    _lock, marker = SCOPES[scope]
    data = read_json(marker)
    if isinstance(data, dict) and data.get("host") == this_host() and int(data.get("pid") or 0) == pid:
        marker.unlink(missing_ok=True)


def acquire(pid, label, scope):
    lock, _marker = SCOPES[scope]
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    remote = remote_holder(scope)
    if remote:
        print(
            "%s is running on %s (%s, started %s min ago)."
            % (remote["label"], remote["host"], scope, remote["age_min"]),
            file=sys.stderr,
        )
        return 2
    owner = local_holder(scope)
    if owner and owner["pid"] != pid:
        print("In use by %s (pid %s)." % (owner["label"], owner["pid"]), file=sys.stderr)
        return 2
    replaced = ""
    if scope == "chrome" and LEGACY.exists() and legacy_pid() == 0:
        LEGACY.unlink(missing_ok=True)
    if lock.exists():
        stale = read_lock(lock)
        if stale and alive(stale["pid"]):
            write_marker(scope, pid, label)
            print("ok")
            return 0
        if stale:
            replaced = stale["label"]
        lock.unlink(missing_ok=True)
    payload = json.dumps({"pid": pid, "label": label}).encode()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        owner = local_holder(scope)
        who = owner["label"] if owner else "another job"
        print("In use by %s." % who, file=sys.stderr)
        return 2
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    write_marker(scope, pid, label)
    print("stale\t%s" % replaced if replaced else "ok")
    return 0


def release(pid, scope):
    lock, _marker = SCOPES[scope]
    owner = read_lock(lock)
    if owner and owner["pid"] == pid:
        lock.unlink(missing_ok=True)
    clear_marker(scope, pid)
    return 0


def status(scope):
    remote = remote_holder(scope)
    if remote:
        print("remote\t%s\t%s" % (remote["host"], remote["label"]))
        return 2
    owner = local_holder(scope)
    if not owner:
        print("free")
        return 0
    print("held\t%s\t%s" % (owner["pid"], owner["label"]))
    return 2


def main(argv):
    scope = "chrome"
    if "--scope" in argv:
        index = argv.index("--scope")
        scope = argv[index + 1]
        del argv[index:index + 2]
    if scope not in SCOPES:
        raise ValueError(scope)
    action = argv[1] if len(argv) > 1 else ""
    if action == "host":
        print(this_host())
        return 0
    if action == "status":
        return status(scope)
    if action == "acquire":
        return acquire(int(argv[2]), argv[3], scope)
    if action == "release":
        return release(int(argv[2]), scope)
    print("use status, host, acquire PID LABEL, or release PID [--scope chrome|publish]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(list(sys.argv)))
    except (IndexError, ValueError):
        print("use status, host, acquire PID LABEL, or release PID [--scope chrome|publish]", file=sys.stderr)
        raise SystemExit(1)
