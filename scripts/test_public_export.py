#!/usr/bin/env python3
"""Privacy, identity, and projection gates for the public CTSU export."""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import public_export as exp


def payload():
    return {
        "generated_at": "2026-10-14T03:36:20+00:00",
        "snapshot_fetched_at": "2026-10-14T03:36:18+00:00",
        "protocol_library_as_of": "2026-10-12",
        "history_start": "2026-10-07",
        "history": {"CCTG CE.7": [["2026-10-13", 10, 100, "Active"]]},
        "studies": [
            {
                "protocol": "CCTG CE.7",
                "nct": "NCT03550391",
                "status": "Active",
                "ctgov_status": "RECRUITING",
                "accrual": 12,
                "target": 100,
                "accrual_type": "INTERVENTION",
                "phase": "3",
                "lead": "CCTG",
                "rt_role": "RT-focused",
                "title": "A public title",
                "disease": "Brain Cancer",
                "anatomy": ["CNS"],
                "histology": [],
                "burden": ["Curative / definitive"],
                "intent": "curative",
                "cancer_types": ["CNS"],
                "avg_rate": 1.2,
                "projected_completion": "2028-01-01",
                "ours": True,
                "brief": {
                    "eligibility": ["Adults."],
                    "notes": "local path /Users/jeffryckman/secret.pdf",
                    "locked": True,
                },
            },
            {
                "protocol": "NCI-1",
                "nct": "NCT00000001",
                "status": "Approved",
                "listed_on": "clinicaltrials.gov",
                "ctgov_status": "NOT_YET_RECRUITING",
                "accrual": None,
                "target": 40,
                "phase": "",
                "title": "Not yet recruiting",
                "cancer_types": ["Not classified"],
            },
        ],
    }


def main():
    export, manifest = exp.build_public_export(payload(), "abc123", "2026-10-12")
    by_id = {study["id"]: study for study in export["studies"]}
    assert "CCTG CE.7" in by_id["CCTG CE.7"]["aliases"]
    assert "CE.7" in by_id["CCTG CE.7"]["aliases"]
    assert by_id["CCTG CE.7"]["nct"] == "NCT03550391"
    assert "notes" not in (by_id["CCTG CE.7"]["brief"] or {})
    assert "ours" not in by_id["CCTG CE.7"]
    assert by_id["NCI-1"]["status_basis"].startswith("ClinicalTrials.gov Not yet recruiting")
    assert by_id["NCI-1"]["phase_normalized"] == "Not stated"
    assert "institution" not in export
    later = payload()
    later["generated_at"] = "2026-10-14T09:00:00+00:00"
    later["snapshot_fetched_at"] = "2026-10-14T09:00:00+00:00"
    later["studies"][0]["projected_completion"] = "2028-02-01"
    export2, manifest2 = exp.build_public_export(later, "abc123", "2026-10-12")
    assert manifest["content_hash"] == manifest2["content_hash"]
    later["studies"][0]["accrual"] = 13
    export3, manifest3 = exp.build_public_export(later, "abc123", "2026-10-12")
    assert manifest3["content_hash"] != manifest["content_hash"]
    today = date(2026, 10, 14)
    assert exp.gate_projected_date(today, 3.7, 1, 408, 0.27) is None
    assert exp.gate_projected_date(today, 24, 80, 200, 4) is not None
    raw = json.dumps(export)
    assert "/Users/" not in raw
    assert "ACCESS_CODE" not in raw
    try:
        bad = payload()
        bad["studies"][0]["title"] = "see /Users/jeffryckman/protocols/secret.pdf"
        exp.build_public_export(bad, "abc", "2026-10-12")
    except exp.ExportPrivacyError:
        pass
    else:
        raise SystemExit("private path was exported")
    print("public export ok", manifest["record_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
