#!/usr/bin/env python3
"""
Download current protocol documents from the CTSU member site (www.ctsu.org)
into protocols/<PROTOCOL>/ and record them in protocols/manifest.json.

Requires the automation Chrome (tools/launch_chrome_debug.sh) to be running and
signed in to CTSU; requests go through that browser's session cookies. Protocol
documents are for site use under the CTSU terms of use and stay on this machine.

Target list: every RT-related study in data/studies.json plus the institution
trials in config/institution_trials.json (run scripts/refresh.py first).
Re-running is safe: a protocol whose current document ID is already on file is
skipped, and an amended protocol is downloaded alongside the older version.

Usage:
    python3 scripts/download_protocols.py --port 9223 [--only NRG-GU013 S2427] [--dry-run]
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
BASE = "https://www.ctsu.org"
DELAY_S = 1.5

CIRB_ROW = re.compile(
    r'href="/readfile\.aspx\?EDocId=(\d+)">([^<]+)</a></td>\s*<td[^>]*ecPOST_DATE[^>]*>\s*<span[^>]*>([^<]*)</span>', re.S)
GRID_ROW = re.compile(
    r'href="/readfile\.aspx\?sectionid=(\d+)"[^>]*>([^<]+)</a>.*?ecFORMTYPEDESCRIPTION[^>]*>\s*<span[^>]*>([^<]*)</span>'
    r'.*?ecRD[^>]*>\s*<span[^>]*>([^<]*)</span>', re.S)
PROTOCOL_LABEL = re.compile(r"(protocol version date|protocol document|^protocol\b)", re.I)
GRID_PROTOCOL_LABEL = re.compile(r"(^protocol( document)?\b|change memo with protocol|^protocol version)", re.I)
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


def find_current_protocol(req, proto, lead):
    """Return (doc dict, note). doc has url, label, posted, source, doc_id."""
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
        for doc_id, label, posted in CIRB_ROW.findall(text):
            label = html.unescape(label).strip()
            if PROTOCOL_LABEL.search(label) and "consent" not in label.lower():
                return {"doc_id": f"EDoc-{doc_id}", "url": f"{BASE}/readfile.aspx?EDocId={doc_id}&mode=download",
                        "label": label, "posted": posted.strip(), "source": "CIRB-approved"}, None
        for section_id, label, doc_type, doc_date in GRID_ROW.findall(text):
            label = html.unescape(label).strip()
            if GRID_PROTOCOL_LABEL.search(label):
                return {"doc_id": f"Section-{section_id}", "url": f"{BASE}/readfile.aspx?sectionid={section_id}&mode=download",
                        "label": label, "posted": doc_date.strip(), "source": f"Documents ({doc_type.strip()})"}, None
        return None, "documents page reachable but no protocol document listed"
    return None, "documents page not available to this account (restricted or not rostered)"


def download(req, doc, proto):
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
    pvd = pvd_iso(doc["label"])
    if pvd:
        stem = f"PVD-{pvd}"
    elif doc.get("posted"):
        stem = "posted-" + datetime.strptime(doc["posted"], "%d-%b-%Y").strftime("%Y-%m-%d")
    else:
        stem = "undated"
    folder = PROTOCOLS / safe(proto)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe(proto)}_protocol_{stem}{ext or '.pdf'}"
    path.write_bytes(body)
    return path, len(body), (m.group(1) if m else None)


def targets(only):
    data = json.loads(STUDIES.read_text())
    rows = [s for s in data["studies"] if s["rt_related"] or s["ours"]]
    if only:
        wanted = set(only)
        rows = [s for s in data["studies"] if s["protocol"] in wanted]
    return [(s["protocol"], s["lead"], s["rt_role"]) for s in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True, help="CDP port of the signed-in automation Chrome")
    ap.add_argument("--only", nargs="*", help="Limit to these protocol numbers")
    ap.add_argument("--dry-run", action="store_true", help="Find documents without downloading")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    summary = {"downloaded": [], "unchanged": [], "unavailable": [], "errors": []}

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{args.port}")
        req = browser.contexts[0].request
        check = req.get(f"{BASE}/pp_default.aspx?nodeKey=3").text()
        if "Log Out" not in check:
            raise RuntimeError("Not signed in to CTSU in the automation Chrome. Sign in and rerun.")

        for proto, lead, role in targets(args.only):
            entry = manifest.get(proto, {})
            try:
                doc, note = find_current_protocol(req, proto, lead)
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if not doc:
                    entry.update({"status": "unavailable", "note": note, "checked_at": now})
                    manifest[proto] = entry
                    summary["unavailable"].append(proto)
                    continue
                if entry.get("doc_id") == doc["doc_id"] and entry.get("files"):
                    entry.update({"status": "unchanged", "checked_at": now})
                    manifest[proto] = entry
                    summary["unchanged"].append(proto)
                    continue
                if args.dry_run:
                    print(json.dumps({"protocol": proto, **doc}))
                    continue
                path, size, server_name = download(req, doc, proto)
                rel = str(path.relative_to(PROTOCOLS))
                history = entry.get("history", [])
                if entry.get("doc_id"):
                    history.append({k: entry.get(k) for k in ("doc_id", "label", "version", "posted", "files")})
                manifest[proto] = {
                    "status": "downloaded", "rt_role": role, "doc_id": doc["doc_id"], "label": doc["label"],
                    "version": pvd_iso(doc["label"]) or doc.get("posted"), "posted": doc.get("posted"),
                    "source": doc["source"], "files": [rel], "server_filename": server_name, "bytes": size,
                    "downloaded_at": now, "checked_at": now, "history": history,
                }
                summary["downloaded"].append(proto)
                print(json.dumps({"protocol": proto, "file": rel, "bytes": size, "label": doc["label"]}), flush=True)
            except Exception as e:
                entry.update({"status": "error", "note": str(e)})
                manifest[proto] = entry
                summary["errors"].append(f"{proto}: {e}")
            MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True))

    print(json.dumps({k: (len(v) if k != "errors" else v) for k, v in summary.items()}))
    if summary["unavailable"]:
        print(json.dumps({"unavailable": summary["unavailable"]}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
