# 17 — Data intake architecture (CSV/JSON files now, Jira and GitHub next)

> **Superseded for storage by doc 11 (13 tables) and by the built intake in `backend/trust/intake/` and `store.py`; kept for history. Where this document and the code differ, the code is right.** The `src_*` schemas, the `raw_` and `std_` tables, `evidence_item`, the 33 tables and the `UNATTRIBUTED` name below are the old design; the built system keeps cut-down files in `kept_file` and says "Not yet mapped".

Status: **design approved by the owner, 1 Nov 2026 (D-83); changed by the owner 2 Nov 2026: every file is independent (§3), files are read tolerantly (§3), every month stands alone.** Builds on `11_data_model_v2.md` (33 tables) and the dataset docs 13–16 and `QUESTION_BANK.md`.

## 1. Owner decisions (D-83)

| # | Decision |
|---|---|
| 1 | **One Postgres database, one schema per source** (`src_hr`, `src_inv`, `src_pm`, `src_tcc`, `src_ntcc`, `src_cmx`; later `src_jira`, `src_ghes`). Each schema has its own database role, so it can be moved out later without changing the model. |
| 2 | **Raw tables hold only the columns TRUST uses.** **TRUST also keeps a copy of every file** (owner, 2 Nov 2026, replacing D-97's "hash and link only"; in Postgres, in a database table), **cut down at upload to the columns TRUST uses** (owner, 2 Nov 2026; HR also to the CTO's line), with the hash of the file as received. Mapping can be re-run without re-uploading, except after fixing the name of a column that wasn't found. The SharePoint link is still recorded. |
| 3 | **No API access in v1.** The cleaned views are the future API surface; nothing is exposed now. Reads are through the TRUST app only. |
| 4 | **Who can read:** Tech Risk and auditors see everything; family leads see only their own family's rows; UNATTRIBUTED rows are Tech Risk only. Raw rows are never shown outside Tech Risk. **Retention:** source-schema rows are kept **24 months** (D-86). |
| 5 | **Jira/GitHub pull timing:** a scheduled pull in the first hours after month end (business day 1, New York time). Event history is replayed to 23:59 New York; settings with no history (branch rules, CODEOWNERS) are recorded **as pulled**, with the pull time on the submission. |

## 2. The layers

**Step 1, upload (one file, on its own; nothing is read):**

1. **Keep the file** — the bytes as received, plus hash, name, size, SharePoint link, feed, month, who and when (`submission`). Build: `backend/trust/store.py`. Only the columns (or JSON fields) TRUST uses are kept (owner, 2 Nov 2026); the HR file also only the CTO's line (doc 13 §3). The hash of the file as received is still recorded. A feed with no reader yet is kept as received.

**Step 2, map (re-run any time; reads the kept files with the current column map and settings). Build: `backend/trust/mapping.py`:**

2. **Source schema** `src_<source>.raw_<entity>` — every delivered column TRUST uses, as TEXT, plus `submission_id`, `row_no`, `row_sha256`, `row_status` (ok / skipped + reason). Append-only. Skipped rows are kept, never dropped.
3. **Cleaned view** `src_<source>.std_<entity>` — typed: dates parsed in any common format (New York unless the layout says otherwise), emails lower-cased, known typos fixed, status words mapped. A value that does not parse becomes NULL plus a parse-failed flag.

**Still step 2, placing (whatever files are loaded for the month, redone every time it runs):**

4. **Placing** — attribution (email → HR → manager → family; repo → app → family; otherwise **UNATTRIBUTED**, shown on Firm position, D-73), using whichever HR, mapping and inventory files are loaded for the month. If none are, everything is UNATTRIBUTED.
**Step 3, score:**

