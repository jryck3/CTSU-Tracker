#!/usr/bin/env python3
"""
Refresh the CTSU trials workspace.

1. Pull the public CTSU protocol list (the same feed behind
   https://ctsu.cancer.gov/protocol), save a dated snapshot, and update
   data/accrual_history.csv (one row per protocol per day).
2. Enrich each study from the ClinicalTrials.gov v2 API (cached in
   data/ctgov/, refreshed when older than CTGOV_MAX_AGE_DAYS).
3. Classify RT involvement, compute accrual rates, and write data/studies.json.
4. Build the public dashboard (docs/index.html, served by GitHub Pages) and,
   when protocols/manifest.json exists, the local dashboard
   (dashboard/index.html) that also shows which protocols are on file.

The public page starts with an empty "My trials" list that each visitor fills
in; Google sign-in (Firebase) is offered when FIREBASE_WEB_CONFIG holds the
Firebase web app config as JSON. The local page starts from
config/institution_trials.json.

GitHub Actions runs this daily and commits the history and public page. On the
Mac, use --no-save after `git pull` so tracked files are left to Actions.

Usage:
    python3 scripts/refresh.py [--skip-ctgov] [--force-ctgov] [--no-save]
"""
import argparse
import csv
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"
CTGOV_CACHE = DATA / "ctgov"
HISTORY_CSV = DATA / "accrual_history.csv"
STUDIES_JSON = DATA / "studies.json"
CONFIG = ROOT / "config" / "institution_trials.json"
OVERRIDES = ROOT / "config" / "rt_overrides.json"
MANIFEST = ROOT / "protocols" / "manifest.json"
TEMPLATE = ROOT / "dashboard" / "template.html"
DASHBOARD = ROOT / "dashboard" / "index.html"
PUBLIC_SITE = ROOT / "docs" / "index.html"
SITE_URL = "https://jryck3.github.io/Rad-Onc-Review/"
LOCAL_ONLY_FIELDS = ("protocol_on_file", "protocol_version", "ours")
LOCAL_ONLY_KEYS = ("institution", "institution_label", "institution_missing")
FIREBASE_KEYS = ("apiKey", "authDomain", "projectId", "appId")

CTSU_BROWSE_URL = "https://ctsu.cancer.gov/web-data-service/v1/protocols/browse"
CTGOV_URL = "https://clinicaltrials.gov/api/v2/studies"
CTGOV_FIELDS = ",".join([
    "protocolSection.identificationModule",
    "protocolSection.statusModule",
    "protocolSection.designModule",
    "protocolSection.armsInterventionsModule",
    "protocolSection.conditionsModule",
    "protocolSection.descriptionModule.briefSummary",
])
CTGOV_MAX_AGE_DAYS = 7
CTGOV_BATCH = 80
DAYS_PER_MONTH = 30.4375
HISTORY_FIELDS = ["date", "protocol", "nct", "status", "accrual", "target", "screening"]

RT_TERMS = re.compile(
    r"\b(radiation|radiotherap\w*|chemoradi\w*|radiochemo\w*|immunoradi\w*|irradiat\w*|"
    r"reirradiat\w*|SBRT|SABR|SRS|stereotactic|radiosurg\w*|proton(?!\s*pump)|brachytherap\w*|"
    r"IMRT|VMAT|hypofractionat\w*|craniospinal|whole[- ]brain|RT)\b",
    re.I,
)
RADIOPHARM = re.compile(
    r"(lutetium|\bLu[- ]?177\b|\b177[- ]?Lu|radium|\bRa[- ]?223\b|actinium|\bAc[- ]?225\b|"
    r"yttrium[- ]?90|\bY[- ]?90\b|thorium|\bPb[- ]?212\b|astatine|iobenguane I[- ]?131|131I[- ]?MIBG|"
    r"radioligand therap\w*|radioemboli\w*|PSMA[- ]?617|\bSIRT\b|radioimmunotherap\w*)",
    re.I,
)
IMAGING = re.compile(
    r"(tomograph|\bPET\b|\bCT\b|x-?ray|radiograph|scintigraph|bone scan|imaging|mammogra|"
    r"\bDXA\b|\bDEXA\b|MUGA|SPECT|\bscan\b|fluciclovine|piflufolastat|gallium|\bGa[- ]?68\b|"
    r"\bF[- ]?18\b|fluorine|FDG|copper Cu|zirconium)",
    re.I,
)


def ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for bundle in ("/etc/ssl/cert.pem", "/usr/local/etc/openssl/cert.pem"):
        if Path(bundle).exists():
            return ssl.create_default_context(cafile=bundle)
    return ssl.create_default_context()


SSL_CTX = ssl_context()


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (CTSU trials workspace; personal research use)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
        return json.load(resp)


def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def parse_date(text):
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- CTSU feed

def snapshot_ctsu(today, save=True):
    protocols = fetch_json(CTSU_BROWSE_URL)
    if not isinstance(protocols, list) or not protocols:
        raise RuntimeError("CTSU browse feed returned no protocols")
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if save:
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        (SNAPSHOTS / f"{today.isoformat()}.json").write_text(json.dumps(
            {"fetched_at": fetched_at, "source": CTSU_BROWSE_URL, "count": len(protocols), "protocols": protocols},
            indent=1,
        ))
    return protocols, fetched_at


def update_history(protocols, today, save=True):
    rows = []
    if HISTORY_CSV.exists():
        with HISTORY_CSV.open(newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["date"] != today.isoformat()]
    for p in protocols:
        rows.append({
            "date": today.isoformat(),
            "protocol": p.get("protocolNumber"),
            "nct": p.get("nctNumber") or "",
            "status": p.get("protocolStatus") or "",
            "accrual": p.get("interventionAccrualTotal") if p.get("interventionAccrualTotal") is not None else "",
            "target": p.get("interventionAccrualTarget") if p.get("interventionAccrualTarget") is not None else "",
            "screening": p.get("screeningAccrualTotal") or "",
        })
    rows.sort(key=lambda r: (r["protocol"], r["date"]))
    if save:
        with HISTORY_CSV.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
            w.writeheader()
            w.writerows(rows)
    history = {}
    for r in rows:
        history.setdefault(r["protocol"], []).append(r)
    return history


# ---------------------------------------------------------- ClinicalTrials.gov

def refresh_ctgov(ncts, force=False):
    CTGOV_CACHE.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stale = []
    for nct in ncts:
        cached = load_json(CTGOV_CACHE / f"{nct}.json", None)
        if force or not cached:
            stale.append(nct)
            continue
        age = now - datetime.fromisoformat(cached["fetched_at"])
        if age > timedelta(days=CTGOV_MAX_AGE_DAYS):
            stale.append(nct)
    for i in range(0, len(stale), CTGOV_BATCH):
        batch = stale[i:i + CTGOV_BATCH]
        token = None
        while True:
            params = {"filter.ids": ",".join(batch), "fields": CTGOV_FIELDS, "pageSize": 100}
            if token:
                params["pageToken"] = token
            data = fetch_json(f"{CTGOV_URL}?{urllib.parse.urlencode(params)}")
            for study in data.get("studies", []):
                ps = study.get("protocolSection", {})
                nct = ps.get("identificationModule", {}).get("nctId")
                if nct:
                    (CTGOV_CACHE / f"{nct}.json").write_text(json.dumps(
                        {"fetched_at": now.isoformat(timespec="seconds"), "protocolSection": ps}, indent=1))
            token = data.get("nextPageToken")
            if not token:
                break
    return len(stale)


def ctgov_record(nct):
    if not nct:
        return {}
    cached = load_json(CTGOV_CACHE / f"{nct}.json", None)
    return cached.get("protocolSection", {}) if cached else {}


# ------------------------------------------------------------- Classification

