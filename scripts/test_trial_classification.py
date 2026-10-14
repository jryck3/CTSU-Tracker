#!/usr/bin/env python3
"""Gold fixtures for the shared trial classifier."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trial_classification as clf


CASES = [
    {
        "id": "NRG-BR009",
        "record": {
            "protocol": "NRG-BR009",
            "title": "A Phase III Adjuvant Trial Evaluating the Addition of Adjuvant Chemotherapy to Ovarian Function Suppression Plus Endocrine Therapy in Premenopausal Patients with ER-Positive Breast Cancer",
            "disease": "Breast Cancer",
            "eligibility": ["Premenopausal patients with resected breast cancer."],
        },
        "cancer_types": ["Breast"],
        "forbid_types": ["Ovary", "Gyn", "Gynecologic"],
        "burden": ["Other"],
    },
    {
        "id": "MYELOMATCH",
        "record": {
            "protocol": "MYELOMATCH",
            "title": "MYELOMATCH, Master Screening and Reassessment Protocol for the NCI MyeloMATCH Clinical Trials",
            "disease": "Leukemia",
            "eligibility": ["Participants must be suspected to have previously untreated acute myeloid leukemia (AML) or myelodysplastic syndrome (MDS)."],
        },
        "forbid_types": ["Myeloma"],
        "require_any_type": ["AML", "Leukemia", "Heme"],
    },
    {
        "id": "pancreas-net",
        "record": {
            "protocol": "NET-1",
            "title": "A trial of therapy for metastatic pancreatic neuroendocrine tumor",
            "disease": "Pancreatic neuroendocrine tumor",
        },
        "require_types": ["Pancreas", "NET"],
        "forbid_types": ["Endocrine"],
    },
    {
        "id": "NRG-GU013",
        "record": {
            "protocol": "NRG-GU013",
            "title": "The Phase III High Five Trial Five Fraction Radiation For High-Risk Prostate Cancer",
            "disease": "Male Reproductive System Cancer",
            "eligibility": [
                "High-risk prostate adenocarcinoma, or a pelvic node of at least 1.0 cm.",
                "No M1 disease on conventional imaging.",
                "Primary endpoint is metastasis-free survival.",
            ],
        },
        "burden": ["Other"],
        "forbid_burden": ["Metastatic, burden not specified"],
    },
    {
        "id": "NRG-LU008",
        "record": {
            "protocol": "NRG-LU008",
            "title": "Primary Lung Tumor Stereotactic Body Radiation Therapy Followed by Concurrent Mediastinal Chemoradiation for Locally Advanced Non-Small Cell Lung Cancer",
            "eligibility": [
                "A primary tumor and at least one nodal metastasis are required.",
                "No distant metastases on FDG PET/CT.",
            ],
        },
        "burden": ["Other"],
        "require_any_type": ["NSCLC", "Lung"],
    },
    {
        "id": "NRG-HN006",
        "record": {
            "protocol": "NRG-HN006",
            "title": "Sentinel Lymph Node Biopsy Versus Elective Neck Dissection for Early-Stage Oral Cavity Cancer",
            "eligibility": [
                "Stage T1-2N0M0 oral cavity cancer.",
                "No clinical evidence of cervical nodal or distant metastases.",
            ],
        },
        "burden": ["Other"],
        "require_any_type": ["Oral cavity", "Head and neck", "H&N"],
    },
    {
        "id": "NRG-GY037",
        "record": {
            "protocol": "NRG-GY037",
            "title": "Induction Pembrolizumab and Chemotherapy Followed by Chemoradiation for High Risk Locally Advanced Cervical Cancer",
            "eligibility": [
                "Locally advanced disease: FIGO IIIC1 or IVA.",
                "No para-aortic node metastasis above the T12/L1 interspace.",
            ],
        },
        "burden": ["Other"],
        "require_any_type": ["Cervix", "Gyn"],
    },
    {
        "id": "A022101",
        "record": {
            "protocol": "A022101",
            "title": "Total Ablative Therapy for Patients with Limited Metastatic Colorectal Cancer (ERASur)",
            "eligibility": [
                "Patients with four or fewer metastatic sites.",
                "Standard-of-care systemic therapy in newly diagnosed oligometastatic colorectal cancer.",
            ],
        },
        "burden": ["Oligometastatic"],
        "forbid_burden": ["Mixed", "Metastatic, burden not specified"],
    },
    {
        "id": "S2511",
        "record": {
            "protocol": "S2511",
            "title": "Multimodality Therapy in HER2 Positive De Novo (AJCC Stage IV) Oligometastatic Breast Cancer",
            "eligibility": [
                "De novo metastatic HER2-positive breast cancer with 1 to 5 distant lesions.",
                "The protocol describes treatment cohorts.",
            ],
        },
        "burden": ["Oligometastatic"],
        "forbid_burden": ["Mixed", "Other"],
    },
    {
        "id": "oligopersistent",
        "record": {
            "protocol": "OLIGO-P",
            "title": "A trial for oligopersistent lung cancer",
        },
        "burden": ["Oligometastatic"],
    },
    {
        "id": "both-specific",
        "record": {
            "protocol": "BOTH",
            "title": "Oligometastatic or polymetastatic breast cancer",
        },
        "burden": ["Other"],
    },
    {
        "id": "polymetastatic",
        "record": {
            "protocol": "POLY",
            "title": "Widespread metastatic prostate cancer with more than ten metastases",
        },
        "burden": ["Polymetastatic"],
    },
    {
        "id": "WVU010924",
        "record": {
            "protocol": "WVU010924",
            "title": "Calaspargase Pegol-mknl with High Dose Cytarabine and Idarubicin in Adult Patients with Newly Diagnosed Acute Myeloid Leukemia",
            "disease": ["Multiple Myeloma"],
            "reviewed": {"cancer_types": ["AML"]},
        },
        "cancer_types": ["AML"],
        "forbid_types": ["Myeloma"],
    },
    {
        "id": "WVU011625",
        "record": {
            "protocol": "WVU011625",
            "title": "Scheduled intravenous fluids during chemo-radiotherapy for head and neck cancers",
            "disease": ["Brain Cancer", "Other Cancers"],
            "reviewed": {"cancer_types": ["Head and Neck Cancer"]},
        },
        "cancer_types": ["Head and Neck Cancer"],
        "forbid_types": ["CNS", "Brain"],
    },
    {
        "id": "A151804",
        "record": {
            "protocol": "A151804",
            "title": "Establishment of a National Biorepository to Advance Studies of Immune-Related Adverse Events",
            "disease": ["Miscellaneous and Metastatic Cancer"],
        },
        "cancer_types": ["Biorepository"],
        "burden": ["Other"],
        "forbid_burden": ["Metastatic, burden not specified"],
    },
    {
        "id": "COG-APEC14B1",
        "record": {
            "protocol": "COG-APEC14B1",
            "title": "EveryChild, a registry, eligibility screening, biology and outcome study",
            "disease": ["Miscellaneous and Metastatic Cancer"],
        },
        "cancer_types": ["Registry"],
        "burden": ["Other"],
    },
    {
        "id": "A211901",
        "record": {
            "protocol": "A211901",
            "title": "Reaching Rural Cancer Survivors Who Smoke Using Text-Based Cessation Interventions",
            "disease": ["Brain Cancer", "Breast Cancer", "Miscellaneous and Metastatic Cancer"],
        },
        "cancer_types": ["Smoking cessation"],
        "burden": ["Other"],
        "forbid_burden": ["Metastatic, burden not specified", "Curative / definitive"],
    },
    {
        "id": "GRAIL-MA-002",
        "record": {
            "protocol": "GRAIL-MA-002",
            "title": "Real-world Evidence to Advance Multi-Cancer Early Detection Health Equity",
            "disease": ["Miscellaneous and Metastatic Cancer"],
        },
        "cancer_types": ["Early detection"],
        "burden": ["Other"],
        "forbid_burden": ["Curative / definitive", "Metastatic, burden not specified"],
    },
]


def check(case):
    got = clf.classify_record(case["record"])
    errors = []
    if "cancer_types" in case and got["cancer_types"] != case["cancer_types"]:
        errors.append(f"cancer_types {got['cancer_types']} != {case['cancer_types']}")
    for label in case.get("require_types") or []:
        if label not in got["cancer_types"]:
            errors.append(f"missing cancer type {label} in {got['cancer_types']}")
    if case.get("require_any_type") and not any(label in got["cancer_types"] for label in case["require_any_type"]):
        errors.append(f"none of {case['require_any_type']} in {got['cancer_types']}")
    for label in case.get("forbid_types") or []:
        if label in got["cancer_types"] or label in got["anatomy"] or label in got["histology"]:
            errors.append(f"forbidden type {label} in {got}")
    if "burden" in case and got["burden"] != case["burden"]:
        errors.append(f"burden {got['burden']} != {case['burden']}")
    for label in case.get("forbid_burden") or []:
        if label in got["burden"]:
            errors.append(f"forbidden burden {label}")
    return errors


def main():
    failed = 0
    for case in CASES:
        errors = check(case)
        if errors:
            failed += 1
            print(case["id"] + ":")
            for error in errors:
                print("  " + error)
    if failed:
        print(f"{failed} gold cases failed")
        return 1
    print(f"{len(CASES)} gold cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
