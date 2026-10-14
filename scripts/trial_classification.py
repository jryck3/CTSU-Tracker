"""Build-time disease classification for the three trial trackers.

Anatomy, histology, metastatic burden, and treatment intent stay separate.
Reviewed fields replace inferred ones. A raw source category, an acronym
substring, a toxicity organ, or a negated exclusion does not become a
population tag. Browsers render these fields. They do not repeat these rules.
"""
import re

TAXONOMY_VERSION = 1

_NOISE_LABELS = {
    "Miscellaneous and Metastatic Cancer",
    "Other Cancers",
    "Other Hematopoietic",
    "Other",
}
_NOISE_TEXT = re.compile(
    r"Miscellaneous and Metastatic Cancer|Other Cancers|Other Hematopoietic",
    re.I,
)
_NONTHERAPEUTIC = (
    (re.compile(r"smoking cessation|\bwho smoke\b", re.I), "Smoking cessation"),
    (re.compile(r"early detection|multi-cancer early", re.I), "Early detection"),
    (re.compile(r"biorepository|biospecimen", re.I), "Biorepository"),
    (re.compile(r"\bregistry\b|eligibility screening", re.I), "Registry"),
)

# Histology. Myeloma does not match the MyeloMATCH acronym. Ovary does not
# match ovarian function suppression.
HISTOLOGY = [
    ("NSCLC", re.compile(r"non[-\s]?small[-\s]?cell lung|\bnsclc\b", re.I)),
    ("SCLC", re.compile(r"(?<!non[-\s])small[-\s]?cell lung|\bsclc\b", re.I)),
    ("Mesothelioma", re.compile(r"mesothelioma", re.I)),
    ("Thymoma", re.compile(r"thymoma|\bthymic\b", re.I)),
    ("Plasmacytoma", re.compile(r"plasmacytoma", re.I)),
    ("Myeloma", re.compile(r"(?<![a-z])myeloma(?![a-z])", re.I)),
    ("Leukemia", re.compile(r"leukemia|leukaemia|\bAML\b|\bMDS\b|myelodysplas", re.I)),
    ("Lymphoma", re.compile(r"lymphoma|hodgkin", re.I)),
    ("Myelofibrosis", re.compile(r"myelofibrosis", re.I)),
    ("Prostate", re.compile(r"prostate|\bcrpc\b", re.I)),
    ("Bladder", re.compile(r"bladder|urothelial", re.I)),
    ("Kidney", re.compile(r"renal cell|renal carcinoma|kidney cancer", re.I)),
    ("Testis", re.compile(r"testicular|\bgerm cell\b", re.I)),
    ("Penile", re.compile(r"\bpenile\b", re.I)),
    ("Pancreas", re.compile(r"pancrea", re.I)),
    ("Colorectal", re.compile(r"colorectal", re.I)),
    ("Rectal", re.compile(r"\brectal\b", re.I)),
    ("Colon", re.compile(r"\bcolon\b", re.I)),
    ("Esophagus", re.compile(r"esophag", re.I)),
    ("Gastric", re.compile(r"gastric|\bstomach\b", re.I)),
    ("Liver", re.compile(r"hepatocellular|\bhcc\b|\bliver\b", re.I)),
    ("Biliary", re.compile(r"biliary|cholangi", re.I)),
    ("Anal", re.compile(r"\banal\b", re.I)),
    ("Cervix", re.compile(r"cervix|cervical cancer|cervical carcinoma", re.I)),
    ("Endometrial", re.compile(r"endometr", re.I)),
    ("Ovary", re.compile(r"ovarian(?!\s+function)", re.I)),
    ("Vulva", re.compile(r"vulvar", re.I)),
    ("Nasopharynx", re.compile(r"nasopharyn", re.I)),
    ("Oropharynx", re.compile(r"oropharyn", re.I)),
    ("Hypopharynx", re.compile(r"hypopharyn", re.I)),
    ("Larynx", re.compile(r"laryng", re.I)),
    ("Sinonasal", re.compile(r"sinonasal", re.I)),
    ("Oral cavity", re.compile(r"oral cavity", re.I)),
    ("Salivary", re.compile(r"salivary", re.I)),
    ("Glioma", re.compile(r"glioblastoma|\bglioma|\bgliom", re.I)),
    ("Meningioma", re.compile(r"meningiom", re.I)),
    ("Medulloblastoma", re.compile(r"medulloblast", re.I)),
    ("Ependymoma", re.compile(r"ependym", re.I)),
    ("Breast", re.compile(r"\bbreast\b", re.I)),
    ("Sarcoma", re.compile(r"sarcoma", re.I)),
    ("Melanoma", re.compile(r"melanoma", re.I)),
    ("Merkel", re.compile(r"merkel", re.I)),
    ("NET", re.compile(r"neuroendocrine", re.I)),
    ("Head and neck", re.compile(r"head and neck|head/neck", re.I)),
    ("AML", re.compile(r"acute myeloid|\bAML\b", re.I)),
]

