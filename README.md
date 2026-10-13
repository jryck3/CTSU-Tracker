# CTSU Trials Workspace (Rad Onc Review)

## Purpose

Track NCI trials on the CTSU Protocol List, flag the ones involving radiation therapy, follow accrual over time for trials each user cares about (for example, the trials open at their institution), and keep current protocol documents on file locally.

Public dashboard: https://jryck3.github.io/CTSU-Tracker/ (repo renamed from Rad-Onc-Review on October 7, 2026; the old Pages URL does not redirect)

## Status

Set up October 7, 2026. Accrual history starts that day. GitHub Actions takes one CTSU snapshot per day (11:17 UTC) and republishes the dashboard. That run is how a new protocol enters the tracker: it reads the whole public browse feed, and it also adds not-yet-recruiting interventional trials from NRG, SWOG, ECOG-ACRIN, Alliance, COG, CCTG, NCI, RTOG, and NSABP that are missing from the feed, with status Approved. The 13 October 2026 run finished in a few seconds (288 registry records refreshed, 32 approved studies). The 10-minute job limit stays.

## Dashboard

- **My trials** starts empty. Users add trials one at a time from a search box (protocol number, NCT number, acronym, or title words) or with the star next to any study. The list drives the trial cards and the accrual charts.
- The list is saved in the browser. **Copy share link** produces a URL with the protocol numbers (`?trials=NRG-GU013,S2427`); opening it offers to save that list.
- **Sign in with Google** (optional) saves the list to Firestore so it follows the user across devices. The button appears only after the Firebase setup below.
- **Explore CTSU studies** defaults to open studies in the three radiotherapy roles: RT-focused, RT component, and Radiopharm. The role menu is checkboxes. Imaging, Surgery, Transplant / cellular therapy, Cancer control, Registry / biospecimen, and Systemic therapy start unchecked. Phase is a checkbox menu that stays closed until opened. Phase 0 and Phase 1 start unchecked. Seamless 1/2 and Seamless 2/3 are the single-protocol phase codes. The status menu also selects Approved, not yet open (ClinicalTrials.gov Not yet recruiting, no CTSU accrual), temporarily closed studies, or every status on the list. Open means CTSU Active. The usual ClinicalTrials.gov pair is Recruiting, and the usual pair for either temporarily closed status is Suspended. An opened study shows the registry status, and the status cell names it when the pair differs. Trials that are closed to accrual, complete, or administratively complete are not on this list. The accrual pace panel lists the fastest accruing open studies that match the current filters (open at least 6 months, below target), by patients per month or % of target per month. The study table is alphabetical by protocol. The protocol cell lists the lead group, RT role, and status on separate lines. The accrual cell shows patients per month under the bar. Site wraps in a narrow column so the title is the widest column. Column headings sort by protocol, disease site, phase, or accrual. Seamless 1/2 and Seamless 2/3 stay those names in the phase menu and show as 1/2 and 2/3 in the table. The site menu uses the same oncology rollup as the WVU tracker: leukemia, lymphoma, myeloma, myelofibrosis, and other hematopoietic neoplasms are Hematologic Cancer; kidney, urothelial, and germ cell cancers are Genitourinary Cancers; prostate stays under Male Reproductive System Cancer and Genitourinary Cancers. Bone, endocrine, and soft tissue stay their own sites. The opened study still shows the CTSU disease string. LAO lead groups are one LAO choice in the lead filter, and the protocol cell still shows the specific LAO code. The filters narrow the same list. Opening a study shows a protocol brief when one is on file: version date, CTSU update date, amendments, schema, eligibility, pre-treatment assessments, assessments during treatment, assessments in follow-up, the study calendar, specimen collection, and data submission, including TRIAD when the protocol requires it. A section is omitted when that protocol does not contain it. When no protocol brief is on file, the opened study says so. Briefs are renditions, not copies of the protocol.

## How it works

