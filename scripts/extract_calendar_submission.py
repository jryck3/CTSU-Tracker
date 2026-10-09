#!/usr/bin/env python3
"""Add study calendar, specimen collection, and data-submission sections.

Reads local protocol PDFs and fills empty calendar, specimens, and submission
keys in data/protocol_briefs.json. Hand-checked entries below are applied
after the automatic pass. A section is left out when the PDF does not contain
a readable version of it.

Usage:
    python3 scripts/extract_calendar_submission.py [--only A032303 NRG-GU015]
"""
import argparse
import json
import re
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PROTOCOLS = ROOT / "protocols"
BRIEFS = ROOT / "data" / "protocol_briefs.json"

KEEP_SUB = re.compile(
    r"TRIAD is the image exchange|Transfer of Images and Data \(TRIAD\)|"
    r"due within \d+ days|Pre-treatment review is required|"
    r"prior to (?:the )?start of RT|PRIOR to start of RT|"
    r"within \d+ days of (?:the )?RT|IROC via TRIAD|"
    r"Radiotherapy plan review from IROC|plan review takes \d+ business days|"
    r"Data Submission Schedule|supporting documentation",
    re.I,
)
DROP_SUB = re.compile(
    r"triadinstall|TRIAD- ?Support@|CTEP-IAM|eLearning|Rave CRA must|"
    r"http://|https://|phone:|fax:|@|credential|questionnaire|Version Date",
    re.I,
)


def clean(text):
    text = text.replace("\u00ad", "").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sentences(text):
    text = clean(text)
    parts = re.split(r"(?<=[.;])\s+", text)
    out = []
    for part in parts:
        part = part.strip(" -")
        if 50 <= len(part) <= 420 and not DROP_SUB.search(part):
            out.append(part)
    return out


def label_for(sentence):
    low = sentence.lower()
    if "triad" in low or "iroc" in low:
        return "TRIAD"
    if "rave" in low or "data submission schedule" in low or "supporting documentation" in low:
        return "Rave"
    return "Data submission"


