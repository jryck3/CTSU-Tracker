#!/usr/bin/env python3
"""Fill protocol brief sections from the local protocol PDFs.

Reads the newest PDF in protocols/<ID>/ and updates data/protocol_briefs.json.
Schema, eligibility, pre-treatment assessments, and amendments already written
by hand are kept. Empty sections, plus assessments during treatment and
assessments in follow-up, are filled from the PDF. A section the PDF does not
contain is left out.

Usage:
    python3 scripts/extract_protocol_briefs.py [--only NRG-GU015 S2427] [--debug]
"""
import argparse
import json
import re
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PROTOCOLS = ROOT / "protocols"
BRIEFS = ROOT / "data" / "protocol_briefs.json"

HAND_KEYS = ("schema", "eligibility", "pretreatment", "amendments")

NEXT_SECTION = re.compile(
    r"^(?:"
    r"\d+\.\s+[A-Z][A-Z \-]{6,}|"
    r"\d+\.\d+\s+[A-Z][A-Z \-]{8,}|"
    r"4\.[123]\s+(?:PRE|ASSESSMENTS)|"
    r"5\.0\s+[A-Z]|6\.0\s+[A-Z]|7\.0\s+[A-Z]"
    r")"
)
ELIG_HEAD = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:ELIGIBILITY(?: AND INELIGIBILITY)? CRITERIA|Eligibility Criteria|PATIENT ELIGIBILITY)\b",
    re.I,
)
SCHEMA_HEAD = re.compile(r"^(?:EXPERIMENTAL DESIGN SCHEMA|SCHEMA)\b", re.I)
PRE_HEAD = re.compile(r"^4\.1\s+PRE-?\s*TREATMENT ASSESSMENTS\b", re.I)
DURING_HEAD = re.compile(r"^4\.2\s+ASSESSMENTS DURING\b", re.I)
FOLLOW_HEAD = re.compile(r"^4\.3\s+ASSESSMENTS IN FOLLOW", re.I)
CAL_HEAD = re.compile(
    r"^(?:\d+(?:\.\d+)*\s+)?(?:STUDY CALENDAR|PARTICIPANT EVALUATION FLOWSHEET|REQUIRED EVALUATIONS)\b",
    re.I,
)
HISTORY_LINE = re.compile(
    r"^(Pre-activation(?:\s+revision)?|Initial(?:\s+Version)?|Amendment\s+\d+|Update\s+\d+)\s+"
    r"([A-Z][a-z]+ \d{1,2},?\s+\d{4})\b",
    re.I,
)
BOILER = re.compile(
    r"exceptions to eligibility|cannot be considered eligible|questions concerning eligibility|"
    r"use the spaces provided|for each criterion requiring|potential eligibility issues|"
    r"nci policy does not allow|eligibility checklist|confirm a patient.s eligibility|"
    r"there will be no exceptions|carefully considered|fulfill its objectives|"
    r"appropriate candidate for this trial|adequate health that permits|"
    r"calculating days of tests|day a test or measurement is done|"
    r"fall on a weekend|cockcroft-gault|creatinine clearance =",
    re.I,
)
ARM = re.compile(r"^(Arm\s*\d+[a-z]?|ARM\s*\d+[a-z]?)\b[:\-]?\s*(.*)$")
CRITERION = re.compile(
    r"^(?:[\u2022\u25cf\u25a0\u25cb\-\*]|\d+(?:\.\d+){1,3}|[A-Z]\.)\s+\S"
)


def pretty_date(text):
    match = re.match(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text.strip())
    if not match:
        return clean(text)
    return f"{match.group(1).title()} {int(match.group(2))}, {match.group(3)}"


def clean(text):
    text = text.replace("\u00ad", "").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?<=\d) (?=\d)", "", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"\)(?=[A-Za-z])", ") ", text)
    text = re.sub(r"(?<=[A-Za-z])\(", " (", text)
    text = re.sub(r"(?<=[A-Za-z]) ([a-z]) (?=[a-z])", r"\1", text)
    text = re.sub(r"\bWeek s\b", "Week", text)
    text = re.sub(r"\s+", " ", text).strip(" |")
    return text


def is_toc(text):
    return text.count(".") >= 5 or "...." in text


