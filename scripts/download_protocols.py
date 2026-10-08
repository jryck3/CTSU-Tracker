#!/usr/bin/env python3
"""
Download current protocol documents from the CTSU member site (www.ctsu.org)
into protocols/<PROTOCOL>/ and record them in protocols/manifest.json.

Requires the automation Chrome (tools/launch_chrome_debug.sh) to be running and
signed in to CTSU. Stop and ask Jeff to complete ID.me before using this script.
Do not call it while logged out. Requests go through that browser's session
cookies. Protocol documents are for site use under the CTSU terms of use and
stay on this machine.

Target list: every RT-related study in data/studies.json plus the institution
trials in config/institution_trials.json (run scripts/refresh.py first).
--open-only limits the check to RT studies whose CTSU status is Active.
Re-running is safe: a protocol whose current document ID is already on file is
skipped, and an amended protocol is downloaded alongside the older version.
Each run appends logs/protocol_changes.md.

Usage:
    python3 scripts/download_protocols.py --port 9223 [--open-only] [--only NRG-GU013 S2427] [--dry-run]
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROTOCOLS = ROOT / "protocols"
MANIFEST = PROTOCOLS / "manifest.json"
STUDIES = ROOT / "data" / "studies.json"
CHANGELOG = ROOT / "logs" / "protocol_changes.md"
BASE = "https://www.ctsu.org"
DELAY_S = 1.5

CIRB_ROW = re.compile(
    r'href="/readfile\.aspx\?EDocId=(\d+)">([^<]+)</a></td>\s*<td[^>]*ecPOST_DATE[^>]*>\s*<span[^>]*>([^<]*)</span>', re.S)
GRID_ROW = re.compile(
    r'href="/readfile\.aspx\?sectionid=(\d+)"[^>]*>([^<]+)</a>.*?ecFORMTYPEDESCRIPTION[^>]*>\s*<span[^>]*>([^<]*)</span>'
    r'.*?ecRD[^>]*>\s*<span[^>]*>([^<]*)</span>', re.S)
PROTOCOL_LABEL = re.compile(r"(protocol version date|protocol document|^protocol\b)", re.I)
GRID_PROTOCOL_LABEL = re.compile(r"(^protocol( document)?\b|change memo with protocol|^protocol version)", re.I)
MEMO_LABEL = re.compile(r"memorandum:\s*amendment\b", re.I)
LINK = re.compile(r'href="/readfile\.aspx\?([^"]+)"[^>]*>([^<]+)</a>')
SUMMARY_HEAD = re.compile(
    r"(summary of changes|section change|list of changes|document history|protocol update|amendment\s*#?\s*\d+)",
    re.I,
)
PVD = re.compile(r"(\d{2})/(\d{2})/(\d{2,4})")


def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


def pvd_iso(label):
    m = PVD.search(label or "")
    if not m:
        return None
    mm, dd, yy = m.groups()
    year = int(yy) + 2000 if len(yy) == 2 else int(yy)
    return f"{year:04d}-{int(mm):02d}-{int(dd):02d}"


def page_is_protocol(text, proto):
    return f">{proto}<" in text or f"protocol={urllib.parse.quote(proto)}" in text or "CIRBDetail" in text


def link_doc(query, label):
    query = html.unescape(query)
    if query.startswith("sectionid="):
        sid = query.split("=", 1)[1].split("&", 1)[0]
        return {"doc_id": f"Section-{sid}", "url": f"{BASE}/readfile.aspx?sectionid={sid}&mode=download", "label": label}
    if query.startswith("EDocId="):
        eid = query.split("=", 1)[1].split("&", 1)[0]
        return {"doc_id": f"EDoc-{eid}", "url": f"{BASE}/readfile.aspx?EDocId={eid}&mode=download", "label": label}
    return None


def amendment_memo(text):
    """Newest amendment memorandum on the documents tab. The page lists newest first."""
    for query, label in LINK.findall(text):
        label = html.unescape(label).strip()
        if MEMO_LABEL.search(label):
            doc = link_doc(query, label)
            if doc:
                return doc
    return None


def find_current_protocol(req, proto, lead):
    """Return (protocol doc, amendment memo, note). doc has url, label, posted, source, doc_id."""
    attempts = [{"protocol": proto}]
    if lead:
        attempts.append({"protocol": proto, "gid": lead})
    for params in attempts:
        url = f"{BASE}/pp_ProtocolDetail.aspx?" + urllib.parse.urlencode({**params, "display": "Documents", "DocType": "ALL"})
        resp = req.get(url)
        text = resp.text()
        time.sleep(DELAY_S)
        if "ProtocolDetail1_vwTabdocuments" not in text:
            continue
        memo = amendment_memo(text)
        for doc_id, label, posted in CIRB_ROW.findall(text):
            label = html.unescape(label).strip()
            if PROTOCOL_LABEL.search(label) and "consent" not in label.lower():
                return {"doc_id": f"EDoc-{doc_id}", "url": f"{BASE}/readfile.aspx?EDocId={doc_id}&mode=download",
                        "label": label, "posted": posted.strip(), "source": "CIRB-approved"}, memo, None
        for section_id, label, doc_type, doc_date in GRID_ROW.findall(text):
            label = html.unescape(label).strip()
            if GRID_PROTOCOL_LABEL.search(label):
                return {"doc_id": f"Section-{section_id}", "url": f"{BASE}/readfile.aspx?sectionid={section_id}&mode=download",
                        "label": label, "posted": doc_date.strip(), "source": f"Documents ({doc_type.strip()})"}, memo, None
        return None, None, "documents page reachable but no protocol document listed"
    return None, None, "documents page not available to this account (restricted or not rostered)"


def download(req, doc, proto, kind="protocol"):
    resp = req.get(doc["url"])
    time.sleep(DELAY_S)
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status}")
    body = resp.body()
    ctype = resp.headers.get("content-type", "")
    disp = resp.headers.get("content-disposition", "")
    if body[:5] != b"%PDF-" and "pdf" not in ctype.lower():
        if b"<html" in body[:2000].lower():
            raise RuntimeError("got an HTML page instead of a document (session expired?)")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disp)
    ext = Path(m.group(1)).suffix.lower() if m else (".pdf" if body[:5] == b"%PDF-" else "")
    if kind == "amendment":
        stem = safe(doc["label"])[:80] or "amendment"
    else:
        pvd = pvd_iso(doc["label"])
        if pvd:
            stem = f"PVD-{pvd}"
        elif doc.get("posted"):
            stem = "posted-" + datetime.strptime(doc["posted"], "%d-%b-%Y").strftime("%Y-%m-%d")
        else:
            stem = "undated"
    folder = PROTOCOLS / safe(proto)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe(proto)}_{kind}_{stem}{ext or '.pdf'}"
    if path.exists():
        path = path.with_name(f"{path.stem}_{safe(doc['doc_id'])}{path.suffix}")
    path.write_bytes(body)
    return path, len(body), (m.group(1) if m else None)


def annotate_pdf(path):
    """Short local note from the opening pages of a protocol or amendment PDF."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(str(path))
    except Exception as e:
        return f"Could not read the PDF ({e})."
    chunks = []
    for page in reader.pages[:8]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n".join(chunks)
    match = SUMMARY_HEAD.search(text)
    if match:
        snippet = text[match.start():match.start() + 1600]
    else:
        snippet = text[:900]
    snippet = re.sub(r"[ \t]+\n", "\n", snippet)
    snippet = re.sub(r"\n{3,}", "\n\n", snippet).strip()
    if not snippet:
        return None
    if not match:
        snippet = "No summary-of-changes heading in the first 8 pages. Opening text: " + re.sub(r"\s+", " ", snippet)
    if len(snippet) > 1400:
        snippet = snippet[:1400].rsplit(" ", 1)[0] + "..."
    return snippet