# Anatomical parents. Neuroendocrine disease is not also endocrine.
ANATOMY = [
    ("Lung", re.compile(r"lung|mesothelioma|thymoma|thymic|pleura|mediastin", re.I)),
    ("Heme", re.compile(r"lymphoma|leukemia|leukaemia|plasmacytoma|myelofibrosis|myelodysplas|hematolog|hematopoietic|\bAML\b|\bMDS\b", re.I)),
    ("GI", re.compile(r"gastrointestinal|\bGI\b|esophag|gastric|\bstomach\b|pancrea|colorectal|\bcolon\b|\brectal\b|hepatocellular|\bliver\b|biliary|cholangi|\banal\b", re.I)),
    ("GU", re.compile(r"prostate|\bGU\b|genitourinary|bladder|urothelial|kidney|renal|testicular|\bpenile\b|male reproductive", re.I)),
    ("Gyn", re.compile(r"gynecolog|\bGyn\b|cervix|cervical|ovarian(?!\s+function)|endometr|vulvar|uterine|female reproductive", re.I)),
    ("Breast", re.compile(r"\bbreast\b", re.I)),
    ("H&N", re.compile(r"head and neck|head/neck|nasopharyn|oropharyn|hypopharyn|laryng|sinonasal|oral cavity|salivary", re.I)),
    ("CNS", re.compile(r"central nervous|\bcns\b|glioblastoma|\bglioma|meningiom|medulloblast|ependym|\bbrain\b", re.I)),
    ("Sarcoma", re.compile(r"sarcoma|soft tissue", re.I)),
    ("Skin", re.compile(r"melanoma|merkel|cutaneous|skin cancer", re.I)),
    ("Endocrine", re.compile(r"(?<!neuro)endocrine", re.I)),
    ("Bone", re.compile(r"\bbone\b", re.I)),
]

