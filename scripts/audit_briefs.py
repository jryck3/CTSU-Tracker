#!/usr/bin/env python3
"""Audit every CTSU study's protocol brief and RT classification.

For each study on data/studies.json it reports:
- whether a protocol is on file, and the manifest status when it is not
- brief defects of the kinds fixed by hand on October 10, 2026: table-of-contents
  text, schema text inside eligibility, joined lab columns, spaced-out
  RANDOMIZE letters, criteria that lost their leading "No", glued words
- schema and eligibility failures of the S2511 kind: repeated or empty arms,
  objectives prose inside the schema, day-counting boilerplate kept as a
  criterion, a deleted "a", a section letter glued onto the previous
  criterion, and eligibility that stops before a later registration step
  still present in the protocol
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
FRAG_ARM = re.compile(r"^(?:\)|\.|,|versus\b|who\b|per protocol\b)", re.I)
OBJECTIVES_IN_SCHEMA = re.compile(r"\bprimary objectives?\b|\b1\.0\s+objectives\b|\bversus those who\b", re.I)
BOILER_FIRST = re.compile(r"falls onaweekend|falls on a weekend|weekend or holiday|NCI policy does not allow|considered Day 0", re.I)
DELETED_A = re.compile(
    r"\b(?:onaweekend|ofasoft|ofadistant|biopsyametastatic|byasurgeon|areagood|foralimb|Asapart|haveaprimary|"
    r"ona[a-z]{4,}|ofas[a-z]{3,}|byas[a-z]{4,}|foral[a-z]{3,})\b"
)
SECTION_GLUE = re.compile(r"\b[a-e]\.\s+(?:Disease|Prior/?Concurrent|Clinical|Additional|Regulatory)\b")
FOOTNOTE_ITEM = re.compile(r"\b[A-Za-z]{3,}\s[a-z]$")
LATER_STEP_LINE = re.compile(
    r"^(?:\d+(?:\.\d+)+\.?\s+)?Registration\s+Step\s+[2-9]\b"
    r"|^Step\s+[2-9]\s*[-–:]\s*(?:Cohort|Registration|Randomization)\b",
    re.I,
)
BRIEF_LATER = re.compile(r"\bStep\s+[2-9]\b", re.I)
SCHEMA_FURNITURE = re.compile(
    r"footnote|detailing|recommended|paragraph|confidential|alliance|oncology|version|update|protocol",
    re.I,
)
ELIG_START = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?ELIGIBILITY CRITERIA\b", re.I)
ELIG_STOP = re.compile(r"^\s*(?:6\.0|7\.0)\s+[A-Z]|^\s*STRATIFICATION\b|^\s*TREATMENT PLAN\b", re.I)
SCHEMA_START = re.compile(r"^\s*(?:EXPERIMENTAL DESIGN SCHEMA|STUDY SCHEMA|TREATMENT SCHEMA|SCHEMA)\b", re.I)
SCHEMA_STOP = re.compile(r"^\s*1\.0\s+[A-Z]|^\s*OBJECTIVES\b", re.I)

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
    found.extend(format_defects(brief))
    return found


def format_defects(brief):
    """Failures the October 10 patterns miss: a flowchart read out of order,
    objectives prose turned into arms, and eligibility cut off or glued."""
    found = []
    schema = brief.get("schema") or []
    arms = [arm for step in schema for arm in (step.get("arms") or [])]
    labels = [arm.get("label") or "" for arm in arms]
    if labels and len(labels) != len(set(labels)):
        found.append({"section": "schema", "tag": "duplicate-arm-labels", "text": ", ".join(labels[:8])})
    for arm in arms:
        text = (arm.get("text") or "").strip()
        if len(text) < 8 or FRAG_ARM.match(text):
            found.append({
                "section": "schema",
                "tag": "fragment-arm",
                "text": "%s: %s" % (arm.get("label") or "", text[:80]),
            })
            break
    schema_blob = " ".join(texts({"schema": schema}))
    if OBJECTIVES_IN_SCHEMA.search(schema_blob):
        found.append({"section": "schema", "tag": "objectives-in-schema", "text": schema_blob[:160]})
    elig = [item for item in (brief.get("eligibility") or []) if isinstance(item, str)]
    if elig and BOILER_FIRST.search(elig[0]):
        found.append({"section": "eligibility", "tag": "boilerplate-first", "text": elig[0][:160]})
    for section in ("schema", "eligibility", "pretreatment", "during", "followup"):
        for text in texts(brief.get(section) or []):
            if DELETED_A.search(text):
                found.append({"section": section, "tag": "deleted-a", "text": text[:160]})
                break
    for item in elig:
        if SECTION_GLUE.search(item) and len(item) > 80:
            found.append({"section": "eligibility", "tag": "section-header-glued", "text": item[:160]})
            break
    for section in ("pretreatment", "during", "followup"):
        for row in brief.get(section) or []:
            item = row.get("item") or ""
            if FOOTNOTE_ITEM.search(item) and len(item) < 48:
                found.append({"section": section, "tag": "footnote-on-row", "text": item[:160]})
                break
    return found


def _page_text(page):
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


def pdf_format_check(path, brief):
    """Compare the brief with the schema page and the eligibility section.

    A later registration step in the protocol that the brief never mentions is
    the S2511 cutoff. The opening schema words are a check that the brief is
    still about the same page.
    """
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    found = []
    schema_words = []
    elig_text = []
    in_schema = False
    in_elig = False
    for index, page in enumerate(reader.pages[:40]):
        text = _page_text(page)
        if "TABLE OF CONTENTS" in text.upper() and text.upper().count("...") > 3:
            continue
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        for line in lines:
            if not in_schema and index < 20 and SCHEMA_START.match(line) and len(line) < 48:
                in_schema = True
                continue
            if in_schema:
                if SCHEMA_STOP.match(line):
                    in_schema = False
                elif len(schema_words) < 40 and not SCHEMA_FURNITURE.search(line):
                    schema_words.extend(word for word in re.findall(r"[A-Za-z]{6,}", line))
            if not in_elig and ELIG_START.match(line) and len(line) < 120:
                in_elig = True
                continue
            if in_elig:
                if ELIG_STOP.match(line):
                    in_elig = False
                    break
                if LATER_STEP_LINE.match(line):
                    elig_text.append(line)
        if elig_text and not in_elig:
            break
    brief_schema = " ".join(texts(brief.get("schema") or [])).lower()
    if schema_words and brief.get("schema"):
        distinctive = []
        for word in schema_words:
            low = word.lower()
            if SCHEMA_FURNITURE.search(low):
                continue
            if low not in distinctive and low not in {"protocol", "version", "page", "schema", "participants", "participant", "section", "summary", "dosing", "details"}:
                distinctive.append(low)
        sample = distinctive[:8]
        hits = sum(1 for word in sample if word in brief_schema)
        if len(sample) >= 4 and hits == 0:
            found.append({
                "section": "schema",
                "tag": "schema-opening-mismatch",
                "text": " ".join(sample),
            })
    brief_elig = " ".join(item for item in (brief.get("eligibility") or []) if isinstance(item, str))
    if elig_text and not BRIEF_LATER.search(brief_elig):
        found.append({
            "section": "eligibility",
            "tag": "eligibility-stops-early",
            "text": elig_text[0][:160],
        })
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
    parser.add_argument("--format", action="store_true", help="Schema and eligibility checks only. Skip the radiotherapy scan.")
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
        if pdf and not args.skip_pdf:
            try:
                row["defects"].extend(pdf_format_check(pdf, brief))
            except Exception as exc:
                row["defects"].append({"section": "pdf", "tag": "pdf-error", "text": str(exc)[:160]})
        if pdf and not args.skip_pdf and not args.format and not row["rt_related"]:
            try:
                row["rt_signal"] = pdf_rt_signal(pdf)
                row["rt_flag"] = rt_flag(row["rt_signal"])
            except Exception as exc:
                row["rt_flag"] = "pdf-error: %s" % exc
        rows.append(row)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    on_file = [row for row in rows if row["pdf"]]
    missing_pdf = [row for row in rows if not row["pdf"]]
    tags = Counter(defect["tag"] for row in on_file for defect in row["defects"])
    queue = []
    for row in on_file:
        seen = []
        for defect in row["defects"]:
            if defect["tag"] not in seen:
                seen.append(defect["tag"])
        if seen:
            queue.append({"protocol": row["protocol"], "reviewed": bool(row.get("reviewed")), "tags": seen})
    print(json.dumps({
        "studies": len(rows),
        "with_protocol": len(on_file),
        "without_protocol": Counter(row["manifest_status"] or "never checked" for row in missing_pdf),
        "defect_tags": tags,
        "flagged": len(queue),
        "queue": queue,
    }, indent=1, default=dict))


if __name__ == "__main__":
    main()
