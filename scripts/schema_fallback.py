"""Fallback schema reader for protocol PDFs whose schema the main parser misses.

Finds the page headed SCHEMA, STUDY SCHEMA, or similar in the first 30 pages
and turns it into the brief's list of {label, text, arms} steps. When a
protocol prints both a pre- and a post-amendment schema, the later page is used.
"""

import re

SCHEMA_HEADING = re.compile(
    r"^(?:(?:study|treatment|experimental design)\s+)?schema\b"
    r"(?:\s+page\s+\d+\s+of\s+\d+)?"
    r"(?:\s*\([^)]{0,48}\))*"
    r"\s*$",
    re.I,
)
ARM_LINE = re.compile(r"^(Arm\s*[A-Z]?\d+[a-z]?)\b[:\-]?\s*(.*)$", re.I)
STEP_LINE = re.compile(r"^(Step\s+\d+[a-z]?)\b[:\-]?\s*(.*)$", re.I)
NEXT_SECTION = re.compile(r"^\d+\.0\s+[A-Z]")
SAMPLE = re.compile(r"^N\s*=\s*[\d,]+", re.I)
FOOTNOTE = re.compile(r"^\d{1,2}\.\s+[A-Z]")


def _lines(text):
    kept = []
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or len(line) == 1:
            continue
        if re.fullmatch(r"\d{1,3}", line):
            continue
        upper = line.upper()
        if upper in {"CONFIDENTIAL", "CONFIDENTIAL CONFIDENTIAL"}:
            continue
        if "CONFIDENTIAL" in upper and len(line) < 48:
            continue
        if re.match(r"^PROTOCOL\s*[–\-]\s*UPDATE", line, re.I):
            continue
        if re.match(r"^(CCTG/NCTN TRIAL:|ECOG-ACRIN|Cancer Research Group|Version Date:|NRG Oncology)\b", line, re.I):
            continue
        if line.count(".") > 8:
            continue
        kept.append(line)
    return kept


def _schema_page_indexes(reader):
    found = []
    limit = min(len(reader.pages), 30)
    for index in range(limit):
        lines = _lines(reader.pages[index].extract_text() or "")
        for line in lines:
            if SCHEMA_HEADING.match(line):
                found.append((index, line))
                break
    if not found:
        return []
    post = [item for item in found if re.search(r"post", item[1], re.I)]
    chosen = post or found
    # The later page is the current amendment when both a pre and a post schema exist.
    return [chosen[-1][0]]


def _clip(text, limit=700):
    text = re.sub(r"\s+", " ", text or "").strip(" -;")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0]


def _strat_item(line):
    low = line.lower().lstrip("•-* ").strip()
    if low.startswith(("participants", "patients", "restaging", "eligible", "key inclusion", "men with", "women with")):
        return False
    if "versus" in low or " vs " in low or " vs." in low:
        return len(line) < 200
    return len(line) < 100


