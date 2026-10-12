#!/usr/bin/env python3
"""Apply hand-reviewed protocol briefs from .tmp/brief_review/out/ to data/protocol_briefs.json.

Each review file holds sections rewritten from the current protocol PDF. This
script checks them, replaces those sections, deletes the sections listed in
"drop", records the review, and locks the reviewed and dropped sections so
the automatic extractors do not refill them. A new protocol version later
lists the locked sections under needs_review.

Radiotherapy decisions go to logs/rt_review.json for config/rt_overrides.json.

    python3 scripts/merge_brief_reviews.py [--dry-run] [--only S1931]
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protocol_library as lib  # noqa: E402

REVIEWS = lib.ROOT / ".tmp" / "brief_review" / "out"
RT_LOG = lib.ROOT / "logs" / "rt_review.json"
SECTIONS = ("schema", "eligibility", "pretreatment", "during", "followup", "calendar", "specimens", "submission", "amendments")
ROWS = ("pretreatment", "during", "followup", "calendar", "specimens")
DASH = re.compile(r"\s[\u2014\u2013]\s|\u2014")


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def problems(review, manifest):
    found = []
    protocol = review.get("protocol")
    entry = manifest.get(protocol) or {}
    if review.get("version_checked") and entry.get("version") and review["version_checked"] != entry["version"]:
        found.append("version %s is not the current %s" % (review["version_checked"], entry["version"]))
    schema = review.get("schema")
    if schema is not None:
        if not isinstance(schema, list) or not all(isinstance(step, dict) and step.get("label") for step in schema):
            found.append("schema steps need a label")
        for step in schema or []:
            for arm in step.get("arms") or []:
                if not isinstance(arm, dict) or not arm.get("label"):
                    found.append("schema arm needs a label")
    elig = review.get("eligibility")
    if elig is not None:
        if not isinstance(elig, list) or not all(isinstance(item, str) and item.strip() for item in elig):
            found.append("eligibility must be a list of sentences")
        elif not 3 <= len(elig) <= 30:
            found.append("eligibility has %d items" % len(elig))
    for key in ROWS:
        rows = review.get(key)
        if rows is not None and not all(isinstance(row, dict) and row.get("item") for row in rows):
            found.append("%s rows need an item" % key)
    for key in SECTIONS:
        if any(DASH.search(text) for text in strings(review.get(key))):
            found.append("%s uses a dash as punctuation" % key)
    return found


def undash(value):
    if isinstance(value, str):
        return re.sub(r"\s*\u2014\s*", ", ", re.sub(r"\s\u2013\s", ", ", value))
    if isinstance(value, list):
        return [undash(item) for item in value]
    if isinstance(value, dict):
        return {key: undash(item) for key, item in value.items()}
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    briefs = json.loads(lib.BRIEFS.read_text())
    manifest = lib.manifest()
    rt_log = json.loads(RT_LOG.read_text()) if RT_LOG.exists() else {}
    today = date.today().isoformat()
    applied, held = [], {}
    for path in sorted(REVIEWS.glob("*.json")):
        try:
            review = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            held[path.stem] = ["not valid JSON: %s" % exc]
            continue
        protocol = review.get("protocol") or path.stem
        review["protocol"] = protocol
        if args.only and protocol not in args.only:
            continue
        issues = problems(review, manifest)
        hard = [issue for issue in issues if "dash" not in issue]
        if hard:
            held[protocol] = issues
            continue
        review = undash(review)
        brief = dict(briefs.get(protocol) or {})
        written = [key for key in SECTIONS if review.get(key)]
        dropped = [key for key in review.get("drop") or [] if key in SECTIONS and key not in written]
        for key in written:
            brief[key] = review[key]
        for key in dropped:
            brief.pop(key, None)
        if "schema" in written:
            brief.pop("schema_source", None)
        brief.pop("needs_review", None)
        brief.pop("protocol_unavailable", None)
        locked = set(brief.get("locked") or []) | set(written) | set(dropped)
        brief["locked"] = sorted(locked)
        brief["reviewed"] = {"date": today, "version": review.get("version_checked") or brief.get("version_date"), "by": "hand, from the protocol PDF"}
        if review.get("notes"):
            brief["reviewed"]["notes"] = review["notes"]
        briefs[protocol] = brief
        if review.get("rt"):
            rt_log[protocol] = dict(review["rt"], checked=today)
        applied.append((protocol, written, dropped))
    if not args.dry_run:
        lib.BRIEFS.write_text(json.dumps(briefs, indent=1, ensure_ascii=False) + "\n")
        RT_LOG.parent.mkdir(exist_ok=True)
        RT_LOG.write_text(json.dumps(rt_log, indent=1, ensure_ascii=False) + "\n")
    for protocol, written, dropped in applied:
        print("%s: wrote %s%s" % (protocol, ", ".join(written) or "nothing", "; dropped " + ", ".join(dropped) if dropped else ""))
    for protocol, issues in held.items():
        print("HELD %s: %s" % (protocol, "; ".join(issues)))
    rt_yes = sorted(p for p, v in rt_log.items() if v.get("protocol_specified_rt"))
    print(json.dumps({"applied": len(applied), "held": len(held), "rt_specified": rt_yes}))


if __name__ == "__main__":
    main()
