"""Read-only access to the CTSU protocol library for this and other projects.

The WVU tracker, the Worldwide RT tracker, and the CTSU extractor all read
protocols through this module. The PDFs stay in protocols/ under the CTSU
terms of use. Other projects get the briefs and manifest metadata, never the
files. The library is located from this file, so it works on either Mac.

    import sys; sys.path.insert(0, ".../CTSU Trials Workspace/scripts")
    import protocol_library as lib
    lib.current_pdf("NRG-GU013")
    lib.find_brief(["NRG-GU013"])        # (protocol, brief) or (None, None)
    lib.library_stamp()                  # {"as_of": "2026-10-11", "hash": "..."}
"""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOLS = ROOT / "protocols"
MANIFEST = PROTOCOLS / "manifest.json"
BRIEFS = ROOT / "data" / "protocol_briefs.json"
STUDIES = ROOT / "data" / "studies.json"

NRG_ID = re.compile(r"\bNRG[-\s]?([A-Z]{2})[-\s]?(\d{3,4})\b", re.I)
SWOG_ID = re.compile(r"\bSWOG[-\s]*S?(\d{4})\b|\bS(\d{4})\b", re.I)
ECOG_EA = re.compile(r"\b(EA\d{3,4})\b", re.I)
ECOG_E = re.compile(r"\bE(\d{4})\b", re.I)
RTOG_ID = re.compile(r"\bRTOG[-\s]?(\d{4})\b", re.I)
GROUP_PREFIX = re.compile(r"^(?:COG|CCTG)[-\s]+(\S+)$", re.I)
LOOSE_ID = re.compile(r"[A-Z]{1,6}[-.\s]?\d{2,5}")


def _compact(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


@lru_cache(maxsize=1)
def manifest():
    return _read_json(MANIFEST, {})


@lru_cache(maxsize=1)
def briefs():
    return _read_json(BRIEFS, {})


def reload():
    manifest.cache_clear()
    briefs.cache_clear()
    _brief_index.cache_clear()


def _is_protocol_pdf(path):
    name = path.name.lower()
    return "amendment" not in name and "memo" not in name


def current_pdf(protocol):
    """The PDF the manifest names as current. Falls back to the newest protocol PDF by name."""
    entry = manifest().get(protocol) or {}
    for rel in entry.get("files") or []:
        path = PROTOCOLS / rel
        if path.is_file():
            return path
    folder = PROTOCOLS / protocol
    if not folder.is_dir():
        return None
    files = sorted(path for path in folder.glob("*.pdf") if path.is_file())
    protocols = [path for path in files if _is_protocol_pdf(path)]
    return (protocols or files or [None])[-1]


def protocol_folders():
    if not PROTOCOLS.is_dir():
        return []
    return sorted(path.name for path in PROTOCOLS.iterdir() if path.is_dir() and any(path.glob("*.pdf")))


def keys(value):
    """Every spelling a protocol number goes by: NRG-GU013, NRGGU013, S2427, SWOG S2427, COG-ANBL2131."""
    text = (value or "").strip()
    if not text:
        return []
    found = {text.upper(), _compact(text)}
    prefixed = GROUP_PREFIX.match(text)
    if prefixed:
        found.add(prefixed.group(1).upper())
        found.add(_compact(prefixed.group(1)))
    for match in NRG_ID.finditer(text):
        found.add(f"NRG-{match.group(1).upper()}{match.group(2)}")
    for match in SWOG_ID.finditer(text):
        number = next(group for group in match.groups() if group)
        found.add(f"S{number}")
    for match in ECOG_EA.finditer(text):
        found.add(match.group(1).upper())
    for match in ECOG_E.finditer(text):
        found.add(f"E{match.group(1)}")
    for match in RTOG_ID.finditer(text):
        found.add(f"RTOG-{match.group(1)}")
        found.add(f"RTOG{match.group(1)}")
    return [key for key in found if key]


def _loose_keys(value):
    found = {_compact(value)}
    for match in LOOSE_ID.finditer((value or "").upper()):
        found.add(_compact(match.group(0)))
    return {key for key in found if len(key) >= 4}


@lru_cache(maxsize=1)
def _brief_index():
    index = {}
    for protocol in briefs():
        for key in keys(protocol):
            index.setdefault(key, protocol)
    return index


def _rank(protocol):
    brief = briefs()[protocol]
    return (bool(brief.get("schema")), len(brief.get("eligibility") or []))


def find_brief(ids):
    """Best brief for a trial's protocol numbers: (protocol, brief) or (None, None).

    Exact spellings first. Otherwise a protocol number that ends the same way
    (RTOG 0617 and NRG-RTOG0617, for example), five characters or more.
    """
    if isinstance(ids, str):
        ids = [ids]
    index = _brief_index()
    exact = []
    for value in ids or []:
        for key in keys(value):
            protocol = index.get(key)
            if protocol and protocol not in exact:
                exact.append(protocol)
    if exact:
        best = max(exact, key=_rank)
        return best, briefs()[best]
    wanted = set()
    for value in ids or []:
        wanted |= _loose_keys(value)
    compact = {_compact(protocol): protocol for protocol in briefs()}
    for key in wanted:
        if len(key) < 5:
            continue
        for folder_key, protocol in compact.items():
            if folder_key.endswith(key) or key.endswith(folder_key):
                return protocol, briefs()[protocol]
    return None, None


def brief(protocol):
    return find_brief([protocol])[1]


def library_stamp():
    """When the library was last checked, plus a hash of the manifest and briefs."""
    digest = hashlib.sha256()
    for path in (MANIFEST, BRIEFS):
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"-")
    checked = [entry.get("checked_at") or "" for entry in manifest().values() if isinstance(entry, dict)]
    return {"as_of": (max(checked) if checked else "")[:10], "hash": digest.hexdigest()[:16]}
