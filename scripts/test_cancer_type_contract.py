#!/usr/bin/env python3
"""Parity of the shared cancer-type helper, plus Approved-study classification."""
import hashlib
import subprocess
from pathlib import Path

from trial_classification import classify_record

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
FILES = [
    ROOT / "dashboard" / "cancer-type-ui.js",
    WORKSPACE / "Worldwide RT Trials" / "dashboard" / "cancer-type-ui.js",
    WORKSPACE / "WVU Trials Demo" / "cancer-type-ui.js",
]
PAGES = [
    ROOT / "dashboard" / "template.html",
    WORKSPACE / "Worldwide RT Trials" / "dashboard" / "template.html",
    WORKSPACE / "WVU Trials Demo" / "Index.html",
]


def extract(text):
    start = text.find("/* BEGIN cancer-type-ui */")
    end = text.find("/* END cancer-type-ui */")
    if start < 0 or end < 0:
        raise SystemExit("missing cancer-type-ui markers")
    body = text[start + len("/* BEGIN cancer-type-ui */"):end].strip() + "\n"
    return body


def main():
    digest = {hashlib.sha256(path.read_bytes()).hexdigest() for path in FILES}
    if len(digest) != 1:
        raise SystemExit("cancer-type-ui.js copies differ")
    canonical = FILES[0].read_text().strip() + "\n"
    for page in PAGES:
        if extract(page.read_text()) != canonical:
            raise SystemExit("inlined helper differs in %s" % page.name)
    script = canonical + """
if (CancerType.normalize([" Prostate ", "", "prostate", "Variety", "Liver"]).join("|") !== "Prostate|Liver") {
  throw new Error("normalize");
}
if (CancerType.html(["Prostate"], "a").indexOf("button") >= 0) throw new Error("single label became a button");
var many = CancerType.html(["Prostate", "Liver", "Prostate"], "a");
if (many.indexOf("Multiple cancer types (2)") < 0) throw new Error("count");
if (many.indexOf("(1)") >= 0) throw new Error("count of one");
if (CancerType.menuKeys(["Prostate"]).indexOf("GU") < 0) throw new Error("prostate parent");
if (CancerType.menuKeys(["Liver"]).indexOf("GI") < 0) throw new Error("liver parent");
if (CancerType.menuKeys(["Breast"]).indexOf("GU") >= 0) throw new Error("breast mapped to GU");
"""
    subprocess.check_call(["node", "-e", script])
    approved = classify_record({
        "protocol": "APPROVED-PROSTATE",
        "title": "Stereotactic radiotherapy for prostate cancer",
        "disease": "Prostate Cancer",
    })
    if "Prostate" not in approved["cancer_types"]:
        raise SystemExit("approved prostate classification missing: %s" % approved["cancer_types"])
    print("cancer type contract ok")


if __name__ == "__main__":
    main()