def submission_from(pages):
    blob = []
    uses_triad = False
    for index, text in enumerate(pages):
        if re.search(r"TRIAD", text, re.I):
            uses_triad = True
        if re.search(r"TRIAD|DATA AND SPECIMEN SUBMISSION|Summary of Data Submission|DISCIPLINE REVIEW|Radiotherapy Review", text, re.I):
            blob.append(text)
            if index + 1 < len(pages):
                blob.append(pages[index + 1])
    found = []
    seen = set()
    specific = re.compile(
        r"due within \d+ days|pre-treatment review|prior to (?:the )?(?:start|delivery)|"
        r"PRIOR to start of RT|business days|"
        r"submit(?:ted)? (?:to|via) (?:TRIAD|IROC)|"
        r"Data Submission Schedule is available|supporting documentation",
        re.I,
    )
    for sentence in sentences(" ".join(blob)):
        if not specific.search(sentence) or re.search(r"Summary of All Data Submission: Refer", sentence, re.I):
            continue
        key = sentence[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        label = "TRIAD" if uses_triad and re.search(r"pre-treatment review|prior to|IROC|due within", sentence, re.I) else label_for(sentence)
        found.append({"label": label, "text": sentence})
    if uses_triad and not found:
        found.append({
            "label": "TRIAD",
            "text": "This protocol names TRIAD for image or digital RT data submission. A separate day deadline was not readable as a clean sentence, so the DICOM list is left to the protocol.",
        })
    return found[:6]


def calendar_from(pages):
    start = None
    for index, text in enumerate(pages):
        if re.search(r"STUDY CALENDAR", text) and re.search(r"To be completed|Prior to\s+Randomization|Tests &", text):
            if "Table of Contents" in text[:500] and "To be completed" not in text:
                continue
            start = index
            break
    if start is None:
        return []
    chunk = "\n".join(pages[start:start + 2])
    blocks = []
    current = ""
    for raw in chunk.splitlines():
        line = clean(raw)
        if not line:
            continue
        if re.search(r"Version Date|^\d+\.\d+\s", line):
            if current:
                blocks.append(current)
                current = ""
            continue
        if re.match(r"To be completed|must be done within \d+ days", line, re.I):
            if current:
                blocks.append(current)
            current = line
        elif current:
            current = clean(current + " " + line)
            if len(current) > 220:
                blocks.append(current)
                current = ""
    if current:
        blocks.append(current)
    rows = []
    for window in blocks:
        if len(window) < 30:
            continue
        item = "Study calendar"
        match = re.search(r"(\d+)\s+days", window, re.I)
        if match:
            item = f"Within {match.group(1)} days"
        rows.append({"item": item, "window": window[:260], "note": ""})
    return rows[:8]


def specimens_from(pages):
    start = None
    for index, text in enumerate(pages):
        if re.search(r"Specimen Collection and Submission|BIOSPECIMEN COLLECTION", text, re.I) and "Table of Contents" not in text[:400]:
            start = index
            break
    if start is None:
        return []
    chunk = clean(" ".join(pages[start:start + 3]))
    rows = []
    seen = set()
    for match in re.finditer(
        r"((?:H&E|whole blood|urine|tumor tissue|plasma|serum|buffy|FFPE|tissue)[^.]{0,180}?(?:prior|before|week|month|registration|progression|baseline)[^.]{0,80})",
        chunk,
        re.I,
    ):
        line = clean(match.group(1))
        if not re.search(r"mL|H&E|FFPE|unstained", line, re.I):
            continue
        if len(line) < 40 or line.lower()[:40] in seen:
            continue
        seen.add(line.lower()[:40])
        rows.append({"item": line[:70], "window": line, "note": ""})
        if len(rows) >= 6:
            break
    return rows


def pdf_pages(protocol):
    folder = PROTOCOLS / protocol
    files = sorted(path for path in folder.glob("*.pdf") if "amendment" not in path.name.lower())
    if not files:
        return []
    reader = PdfReader(str(files[-1]))
    return [(page.extract_text() or "") for page in reader.pages]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    briefs = json.loads(BRIEFS.read_text())
    wanted = set(args.only) if args.only else None
    stats = {"calendar": 0, "specimens": 0, "submission": 0}
    for protocol, brief in list(briefs.items()):
        if wanted and protocol not in wanted:
            continue
        folder = PROTOCOLS / protocol
        if not folder.exists():
            continue
        try:
            pages = pdf_pages(protocol)
        except Exception as exc:
            print(f"{protocol}: {exc}")
            continue
        if not pages:
            continue
        locked = set(brief.get("locked") or [])
        extracted = {
            "calendar": calendar_from(pages),
            "specimens": specimens_from(pages),
            "submission": submission_from(pages),
        }
        for key, value in extracted.items():
            if key in locked or brief.get(key) or not value:
                continue
            brief[key] = value
            stats[key] += 1
        briefs[protocol] = brief
    apply_checked(briefs)
    if not wanted:
        BRIEFS.write_text(json.dumps(briefs, indent=1, ensure_ascii=False) + "\n")
    else:
        BRIEFS.write_text(json.dumps(briefs, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(stats))


def apply_checked(briefs):
    """Renditions read from the protocol pages, not from the automatic pass."""
    briefs["A032303"] = {
        "version_date": "2026-07-28",
        "version_label": "Protocol Version Date 07/28/26",
        "posted": briefs.get("A032303", {}).get("posted") or "01-Oct-2026",
        "amendments": [
            {
                "date": "July 28, 2026",
                "text": "Update 1, the version date on this file. The cover page does not summarize what changed.",
            }
        ],
        "schema": [
            {
                "label": "Entry",
                "text": "BCG-exposed non-muscle-invasive bladder cancer: recurrent high-grade Ta, T1, or Tis within 24 months of the last BCG dose, and not BCG-unresponsive.",
            },
            {
                "label": "Randomize",
                "text": "Patients must not start protocol treatment before randomization. Treatment should start within 28 business days after randomization.",
                "arms": [
                    {
                        "label": "Arm A",
                        "text": "Standard BCG induction: full-strength intravesical BCG once weekly for 6 weeks.",
                    },
                    {
                        "label": "Arm B",
                        "text": "Gemcitabine alternating with BCG. Gemcitabine 2000 mg twice weekly in weeks 1 and 10 and once weekly in weeks 4 and 7 (6 doses). Full-strength BCG once weekly in weeks 2, 3, 5, 6, 8, and 9 (6 doses).",
                    },
                ],
            },
            {
                "label": "Month 3, week 13",
                "text": "Treatment assessment with cystoscopic biopsies, with or without TURBT, and urine cytology.",
            },
            {
                "label": "Maintenance and follow-up",
                "text": "Maintenance at months 3, 6, and 12. Arm A is BCG once weekly for 3 weeks. Arm B is gemcitabine 2000 mg once in the first week, then BCG once weekly for 3 weeks. Cystoscopy and urine cytology every 3 months through month 24, then every 6 months through month 60. Follow-up continues for 5 years after randomization or until death.",
            },
        ],
        "eligibility": [
            "Histologic high-grade Ta, high-grade T1, or Tis/CIS urothelial carcinoma.",
            "BCG-exposed disease: recurrent high-grade NMIBC within 24 months of the last BCG exposure, and not BCG-unresponsive.",
            "Age 18 or older. Not pregnant and not nursing.",
            "No prior or current muscle-invasive or metastatic urothelial carcinoma.",
            "No history of intolerance to BCG or other intravesical treatment, and no contraindication to BCG.",
        ],
        "pretreatment": [
            {"item": "History and physical", "window": "Within 48 days before randomization", "note": ""},
            {"item": "TURBT or bladder biopsies, and urine cytology", "window": "Within 90 days before randomization", "note": "Visible papillary lesions must be macroscopically resected. Residual CIS is allowed. If a restaging TURBT shows no carcinoma, enrollment is still allowed when high-grade Ta, T1, or Tis was confirmed within 120 days."},
            {"item": "CT or MRI of the abdomen and pelvis", "window": "Within 120 days before randomization", "note": "Required at baseline. Later imaging is for symptoms that suggest metastases."},
            {"item": "Serum or urine pregnancy test", "window": "Within 14 days before registration", "note": "Persons of childbearing potential."},
        ],
        "during": [
            {"item": "Adverse event assessment", "window": "During induction and during maintenance", "note": "Only grade 3 or higher events are recorded in Rave."},
            {"item": "Cystoscopy, urine cytology, and biopsy", "window": "Week 13, plus or minus 2 weeks, after induction starts", "note": "Mandatory even if there was no CIS and the disease was papillary only. If no suspicious area is seen, at least 4 quadrant biopsies and biopsies of prior CIS sites are required. Papillary tumors are resected."},
        ],
        "followup": [
            {"item": "Cystoscopy and urine cytology", "window": "Month 6 (week 25, plus or minus 3 weeks), then every 3 months through 2 years, then every 6 months through 5 years", "note": "The later visits are at months 30, 36, 42, 48, 54, and 60, each plus or minus 3 weeks."},
            {"item": "Biopsy", "window": "When a papillary lesion is seen, and for high-grade cytology without a visible lesion after month 6", "note": "That for-cause biopsy includes at least 4 quadrants, prostatic urethra in men, and bilateral upper-tract washings."},
            {"item": "CT or MRI of the abdomen and pelvis", "window": "If signs or symptoms suggest metastases", "note": ""},
        ],
        "calendar": [
            {"item": "History and physical", "window": "Before randomization", "note": "Within 48 days."},
            {"item": "Adverse event assessment", "window": "Induction and maintenance", "note": "Grade 3 or higher is recorded in Rave."},
            {"item": "Bladder biopsy or TURBT", "window": "Before randomization, and at the week-13 assessment", "note": "Later biopsies are as needed."},
            {"item": "Urine cytology", "window": "Before randomization, week 13, maintenance, and follow-up", "note": ""},
            {"item": "Cystoscopy", "window": "Week 13, maintenance, and follow-up", "note": ""},
            {"item": "Pregnancy test", "window": "Before randomization", "note": "Within 14 days before registration."},
            {"item": "CT or MRI abdomen/pelvis", "window": "Before randomization", "note": "Later only if metastases are suspected."},
            {"item": "Tissue, urine, and blood", "window": "See specimen collection", "note": "For patients who consent to biobanking, plus the required H&E for central review."},
        ],
        "specimens": [
            {"item": "H&E slide for central pathology review", "window": "After registration and before treatment; week 13; at progression", "note": "Required for every registered patient. Enrollment and treatment may proceed on local pathology. Central review is retrospective. Week-13 and progression tissue is from a standard-of-care biopsy."},
            {"item": "Whole blood in EDTA for PBMC", "window": "Before treatment, week 13, week 25, and at progression", "note": "Optional biobanking. 2 tubes of 10 mL at each of those times."},
            {"item": "Urine", "window": "Before treatment, week 13, week 25, months 12 and 18, and at progression", "note": "Optional. 50 mL at each time."},
            {"item": "Tumor tissue", "window": "Before treatment, week 13, and at progression", "note": "Optional. From a standard-of-care biopsy."},
            {"item": "Plasma and buffy coat", "window": "Before treatment, week 13, and at progression", "note": "Optional. Buffy coat is required at only one time. Before treatment is preferred. 2 tubes of 10 mL."},
        ],
        "submission": [
            {"label": "Rave", "text": "Medidata Rave is the clinical database. The data submission schedule is on the CTSU study page. This is an IND-exempt trial and it does not use TRIAD."},
            {"label": "Source documents", "text": "Baseline: pathology, cytology, cystoscopy report, imaging report, BCG dates and dose, and the TURBT operative note. During treatment: cystoscopy, cytology, operative note, and imaging. At recurrence or progression: pathology, cytology, cystoscopy, operative note, and imaging."},
        ],
        "locked": ["schema", "eligibility", "pretreatment", "during", "followup", "calendar", "specimens", "submission", "amendments"],
    }

    gu = briefs.setdefault("NRG-GU015", {})
    gu["specimens"] = [
        {"item": "Mandatory specimens", "window": "Not applicable", "note": "Section 10.1.1. Collection below is optional and requires consent. Non-US sites are not required to take part."},
        {"item": "Signatera: H&E and unstained slides from the primary tumor", "window": "Before chemotherapy", "note": "Ship the FFPE to Natera within 30 days of registration. Do not ship these slides to the NRG bank."},
        {"item": "Signatera: whole blood in one EDTA tube", "window": "Before chemotherapy", "note": "4 to 6 mL. Ship to Natera within 5 days of collection."},
        {"item": "Signatera: whole blood for plasma in two Streck tubes", "window": "Before chemotherapy; 4 weeks (±14 days); 16, 28, and 40 weeks (±14 days); 56 weeks (±30 days); and at progression", "note": "8 to 10 mL in each tube. If a baseline Signatera profile is not created, no further study-1 samples are required. A prior commercial Signatera whole-genome profile can be used instead."},
        {"item": "Bank: H&E and FFPE block, or a 5 mm core", "window": "Before chemotherapy. Cystoscopy tissue at 16 weeks (+14 days) if applicable, and at recurrence", "note": "Ship to the NRG Oncology Biospecimen Bank San Francisco within 30 days of registration. If Signatera slides went to Natera, the bank still needs the FFPE block and matching H&E. Unstained slides are not accepted for banking."},
        {"item": "Bank: whole blood for DNA", "window": "Before chemotherapy", "note": "5 to 10 mL in EDTA, frozen. If that draw is missed, a later visit may be used and coded WB02."},
        {"item": "Bank: serum", "window": "Before chemotherapy, 16 weeks (±14 days), and 56 weeks (±30 days)", "note": "5 to 10 mL, frozen, to the NRG bank."},
        {"item": "Bank: plasma in two Streck tubes", "window": "Before chemotherapy; 16, 28, 40, and 56 weeks; and at progression or the last follow-up", "note": ""},
        {"item": "Bank: urine", "window": "Before chemotherapy", "note": "10 to 25 mL midstream."},
    ]
    gu["submission"] = [
        {"label": "Rave", "text": "Routine adverse events are reported in Medidata Rave. PRO-CTCAE is not used for expedited reporting, real-time safety review, or stopping rules. Section 14.2 is dated August 6, 2026."},
        {"label": "TRIAD", "text": "TRIAD is the NRG image exchange. It anonymizes and validates DICOM and other objects as they transfer."},
        {"label": "Arm 1, non-adaptive", "text": "Submit the DICOM CT, planning MR when used, RT structure, RT dose for all initial plans, and RT plan for all initial plans. The first Arm 1 case from each site needs pre-treatment review before RT starts, unless that case uses adaptive planning, in which case the adaptive tables apply. After the site completes the required pre-treatment reviews, later Arm 1 submissions are due within 7 days of RT start."},
        {"label": "Plan library", "text": "Required for Arm 2 and optional for Arm 1. The first Arm 2 plan-library case from each site needs pre-treatment review before RT, and a second pre-treatment review of delivered adapted fraction 1 before fraction 2. After those reviews, later cases are due within 7 days of the RT end date. The initial submission is the planning CT (three sets if differential bladder filling is used), planning MR when used, RT structures, three RT plans, and three RT doses. The delivered-fraction submission adds the selected plan and dose, daily volumetric images with alignment, a post-adaptation pre-delivery image, and a post-delivery image."},
        {"label": "Online adaptive", "text": "Required for Arm 2. The first Arm 2 online-adaptive case from each site needs pre-treatment review before RT, and a second review of delivered adapted fraction 1 before fraction 2. After the site completes the required pre-treatment reviews, adaptive data for later Arm 2 cases are due within 14 days of the RT end date."},
    ]
    locked = set(gu.get("locked") or [])
    locked.update(["specimens", "submission"])
    gu["locked"] = sorted(locked)

    s2427 = briefs.setdefault("S2427", {})
    s2427["submission"] = [
        {"label": "TRIAD", "text": "Digital RT data go to IROC through TRIAD. The submission is DICOM RT and must include the planning CT, structures, plan, and dose. sFTP to IROC Rhode Island is allowed when needed."},
        {"label": "Pre-treatment review", "text": "Required for the first case of each modality, 3DCRT or IMRT, from each institution. IROC review must be received before RT starts for that first case. The review takes 3 business days."},
        {"label": "After radiotherapy", "text": "Within 7 days after RT, the first case of each modality submits the RT treatment summary through TRIAD. Every later case submits the digital plan for the whole course and the RT treatment summary through TRIAD."},
        {"label": "Rave", "text": "Within 30 days after each pembrolizumab cycle: vital status, treatment, and adverse event forms. Within 30 days after RT: vital status and the RT treatment summary. Within 30 days after each disease assessment while on protocol treatment: vital status, disease assessment, and the radiographic form if CT or MRI shows metastatic disease. Cytology reports are uploaded in Rave."},
    ]
    locked = set(s2427.get("locked") or [])
    locked.add("submission")
    s2427["locked"] = sorted(locked)


if __name__ == "__main__":
    main()
