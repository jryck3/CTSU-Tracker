"""Sanitized CTSU public export. Consumers trust this file, not a local cache."""
import hashlib
import json
import re
from datetime import date, timedelta

SCHEMA_VERSION = 1
TAXONOMY_VERSION = 1
DAYS_PER_MONTH = 30.4375

BRIEF_KEYS = (
    "version_date", "version_label", "posted", "amendments", "schema",
    "eligibility", "pretreatment", "during", "followup", "calendar",
    "specimens", "submission", "schema_source",
)
FORBIDDEN_KEYS = re.compile(r"password|secret|token|apiKey|institution|credential", re.I)
FORBIDDEN_VALUES = re.compile(
    r"/Users/|ACCESS_CODE|ghp_|xoxb-|BEGIN PRIVATE|protocols[/\\].+\.pdf",
    re.I,
)


class ExportPrivacyError(ValueError):
    pass


def gate_projected_date(today, months_open, accrual, target, avg_rate, days_per_month=DAYS_PER_MONTH):
    """Show a source-based month only when the average rate is stable enough."""
    if today is None or accrual is None or not target or not avg_rate or avg_rate <= 0:
        return None
    if accrual >= target or months_open is None or months_open < 6 or accrual < 20:
        return None
    projected = today + timedelta(days=(target - accrual) / avg_rate * days_per_month)
    if (projected - today).days > 15 * 365:
        return None
    return projected.isoformat()


def _aliases(protocol):
    protocol = protocol or ""
    found = []
    for item in (protocol, re.sub(r"\s+", "", protocol)):
        if item and item not in found:
            found.append(item)
    match = re.match(r"^(?:COG|CCTG)[\s-]+(.+)$", protocol)
    if match and match.group(1) not in found:
        found.append(match.group(1))
    return found


def _status_basis(study):
    if study.get("status") == "Approved" and study.get("listed_on") == "clinicaltrials.gov":
        return "ClinicalTrials.gov Not yet recruiting and absent from the CTSU list"
    return "CTSU protocol list"


def _phase_normalized(phase):
    text = str(phase or "").strip()
    if not text or text.lower() in ("null", "none", "not specified"):
        return "Not stated"
    return text


def _copy_brief(brief):
    if not isinstance(brief, dict):
        return None
    copied = {}
    for key in BRIEF_KEYS:
        if key in brief:
            copied[key] = brief[key]
    return copied or None


def _scan(value, path):
    if isinstance(value, dict):
        for key, item in value.items():
            if FORBIDDEN_KEYS.search(str(key)):
                raise ExportPrivacyError(f"forbidden field {path}{key}")
            _scan(item, f"{path}{key}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan(item, f"{path}{index}.")
    elif isinstance(value, str) and FORBIDDEN_VALUES.search(value):
        raise ExportPrivacyError(f"forbidden value at {path}")


def public_study(study, snapshot_at):
    protocol = study.get("protocol") or ""
    accrual = study.get("accrual")
    return {
        "id": protocol,
        "protocol": protocol,
        "aliases": _aliases(protocol),
        "nct": study.get("nct") or "",
        "ctsu_status": study.get("status") or "",
        "registry_status": study.get("ctgov_status") or "",
        "status_basis": _status_basis(study),
        "accrual": accrual,
        "target": study.get("target"),
        "accrual_type": study.get("accrual_type"),
        "measurement": {
            "kind": "intervention accrual" if study.get("accrual_type") in (None, "", "INTERVENTION") else study.get("accrual_type"),
            "source": "CTSU browse feed" if study.get("listed_on") != "clinicaltrials.gov" else "not on the CTSU list",
            "snapshot_at": snapshot_at,
        },
        "phase": study.get("phase") or "",
        "phase_normalized": _phase_normalized(study.get("phase")),
        "lead": study.get("lead") or "",
        "rt_role": study.get("rt_role") or "",
        "anatomy": list(study.get("anatomy") or []),
        "histology": list(study.get("histology") or []),
        "burden": list(study.get("burden") or []),
        "intent": study.get("intent") or "not_classified",
        "cancer_types": list(study.get("cancer_types") or ["Not classified"]),
        "title": study.get("title") or "",
        "disease": study.get("disease") or "",
        "brief": _copy_brief(study.get("brief")),
        "projected_completion": study.get("projected_completion"),
        "avg_rate": study.get("avg_rate"),
    }


def _hash_study(study):
    copied = {key: value for key, value in study.items() if key not in ("projected_completion", "avg_rate")}
    measurement = dict(copied.get("measurement") or {})
    measurement.pop("snapshot_at", None)
    copied["measurement"] = measurement
    return copied


def content_hash(export):
    consumed = {
        "schema_version": export["schema_version"],
        "taxonomy_version": export["taxonomy_version"],
        "studies": [_hash_study(study) for study in export["studies"]],
        "history": export.get("history") or {},
    }
    raw = json.dumps(consumed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_public_export(payload, producer_revision="", library_as_of=""):
    snapshot_at = payload.get("snapshot_fetched_at") or ""
    studies = [public_study(study, snapshot_at) for study in payload.get("studies") or []]
    export = {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "generated_at": payload.get("generated_at") or "",
        "snapshot_fetched_at": snapshot_at,
        "protocol_library_as_of": library_as_of or payload.get("protocol_library_as_of") or "",
        "producer_revision": producer_revision,
        "history_start": payload.get("history_start") or "",
        "record_count": len(studies),
        "studies": studies,
        "history": payload.get("history") or {},
    }
    _scan(export, "")
    export_hash = content_hash(export)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "producer_revision": producer_revision,
        "snapshot_fetched_at": snapshot_at,
        "history_start": export["history_start"],
        "protocol_library_as_of": export["protocol_library_as_of"],
        "record_count": len(studies),
        "content_hash": export_hash,
    }
    return export, manifest


def unchanged(manifest_path, export_hash):
    if not manifest_path.is_file():
        return False
    try:
        previous = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return False
    return previous.get("content_hash") == export_hash