| Piece | What it does |
|---|---|
| `scripts/refresh.py` | Pulls the public CTSU feed (`ctsu.cancer.gov/web-data-service/v1/protocols/browse`, the data behind ctsu.cancer.gov/protocol), appends `data/accrual_history.csv`, enriches each study from the ClinicalTrials.gov v2 API, classifies RT involvement, and builds the dashboards. |
| `.github/workflows/refresh.yml` | Runs `refresh.py` daily and commits the history and `docs/index.html` (served by GitHub Pages). A push that changes the briefs, `data/protocol_library.json`, or the template rebuilds the page only (`--page-only`). Passes the `FIREBASE_WEB_CONFIG` repository variable to the build. |
| `scripts/protocol_library.py` | The one reader of `protocols/` and `data/protocol_briefs.json`: current PDF per protocol, protocol-number matching across group spellings, and the library stamp (latest check date plus a content hash). WVU and Worldwide import it. |
| `scripts/extract_protocol_briefs.py` | Fills brief sections from the current PDF. Never overwrites a hand-written or locked section. When a protocol version changes, it marks those sections `needs_review`. |
| `scripts/rebuild_consumers.sh` | Republishes all three trackers from the library after `publish_checks.py` passes for each: CTSU (commit and push), Worldwide (`build.py --briefs-only`, push to Pages), WVU (`enrich_details.py`, push, `clasp push`, redeploy the same web-app deployment). `--if-stale` skips trackers already built from the current library. Log: `logs/publish.<host>.log`. |
| `scripts/audit_briefs.py`, `scripts/merge_brief_reviews.py`, `scripts/protocol_text.py` | Brief quality audit and RT check against the PDFs, merge of hand-reviewed briefs (marked `reviewed` and locked), and a text viewer for one protocol. |
| `dashboard/template.html` | Dashboard page (vanilla JS, Chart.js, optional Firebase Auth and Firestore from Google's CDN). |
| `firestore.rules` | Firestore security rules: each signed-in user can read and write only `users/{their uid}`. |
| `scripts/download_protocols.py` | Downloads the current CIRB-approved protocol for every study on the CTSU list from the member site through a signed-in browser session. Re-runs skip unchanged documents and keep older versions when a protocol is amended. `--open-only` limits the check to active RT studies. |
| `scripts/update_local.sh` | Pulls the shared history and rebuilds the local dashboard (`dashboard/index.html`), which adds protocol-on-file status. `--protocols` also checks CTSU for amendments. |
| `config/institution_trials.json` | Trials open at our institution. Seeds My trials in the local dashboard and is always included in protocol downloads. Not shown on the public dashboard. |
| `config/rt_overrides.json` | Manual RT classifications where ClinicalTrials.gov intervention data misleads. |

## RT classification

- **RT-focused**: RT named in the CTSU or ClinicalTrials.gov title (radiation, radiotherapy, SBRT, protons, brachytherapy, and similar). This is a title rule, not a claim that RT is the randomized question.
- **RT component**: a RADIATION intervention or RT-named intervention on ClinicalTrials.gov, with no RT term in the title. Also studies whose protocol prescribes RT (dose, volumes, credentialing) although the registry does not list it; those are set in `config/rt_overrides.json` with the protocol section as the reason.
- **Radiopharm**: therapeutic isotope (Lu-177, Ac-225, Ra-223, I-131, Y-90, SIRT, Zevalin, and similar) and no external-beam or brachytherapy intervention. A mixed Lu-177 plus EBRT trial stays RT-focused or RT component. Imaging tracers (Ga-68, F-18, FDG) are excluded.
- Imaging tracers and MUGA scans are excluded. Each study's evidence is shown in the dashboard row details.

## Accrual and rates

CTSU publishes study-wide actual and planned intervention accrual (all sites, not any one institution) and no past values. Average rate uses months since the ClinicalTrials.gov actual start date and understates the current rate for trials still ramping up. The 30- and 90-day rates come from the daily snapshots and appear once enough history exists.

## Protocol documents

`protocols/` on Jeff's Mac is the only CTSU protocol library. The PDFs are excluded from git, per the CTSU terms of use. Do not copy them into another project. `protocols/manifest.json` records version, CTSU document ID, and status for each study. A changed protocol is a new CIRB document id, or a new amendment memorandum id, on the signed-in Documents page. The PDF is saved only when that id changes. `checked_at` is the day that page was opened, not the day the protocol was amended. ETCTN and PEP-CTN documents are restricted to member sites and are not available to this account.

Downloaders use `scripts/download_protocols.py` after an ID.me session on the CTSU automation Chrome. They do not download while logged out, and they do not type the password.

- This project: `scripts/check_protocol_updates.sh` (the scheduled Sunday check) and `scripts/update_local.sh --protocols`.
- WVU Trial Tracker: `scripts/run_protocol_check.sh` for the list in `Projects/WVU Trials Demo/data/ctsu_protocols.json`. The protocol button and its poller are off. The ClinicalTrials.gov ingest button does not download PDFs.
- Patient Trial Matching: `download_queue.py` writes into this folder, not into that project.

`download_protocols.py` `check_one()` is the only writer of `protocols/manifest.json`.

Readers do not log into CTSU and do not read PDFs. This dashboard, WVU, and Worldwide RT Trials read the briefs and manifest through `scripts/protocol_library.py`. A schema read from the protocol's schema page is filled into the brief here, by the extractor, when it passes a readability check.

`scripts/ctsu_chrome_lock.py` locks the CTSU Chrome profile (scope `chrome`) and publishing (scope `publish`). Each Mac has its own lock file under `~/Library/Application Support/wvu-trial-tracker/`, and a marker in `protocols/` (synced by Syncthing) keeps the other Mac from starting the same work. A marker older than 3 hours is stale.

The public protocol list (`ctsu.cancer.gov/protocol` and its browse feed) does not need a login. Anything on the CTSU member site (`www.ctsu.org`), including protocol PDFs and amendment checks, does.

Before opening the member site, prompt Jeff to sign in with ID.me in the automation Chrome window and wait until that sign-in is finished. Do not try the member site while logged out, and do not ask for or type the ID.me password. Skip the prompt when the public feed is enough.

To refresh protocols, have Jeff complete that sign-in, then run `scripts/update_local.sh --protocols`. The CTSU session expires, so expect a new sign-in for each protocol check.

`scripts/check_protocol_updates.sh` refreshes the public study list, then checks the current protocol document for every study on the list. It appends `logs/protocol_changes.md` (local only, with the PDFs). A new protocol version is downloaded beside the previous file, and the log quotes the amendment memorandum or the summary-of-changes text from the opening pages. It opens https://www.ctsu.org/ in the automation Chrome and waits up to 60 minutes for Jeff's ID.me sign-in; Chrome stays open from sign-in through the downloads. After the downloads it refills the briefs of changed protocols and runs `rebuild_consumers.sh`. Either Mac can run it. It skips when the other Mac finished a full check within 12 hours (`protocols/.last_full_check.json`) or holds the lock. `--force` ignores the 12-hour rule. Log: `logs/protocol_check.<host>.log`.

Scheduled jobs (`launchd/`, copied into `~/Library/LaunchAgents` and loaded on each Mac that should run them; loaded on Ryck's MB Air October 11, 2026):

- `com.jeffryckman.ctsuProtocolCheck.plist`: Sunday 7:00 PM protocol check. If the Mac is asleep then, launchd runs it at the next wake.
- `com.jeffryckman.trackerPublish.plist`: daily 6:30 AM `rebuild_consumers.sh --if-stale`, which republishes any tracker left behind by a failed publish or a hand edit to the briefs.

## Google sign-in setup (one time)

Done October 7, 2026: Firebase project `ctsu-dashboard` (display name "CTSU Dashboard", Spark plan, Firestore in nam5). The API key accepts requests only from `https://jryck3.github.io/*` and `https://ctsu-dashboard.firebaseapp.com/*`. The steps below document the setup in case it needs to be redone.

1. In the [Firebase console](https://console.firebase.google.com/), create a project (Google Analytics not needed) and add a **Web app**. Copy its config object.
2. **Authentication** > Get started > Sign-in method > enable **Google**. Under Settings > Authorized domains, add `jryck3.github.io`.
3. **Firestore Database** > Create database (production mode). Replace the rules with the contents of `firestore.rules` and publish.
4. Save the web config as a repository variable (not a secret; the values are public identifiers that end up in the page):
   `gh variable set FIREBASE_WEB_CONFIG --repo jryck3/CTSU-Tracker --body '{"apiKey":"...","authDomain":"...","projectId":"...","appId":"..."}'`
5. Run the workflow from the Actions tab (or wait for the daily run). The Sign in with Google button then appears.

Optional hardening: in Google Cloud console > APIs & Services > Credentials, restrict the browser API key to the `https://jryck3.github.io/*` and `https://<project-id>.firebaseapp.com/*` referrers (the second hosts the sign-in popup).

The local dashboard opens from a `file://` path, where Google sign-in cannot run, so it keeps its list in the browser only.