def targets(only, open_only):
    data = json.loads(STUDIES.read_text())
    if only:
        wanted = set(only)
        rows = [s for s in data["studies"] if s["protocol"] in wanted]
    elif open_only:
        rows = [s for s in data["studies"] if s["rt_related"] and s.get("status") == "Active"]
    else:
        rows = [s for s in data["studies"] if s["rt_related"] or s["ours"]]
    return [(s["protocol"], s["lead"], s["rt_role"]) for s in rows]


def append_log(checked, summary, notes, baseline):
    CHANGELOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = []
    if baseline is not None:
        lines += [
            "# CTSU protocol change log",
            "",
            "Local record of checks against the current CIRB-approved protocol on the CTSU member site. "
            "Quoted amendment text stays on this Mac with the protocol PDFs.",
            "",
            "## Versions on file at the first check",
            "",
        ]
        for proto, entry in baseline:
            if entry.get("files"):
                posted = entry.get("posted") or "date not listed"
                lines.append(f"- **{proto}**: {entry.get('label')} (posted {posted})")
        lines += ["", "Later sections record only what changed after this list.", ""]
    lines += [
        f"## {stamp}",
        "",
        f"Checked {checked} protocols. "
        f"{len(summary['unchanged'])} unchanged, "
        f"{len(summary['downloaded'])} new or updated, "
        f"{len(summary.get('memos', []))} amendment memoranda updated, "
        f"{len(summary['unavailable'])} unavailable, "
        f"{len(summary['errors'])} errors.",
        "",
    ]
    if notes:
        lines.append("### Changes")
        lines.append("")
        for note in notes:
            lines.append(f"- **{note['protocol']}**: {note['summary']}")
            if note.get("file"):
                lines.append(f"  - File: `{note['file']}`")
            if note.get("memo"):
                lines.append(f"  - Amendment memorandum: {note['memo']}")
            if note.get("annotation"):
                lines.append("")
                lines.append("  ```")
                for row in note["annotation"].splitlines():
                    lines.append(f"  {row}")
                lines.append("  ```")
            lines.append("")
    else:
        lines.append("No protocol document changes.")
        lines.append("")
    if summary["unavailable"]:
        lines.append("Unavailable to this account: " + ", ".join(summary["unavailable"]) + ".")
        lines.append("")
    if summary["errors"]:
        lines.append("Errors:")
        lines += [f"- {err}" for err in summary["errors"]]
        lines.append("")
    with CHANGELOG.open("a") as f:
        f.write("\n".join(lines).rstrip() + "\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True, help="CDP port of the signed-in automation Chrome")
    ap.add_argument("--only", nargs="*", help="Limit to these protocol numbers")
    ap.add_argument("--open-only", action="store_true", help="Active RT-related studies only")
    ap.add_argument("--dry-run", action="store_true", help="Find documents without downloading")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    summary = {"downloaded": [], "unchanged": [], "memos": [], "unavailable": [], "errors": []}
    notes = []
    rows = targets(args.only, args.open_only)
    baseline = None
    if not args.dry_run and not CHANGELOG.exists():
        baseline = [(proto, dict(manifest.get(proto, {}))) for proto, _lead, _role in rows]

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{args.port}")
        req = browser.contexts[0].request
        check = req.get(f"{BASE}/pp_default.aspx?nodeKey=3").text()
        if "Log Out" not in check:
            raise RuntimeError(
                "Not signed in to CTSU. Stop and ask Jeff to complete ID.me in the automation Chrome, then rerun. Do not continue against the member site while logged out."
            )

        for proto, lead, role in rows:
            entry = manifest.get(proto, {})
            try:
                doc, memo, note = find_current_protocol(req, proto, lead)
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if not doc:
                    entry.update({"status": "unavailable", "note": note, "checked_at": now})
                    manifest[proto] = entry
                    summary["unavailable"].append(proto)
                    continue
                protocol_same = entry.get("doc_id") == doc["doc_id"] and entry.get("files")
                memo_changed = bool(entry.get("amendment_doc_id")) and memo and entry.get("amendment_doc_id") != memo["doc_id"]
                if protocol_same and not memo_changed:
                    entry.update({"status": "unchanged", "checked_at": now})
                    if memo and not entry.get("amendment_doc_id"):
                        entry["amendment_doc_id"] = memo["doc_id"]
                        entry["amendment_label"] = memo["label"]
                    manifest[proto] = entry
                    summary["unchanged"].append(proto)
                    continue
                if args.dry_run:
                    print(json.dumps({"protocol": proto, "protocol_doc": doc, "memo": memo, "memo_changed": memo_changed}))
                    continue
                if protocol_same and memo_changed:
                    path, size, server_name = download(req, memo, proto, kind="amendment")
                    rel = str(path.relative_to(PROTOCOLS))
                    entry.update({
                        "status": "unchanged", "checked_at": now,
                        "amendment_doc_id": memo["doc_id"], "amendment_label": memo["label"],
                        "amendment_file": rel, "amendment_bytes": size,
                    })
                    manifest[proto] = entry
                    summary["memos"].append(proto)
                    notes.append({
                        "protocol": proto,
                        "summary": f"Amendment memorandum changed to {memo['label']}. The protocol file on disk is still {entry.get('label')}.",
                        "file": rel,
                        "memo": memo["label"],
                        "annotation": annotate_pdf(path),
                    })
                    print(json.dumps({"protocol": proto, "amendment": rel, "label": memo["label"]}), flush=True)
                    continue
                path, size, server_name = download(req, doc, proto)
                rel = str(path.relative_to(PROTOCOLS))
                history = entry.get("history", [])
                previous = entry.get("label")
                if entry.get("doc_id"):
                    history.append({k: entry.get(k) for k in ("doc_id", "label", "version", "posted", "files")})
                memo_file = entry.get("amendment_file")
                memo_label = memo["label"] if memo else None
                if memo and (not protocol_same):
                    try:
                        mpath, msize, _ = download(req, memo, proto, kind="amendment")
                        memo_file = str(mpath.relative_to(PROTOCOLS))
                    except Exception as e:
                        memo_label = f"{memo['label']} (download failed: {e})"
                        mpath = None
                        msize = None
                else:
                    mpath = None
                    msize = None
                manifest[proto] = {
                    "status": "downloaded", "rt_role": role, "doc_id": doc["doc_id"], "label": doc["label"],
                    "version": pvd_iso(doc["label"]) or doc.get("posted"), "posted": doc.get("posted"),
                    "source": doc["source"], "files": [rel], "server_filename": server_name, "bytes": size,
                    "downloaded_at": now, "checked_at": now, "history": history,
                    "amendment_doc_id": memo["doc_id"] if memo else entry.get("amendment_doc_id"),
                    "amendment_label": memo["label"] if memo else entry.get("amendment_label"),
                    "amendment_file": memo_file,
                    "amendment_bytes": msize if mpath else entry.get("amendment_bytes"),
                }
                summary["downloaded"].append(proto)
                if previous:
                    change = f"{previous} replaced by {doc['label']}"
                    if doc.get("posted"):
                        change += f" (posted {doc['posted']})"
                else:
                    change = f"First copy on file: {doc['label']}"
                    if doc.get("posted"):
                        change += f" (posted {doc['posted']})"
                annotation = annotate_pdf(Path(PROTOCOLS / memo_file)) if memo_file and mpath else annotate_pdf(path)
                notes.append({
                    "protocol": proto, "summary": change, "file": rel,
                    "memo": memo_label, "annotation": annotation,
                })
                print(json.dumps({"protocol": proto, "file": rel, "bytes": size, "label": doc["label"]}), flush=True)
            except Exception as e:
                entry.update({"status": "error", "note": str(e)})
                manifest[proto] = entry
                summary["errors"].append(f"{proto}: {e}")
            MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True))

    if not args.dry_run:
        append_log(len(rows), summary, notes, baseline)
    printable = {k: (len(v) if k != "errors" else v) for k, v in summary.items()}
    print(json.dumps(printable))
    if summary["unavailable"]:
        print(json.dumps({"unavailable": summary["unavailable"]}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