def furniture(text, protocol):
    if not text:
        return True
    if is_toc(text):
        return True
    if re.fullmatch(r"\d{1,3}", text):
        return True
    if re.search(r"Version Date|Protocol Version", text, re.I):
        return True
    if re.match(r"^(Page|NRG Oncology|SWOG|Alliance|COG|CCTG)\b", text, re.I):
        return True
    if protocol and re.search(rf"\b{re.escape(protocol)}\b\s+\d{{1,3}}\b", text) and len(text) < 80:
        return True
    if protocol and text.replace(" ", "") == protocol.replace(" ", ""):
        return True
    if re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{2,14}", text) and protocol and protocol in text:
        return True
    return False


def page_lines(page):
    items = []

    def visitor(text, cm, tm, font_dict, font_size):
        raw = (text or "").replace("\x00", "")
        if raw.strip():
            items.append((tm[5], tm[4], raw, font_size or 9))

    page.extract_text(visitor_text=visitor)
    items.sort(key=lambda row: (-row[0], row[1]))
    lines = []
    for y, x, raw, size in items:
        if lines and abs(lines[-1]["y"] - y) <= 3.4:
            lines[-1]["toks"].append((x, raw, size))
        else:
            lines.append({"y": y, "toks": [(x, raw, size)]})
    for line in lines:
        line["toks"].sort()
        parts = []
        for x, raw, size in line["toks"]:
            token = raw.strip()
            if not token:
                continue
            if parts:
                prev = parts[-1]
                gap = x - prev["x"]
                expected = max(len(prev["text"]) * prev["size"] * 0.42, prev["size"])
                hyphen = token in {"-", "/"} or prev["text"].endswith("-")
                if hyphen or gap <= expected * 0.72:
                    prev["text"] = clean(prev["text"] + token)
                    prev["x"] = min(prev["x"], x)
                    continue
                if gap <= expected + prev["size"]:
                    prev["text"] = clean(prev["text"] + " " + token)
                    continue
            parts.append({"x": x, "text": token, "size": size})
        line["parts"] = parts
        line["text"] = clean(" ".join(part["text"] for part in parts))
    return lines


def plain_pages(reader):
    pages = []
    for page in reader.pages:
        pages.append(page_lines(page))
    return pages


def find_heading(pages, pattern, protocol):
    hits = []
    for index, lines in enumerate(pages):
        for line in lines:
            text = line["text"]
            if furniture(text, protocol) or is_toc(text):
                continue
            if pattern.search(text) and len(text) < 140:
                hits.append(index)
                break
    return hits[0] if hits else None


def section_lines(pages, start, protocol, start_pattern, stop_patterns, limit=4):
    collected = []
    if start is None:
        return collected
    started = False
    for index in range(start, min(len(pages), start + limit)):
        for line in pages[index]:
            text = line["text"]
            if furniture(text, protocol):
                continue
            if not started:
                if start_pattern.search(text) and len(text) < 150 and not is_toc(text):
                    started = True
                continue
            if any(pat.search(text) and len(text) < 140 and not is_toc(text) for pat in stop_patterns):
                return collected
            collected.append(line)
    return collected


TIME_WORD = re.compile(
    r"prior|day|week|cycle|time|follow|treatment|registration|baseline|month|during|pre-study|on study",
    re.I,
)
JUNK_ROW = re.compile(
    r"^(Assessments?\b|calendar days|Paper copies|from the CIRB|Documents page|Approved Documents|"
    r"downloaded from|registration \(VTOC\)|PRO assessments after|Outcomes \(PROs\)|"
    r"qualified healthcare|In ?person preferred|Please see Section|For patients who|"
    r"Start of chemotherapy|applicable\b|NOTE\b|This study (?:visit|uses)|"
    r"telephone or mail|see appendix)",
    re.I,
)


def column_headers(line):
    headers = []
    for part in line["parts"]:
        label = clean(part["text"])
        if re.match(r"^Assessments?\b", label, re.I):
            continue
        if part["x"] < 150 or len(label) < 2:
            continue
        if not TIME_WORD.search(label):
            continue
        headers.append({"x": part["x"], "label": label})
    headers.sort(key=lambda item: item["x"])
    merged = []
    for header in headers:
        if merged and header["x"] - merged[-1]["x"] < 70:
            merged[-1]["label"] = clean(merged[-1]["label"] + " " + header["label"])
        else:
            merged.append(dict(header))
    return merged


