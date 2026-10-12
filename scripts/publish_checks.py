#!/usr/bin/env python3
"""Checks run by rebuild_consumers.sh before anything is pushed.

Each check compares the new build with the last published copy (git HEAD in
that tracker's repository). Exit 0 passes. Exit 1 prints why and blocks the push.

    publish_checks.py briefs              # CTSU data/protocol_briefs.json
    publish_checks.py wvu PATH            # WVU Trials Demo folder, after enrich_details.py
    publish_checks.py worldwide PATH      # Worldwide RT Trials folder, after build.py --briefs-only
"""
import base64
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ("schema", "eligibility")
TOLERANCE = 0.05


def head_json(repo, rel):
    try:
        out = subprocess.run(["git", "-C", str(repo), "show", "HEAD:" + rel], capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    return json.loads(out)


def within(new, old, what):
    if old and abs(new - old) > TOLERANCE * old:
        return ["%s changed from %d to %d (more than %d%%)." % (what, old, new, TOLERANCE * 100)]
    return []


def briefs():
    path = ROOT / "data" / "protocol_briefs.json"
    try:
        new = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return ["protocol_briefs.json does not parse: %s" % exc]
    old = head_json(ROOT, "data/protocol_briefs.json") or {}
    problems = []
    for protocol, brief in old.items():
        if protocol not in new:
            problems.append("%s lost its brief." % protocol)
            continue
        locked = set(new[protocol].get("locked") or [])
        for key in SECTIONS:
            if brief.get(key) and not new[protocol].get(key) and key not in locked:
                problems.append("%s lost its %s without a review." % (protocol, key))
    return problems


def wvu_records(folder):
    text = (folder / "Data.gs").read_text()
    parts = re.findall(r'"([A-Za-z0-9+/=]+)"', text.split("var packed =", 1)[1].split(";", 1)[0])
    return json.loads(gzip.decompress(base64.b64decode("".join(parts))).decode("utf-8"))


def wvu(folder):
    folder = Path(folder)
    try:
        records = wvu_records(folder)
    except Exception as exc:
        return ["Data.gs payload does not decode: %s" % exc]
    old = head_json(folder, "data/trials.json") or []
    problems = within(len(records), len(old), "WVU trial count")
    had = {row["protocol"] for row in old if row.get("ctsu") and (row.get("details") or {}).get("kind") == "ctsu"}
    now = {row["protocol"] for row in records if row.get("ctsu") and (row.get("details") or {}).get("kind") == "ctsu"}
    for protocol in sorted(had - now):
        problems.append("WVU %s lost its CTSU brief." % protocol)
    return problems


def worldwide(folder):
    folder = Path(folder)
    try:
        new = json.loads((folder / "data" / "trials.json").read_text())["trials"]
    except Exception as exc:
        return ["Worldwide trials.json does not parse: %s" % exc]
    html = (folder / "docs" / "index.html").read_text()
    if "__DATA__" in html or len(html) < 100000:
        return ["Worldwide docs/index.html was not filled with data."]
    old = (head_json(folder, "data/trials.json") or {}).get("trials") or []
    problems = within(len(new), len(old), "Worldwide trial count")
    briefed_old = sum(1 for trial in old if (trial.get("brief") or {}).get("eligibility") or (trial.get("brief") or {}).get("schema"))
    briefed_new = sum(1 for trial in new if (trial.get("brief") or {}).get("eligibility") or (trial.get("brief") or {}).get("schema"))
    if briefed_old and briefed_new < (1 - TOLERANCE) * briefed_old:
        problems.append("Worldwide trials with a brief fell from %d to %d." % (briefed_old, briefed_new))
    return problems


def main(argv):
    kind = argv[1] if len(argv) > 1 else ""
    if kind == "briefs":
        problems = briefs()
    elif kind == "wvu":
        problems = wvu(argv[2])
    elif kind == "worldwide":
        problems = worldwide(argv[2])
    else:
        print(__doc__)
        return 2
    for line in problems:
        print(line)
    if not problems:
        print("%s checks passed." % kind)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
