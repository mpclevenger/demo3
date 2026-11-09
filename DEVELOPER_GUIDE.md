# Developer guide: read this first

For developers working in this repository. The product owner is a tech risk advisor, not a developer, and the readers are the CTO and senior leaders: write docs and on-screen wording in plain, friendly, short sentences, and say what a term means the first time.

## What this is

TRUST is the monthly tech-risk scorecard for the CTO and senior leaders. Providers send monthly files; TRUST reads them, places every number with a product family, scores its metrics (20 in the dictionary, 10 measured today) into six building blocks (Security, Resiliency, Stability, Releases, Accountability, Modernization) and a TRUST score, and locks each month into an official, auditable record. **TRUST makes no PDFs** (owner, 2 Nov 2026): every page has a Print view that expands everything, and people print with their browser's own Print.

**The prototype is the locked v1 design** (owner, 3 Nov 2026). The screens follow it; don't redesign them. A design change is a v2 candidate: raise it with the owner.

Stack: Python 3.13, Flask and gunicorn, Postgres (the platform's add-on, `DATABASE_URL`; psycopg 3), the screens in `frontend/index.html` (the v1 design, live data only). Built with the **Heroku Python buildpack** (`requirements.txt`, `.python-version`, `Procfile`): see [deployment](docs/wiki/deployment.md). No PDF generation.

Start with the wiki index, `docs/wiki/README.md`. The rules are decided in `docs/review/ARCH_REVIEW.md` §6 (decisions D-01 to D-106): link to a decision by its ID, never restate it. **Both are kept outside this repo for now**, as do the wiki pages `modules`, `tables`, `settings`, `recipes`, `glossary`, the diagrams and the per-source data-source pages. Links to them from the pages in this repo stay broken until they are copied in.

## The three rules that matter most (owner, 2 Nov 2026)

The build kept refusing real data. These rules override anything older in the docs or code that says otherwise.

**0. Every file stands alone, and upload is separate from mapping.** Each of the 19 feeds uploads on its own, with **no other file present**: SCA loads with no HR, no inventory, no repo list, nothing. There are three separate steps:

The website (This month and Data sources pages) does all of this too: upload, Update the scorecard (map + score + publish, run in the background by `backend/trust/jobs.py`, progress in the event log), Lock and Reopen, and families' comments. Anyone past the access add-on can; their typed name is recorded (owner, 3 Nov 2026). The data model is thirteen tables ([doc 11](docs/design/11_data_model_v2.md)). The Data dictionary page (everyone) lists every file, its checks and its data contract; a contract approved by Tech Risk is formal: the file is used only for the metrics it lists, and a changed layout is flagged at upload (owner, 4 Nov 2026).

1. **Upload** (`backend/trust/store.py`): keep the file, with its hash, feed, month, who and when. Refused: an empty file, an unknown feed, a badly written month, a locked month, and junk. **Checked at upload, on its own** (owner, 3 Nov 2026): each file is read with its own feed's reader the moment it arrives, with no other file needed (`backend/trust/checks.py`). **Junk is refused and not stored**: a file that can't be read, that doesn't look like this feed's file (most of the fields TRUST needs aren't in it), where every row is unusable, or an HR file with nobody in the CTO's line. The attempt is logged with the reasons. Everything else is stored, with any warnings shown straight away; each warning must be acknowledged on This month before the month can be locked. A real file with no rows this month is kept, with a warning. TRUST keeps a copy of every file (owner, 2 Nov 2026; replaces part of D-97): in the database when `DATABASE_URL` is set (table `kept_file`), otherwise in `store/`. **Only what TRUST uses is kept** (owner, 2 Nov 2026): each file with a reader is cut down as it arrives to the columns (or JSON fields) TRUST uses; everything else is dropped and never stored. The hash of the file as received is still recorded. The HR file is cut down further, to the CTO and everyone reporting up to them (setting `hr_root_sam_account`); if that setting is empty or the person isn't in the file, nothing of it is kept. A file whose layout hasn't been given yet is kept as received until it has a reader. **A column TRUST couldn't find was dropped**, so after fixing its name in the column map, upload the file again (the upload result lists what wasn't found).
2. **Map** (`backend/trust/mapping.py`): read the kept files with the current `config/column_maps.json` and `config/settings.json`, clean them, and place rows with people and families from whatever is loaded. **Re-run it any time** (HR arrived, a setting changed): nothing is uploaded twice, except a file whose column wasn't found, or HR after the CTO setting changes. It never refuses; problems become notes.
3. **Score**: metrics, building blocks, TRUST, `data.json`, from the mapped result.

- **Joining files happens only in mapping**, and is redone every time it runs. Whatever is there gets joined; whatever is missing leaves rows as Not yet mapped.
- Each feed's own numbers are always visible, even with nothing else loaded (on the Data sources page and Firm position, as Not yet mapped). Uploading HR or the inventory later, then mapping again, places them with families. Nothing needs re-uploading.
- Cross-file checks (an action's incident in the postmortem file, a Ticket ID also in Non-TCC) run in mapping, only when both files are there, and are warnings.

**1. Every month stands alone.** Any month can be loaded, scored and locked on its own, in any order, with whatever files have arrived.

- Never require an earlier month, an earlier quarter or a minimum number of months. No "score earlier months first", no "lock in order".
- Change arrows, trends, New Red, Chronic Red, Sharp drop and Declining appear only when the earlier months they need are scored; otherwise they are simply not shown.
- Prevailing median: from the month itself (using an earlier scored quarter isn't built yet), **always calculated from the data, however few families have a result: no static starting values** (owner, 3 Nov 2026). See [scoring rules](docs/wiki/scoring-rules.md).

**2. The provider's real file is the layout.** TRUST adapts to the files; the files never have to adapt to TRUST. A real file is never "wrong" because it differs from a layout written in these docs: the layouts in `docs/design/13`–`16` were first guesses and are replaced by the real files' headers.

- **Every** feed has a **column map** in **`config/column_maps.json`** (owner-editable; no code change; never hard-code a column name in a reader, only built-in fall-backs): which of the provider's real headers gives TRUST each field it needs. It is built from the real file, and updated whenever the provider's file changes. Order does not matter; columns TRUST does not use are simply not read.
- **Matching is case-insensitive everywhere** (file headers, JSON keys, the names in the column map, code values such as statuses) **and fuzzy**, in this order: (1) exact after ignoring case, spaces, underscores, hyphens and punctuation; (2) a name in the column map; (3) **fuzzy**: the closest header by spelling (similarity of at least 0.85, e.g. `postmoretm_id` → `postmortem_id`, `Approval recorded at UTC` → `Approval recorded at (UTC)`), also allowing words in another order. If two headers are equally close, neither is used and the note names both. Every fuzzy match is listed on the upload result ("used 'postmoretm_id' for postmortem_id") so a person can see it.
- **Delimiters are detected, not assumed.** CSV files may be comma, semicolon, tab or pipe delimited; quoted fields may hold the delimiter. Lists inside a cell (assignees, violations) may be separated by commas or semicolons. **Checkmarx SAST and SCA files are JSON**; the violations list in their comment is comma-separated, and the JSON may have trailing commas, which are accepted ([doc 16](docs/design/16_checkmarx_sast_sca_dataset.md)).
- **Every date in every input file goes through one reader, `parse_when` in `backend/trust/intake/common.py`.** It reads whatever format the file uses (M/D/YYYY, MM/DD/YYYY HH:MM:SS AM/PM, YYYY-MM-DD, ISO with `T`, D Mon YYYY, with or without a time), fractions of a second of any length, `Z` as UTC, and no timezone as New York (L-TCC-04). A reader must never parse dates itself; `tests/test_dates.py` fails if one does. To add a format, add it in `parse_when` and a line in `tests/test_dates.py`, and every feed gets it. Numbers may carry thousands separators or a % sign.
- If a field a metric needs is not in the file, the file still loads and that metric shows **No data**, with a plain note saying which field it needs. That is a gap in what the provider sends, not an error in the file.
- A row without its own key is set aside and listed with the reason; the rest of the file loads.

Upload refuses a file only when it is empty, its month is locked, or it is junk (see rule 0: unreadable, the wrong file, every row unusable). A real file with problems is kept, and its warnings are acknowledged before the lock.

## Where things live

| Path | What |
|---|---|
| `frontend/index.html` | The screens: one page in the locked v1 design, filled with `data.json` by `publish` and served by `backend/trust/web.py`. It holds only definitions (building blocks, method page and the screens' code); the metrics and their dictionary cards come from `config/metrics.json` (owner, 8 Nov 2026). There is no sample data or prototype mode in it (owner, 3 Nov 2026), so opened on its own it shows nothing. **Sortable columns** (owner, 4 Nov 2026): every data table's column heads sort it (low to high, high to low, then the usual order; blanks last; a detail row stays with its row); the family heatmap sorts families within their band, Firmwide stays last. A table whose order means something carries class `nosort`; a cell can give its exact sort value in `data-sv`. Sorting only reorders rows on the screen and never changes a score. **Family page (owner, 6 Nov 2026):** one metrics table replaces Where to focus and the block sections: worst first, rows tinted by status with a solid strip on the left, every column sortable, the block tiles above filter it, ▸ opens a row's detail (Which ones, Explain, Challenge, the drill-down). The CTO watch list's metric names open that row on the family page. |
| `config/metrics.json` | **Every metric, in one place (owner, 8 Nov 2026):** name, building block, status (Measured, In progress, Planned, Coming soon), the dictionary card, the known limits (one line each), the wording the pages use, and how it is counted (which files it needs, what its items are, the code behind it). `score_month.template()` merges it into the page data; `measure.py`, `evidence.py`, `score_month.py` and `codelinks.py` read their per-metric facts from it. The counting itself stays in the metric's function in `measure.py`. Edited by the owner ([how](docs/wiki/runbook.md#change-a-metric)); `tests/test_metrics_file.py` catches typos. |
| `config/column_maps.json` | The column names each provider file uses, per feed. Edited by the owner ([how](docs/wiki/data-sources/README.md#change-a-column-name)). |
| `config/thresholds.json` | Tolerance thresholds for the scoring step (policy values and prevailing-median settings; prevailing medians are calculated from each month's data). Edited by the owner; score again after a change. |
| `config/access.json` | Roles (owner, 3 Nov 2026): the add-on's header names for SAM_ACCOUNT and AD groups, and the AD groups for each role. Empty `user_header` = open (everyone can do everything, with a banner). `backend/trust/access.py` reads it. |
| `config/settings.json` | Owner settings: `hr_root_sam_account` (the CTO's SAM_ACCOUNT; upload HR again after a change) `subteam_hr_column` (which HR column names the sub-teams on family pages), and `team_grouping` (owner, 3 Nov 2026: `product_family`, the default, from the owners file; or `l3`, each level-3 person's org from HR, level set by `l3_level`). Change, deploy, then update the scorecard. |
| `backend/trust/` | The application: `storage.py` (where things are kept: the database add-on when `DATABASE_URL` is set, else `store/`), `web.py` (the website), `migrate.py` (sets up the tables), `lock.py` (lock and reopen a month, with the seal), `evidence.py` (the items behind each family's numbers: drill-down and CSV), `store.py` (upload), `mapping.py` (map), `linking.py` (joins), `intake/` (one reader per feed), `measure.py` (count per family), `score_month.py` (judge and score, using `scoring.py`), `publish.py` (data.json + page for the front end), `codelinks.py` ("See the code" on each metric card: function line numbers read from the source with `ast`, linked at the deployed commit; needs `code_repo_url`), `retention.py` (keep 24 months and the newest run of each month; dry run unless `--write`; the scheduler add-on runs it monthly; [deployment](docs/wiki/deployment.md#retention)). Command line: `python manage.py upload …` / `map …` / `score …` / `publish` / `lock` / `reopen` / `calibrate` / `migrate` / `retention`. |
| `tools/` | Scripts run outside the app: `github_repo_export.py` + `github_client.py` (the repos file), `jira_export.py` (Jira issues), `why_owners.py <month>` (read-only: every owners-file upload for the month, the leads in the newest one, and how they differ from what the last Update used), `why_family.py <month> <family>` (read-only: where a family's rows came from, its counts with and without a shared lead's group, each metric's result and the coverage settings), `expand_owner_groups.ps1` (PowerShell, run on a Windows desktop with the AD module: the members of app owner emails that are AD groups, for the `app_owner_members` feed), `make_test_data.py` (made-up provider files for the TEST site, written to a folder) and `upload_test_data.py` (uploads a folder of files to a site and updates each month). The app holds no made-up data ([deployment](docs/wiki/deployment.md#the-test-environment)). |
| `store/` | Kept uploads and results when there is no database (`TRUST_STORE_DIR`; local use and tests). Real data: **never committed** (in `.gitignore`). |
| `migrations/` | Numbered SQL for the tables, run by `python manage.py migrate` (the Procfile's release line). **Append-only.** |
| `requirements.txt`, `requirements-dev.txt`, `.python-version`, `Procfile`, `bin/trust` | What the Python buildpack uses, the test tools, and a helper to run TRUST commands on the platform ([deployment](docs/wiki/deployment.md)). |
| `tests/` | One file per area (`test_tcc.py`, `test_web.py`, ...), sample provider files in `fixtures/`; `test_database.py` starts its own throwaway Postgres. Run them locally when useful; nothing runs them automatically. |
| `docs/wiki/` | The knowledge base pages kept in this repo: how a month works, architecture, scoring rules, runbook, deployment, roles and permissions, data sources. The rest is kept outside this repo for now (see above). |
| `docs/design/` | Data model (doc 11), identity and access (doc 10), the dataset documents (13–16) and the intake design (17). |
| `docs/reference/old-demo/` | Scoring code and 32 rule tests kept from the old demo, for the watch-list and trend rules not built yet ([README](docs/reference/old-demo/README.md)). Reference only. |

## Commands

```bash
python manage.py upload cx_sca report.json --month 2026-10 --by "Your Name"   # step 1
python manage.py map 2026-10                                                  # step 2, any time
python manage.py score 2026-10                                                # step 3, any time
python manage.py publish                                                      # step 4: what the website shows (database, or store/published/)
python manage.py migrate                                                      # set up the database tables (needs DATABASE_URL; runs on every deploy)
bin/trust map 2026-10                                                                           # the same commands from anywhere, e.g. one-off on the platform
bin/trust lock 2026-10 --by "Your Name"                                                         # lock by hand (also on the website: This month)
pip install -r requirements-dev.txt                                                             # the app plus pytest
python -m pytest -q tests                                                                       # the tests (tests/test_database.py starts its own throwaway Postgres)
bin/trust --help                                                                                # every command and what it does
```

The database tests need the Postgres 16 programs in `/usr/lib/postgresql/16/bin` (set `PG_BIN` otherwise); without them those tests are skipped. They never touch a real database.

**No CI and no golden test (owner decision, 2 Nov 2026).** There is no GitHub Actions workflow, no golden comparison against the prototype and no wiki staleness check. Do not add them back, and do not block work on a test result. What matters is that the app starts and loads the owner's real files.

## Ask the owner before

Stop and ask for any of these. Do not assume.

- Any **scoring change** beyond the rules above: thresholds, caps, points, how a status or building block score is worked out, the watch list.
- **Adding or retiring a metric**.
- Changing a **locked decision** in ARCH_REVIEW §6, or the meaning of a seeded setting.
- Anything that could **lose data or access** (dropping a table, rotating logins, changing `pg_hba`): warn first, before the step, say what could go wrong and how to undo it. Do not assume the current state of things (which logins, which devices, which data): check or ask.

## Migrations

Applied migrations are **append-only**. The runner records each file's SHA-256 and refuses to start if one was edited. To change anything, add a new numbered file. Give every new table and column a `COMMENT ON` (they say what each table holds in plain words), and describe the new table in [doc 11](docs/design/11_data_model_v2.md).

## Vocabulary

The words a person reads are part of the product.

- Say **Green tolerance**, **Red limit**, **tolerance threshold**, **prevailing median**, **usual spread between families**, **item allowance**.
- Never use <!-- forbidden-words-ok --> "target" as a name for a threshold, "offenders", "Held by", "Top offenders".
- Direction convention: a green up-arrow means better, a red down-arrow means worse, a flat grey bar means no change.
- Counts always carry units ("7 reverts out of 92 releases"), never a bare ratio.
- Plain and friendly. "We want people to like us." Nothing duplicated: link instead of repeating.

## Security rules

- **Database login.** For now TRUST uses the one login the Postgres add-on gives (`DATABASE_URL`) for everything. Separate logins with only the access each job needs (`trust_app`, `trust_engine`, `trust_intake`, `trust_signin`) come back if the add-on allows extra logins ([deployment](docs/wiki/deployment.md#database-logins)). Never print, log or commit `DATABASE_URL`.
- **When the separate logins come back, every table needs grants, and row-level security if it holds family data.** Nothing is granted automatically. (Today's migrations grant nothing: there is only the one login.)
- `pg_hba.conf` never says `trust` for these logins. Passwords come from the environment, never from code or files. (A command to set the separate logins' passwords is not built yet.)
- **Access is handled by the company's add-on container in front of TRUST, not Entra (owner, 2 Nov 2026).** TRUST has no sign-in of its own: don't build one, and don't add Entra, OIDC or login settings. The add-on identifies people by `user_id`, which is their SAM_ACCOUNT in HR.
- Item-level evidence (the items behind each family's numbers) leaves TRUST only through `backend/trust/evidence.py`: `page_evidence` (the page's `evidence.json`, written by `publish`) and `family_items` (the CSV download at `/api/items/<month>/<family>.csv`). Do not add a second door. Item views and downloads are logged (migration 0005), and each person is shown only what their role allows ([roles and permissions](docs/wiki/roles-and-permissions.md)).
- No real data, secrets or tokens in the repository, in tests or in logs.

## Keep the wiki current

Change the wiki in the same commit as the code it describes: a rule changed means [scoring rules](docs/wiki/scoring-rules.md); a table means [doc 11](docs/design/11_data_model_v2.md); a source means its [data-sources page](docs/wiki/data-sources/README.md); a setting or a command means the `settings` / `modules` pages (kept outside this repo for now). Wiki pages are also kept in the team's knowledge base (D-105).

## Working conventions

- Small commits with plain messages. Work on a branch. Comments in code are plain language.
- Servers started in tests use ports 8700 to 8719; stop them afterwards.
- Do not create report files for your own summaries; put durable knowledge in the wiki.