def classify_rt(ctsu, ps, overrides):
    """Return (role, evidence list). Roles: RT-focused, RT component,
    Radiopharmaceutical, Possible (arm text only), or None."""
    ident = ps.get("identificationModule", {})
    titles = " | ".join(filter(None, [ctsu.get("protocolTitle"), ident.get("officialTitle"), ident.get("briefTitle")]))
    interventions = ps.get("armsInterventionsModule", {}).get("interventions", []) or []
    arms = ps.get("armsInterventionsModule", {}).get("armGroups", []) or []

    evidence = []
    title_rt = RT_TERMS.search(titles)
    if title_rt:
        evidence.append(f"title: {title_rt.group(0)}")

    rt_iv, radiopharm_iv = [], []
    for iv in interventions:
        name = iv.get("name", "")
        names = " ".join([name] + (iv.get("otherNames") or []))
        if RADIOPHARM.search(names):
            radiopharm_iv.append(name)
        elif IMAGING.search(names) and not RT_TERMS.search(name):
            continue
        elif iv.get("type") == "RADIATION" or RT_TERMS.search(name):
            rt_iv.append(name)
    if rt_iv:
        evidence.append("intervention: " + "; ".join(sorted(set(rt_iv))))
    if radiopharm_iv:
        evidence.append("radiopharmaceutical: " + "; ".join(sorted(set(radiopharm_iv))))

    arm_hits = [a.get("label", "") for a in arms
                if RT_TERMS.search(a.get("description", "") or "") or RT_TERMS.search(a.get("label", "") or "")]
    if arm_hits and not (title_rt or rt_iv):
        evidence.append("arm text: " + "; ".join(arm_hits[:3]))

    override = overrides.get(ctsu.get("protocolNumber"))
    if override:
        evidence.append(f"manual: {override.get('reason', '')}".strip())
        return override.get("role"), evidence
    if (radiopharm_iv or RADIOPHARM.search(titles)) and not rt_iv:
        return "Radiopharmaceutical", evidence
    if title_rt:
        return "RT-focused", evidence
    if rt_iv:
        return "RT component", evidence
    if arm_hits:
        return "Possible (arm text only)", evidence
    return None, evidence


RT_RELATED_ROLES = {"RT-focused", "RT component", "Radiopharmaceutical"}


# ------------------------------------------------------------------- Rates

def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def trailing_rate(points, today, window_days, min_days=7):
    """Accrual per month over roughly the last window_days, from daily history."""
    if len(points) < 2:
        return None
    latest = points[-1]
    cutoff = today - timedelta(days=window_days)
    candidates = [p for p in points[:-1]
                  if date.fromisoformat(p["date"]) >= cutoff
                  and (today - date.fromisoformat(p["date"])).days >= min_days]
    if not candidates:
        return None
    base = candidates[0]
    a0, a1 = to_int(base["accrual"]), to_int(latest["accrual"])
    if a0 is None or a1 is None:
        return None
    span = (date.fromisoformat(latest["date"]) - date.fromisoformat(base["date"])).days
    return {"per_month": round((a1 - a0) / span * DAYS_PER_MONTH, 2), "days": span, "delta": a1 - a0}


def compress_history(points):
    """Keep first, last, and every change in accrual or target."""
    out, last = [], None
    for i, p in enumerate(points):
        key = (p["accrual"], p["target"], p["status"])
        if i == 0 or i == len(points) - 1 or key != last:
            out.append([p["date"], to_int(p["accrual"]), to_int(p["target"]), p["status"]])
        last = key
    return out


# ------------------------------------------------------------------- Build