def parse_table(lines):
    header_at = None
    columns = []
    for index, line in enumerate(lines[:30]):
        if re.match(r"^4\.\d", line["text"]):
            continue
        if re.search(r"\bAssessments?\b", line["text"], re.I):
            columns = column_headers(line)
            if columns:
                header_at = index
                break
    if header_at is None:
        return []
    if header_at + 1 < len(lines):
        nxt = lines[header_at + 1]
        if re.search(r"calendar|cycle 1|day 1|time point", nxt["text"], re.I):
            for part in nxt["parts"]:
                for column in columns:
                    if abs(part["x"] - column["x"]) < 40:
                        column["label"] = clean(column["label"] + " " + part["text"])
            header_at += 1
    boundary = columns[0]["x"] - 18
    rows = []
    notes = {}
    current = None
    orphans = []

    def flush():
        nonlocal current
        if not current or not current["item"]:
            current = None
            return
        current["item"] = clean(current["item"])
        current["window"] = clean(current["window"])
        current["letters"] = "".join(current["letters"])
        if len(current["item"]) > 2 and not JUNK_ROW.search(current["item"]):
            rows.append(current)
        current = None

    for line in lines[header_at + 1:]:
        text = line["text"]
        if re.match(r"^4\.[23]\s+ASSESSMENTS|^5\.\s|^6\.\s|^7\.\s", text):
            break
        if re.fullmatch(r"[a-z]", text):
            orphans.append(text)
            continue
        if re.match(r"^[a-z]\s+\S", text) and len(text) > 40:
            notes[text[0]] = clean(text[2:])
            continue
        if JUNK_ROW.search(text) or re.match(r"^(NOTE|Note|\*)\b", text):
            flush()
            if re.match(r"^[a-z]\s+\S", text) and len(text) > 40:
                notes.setdefault(text[0], clean(text[2:]))
            continue
        left, values, marks = [], {i: [] for i in range(len(columns))}, []
        for part in line["parts"]:
            token = part["text"]
            if re.fullmatch(r"[a-z](?:,[a-z])?", token):
                marks.append(token)
                continue
            if part["x"] < boundary:
                left.append(token)
                continue
            index = 0
            for i, column in enumerate(columns):
                if part["x"] + 6 >= column["x"]:
                    index = i
            values[index].append(token)
        left_text = clean(" ".join(left))
        filled = []
        for i, column in enumerate(columns):
            val = clean(" ".join(values[i]))
            if val:
                filled.append((column["label"], val))
        if len(filled) == 1 and re.fullmatch(r"[Xx]", filled[0][1]):
            right_text = filled[0][0]
        elif len(filled) == 1:
            right_text = filled[0][1]
        else:
            right_text = "; ".join(
                label if re.fullmatch(r"[Xx]", val) else f"{label}: {val}" for label, val in filled
            )
        if not left_text and not right_text:
            continue
        if left_text and current and (left_text[:1].islower() or left_text[:1] in "(,"):
            current["item"] = clean(current["item"] + " " + left_text)
            if right_text:
                current["window"] = clean(current["window"] + " " + right_text)
            if marks:
                current["letters"] += "".join(marks)
            continue
        if left_text and current and not (right_text and current["window"]):
            current["item"] = clean(current["item"] + " " + left_text)
            if right_text:
                current["window"] = clean(current["window"] + " " + right_text)
        elif left_text:
            flush()
            current = {"item": left_text, "window": right_text, "letters": "".join(orphans + marks)}
            orphans = []
        elif current and right_text:
            current["window"] = clean(current["window"] + " " + right_text)
        if current and marks:
            current["letters"] += "".join(marks)
    flush()
    # Footnote definitions often follow the table on the same pages.
    for line in lines:
        text = line["text"]
        match = re.match(r"^([a-z])\s+(\S.{20,})$", text)
        if match:
            notes[match.group(1)] = clean(match.group(2))
    cleaned = []
    for row in rows:
        extra = []
        for letter in row["letters"]:
            if letter in notes and notes[letter] not in extra:
                extra.append(notes[letter])
        item = re.sub(r"^(?:[a-z],\s*)+", "", row["item"])
        item = re.sub(r"(?:\s+[a-z],?)+$", "", item).strip(" :")
        window = clean(re.sub(r"\(calendar days\)", "", row["window"]))
        note = clean(" ".join(extra))
        if re.search(r"window is extended|TURBT window", item, re.I):
            target = next((row for row in cleaned if re.search(r"\bTURBT\b", row["item"]) and "window" not in row["item"].lower()), None)
            if target:
                target["note"] = clean((target["note"] + " " + item).strip())
            elif cleaned:
                cleaned[-1]["note"] = clean((cleaned[-1]["note"] + " " + item).strip())
            continue
        if re.search(r"website|CIRB|VTOC", item, re.I):
            item = clean(re.sub(r"^.*?(website|CIRB|VTOC)[.:]?\s*", "", item, flags=re.I))
        if JUNK_ROW.search(item) or len(item) < 3:
            continue
        if not window and len(item.split()) > 12:
            continue
        if len(item) > 240:
            item = item[:240].rsplit(" ", 1)[0]
        if len(window) > 300:
            window = window[:300].rsplit(" ", 1)[0]
        if len(note) > 400:
            note = note[:400].rsplit(" ", 1)[0]
        cleaned.append({"item": item, "window": window, "note": note})
    return cleaned[:20]