_NOT_OLIGO = r"(?<!non[-\s])"
_MIXED_BURDEN = re.compile(
    r"locally advanced\s+or\s+metastatic|locally advanced\s+and\s+metastatic|"
    r"metastatic\s+or\s+locally advanced|"
    r"oligometastatic\s+or\s+polymetastatic|polymetastatic\s+or\s+oligometastatic|"
    r"stage\s+(?:IIIC|IIIB|IIIA|III|IIB|IIA|II|IB|IA|I|[1-3])\s*(?:/|or)\s*(?:IV|4)\b",
    re.I,
)
_OLIGO_CAP = re.compile(
    r"(?:up to|no more than|fewer than|less than|maximum(?: of)?|max(?:imum)?(?: of)?|≤|<=)\s*"
    r"(?:[1-5]|one|two|three|four|five)\s+"
    r"((?:brain|intracranial|cerebral)\s+)?(?:metastases|metastasis|lesions|sites)\b"
    r"|(?:[1-5]|one|two|three|four|five)\s*(?:to|–|-)\s*(?:[1-5]|one|two|three|four|five)\s+"
    r"((?:brain|intracranial|cerebral)\s+)?(?:metastases|metastasis|lesions|sites)\b"
    r"|(?:[1-5]|one|two|three|four|five)\s+or fewer\s+"
    r"((?:brain|intracranial|cerebral)\s+)?(?:metastases|metastasis|lesions|sites)\b",
    re.I,
)
_POLY = re.compile(
    _NOT_OLIGO + r"\bpolymetast|\b(?:widespread|extensive)\s+metast|"
    r"(?:more than|greater than|>)\s*(?:5|five|[6-9]|[1-9]\d|six|seven|eight|nine|ten)\s+"
    r"(?:\w+\s+){0,3}(?:metastases|metastasis|lesions|sites)\b|"
    r"(?:at least|≥|>=)\s*(?:[6-9]|[1-9]\d|six|seven|eight|nine|ten)\s+"
    r"(?:\w+\s+){0,3}(?:metastases|metastasis|lesions|sites)\b",
    re.I,
)
_CURATIVE = re.compile(
    r"non[-\s]?metastatic|\bM0\b|no distant metast|without distant metast|"
    r"locally advanced|locoregional|resectable primary|\badjuvant\b|\bneoadjuvant\b|"
    r"high-risk prostate|early-stage|node-positive",
    re.I,
)
_NEGATED_CLAUSE = re.compile(
    r"\b(?:no|not|without|excluding|except|absence of|free of|ineligible|must not)\b",
    re.I,
)
_ENDPOINT_MET = re.compile(
    r"\bmetastas(?:is|es)[-\s]free\b|\bdistant[-\s]metastasis[-\s]free\b",
    re.I,
)
_NODAL_MET = re.compile(
    r"\b(?:nodal|node|regional|pelvic|mediastinal|para-aortic|cervical)\s+"
    r"(?:lymph\s+)?metast\w*|\bnodal metastases\b",
    re.I,
)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value if str(item).strip()]


def _eligibility_text(value):
    if isinstance(value, str):
        return value
    lines = []
    for item in value or []:
        if isinstance(item, dict):
            lines.append(" ".join(str(item.get(key) or "") for key in ("label", "text", "note")))
        else:
            lines.append(str(item))
    return " ".join(lines)


def _population_text(record, include_disease):
    parts = [record.get("title") or "", record.get("population") or ""]
    if include_disease:
        parts.extend(_as_list(record.get("disease")))
        parts.extend(_as_list(record.get("conditions")))
        parts.append(record.get("ctsu_disease") or "")
    parts.append(_eligibility_text(record.get("eligibility")))
    text = _NOISE_TEXT.sub(" ", " ".join(parts))
    text = _ENDPOINT_MET.sub(" ", text)
    return text


def _sentences(text):
    return [part.strip() for part in re.split(r"(?<=[.!;])\s+|\s*\|\s*", text or "") if part.strip()]


def _enrolled_text(text):
    """Drop exclusions and negated metastatic clauses before burden matching."""
    kept = []
    for sentence in _sentences(text):
        if _NEGATED_CLAUSE.search(sentence) and re.search(r"\bmetast|\bM1[a-c]?\b", sentence, re.I):
            continue
        kept.append(sentence)
    cleaned = " ".join(kept)
    cleaned = _NODAL_MET.sub(" ", cleaned)
    cleaned = re.sub(r"\bNo M1[a-c]?\b", " ", cleaned, flags=re.I)
    return cleaned


def _hits(rules, text):
    found = []
    for label, pattern in rules:
        if pattern.search(text or "") and label not in found:
            found.append(label)
    if "Colorectal" in found:
        found = [label for label in found if label not in ("Colon", "Rectal")]
    if "AML" in found and "Leukemia" in found:
        found = [label for label in found if label != "Leukemia"]
    return found


def _oligo_cap(text):
    matches = list(_OLIGO_CAP.finditer(text or ""))
    if not matches:
        return False
    return any(not (match.group(1) or match.group(2) or match.group(3)) for match in matches)


def _metastatic_signal(text):
    if re.search(r"\bM0\b", text or "") and not re.search(r"\bM1[a-c]?\b", text or ""):
        return False
    if re.search(_NOT_OLIGO + r"\bmetast", text or "", re.I):
        return True
    if re.search(r"\bM1[a-c]?\b", text or ""):
        return True
    return bool(re.search(r"\bstage\s+(?:IV|4)\b", text or "", re.I))


