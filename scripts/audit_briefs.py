#!/usr/bin/env python3
"""Audit every CTSU study's protocol brief and RT classification.

For each study on data/studies.json it reports:
- whether a protocol is on file, and the manifest status when it is not
- brief defects of the kinds fixed by hand on October 10, 2026: table-of-contents
  text, schema text inside eligibility, joined lab columns, spaced-out
  RANDOMIZE letters, criteria that lost their leading "No", glued words
- for studies classed as not RT-related, radiotherapy that the protocol itself
  specifies (dose prescriptions and RT terms on the schema page)

Writes logs/brief_audit.json and prints a summary. Protocol text is not saved.

    python3 scripts/audit_briefs.py [--only S1931 EA2174] [--skip-pdf]
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import protocol_library as lib  # noqa: E402

OUT = lib.ROOT / "logs" / "brief_audit.json"

TOC = re.compile(r"\.{4,}|\bTable of Contents\b|\b\d+\.\d+\s+[A-Z][A-Za-z ]+\s\d{1,3}\b.*\b\d+\.\d+\s+[A-Z]|^\d+\.0\s+[A-Z ]{6,}\s*\d+", re.I)
SCHEMA_IN_TEXT = re.compile(r"\bSchema\b|Please refer to the full protocol|\bR\s+A\s+N\s+D\b|\bN D O M I\b|\b(?:[A-Z]\s){5,}", re.I)
LAB_JOIN = re.compile(r"(?:x|times)\s*(?:upper limit|ULN|institutional).{0,80}\b(?:Histolog|Documentation|Stage|Prior)\b", re.I)
LOST_NO = re.compile(r"^(?:known|prior|history of|active|current|concurrent|uncontrolled|planned|patients on|nonprescribed|prescribed|investigational|enrollment on)\b")
GLUED = re.compile(r"\b[a-z]{3,}(?:a|the|of|for|and)[A-Z][a-z]{2,}|\b(?:a|the)(?:complete|patient|participant)\b|\b\w+(?:mgthree|timesaday|forapsych|foracomplete)\b")
SPLIT_WORD = re.compile(r"\b(?:pa rticipants|system ic|week s|C isplatin|G emcitabine|multi -centre|non -inferiority)\b|\b[a-z]{2,} (?!(?:of|or|to|in|at|by|an|on|as|is|if|no|up|be|vs|a)\b)[a-z]{1,2}\b(?= [a-z]{3,}tion)")
PAGE_TAIL = re.compile(r"\s\d{2,3}$")
FOOTNOTE_GLUE = re.compile(r"\b(?:Arm|Step)\s+[A-Z]?\d{2,}\b|\bRev\.\s|\bAdd\d")

DOSE = re.compile(r"\b\d{1,3}(?:\.\d)?\s*(?:Gy|cGy)\b")
RT_TERM = re.compile(r"radiation therapy|radiotherapy|chemoradiation|chemoradiotherapy|\bSBRT\b|\bSABR\b|\bIMRT\b|brachytherapy|stereotactic radiosurgery|\bSRS\b|whole brain|\bTBI\b|total body irradiation|involved[- ]site|\bISRT\b|\bXRT\b", re.I)
PRIOR_RT = re.compile(r"prior|previous|history of|received|no radiation|not have had|excluded|within \d+ (?:days|weeks)", re.I)


def texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from texts(item)
    elif isinstance(value, dict):
        for key in ("label", "text", "item", "window", "note"):
            if isinstance(value.get(key), str):
                yield value[key]
        for item in value.get("arms") or []:
            yield from texts(item)


def brief_defects(brief):
    found = []
    elig = brief.get("eligibility") or []
    for index, item in enumerate(elig):
        if not isinstance(item, str):
            continue
        tags = []
        if TOC.search(item) or PAGE_TAIL.search(item) and len(item) < 70:
            tags.append("toc")
        if SCHEMA_IN_TEXT.search(item):
            tags.append("schema-in-eligibility")
        if LAB_JOIN.search(item):
            tags.append("lab-column-joined")
        if LOST_NO.match(item):
            tags.append("lost-no")
        if len(item) < 12:
            tags.append("fragment")
        if len(item) > 600:
            tags.append("run-on")
        for tag in tags:
            found.append({"section": "eligibility", "index": index, "tag": tag, "text": item[:160]})
    for step in brief.get("schema") or []:
        for text in texts(step):
            tags = []
            if TOC.search(text):
                tags.append("toc")
            if re.search(r"\b(?:[A-Z]\s){4,}[A-Z]\b|\bN D O M I\b|[↓→]{1}\s*[↓→]", text):
                tags.append("spaced-letters-or-arrows")
            if FOOTNOTE_GLUE.search(text):
                tags.append("footnote-glued")
            for tag in tags:
                found.append({"section": "schema", "tag": tag, "text": text[:160]})
    for section in ("schema", "eligibility", "pretreatment", "during", "followup"):
        for text in texts(brief.get(section) or []):
            if GLUED.search(text) or SPLIT_WORD.search(text):
                found.append({"section": section, "tag": "glued-or-split-words", "text": text[:160]})
                break
    if not elig:
        found.append({"section": "eligibility", "tag": "missing"})
    if not brief.get("schema"):
        found.append({"section": "schema", "tag": "missing"})
    return found


def pdf_rt_signal(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    doses, schema_terms, treatment_terms = Counter(), Counter(), Counter()
    in_eligibility = False
    for index, page in enumerate(reader.pages[:120]):
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        upper = text.upper()
        if re.search(r"ELIGIBILITY CRITERIA", upper) and "TABLE OF CONTENTS" not in upper:
            in_eligibility = True
        if re.search(r"^\s*(?:5|6|7)\.0?\s+(?:TREATMENT|STUDY TREATMENT|TREATMENT PLAN)", text, re.M | re.I):
            in_eligibility = False
        is_schema = index < 30 and re.search(r"^\s*(?:STUDY |TREATMENT )?SCHEMA\b", text, re.M | re.I)
        for line in text.splitlines():
            if PRIOR_RT.search(line):
                continue
            for match in DOSE.finditer(line):
                if not in_eligibility:
                    doses[match.group(0).replace(" ", "")] += 1
            for match in RT_TERM.finditer(line):
                term = match.group(0).lower()
                if is_schema:
                    schema_terms[term] += 1
                elif not in_eligibility:
                    treatment_terms[term] += 1
    return {
        "doses": dict(doses.most_common(6)),
        "schema_rt_terms": dict(schema_terms.most_common(6)),
        "treatment_rt_terms": dict(treatment_terms.most_common(6)),
    }


def rt_flag(signal):
    dose_hits = sum(signal["doses"].values())
    if signal["schema_rt_terms"]:
        return "rt-on-schema"
    if dose_hits >= 5 and sum(signal["treatment_rt_terms"].values()) >= 10:
        return "rt-prescribed"
    if dose_hits >= 2 or sum(signal["treatment_rt_terms"].values()) >= 15:
        return "check"
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--skip-pdf", action="store_true", help="Brief checks only")
    args = parser.parse_args()
    studies = json.loads(lib.STUDIES.read_text())["studies"]
    manifest, briefs = lib.manifest(), lib.briefs()
    wanted = set(args.only or [])
    rows = []
    for study in studies:
        protocol = study["protocol"]
        if wanted and protocol not in wanted:
            continue
        pdf = lib.current_pdf(protocol)
        entry = manifest.get(protocol) or {}
        brief = briefs.get(protocol) or {}
        row = {
            "protocol": protocol,
            "lead": study.get("lead"),
            "status": study.get("status"),
            "rt_role": study.get("rt_role"),
            "rt_related": bool(study.get("rt_related")),
            "pdf": pdf.name if pdf else None,
            "manifest_status": entry.get("status"),
            "manifest_note": entry.get("note"),
            "reviewed": brief.get("reviewed"),
            "defects": brief_defects(brief) if pdf else [],
        }
        if pdf and not args.skip_pdf and not row["rt_related"]:
            try:
                row["rt_signal"] = pdf_rt_signal(pdf)
                row["rt_flag"] = rt_flag(row["rt_signal"])
            except Exception as exc:
                row["rt_flag"] = "pdf-error: %s" % exc
        rows.append(row)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    non = [row for row in rows if not row["rt_related"]]
    with_pdf = [row for row in non if row["pdf"]]
    tags = Counter(defect["tag"] for row in with_pdf for defect in row["defects"])
    flagged = [row["protocol"] for row in with_pdf if any(d["tag"] != "missing" for d in row["defects"])]
    print(json.dumps({
        "studies": len(rows),
        "non_rt": len(non),
        "non_rt_with_protocol": len(with_pdf),
        "non_rt_without_protocol": Counter(row["manifest_status"] or "never checked" for row in non if not row["pdf"]),
        "non_rt_defect_tags": tags,
        "non_rt_briefs_with_defects": len(flagged),
        "rt_flags": Counter(row.get("rt_flag") or "none" for row in with_pdf),
        "rt_flagged": {row["protocol"]: row["rt_flag"] for row in with_pdf if row.get("rt_flag")},
    }, indent=1, default=dict))


if __name__ == "__main__":
    main()
