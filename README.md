# CTSU Trials Workspace (Rad Onc Review)

## Purpose

Track NCI trials on the CTSU Protocol List, flag the ones involving radiation therapy, follow accrual over time for the trials open at our institution, and keep current protocol documents on file locally.

Public dashboard: https://jryck3.github.io/Rad-Onc-Review/

## Status

Set up October 7, 2026. Accrual history starts that day. GitHub Actions takes one CTSU snapshot per day (11:17 UTC) and republishes the dashboard.

## How it works

| Piece | What it does |
|---|---|
| `scripts/refresh.py` | Pulls the public CTSU feed (`ctsu.cancer.gov/web-data-service/v1/protocols/browse`, the data behind ctsu.cancer.gov/protocol), appends `data/accrual_history.csv`, enriches each study from the ClinicalTrials.gov v2 API, classifies RT involvement, and builds the dashboards. |
| `.github/workflows/refresh.yml` | Runs `refresh.py` daily and commits the history and `docs/index.html` (served by GitHub Pages). |
| `scripts/download_protocols.py` | Downloads the current CIRB-approved protocol for every RT-related study from the CTSU member site through a signed-in browser session. Re-runs skip unchanged documents and keep older versions when a protocol is amended. |
| `scripts/update_local.sh` | Pulls the shared history and rebuilds the local dashboard (`dashboard/index.html`), which adds protocol-on-file status. `--protocols` also checks CTSU for amendments. |
| `config/institution_trials.json` | Trials open at our institution (shown as cards and charted by default). |
| `config/rt_overrides.json` | Manual RT classifications where ClinicalTrials.gov intervention data misleads. |

## RT classification

- **RT-focused**: RT named in the CTSU or ClinicalTrials.gov title.
- **RT component**: protocol-specified RT intervention on ClinicalTrials.gov, often part of the treatment backbone.
- **Radiopharmaceutical**: therapeutic isotope (Lu-177, Ac-225, Ra-223, and similar) without external-beam RT.
- Imaging tracers and MUGA scans are excluded. Each study's evidence is shown in the dashboard row details.

## Accrual and rates

CTSU publishes study-wide actual and planned intervention accrual (all sites, not our institution) and no past values. Average rate uses months since the ClinicalTrials.gov actual start date and understates the current rate for trials still ramping up. The 30- and 90-day rates come from the daily snapshots and appear once enough history exists.

## Protocol documents

Protocol PDFs live only in `protocols/` on Jeff's Mac (excluded from git, per the CTSU terms of use). `protocols/manifest.json` records version, CTSU document ID, and status for each study. ETCTN and PEP-CTN documents are restricted to member sites and are not available to this account.

To refresh protocols, sign in to CTSU (ID.me) in the automation Chrome window, then run `scripts/update_local.sh --protocols`. The CTSU session expires, so expect to sign in again for each protocol check.

## Editing the institution trial list

Edit `config/institution_trials.json` on GitHub (or locally, then commit and push). The next daily run, or a manual run from the Actions tab, updates the public dashboard.