5. **TRUST model** — `evidence_item` → `metric_value` → `calc_run`, rebuilt on every score.

   *Built 2 Nov 2026 (files, before Postgres):* `backend/trust/measure.py` counts each metric per family from the mapped month; `backend/trust/score_month.py` judges each result against `config/thresholds.json` and scores building blocks and TRUST with `scoring.py`, writing `store/scored/<month>.json`. Rules: [scoring rules, live scoring step](../wiki/scoring-rules.md#live-scoring-step-built-2-nov-2026).

**Step 4, publish:** `backend/trust/publish.py` puts every scored month into one `data.json` for the front end and writes `store/published/index.html` (the front end with the data built in) and an empty `evidence.json`. Values that need an earlier month (change arrows, history, New/Chronic red, trend) appear only where that month is scored.

**Table count:** the 33 model tables stay at 33. The file layout lives in `data_feed.layout jsonb`, including each column's **header aliases**; the load log is `submission` + `validation_result`. Source schemas add about 8 holding tables for today's files, plus 2–3 each for Jira and GitHub.

## 3. One intake path for every source

### Every file is independent (2 Nov 2026, owner decision)

Each of the 19 feeds uploads on its own (AD owner groups added 6 Nov 2026; DR tests added 3 Nov 2026; 19 until 2 Nov 2026: there is no incidents file and no client-issues file), with **no other file present**. SCA loads with no HR, no inventory, no repo list, nothing.

- **Upload** (`store.upload(feed, month, bytes, …)`) keeps the file, cut down to the columns TRUST uses. It never reads another feed and never refuses because another feed is missing. It checks the file on its own and refuses junk (owner, 3 Nov 2026; below).
- **Mapping** (`mapping.map_month(month)`) reads each kept file on its own, then joins whatever is loaded. Safe to run as often as wanted. Loading HR or the inventory later, fixing a column name or changing a setting, then mapping again, re-places everything; nothing is re-uploaded.
- Each feed's own counts are shown as soon as it is uploaded (Data sources page; Firm position as Not yet mapped), with no other file.
- Cross-file checks (an action's incident is in the postmortem file; a Ticket ID is also in Non-TCC; summary = detail between postmortems and actions) run in mapping, only when both files are loaded, and are **warnings**.
- The same hash twice is a no-op warning; a different file for the same feed and month replaces the accepted one (D-92).
- **Refusals at upload:** an empty file, a locked month, and junk. **Checked at upload, on its own** (owner, 3 Nov 2026): each file is read with its own feed's reader the moment it arrives, with no other file needed (`backend/trust/checks.py`). **Junk is refused and not stored**: a file that can't be read, that doesn't look like this feed's file (most of the fields TRUST needs aren't in it), where every row is unusable, or an HR file with nobody in the CTO's line. The attempt is logged with the reasons. Everything else is stored, with any warnings shown straight away; each warning must be acknowledged on This month before the month can be locked. A real file with no rows this month is kept, with a warning.

### The provider's real file is the layout (2 Nov 2026, owner decision)

TRUST adapts to the files; the files never adapt to TRUST. The column lists in docs 13–16 were first guesses; the real files replace them.

- **Column map.** Each feed's entry in `config/column_maps.json` (owner-editable; later also `data_feed.layout`) says which of the provider's real headers gives each field TRUST needs. It is written from the real file's header row and updated whenever the provider's file changes. Order does not matter; columns TRUST does not use are not read.
- **Case-insensitive fuzzy header matching**, in order: (1) exact after ignoring case, spaces, underscores, hyphens and punctuation; (2) a name in the column map; (3) closest header by spelling, similarity ≥ 0.85 (setting `header_fuzzy_min`), word order ignored. A tie between two headers uses neither and names both. Every fuzzy match is shown on the upload result.
- **Delimiters detected**: comma, semicolon, tab or pipe; quoted fields may contain the delimiter; a UTF-8 byte-order mark is ignored. Lists inside a cell may use commas or semicolons. Code values (statuses, outcomes, severities) are matched case-insensitively too.
- **A field TRUST needs is not in the file:** the file loads, and the metrics that need that field show **No data** with a plain note naming the field. That is a gap in what is sent, raised with the provider if wanted, not a fault in the file.
- **Dates and times** in whatever format the file uses (M/D/YYYY, MM/DD/YYYY HH:MM:SS AM/PM, YYYY-MM-DD, D Mon YYYY, with or without a time), with **fractions of a second of any length** (`.1`, `.123`, the TCC's 7-digit `.1234567`, or a bare `.`) in any of those formats. Fractions are kept to the microsecond. A trailing `Z` means UTC; no timezone means New York (L-TCC-04). **The same reader (`parse_when`) is used for every date in every feed**; a guard test in `tests/test_dates.py` fails if a reader parses dates any other way. **Numbers** may carry thousands separators or a % sign.
- **A row without its own key** is set aside and listed with its row number and reason; the rest loads.
- **The provider's file changes:** update the column map. No new layout version or approval needed.

### Other ways in (later)

- **Scheduled pull** (Jira, GHES): token from the vault at run time (`data_feed.vault_ref`); requests only the layout's fields; the pull is saved as one canonical file and then goes through `ingest` like an upload.
- **Provider database view**: a read-only account reads the view into a file, then `ingest`. Only the method changes.

## 4. Checks

| When | Checks (all WARN unless marked) |
|---|---|
| Upload | Empty file, locked month, and junk (unreadable, wrong file, every row unusable, HR with nobody in the CTO's line): **refused, not stored**, attempt logged. Same hash as an earlier upload: no-op. Otherwise the feed's reader runs on the kept file and its notes are stored as warnings (owner, 3 Nov 2026). |
| Map: file | Can be read at all (else "could not be read", noted; other files still mapped); required headers found by loose match (missing = note, its metrics show No data). |
| Map: rows | Key present and readable (else row skipped and listed); duplicate keys (later row skipped); values parse; unknown code values; parsed = loaded + skipped. |
| Map: cleaned | In the month (New York). Documented exclusions (DEFCON 0, cancelled, outcome 99) applied here with `exclusion_reason` — no hand filtering. |
| Map: across files, then scoring | Cross-file links when both files are loaded; share not placed with a family; summary = detail; minimum population; change vs prior month (when scored); then V01–V23 (format and layout ones are warnings) and lock checks. |

## 5. Per-file raw schemas and mappings

| File | Schema.table | Loaded / not loaded | Feeds | Used for placing at scoring (optional) |
|---|---|---|---|---|
| HR CSV (22 cols) | `src_hr.raw_hr` | 15 loaded (incl. Department, and Country temporarily, owner 3 Nov 2026); 7 not (minimisation) | `hr_mapping`, `hr_membership`, `app_user` | — |
| Postmortem CSV | `src_pm.raw_postmortem` | Exec summary, contributing factors, participants, `status` not loaded | UN-02 scope and coverage check | HR |
| Action items CSV | `src_pm.raw_action_item` | Link formula kept as text; parsed to `item_ref` / URL | UN-02 | HR; postmortem file for scope (until loaded, all actions count, with a warning) |
| Checkmarx SAST / SCA JSON (trailing commas accepted; violations comma-separated) | `src_cmx.raw_sast`, `src_cmx.raw_sca` | All fields TRUST uses | SE-01 / SE-02 pass/fail per repo (D-81, D-85) | Repo list → inventory (tiers) |
| TCC CSV (33 cols) | `src_tcc.raw_tcc` | 4 not loaded | TE-01, TE-02, client-impact Red | HR |
| Non-TCC CSV (12 cols) | `src_ntcc.raw_ntcc` | Title, department, assignees not loaded (to confirm) | None: read, not scored (TE-01 is TCC only; changes outside TCC are left to TE-06, not on the scorecard yet) | HR |

Open questions per file (closed date Q4, approval code list Q-TCC-03, timezone Q-TCC-15, Non-TCC deployment date Q-NTCC-01, report date from Cyber) are in the question bank. None of them stops a file from loading.

**Jira and GitHub can close the postmortem gap.** Action links are labelled `JIRA:` or `GITHUB:`. For those actions, Jira change history gives the real closed date and every due-date move, and GitHub issues give `closed_at`.

## 6. Jira and GitHub Enterprise Server (next)

**Identity and tokens.** A named read-only service account (e.g. `svc-trust-readonly`) owned by a team with a second custodian — no personal tokens. Tokens in the vault only, never in the database, code or logs. Rotate every 90 days; alert 14 days before expiry.

**GitHub needs Administration: read** to see branch protection. Without it calls return 403/404 and a repo looks unprotected. Rule: 403/404 = **unknown**, shown separately, never "fail".

**GHES calls per metric** (verify against the installed version from `GET /meta`; rulesets need ~3.11+):

| Need | Call |
|---|---|
| Repo list (TR-01/02/05) | `GET /orgs/{org}/repos` or GraphQL `organization.repositories` |
| Active in 90 days | `GET /repos/{o}/{r}/commits?since=…&per_page=1` (not `pushed_at`) |
| Owning team | Custom property `GET /repos/{o}/{r}/properties/values` (preferred) or `GET /repos/{o}/{r}/teams` |
| Branch rules (TR-02) | `GET /repos/{o}/{r}/branches/{b}/protection`, plus `GET /repos/{o}/{r}/rules/branches/{b}` and org rulesets (check bypass actors) |
| Re-approval after new commits | `dismiss_stale_reviews` or `require_last_push_approval` = pass |
| CODEOWNERS | contents at `CODEOWNERS`, `.github/CODEOWNERS`, `docs/CODEOWNERS` |
| Branches and committers (TR-05) | `GET /repos/{o}/{r}/branches`, commits per branch in window; bots excluded |
| Merged PRs and reviews (TE-05) | GraphQL `pullRequests(states:MERGED){reviews…}`; direct pushes via `GET /commits/{sha}/pulls` = empty |
| Issues (UN-02) | `GET /repos/{o}/{r}/issues/{n}` (`closed_at`; due date via milestone `due_on`) |

**Jira.** Data Center: `GET /rest/api/2/search` with `expand=changelog`. Cloud: `/rest/api/3/search/jql` (token paging; changelog capped at 20, page `/issue/{key}/changelog`). Fields: status, resolution, resolution date, due date, assignee, created. Due-date history from changelog `field == "duedate"`. Cloud may hide emails — map by account ID.

**Raw storage.** `src_ghes.raw_response` / `src_jira.raw_response` (+ `raw_changelog`): one row per object per pull, with endpoint, params, HTTP status, ETag, API version, `object_key`, `payload jsonb`, `payload_sha256`.

**Operations.** Serial requests with back-off on 429/5xx (max 5 tries); ETags; incremental watermarks; full monthly re-read of settings. A failed pull = late or not-received submission, never a partial one.

## 7. Questions for platform teams (in the question bank)

Q-GH-01 GHES version · Q-GH-02 rate limits · Q-GH-03 audit-log retention for branch-rule history · Q-GH-04 GitHub login → work email source · Q-GH-05 are production deployments recorded in GitHub · Q-GH-06 how a repo's owning team is recorded · Q-JIRA-01 Cloud or Data Center · Q-SEC-01 service account and Administration: read grant.

## 8. Risks

- Settings have no history API: TR-02 is "as pulled" unless the audit log is kept (Q-GH-03).
- Commit emails are often noreply: TR-05 shows an "unmatched" count until Q-GH-04 is answered.
- If the New York timezone assumption is wrong, month-end rows move month. A change is a reprocess, and for a locked month a formal restatement.
- Tolerant, independent loading means a month can be scored with files or columns missing. The warnings, the **No data** statuses and the Not yet mapped share are what make that visible, so Tech Risk must read them before locking.
