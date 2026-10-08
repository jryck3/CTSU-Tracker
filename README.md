# CTSU Trials Workspace (Rad Onc Review)

## Purpose

Track NCI trials on the CTSU Protocol List, flag the ones involving radiation therapy, follow accrual over time for trials each user cares about (for example, the trials open at their institution), and keep current protocol documents on file locally.

Public dashboard: https://jryck3.github.io/Rad-Onc-Review/

## Status

Set up October 7, 2026. Accrual history starts that day. GitHub Actions takes one CTSU snapshot per day (11:17 UTC) and republishes the dashboard.

## Dashboard

- **My trials** starts empty. Users add trials one at a time from a search box (protocol number, NCT number, acronym, or title words) or with the star next to any study. The list drives the trial cards and the accrual charts.
- The list is saved in the browser. **Copy share link** produces a URL with the protocol numbers (`?trials=NRG-GU013,S2427`); opening it offers to save that list.
- **Sign in with Google** (optional) saves the list to Firestore so it follows the user across devices. The button appears only after the Firebase setup below.
- **Explore CTSU studies** defaults to RT-related and open studies. The accrual pace panel lists the fastest and slowest accruing open studies that match the current filters (open at least 6 months, below target), by patients per month or % of target per month.

## How it works

| Piece | What it does |
|---|---|
| `scripts/refresh.py` | Pulls the public CTSU feed (`ctsu.cancer.gov/web-data-service/v1/protocols/browse`, the data behind ctsu.cancer.gov/protocol), appends `data/accrual_history.csv`, enriches each study from the ClinicalTrials.gov v2 API, classifies RT involvement, and builds the dashboards. |
| `.github/workflows/refresh.yml` | Runs `refresh.py` daily and commits the history and `docs/index.html` (served by GitHub Pages). Passes the `FIREBASE_WEB_CONFIG` repository variable to the build. |
| `dashboard/template.html` | Dashboard page (vanilla JS, Chart.js, optional Firebase Auth and Firestore from Google's CDN). |
| `firestore.rules` | Firestore security rules: each signed-in user can read and write only `users/{their uid}`. |
| `scripts/download_protocols.py` | Downloads the current CIRB-approved protocol for every RT-related study and every trial in `config/institution_trials.json` from the CTSU member site through a signed-in browser session. Re-runs skip unchanged documents and keep older versions when a protocol is amended. |
| `scripts/update_local.sh` | Pulls the shared history and rebuilds the local dashboard (`dashboard/index.html`), which adds protocol-on-file status. `--protocols` also checks CTSU for amendments. |
| `config/institution_trials.json` | Trials open at our institution. Seeds My trials in the local dashboard and is always included in protocol downloads. Not shown on the public dashboard. |
| `config/rt_overrides.json` | Manual RT classifications where ClinicalTrials.gov intervention data misleads. |

## RT classification

- **RT-focused**: RT named in the CTSU or ClinicalTrials.gov title.
- **RT component**: protocol-specified RT intervention on ClinicalTrials.gov, often part of the treatment backbone.
- **Radiopharmaceutical**: therapeutic isotope (Lu-177, Ac-225, Ra-223, and similar) without external-beam RT.
- Imaging tracers and MUGA scans are excluded. Each study's evidence is shown in the dashboard row details.

## Accrual and rates

CTSU publishes study-wide actual and planned intervention accrual (all sites, not any one institution) and no past values. Average rate uses months since the ClinicalTrials.gov actual start date and understates the current rate for trials still ramping up. The 30- and 90-day rates come from the daily snapshots and appear once enough history exists.

## Protocol documents

Protocol PDFs live only in `protocols/` on Jeff's Mac (excluded from git, per the CTSU terms of use). `protocols/manifest.json` records version, CTSU document ID, and status for each study. ETCTN and PEP-CTN documents are restricted to member sites and are not available to this account.

To refresh protocols, sign in to CTSU (ID.me) in the automation Chrome window, then run `scripts/update_local.sh --protocols`. The CTSU session expires, so expect to sign in again for each protocol check.

## Google sign-in setup (one time)

1. In the [Firebase console](https://console.firebase.google.com/), create a project (Google Analytics not needed) and add a **Web app**. Copy its config object.
2. **Authentication** > Get started > Sign-in method > enable **Google**. Under Settings > Authorized domains, add `jryck3.github.io`.
3. **Firestore Database** > Create database (production mode). Replace the rules with the contents of `firestore.rules` and publish.
4. Save the web config as a repository variable (not a secret; the values are public identifiers that end up in the page):
   `gh variable set FIREBASE_WEB_CONFIG --repo jryck3/Rad-Onc-Review --body '{"apiKey":"...","authDomain":"...","projectId":"...","appId":"..."}'`
5. Run the workflow from the Actions tab (or wait for the daily run). The Sign in with Google button then appears.

Optional hardening: in Google Cloud console > APIs & Services > Credentials, restrict the browser API key to the `https://jryck3.github.io/*` and `https://<project-id>.firebaseapp.com/*` referrers (the second hosts the sign-in popup).

The local dashboard opens from a `file://` path, where Google sign-in cannot run, so it keeps its list in the browser only.