def schema_from(lines, protocol):
    steps = []
    current = None
    for line in lines:
        text = line["text"]
        if furniture(text, protocol) or SCHEMA_HEAD.match(text):
            continue
        if re.match(r"^(1\.|2\.|3\.)\s+[A-Z]", text) and len(text) < 90:
            break
        arm_hits = list(re.finditer(r"\b(Arm\s*\d+[a-z]?)\b[:\-]?\s*", text, re.I))
        if arm_hits and current is not None:
            for index, hit in enumerate(arm_hits):
                end = arm_hits[index + 1].start() if index + 1 < len(arm_hits) else len(text)
                body = clean(text[hit.end():end])
                if re.fullmatch(r"Arm\s*\d+[a-z]?", body, re.I):
                    body = ""
                current.setdefault("arms", []).append({"label": hit.group(1).title(), "text": body})
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9 /&\-]{2,48}", text) or re.match(r"^(Stratify|Randomize|Register|Step \d+)\b", text, re.I):
            current = {"label": text.title() if text.isupper() else text, "text": ""}
            steps.append(current)
            continue
        if current is None:
            current = {"label": "Entry", "text": text}
            steps.append(current)
        elif not current["text"]:
            current["text"] = text
        else:
            current["text"] = clean(current["text"] + " " + text)
    cleaned = []
    for step in steps:
        step["label"] = clean(step["label"])[:80]
        step["text"] = clean(step.get("text") or "")
        if len(step["text"]) > 500:
            step["text"] = step["text"][:500].rsplit(" ", 1)[0]
        arms = []
        for arm in step.get("arms") or []:
            if arm.get("label"):
                arms.append({k: v for k, v in arm.items() if v})
        if arms:
            step["arms"] = arms
        elif "arms" in step:
            del step["arms"]
        if step["label"] or step["text"] or step.get("arms"):
            cleaned.append({k: v for k, v in step.items() if v})
    return cleaned[:12]


def eligibility_from(lines, protocol):
    items = []
    buf = ""

    def push(text):
        text = clean(text)
        text = re.sub(r"^(?:\d+(?:\.\d+){1,3}|[A-Z]\.|[\u2022\u25cf\-])\s*", "", text)
        text = re.sub(r"\b(Yes|No)\b", "", text)
        text = clean(text.strip(" _:-"))
        if len(text) < 25 or BOILER.search(text):
            return
        if len(text) > 420:
            text = text[:420].rsplit(" ", 1)[0]
        if text not in items:
            items.append(text)

    for line in lines:
        text = line["text"]
        if furniture(text, protocol) or ELIG_HEAD.match(text):
            continue
        if re.match(r"^(4\.|5\.|6\.|7\.)\s+[A-Z]", text) and "ELIGIB" not in text.upper() and len(text) < 100:
            break
        if CRITERION.match(text) or re.match(r"^(Ineligible|Patients? with|Participants? (must|who)|No prior|Histolog)", text):
            if buf:
                push(buf)
            buf = text
        elif buf and (text[:1].islower() or text[:1] in "(," or len(text) < 40):
            buf = clean(buf + " " + text)
        elif buf:
            push(buf)
            buf = text if len(text) > 40 else ""
        elif len(text) > 50:
            buf = text
    if buf:
        push(buf)
    return items[:30]


def amendments_from(pages, protocol):
    found = []
    seen = set()
    for lines in pages[:4]:
        for line in lines:
            text = line["text"]
            if is_toc(text):
                continue
            match = HISTORY_LINE.match(text)
            if not match:
                continue
            date = clean(match.group(2).replace(",", ""))
            kind = clean(match.group(1))
            key = (kind.lower(), date)
            if key in seen:
                continue
            seen.add(key)
            rest = clean(text[match.end():]).strip(" .:-")
            if rest and len(rest) > 20 and "do not" not in rest.lower():
                body = rest[:300]
            else:
                body = "Listed in the document history. These opening pages do not summarize what changed."
            found.append({"date": pretty_date(date), "text": f"{kind}. {body}"})
    return found


