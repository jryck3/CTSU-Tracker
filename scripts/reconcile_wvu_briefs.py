#!/usr/bin/env python3
"""Replace broken WVU CTSU briefs with text taken from the local protocol PDF.

Keeps renditions that were already written from the protocol. Does not delete
the word No. Does not join a right-hand lab column into the eligibility line.
An amendment memorandum is not a full protocol.
"""
import json
import re
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PROTOCOLS = ROOT / "protocols"
BRIEFS = ROOT / "data" / "protocol_briefs.json"
WVU = [
    "A012103", "A012303", "A032103", "A032201", "A081801", "A151804", "A211901",
    "A222301", "ANBL2131", "APEC14B1", "EA2192", "EAA173", "EAF223", "EAY191",
    "EAY191-N5", "LUNGMAP", "NRG-BR009", "NRG-CC005", "NRG-CC008", "NRG-GI008",
    "NRG-GU013", "NRG-GU014", "NRG-GU015", "NRG-GY035", "NRG-GY036", "NRG-GY037",
    "NRG-LU008", "S1501", "S1800E", "S1802", "S1900J", "S1900K", "S2012", "S2206",
    "S2212", "S2312", "S2427",
]
KEEP = {"NRG-GU013", "NRG-GU015", "S2427"}
UNAVAILABLE = "Full protocol was not available to build this section."
VERTICAL = {"R", "A", "N", "D", "O", "M", "I", "Z", "E"}


def tidy(text):
    text = (text or "").replace("\u00ad", "").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip(" |")


def newest_pdf(protocol):
    folder = PROTOCOLS / protocol
    if not folder.is_dir():
        return None
    files = sorted(folder.glob("*.pdf"))
    full = [path for path in files if "protocol" in path.name.lower() and "amendment" not in path.name.lower() and "memo" not in path.name.lower()]
    return full[-1] if full else None


def page_rows(page):
    items = []

    def visitor(text, cm, tm, font_dict, font_size):
        raw = (text or "").replace("\x00", " ")
        if raw.strip():
            items.append((tm[5], tm[4], raw.strip()))

    page.extract_text(visitor_text=visitor)
    items.sort(key=lambda row: (-row[0], row[1]))
    lines = []
    for y, x, raw in items:
        if lines and abs(lines[-1]["y"] - y) <= 2.8:
            lines[-1]["toks"].append((x, raw))
        else:
            lines.append({"y": y, "toks": [(x, raw)]})
    rows = []
    for line in lines:
        toks = sorted(line["toks"])
        xs = [x for x, _raw in toks]
        use = toks
        if xs and max(xs) - min(xs) > 160 and any(x >= 320 for x, _raw in toks):
            use = [(x, raw) for x, raw in toks if x < 320]
        text = tidy(" ".join(raw for _x, raw in use))
        if text:
            rows.append(text)
    return rows


def is_toc(text):
    return text.count(".") >= 6 or "...." in text