def parse_schema_text(text):
    lines = _lines(text)
    body = []
    started = False
    for line in lines:
        if not started:
            if SCHEMA_HEADING.match(line):
                started = True
            continue
        if NEXT_SECTION.match(line):
            break
        body.append(line)
    if not body:
        return []
    design, strat, entry, arms, notes = [], [], [], [], []
    mode = "design"
    current = None
    footnote = False
    for line in body:
        arm = ARM_LINE.match(line)
        step = STEP_LINE.match(line)
        stratify = re.match(r"^Stratification\b", line, re.I)
        # pypdf puts the numbered schema footnotes wherever they fall in the
        # text stream, often before the arms. Skip each one up to the next
        # arm, step, stratification, or sample-size line.
        if FOOTNOTE.match(line):
            footnote = True
            continue
        if footnote:
            if not (arm or step or stratify or SAMPLE.match(line)):
                continue
            footnote = False
        if stratify:
            mode = "strat"
            rest = re.sub(r"^Stratification(?:\s+Factors)?\s*:?\s*", "", line, flags=re.I).strip()
            if rest:
                strat.append(rest.lstrip("•-* ").strip())
            continue
        if step:
            mode = "step"
            current = {"label": step.group(1).title(), "text": _clip(step.group(2))}
            arms.append(current)
            continue
        if arm:
            mode = "arm"
            current = {"label": re.sub(r"\s+", " ", arm.group(1)).title(), "text": _clip(arm.group(2))}
            arms.append(current)
            continue
        if SAMPLE.match(line):
            notes.append(line.rstrip("."))
            continue
        if line.startswith("*"):
            notes.append(line.lstrip("* ").strip())
            continue
        if mode == "strat" and not _strat_item(line):
            mode = "entry"
        if mode == "design":
            design.append(line)
        elif mode == "strat":
            strat.append(line.lstrip("•-* ").strip())
        elif mode == "entry":
            entry.append(line)
        elif current is not None:
            current["text"] = _clip((current.get("text") or "") + " " + line)
    steps = []
    if design:
        steps.append({"label": "Design", "text": _clip(" ".join(design))})
    if strat:
        steps.append({"label": "Stratify", "text": _clip(" ".join(item for item in strat if item))})
    if entry:
        steps.append({"label": "Entry", "text": _clip(" ".join(entry))})
    if arms:
        step = {"label": "Randomize", "arms": []}
        for arm in arms:
            item = {"label": arm["label"]}
            if arm.get("text"):
                item["text"] = arm["text"]
            step["arms"].append(item)
        if notes:
            step["note"] = _clip(" ".join(notes))
        steps.append(step)
    elif notes:
        steps.append({"label": "Sample size", "text": _clip(" ".join(notes))})
    blob = " ".join(step.get("text") or "" for step in steps)
    blob += " ".join(arm.get("text") or "" for step in steps for arm in step.get("arms") or [])
    if len(blob) < 80 and not any(step.get("arms") for step in steps):
        return []
    return steps


CLEAN_LABEL = re.compile(r"^(?:Arm|Step)\s+[A-Z]?\d?[a-z]?$")
NOISE = re.compile(r"\bRev\.\s|\bAdd\d|\bAddendum\s*#|Step \d+Step|\bp\d+\b")


def readable(steps):
    """Keep a parsed schema only when it reads cleanly.

    Flowchart schemas (most ECOG-ACRIN and some Alliance protocols) come out of
    pypdf with footnote digits glued to arm labels, empty boxes, and revision
    marks. A protocol's own design paragraph ("This is a ... trial") or a clean
    list of two or more described arms is kept. Anything else is dropped,
    because no schema is better than a wrong one.
    """
    if not steps:
        return False
    texts = [step.get("text") or "" for step in steps]
    arms = [arm for step in steps for arm in step.get("arms") or []]
    texts += [arm.get("text") or "" for arm in arms]
    if any(NOISE.search(text) for text in texts):
        return False
    if any(step.get("label") in ("Stratify", "Entry") and len(step.get("text") or "") < 12 for step in steps):
        return False
    if any(text[:1].islower() for text in texts if text):
        return False
    labels = [arm.get("label") or "" for arm in arms]
    if arms:
        if len(set(labels)) != len(labels):
            return False
        if not all(CLEAN_LABEL.match(label) for label in labels):
            return False
        if not all(len(arm.get("text") or "") >= 25 for arm in arms):
            return False
    design = next((step.get("text") or "" for step in steps if step.get("label") == "Design"), "")
    if re.match(r"^This is an? ", design):
        return True
    return len(arms) >= 2 and all(label.startswith("Arm") for label in labels)


def schema_from_reader(reader):
    try:
        indexes = _schema_page_indexes(reader)
        if not indexes:
            return []
        text = "\n".join(reader.pages[index].extract_text() or "" for index in indexes)
        steps = parse_schema_text(text)
        return steps if readable(steps) else []
    except Exception:
        return []