def tidy_calendar_label(label):
    low = label.lower()
    if "prior to" in low or "pre-cycle" in low or "pre-reg" in low:
        return "Before registration (within 28 days unless the calendar says otherwise)"
    has_c1 = re.search(r"\bC1\b", label)
    has_later = "C2" in label or "2-18" in label
    if has_c1 and has_later:
        return "Cycle 1 and cycles 2-18"
    if has_c1:
        return "Cycle 1 (21-day cycles)"
    if has_later:
        return "Cycles 2-18"
    if "after first" in low:
        return "After the first BI-EFS event"
    if "at time of first" in low or "first bi" in low:
        return "At the first BI-EFS event"
    if "21 week" in low or "weeks after" in low:
        return "From 21 weeks after registration until the first BI-EFS event or 3 years"
    return label[:80]


def phase_of(label):
    text = label.lower()
    if any(token in text for token in ("prior to", "pre-reg", "pre-registration", "pre-study", "baseline", "screening", "pre-cycle", "before registration")):
        return "pretreatment"
    if any(token in text for token in ("follow", "after", "week", "year", "bi-efs", "post-", "month")):
        return "followup"
    return "during"


def calendar_tables(pages, start, protocol):
    lines = section_lines(
        pages, start, protocol, CAL_HEAD,
        [re.compile(r"^10(?:\.0|\.)\s+"), re.compile(r"^11(?:\.0|\.)\s+"), re.compile(r"^Footnotes\b")],
        1,
    )
    marks = []
    for line in lines:
        for part in line["parts"]:
            if re.fullmatch(r"X\d*", part["text"]):
                marks.append((line, part))
    if len(marks) < 4:
        return {}
    centers = []
    for _line, part in sorted(marks, key=lambda item: item[1]["x"]):
        if centers and part["x"] - centers[-1]["x"] <= 22:
            centers[-1]["xs"].append(part["x"])
            centers[-1]["x"] = sum(centers[-1]["xs"]) / len(centers[-1]["xs"])
        else:
            centers.append({"x": part["x"], "xs": [part["x"]], "label": ""})
    top = max(line["y"] for line, _part in marks)
    for center in centers:
        pieces = []
        for line in lines:
            if line["y"] <= top:
                continue
            for part in line["parts"]:
                if abs(part["x"] - center["x"]) <= 36 and not re.fullmatch(r"X\d*|\d{1,2}", part["text"]):
                    pieces.append((line["y"], part["text"]))
        pieces.sort(reverse=True)
        center["label"] = tidy_calendar_label(clean(" ".join(dict.fromkeys(text for _y, text in pieces))))
        if not center["label"]:
            center["label"] = "On study"
    buckets = {"pretreatment": [], "during": [], "followup": []}
    pending = ""
    label_cut = min(center["x"] for center in centers) - 20
    for line in lines:
        hits = [part for part in line["parts"] if re.fullmatch(r"X\d*", part["text"])]
        left = clean(" ".join(
            part["text"] for part in line["parts"]
            if part["x"] < label_cut and not re.fullmatch(r"X\d*", part["text"])
        ))
        if left and re.fullmatch(r"[A-Z][A-Z /]{3,}", left):
            pending = ""
            continue
        if re.fullmatch(r"\d{1,2}", left or ""):
            left = ""
        if hits and not left and pending:
            left = pending
            pending = ""
        elif left and not hits:
            attached = False
            for rows in buckets.values():
                if rows and rows[-1]["item"].endswith(("-", "(", "/")):
                    rows[-1]["item"] = clean(rows[-1]["item"] + " " + left)
                    attached = True
            if attached:
                pending = ""
                continue
            pending = clean(pending + " " + left) if pending else left
            continue
        if not hits or not left or len(left) < 3:
            continue
        left = re.sub(r"\s+\d{1,2}[a-z]?$", "", left).strip(" .")
        pending = ""
        by_phase = {}
        for part in hits:
            center = min(centers, key=lambda item: abs(item["x"] - part["x"]))
            phase = phase_of(center["label"])
            by_phase.setdefault(phase, [])
            if center["label"] not in by_phase[phase]:
                by_phase[phase].append(center["label"])
        for phase, labels in by_phase.items():
            buckets[phase].append({"item": left[:180], "window": "; ".join(labels), "note": ""})
    return {key: rows[:20] for key, rows in buckets.items() if rows}