def eligibility_from(reader):
    pages = []
    for index, page in enumerate(reader.pages):
        rows = page_rows(page)
        blob = " ".join(rows)
        if is_toc(blob[:400]):
            continue
        if re.search(r"Eligibility Criteria|ELIGIBILITY CRITERIA|Registration Eligibility", blob, re.I):
            if re.search(r"\bAge\b|\bECOG\b|\bmust\b", blob, re.I):
                pages.append(index)
    if not pages:
        return []
    start = pages[0]
    items = []
    buf = ""

    def push(text):
        nonlocal buf
        text = tidy(re.sub(r"^(?:___|\d+(?:\.\d+){0,3}|[A-Z]\.|[\u2022\u25cf\-])\s*", "", text))
        text = re.sub(r"\s*_{2,}.*$", "", text).strip(" _:-")
        if len(text) < 8:
            return
        if re.search(r"exceptions to eligibility|cannot be considered eligible|questions concerning eligibility|use the spaces provided|day a test or measurement is done|table of contents|version date", text, re.I):
            return
        if text not in items:
            items.append(text)

    for index in range(start, min(len(reader.pages), start + 6)):
        for text in page_rows(reader.pages[index]):
            if is_toc(text) or re.match(r"^(Version Date|Page \d+|Alliance |NRG-|SWOG )", text):
                continue
            if re.match(r"^[4-9]\.\s+[A-Z]", text) and "ELIGIB" not in text.upper() and len(text) < 80:
                push(buf)
                return items[:36]
            if re.match(r"^(?:[\u2022\u25cf\-]|___|\d+(?:\.\d+){1,3}\b)", text) or re.match(r"^(?:No|Age|ECOG|Patients?|Participants?|Histolog|Not pregnant)", text, re.I):
                if buf:
                    push(buf)
                buf = text
            elif buf:
                buf = tidy(buf + " " + text)
            elif len(text) > 40 and re.search(r"\b(must|eligible|No )\b", text):
                buf = text
    if buf:
        push(buf)
    return items[:36]


def schema_from(reader):
    best = None
    for page in reader.pages:
        rows = [row for row in page_rows(page) if not is_toc(row)]
        blob = " ".join(rows)
        if not re.search(r"\bSCHEMA\b", blob):
            continue
        if "TABLE OF CONTENTS" in blob.upper() or blob.count("...") > 3:
            continue
        if re.search(r"\b(Arm|Randomiz|STEP \d|Registration)\b", blob, re.I):
            best = rows
            break
    if not best:
        return []
    steps = []
    buf = []
    started = False
    for text in best:
        if re.match(r"^SCHEMA\b", text, re.I):
            started = True
            continue
        if not started:
            continue
        if re.match(r"^(Version Date|Please refer to the full protocol|\d+\.\s+OBJECTIVES)", text, re.I):
            break
        token = text.strip()
        if token in VERTICAL or re.fullmatch(r"[A-Z]", token):
            continue
        if re.match(r"^(Arm\s*\d+|STEP\s*\d+|Randomiz|Stratification|Registration)\b", text, re.I):
            if buf:
                steps.append(tidy(" ".join(buf)))
            buf = [text]
        else:
            buf.append(text)
    if buf:
        steps.append(tidy(" ".join(buf)))
    out = []
    for index, text in enumerate(steps):
        if len(text) < 12:
            continue
        label = "Entry"
        match = re.match(r"^(Arm\s*\d+[A-Za-z]?|Step\s*\d+|Randomization|Stratification|Registration)\b[:\-]?\s*(.*)$", text, re.I)
        body = text
        if match:
            label = match.group(1).title()
            body = tidy(match.group(2) or text)
        out.append({"label": label, "text": body[:700]})
    return out[:8]


def main():
    briefs = json.loads(BRIEFS.read_text())
    report = []
    for protocol in WVU:
        current = briefs.get(protocol) or {}
        if protocol in KEEP:
            report.append(f"{protocol}: kept existing rendition")
            continue
        pdf = newest_pdf(protocol)
        if pdf is None:
            current["protocol_unavailable"] = True
            current["schema"] = []
            current["eligibility"] = []
            briefs[protocol] = current
            report.append(f"{protocol}: no full protocol")
            continue
        reader = PdfReader(str(pdf))
        eligibility = eligibility_from(reader)
        schema = schema_from(reader)
        if len(eligibility) >= 4:
            current["eligibility"] = eligibility
            current.pop("protocol_unavailable", None)
        if len(schema) >= 1:
            current["schema"] = schema
        if len(eligibility) < 4 and len(schema) < 1:
            current["protocol_unavailable"] = True
            report.append(f"{protocol}: extraction failed")
        else:
            report.append(f"{protocol}: eligibility {len(eligibility)} schema {len(schema)}")
        briefs[protocol] = current
    BRIEFS.write_text(json.dumps(briefs, indent=1, ensure_ascii=False) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