def _nontherapeutic(text):
    for pattern, label in _NONTHERAPEUTIC:
        if pattern.search(text or ""):
            return label
    return ""


BURDEN_ORDER = ("Oligoprogressive", "Oligometastatic", "Polymetastatic", "Other")
_BURDEN_FOLD = {"Oligopersistent": "Oligometastatic"}


def one_burden(labels):
    """Keep a single specific burden. Anything else, including curative and screening, is Other."""
    specific = []
    for label in labels or []:
        mapped = _BURDEN_FOLD.get(label, label)
        if mapped in BURDEN_ORDER[:3] and mapped not in specific:
            specific.append(mapped)
    ordered = [label for label in BURDEN_ORDER if label in specific]
    if len(ordered) == 1:
        return [ordered[0]]
    return ["Other"]


def burden_labels(text):
    """One of four labels. Oligopersistent counts as oligometastatic."""
    original = text or ""
    enrolled = _enrolled_text(original)
    if _nontherapeutic(original):
        return ["Other"]
    oligop = re.search(_NOT_OLIGO + r"\boligoprogress", enrolled, re.I)
    oligopersist = re.search(_NOT_OLIGO + r"\boligopersist", enrolled, re.I)
    oligom = re.search(_NOT_OLIGO + r"\boligometa|" + _NOT_OLIGO + r"\boligorecurren", enrolled, re.I)
    cap = _oligo_cap(enrolled)
    sbrt = re.search(r"all sites amenable to (?:SBRT|SABR|metastasis-directed)", enrolled, re.I)
    poly = _POLY.search(enrolled)
    specific = []
    if oligop:
        specific.append("Oligoprogressive")
    if oligopersist or oligom or cap or sbrt:
        specific.append("Oligometastatic")
    if poly:
        specific.append("Polymetastatic")
    return one_burden(specific)


def _intent(burden):
    label = (burden or ["Other"])[0]
    if label == "Oligoprogressive":
        return "oligoprogressive"
    if label == "Oligometastatic":
        return "oligometastatic"
    if label == "Polymetastatic":
        return "polymetastatic"
    return "other"


def _clean_labels(labels):
    out = []
    for label in labels or []:
        text = str(label or "").strip()
        if not text or text in _NOISE_LABELS or text in out:
            continue
        out.append(text)
    return out


def classify_record(record):
    """Classify one trial. `reviewed` keys replace inferred anatomy, histology, burden, intent, and cancer types."""
    record = record or {}
    reviewed = record.get("reviewed") or {}
    use_disease = not reviewed.get("cancer_types")
    text = _population_text(record, include_disease=use_disease)
    special = _nontherapeutic(text)
    histology = _hits(HISTOLOGY, text)
    anatomy = _hits(ANATOMY, text)
    burden = burden_labels(text)
    if special:
        burden = ["Other"]
        if not histology:
            histology = []
    cancer_types = _clean_labels(histology or anatomy)
    if special and not reviewed.get("cancer_types"):
        cancer_types = [special]
    if not cancer_types:
        cancer_types = ["Not classified"]
    result = {
        "anatomy": anatomy,
        "histology": histology,
        "burden": burden,
        "intent": _intent(burden),
        "cancer_types": cancer_types,
        "taxonomy_version": TAXONOMY_VERSION,
    }
    if reviewed.get("anatomy"):
        result["anatomy"] = _clean_labels(reviewed["anatomy"])
    if reviewed.get("histology"):
        result["histology"] = _clean_labels(reviewed["histology"])
    if reviewed.get("cancer_types"):
        result["cancer_types"] = _clean_labels(reviewed["cancer_types"]) or ["Not classified"]
    if reviewed.get("burden"):
        result["burden"] = one_burden(reviewed["burden"])
        result["intent"] = _intent(result["burden"])
    if reviewed.get("intent"):
        result["intent"] = reviewed["intent"]
    return result