def build(protocols, history, fetched_at, today):
    config = load_json(CONFIG, {"trials": []})
    ours = {t["protocol"]: t for t in config["trials"]}
    overrides = load_json(OVERRIDES, {})
    manifest = load_json(MANIFEST, {})

    studies = []
    for p in protocols:
        proto = p.get("protocolNumber")
        ps = ctgov_record(p.get("nctNumber"))
        status_mod = ps.get("statusModule", {})
        start = parse_date(status_mod.get("startDateStruct", {}).get("date"))
        start_type = status_mod.get("startDateStruct", {}).get("type")
        acronym = ps.get("identificationModule", {}).get("acronym")
        accrual, target = p.get("interventionAccrualTotal"), p.get("interventionAccrualTarget")
        role, evidence = classify_rt(p, ps, overrides)

        months_open = avg_rate = projected = None
        if start and start <= today:
            months_open = round((today - start).days / DAYS_PER_MONTH, 1)
            if accrual is not None and months_open >= 0.5:
                avg_rate = round(accrual / months_open, 2)
                if target and avg_rate > 0 and accrual < target:
                    projected = (today + timedelta(days=(target - accrual) / avg_rate * DAYS_PER_MONTH)).isoformat()

        pts = history.get(proto, [])
        doc = manifest.get(proto) or {}
        studies.append({
            "protocol": proto,
            "nct": p.get("nctNumber"),
            "lead": p.get("leadGrp"),
            "program": p.get("nciProgram"),
            "phase": p.get("phase"),
            "status": p.get("protocolStatus"),
            "disease": p.get("disease"),
            "title": p.get("protocolTitle"),
            "accrual": accrual,
            "target": target,
            "screening": p.get("screeningAccrualTotal"),
            "accrual_type": p.get("accrualTypeCsv"),
            "pct": round(100 * accrual / target, 1) if accrual is not None and target else None,
            "rt_role": role,
            "rt_related": role in RT_RELATED_ROLES,
            "rt_evidence": evidence,
            "start_date": start.isoformat() if start else None,
            "start_type": start_type,
            "primary_completion": status_mod.get("primaryCompletionDateStruct", {}).get("date"),
            "ctgov_status": status_mod.get("overallStatus"),
            "months_open": months_open,
            "avg_rate": avg_rate,
            "projected_completion": projected,
            "trailing30": trailing_rate(pts, today, 30),
            "trailing90": trailing_rate(pts, today, 90),
            "ours": proto in ours,
            "alias": ours.get(proto, {}).get("alias") or acronym,
            "protocol_on_file": bool(doc.get("files")),
            "protocol_version": doc.get("version"),
        })

    missing = sorted(set(ours) - {s["protocol"] for s in studies})
    rt = [s for s in studies if s["rt_related"]]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_fetched_at": fetched_at,
        "history_start": min((pts[0]["date"] for pts in history.values() if pts), default=today.isoformat()),
        "snapshot_days": len({p["date"] for pts in history.values() for p in pts}),
        "sources": {"ctsu": "https://ctsu.cancer.gov/protocol", "ctgov": "https://clinicaltrials.gov"},
        "site_url": SITE_URL,
        "institution_label": config.get("institution_label"),
        "institution": [t["protocol"] for t in config["trials"]],
        "institution_missing": missing,
        "counts": {
            "all": len(studies),
            "active": sum(s["status"] == "Active" for s in studies),
            "rt_related": len(rt),
            "rt_open": sum(s["status"] == "Active" for s in rt),
            "ours": sum(s["ours"] for s in studies),
        },
        "studies": studies,
        "history": {proto: compress_history(pts) for proto, pts in history.items()},
    }
    STUDIES_JSON.write_text(json.dumps(payload, indent=1))
    return payload


def firebase_config():
    """Firebase web app config from the FIREBASE_WEB_CONFIG environment variable
    (a GitHub Actions repository variable). These values identify the project and
    are public by design; access is enforced by Firestore rules."""
    raw = os.environ.get("FIREBASE_WEB_CONFIG", "").strip()
    if not raw:
        return None
    cfg = json.loads(raw)
    missing = [k for k in FIREBASE_KEYS if not cfg.get(k)]
    if missing:
        raise ValueError(f"FIREBASE_WEB_CONFIG is missing {', '.join(missing)}")
    return cfg


def to_script(obj):
    return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")


def render_dashboard(payload, out, local, firebase=None):
    data = dict(payload, local=local)
    if not local:
        for k in LOCAL_ONLY_KEYS:
            data.pop(k, None)
        data["counts"] = {k: v for k, v in payload["counts"].items() if k != "ours"}
        data["studies"] = [{k: v for k, v in s.items() if k not in LOCAL_ONLY_FIELDS} for s in payload["studies"]]
    html = (TEMPLATE.read_text()
            .replace("/*__FIREBASE__*/null", to_script(firebase))
            .replace("/*__DATA__*/null", to_script(data)))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ctgov", action="store_true", help="Use cached ClinicalTrials.gov data only")
    ap.add_argument("--force-ctgov", action="store_true", help="Refetch all ClinicalTrials.gov records")
    ap.add_argument("--no-save", action="store_true",
                    help="Leave the snapshot, history CSV, and public page untouched (local rebuild)")
    args = ap.parse_args()

    today = date.today()
    save = not args.no_save
    protocols, fetched_at = snapshot_ctsu(today, save=save)
    history = update_history(protocols, today, save=save)
    refreshed = 0
    if not args.skip_ctgov:
        ncts = sorted({p["nctNumber"] for p in protocols if p.get("nctNumber")})
        refreshed = refresh_ctgov(ncts, force=args.force_ctgov)
    payload = build(protocols, history, fetched_at, today)
    if save:
        render_dashboard(payload, PUBLIC_SITE, local=False, firebase=firebase_config())
    if MANIFEST.exists():
        render_dashboard(payload, DASHBOARD, local=True)
    c = payload["counts"]
    print(json.dumps({
        "date": today.isoformat(), "ctgov_refreshed": refreshed, **c,
        "institution_missing": payload["institution_missing"],
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