def brief_from_pdf(path, protocol):
    reader = PdfReader(str(path))
    pages = plain_pages(reader)
    stops = [PRE_HEAD, DURING_HEAD, FOLLOW_HEAD, CAL_HEAD, re.compile(r"^[1-9]\.\s+[A-Z]")]
    schema_at = find_heading(pages, SCHEMA_HEAD, protocol)
    elig_at = find_heading(pages, ELIG_HEAD, protocol)
    pre_at = find_heading(pages, PRE_HEAD, protocol)
    during_at = find_heading(pages, DURING_HEAD, protocol)
    follow_at = find_heading(pages, FOLLOW_HEAD, protocol)
    calendar_at = find_heading(pages, CAL_HEAD, protocol)
    brief = {
        "amendments": amendments_from(pages, protocol),
        "schema": schema_from(section_lines(pages, schema_at, protocol, SCHEMA_HEAD, [ELIG_HEAD, re.compile(r"^1\.\s+"), re.compile(r"^2\.\s+"), re.compile(r"^3\.\s+")], 2), protocol) if schema_at is not None else [],
        "eligibility": eligibility_from(section_lines(pages, elig_at, protocol, ELIG_HEAD, [PRE_HEAD, CAL_HEAD, re.compile(r"^4\.\s+"), re.compile(r"^6\.0\s+"), re.compile(r"^5\.0\s+(?!ELIG)")], 5), protocol) if elig_at is not None else [],
    }
    if pre_at is not None:
        brief["pretreatment"] = parse_table(section_lines(pages, pre_at, protocol, PRE_HEAD, [DURING_HEAD, FOLLOW_HEAD, re.compile(r"^5\.\s+")], 2))
    if during_at is not None:
        brief["during"] = parse_table(section_lines(pages, during_at, protocol, DURING_HEAD, [FOLLOW_HEAD, re.compile(r"^5\.\s+")], 2))
    if follow_at is not None:
        brief["followup"] = parse_table(section_lines(pages, follow_at, protocol, FOLLOW_HEAD, [re.compile(r"^5\.\s+"), re.compile(r"^6\.\s+")], 3))
    if calendar_at is not None and not all(brief.get(key) for key in ("pretreatment", "during", "followup")):
        for key, rows in calendar_tables(pages, calendar_at, protocol).items():
            if rows and not brief.get(key):
                brief[key] = rows
    for key in ("amendments", "schema", "eligibility", "pretreatment", "during", "followup"):
        if not brief.get(key):
            brief.pop(key, None)
    return brief


def newest_pdf(protocol):
    files = sorted((PROTOCOLS / protocol).glob("*.pdf"))
    protocols = [path for path in files if "amendment" not in path.name.lower() and "memo" not in path.name.lower()]
    return protocols[-1] if protocols else (files[-1] if files else None)


def merge(existing, extracted):
    locked = set(existing.get("locked") or [])
    out = dict(existing)
    for key, value in extracted.items():
        if key in locked:
            continue
        if key in HAND_KEYS and existing.get(key):
            continue
        if value:
            out[key] = value
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    briefs = json.loads(BRIEFS.read_text()) if BRIEFS.exists() else {}
    wanted = set(args.only) if args.only else None
    stats = {"pdfs": 0, "updated": 0, "sections": {}}
    for folder in sorted(path for path in PROTOCOLS.iterdir() if path.is_dir()):
        protocol = folder.name
        if wanted and protocol not in wanted:
            continue
        pdf = newest_pdf(protocol)
        if not pdf:
            continue
        stats["pdfs"] += 1
        try:
            extracted = brief_from_pdf(pdf, protocol)
        except Exception as exc:
            print(f"{protocol}: {exc}")
            continue
        if args.debug:
            print(json.dumps({protocol: extracted}, indent=1)[:8000])
        for key in extracted:
            stats["sections"][key] = stats["sections"].get(key, 0) + 1
        merged = merge(briefs.get(protocol, {}), extracted)
        manifest = json.loads((PROTOCOLS / "manifest.json").read_text()) if (PROTOCOLS / "manifest.json").exists() else {}
        doc = manifest.get(protocol) or {}
        if doc.get("version") and not merged.get("version_date"):
            merged["version_date"] = doc["version"]
            if doc.get("label"):
                merged["version_label"] = doc["label"]
            if doc.get("posted"):
                merged["posted"] = doc["posted"]
        briefs[protocol] = merged
        stats["updated"] += 1
    if not args.debug:
        BRIEFS.write_text(json.dumps(briefs, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
