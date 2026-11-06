# TRUST data model, v1 (13 tables)

Status: **agreed by the owner, 3 Nov 2026** (seven tables; `warning_ack` added the same day for the data quality checks; `proposal` and `proposal_decision` added 3 Nov for dictionary proposals; `itdr_application` and `dr_test` added 3 Nov to keep the ITDR application and DR tests files as tables). Replaces the 33-table design of 31 Oct 2026 (D-65, D-66), which was written before the owner's 2 Nov decisions: every file stands alone, mapping can be re-run at any time, settings live in files, every month stands alone. Most of those 33 tables would have held things TRUST now keeps another way (below).

All tables are in the Postgres add-on (`DATABASE_URL`). Without a database (a laptop, tests) the same things are kept in the `store/` folder. Migrations are in `migrations/`, append-only.

## The tables

| Table | One row per | Holds | Changes |
|---|---|---|---|
| `submission` | upload | feed, month, who (typed name), when, file name, hash of the file as received, hash of what was kept, columns kept and not found, SharePoint link | Never edited. The newest per feed and month is the one mapping uses; earlier ones are kept (D-92). |
| `kept_file` | kept file | the file cut down to what TRUST uses (HR: only the CTO's line), by the hash of what was kept | Never edited. |
| `month` | month | status (`open` or `locked`), locked by and at, and the **seal**: hashes of the scored result, the files used, the settings and the comments at the moment of the lock | Only by lock and reopen, each written to `event_log`. |
| `month_result` | mapping or scoring run | kind (`mapped` or `scored`), month, the full result, when, by, and the git commit and settings hash it used | Never edited. The latest run of each kind is the current one; earlier runs stay, so we can see what a month looked like before a re-score. The scored document (`doc`, jsonb) holds `blocks` and `blocks_scored` per family (was `letters` / `letters_scored`), plus `firm_blocks`, `firm_status`, `firm_capped`, `firm_blocks_scored` and `firm_trust_average` (the old average of family TRUST scores, kept for comparison; firm TRUST itself is now scored from the pooled results, owner 4 Nov 2026). |
| `published_file` | file | what the website shows: `index.html`, `data.json`, `evidence.json` | Replaced by each publish. |
| `event_log` | action | upload, map, score, publish, lock, reopen, comment, acknowledge, proposal, decision, download: who, when, which month, and a short note. A download is logged with the name given and how many rows | Never edited. |
| `warning_ack` | acknowledgement | the month, the feed, which warning (a fingerprint of its wording) and the wording, who, when, and an optional reason. The lock refuses while any of the month's warnings has none | Never edited. A warning whose wording changes needs acknowledging again. |
| `proposal` | proposal | a suggestion to change a metric's wording, add a new metric or retire one: kind, the metric (empty for a new one), a short title, the details as filled in, who, when | Never edited. |
| `proposal_decision` | decision | the answer to a proposal: approved, returned, declined or withdrawn, with a reason (required for returned and declined), who, when. A proposal with no decision is open, and one decision closes it | Never edited. A decision is a new row. Approving records the decision only; the dictionary and the scoring are changed separately, with the owner's agreement. |
| `itdr_application` | application, per upload | from the ITDR application file: Ref (number), Application Name (tidied), Business Product Area (may be empty), Recovery Tier (0 to 5, empty for TBC or not given) and its label (Tier 0 to Tier 5, TBC, Not given), and the upload it came from | Never edited. Written with its upload in one step; the newest upload for a month is the current list. Not scored yet (RE-01 to RE-03 are planned). |
| `dr_test` | DR test, per upload | from the DR tests file: Name (tidied, as the ITDR application file), Tier, Business Area, ITDR Lead, Type of Test (Open, Closed, TTX), what it is (DR test, or tabletop exercise for TTX) and, for a DR test, production or non-production, When, Status (Successful, or Not performed when blank), when it was last performed (a DR test's comment date, a tabletop exercise's When; only when Successful), Comments, the date read from the comment, whether the comment mentions TTX, and the upload it came from (migrations 0007, 0008) | Never edited. Written with its upload; the newest upload for a month is the current list. Linked to `itdr_application` by name at mapping, not stored. Not scored yet (RE-03 is planned). |
| `data_contract` | request to onboard a data source, or a new version of one | feed, version, provider, contact, what the file is, how often, the columns TRUST may read, the metrics it may be used for, who asked and when; status (draft, approved = formal, returned, withdrawn), who decided and when, reason (migration 0009; owner, 4 Nov 2026) | The request is never edited; the decision columns are filled in once. The highest approved version per feed is the current contract. |
| `comment` | comment | month, family, metric or building block (empty = the whole family; column `comment.block`), kind (explanation, data query, action), text, who, when, the comment it replies to, status for queries and actions (open, answered, closed), and whether it came after the lock | Never edited. A reply is a new row; a thread's status is its latest row's. |

## Rules

- **Comments never change a score.** They sit beside the results. The page reads them live, so a new comment shows without publishing again.
- **Lock** (by hand, from the Tech Risk console, for now; owner, 3 Nov 2026; a lock on a set date may come later): the month becomes `locked` with the seal stored. A locked month refuses upload, map and score. Comments after the lock are marked "received after lock" and never touch the figures (D-22).
- **Reopen**: with a reason, recorded in `event_log`. The month is `open` again and can be changed and locked again; the earlier seal stays in the event log. This stands in for restatement until that is built.
- **Who.** Anyone who gets past the company's access add-on can upload, comment, lock and reopen (owner, 3 Nov 2026). They type their name, which is recorded on every row.

## Where the rest of the earlier design lives now

| Earlier tables | Now |
|---|---|
| `metric`, `metric_version`, `metric_setting`, `config_parameter`, `reference_text`, `metric_limitation`, `block` | The config files (`config/thresholds.json`, `column_maps.json`, `settings.json`) and the dictionary in the front end, all in git. Each run records the git commit and a hash of the settings it used. |
| `provider`, `source_system`, `data_feed`, `expected_submission` | The list of 19 feeds in the code. "Received" or "not received" comes from the uploads. |
| `product_family`, `snapshot`, `hr_mapping`, `inventory_app` | The month's own uploaded files (family owners, HR, inventory). Mapping works out who belongs where each time it runs. |
| `metric_value`, `evidence_item`, `validation_rule`, `validation_result`, `calc_run`, `metric_result`, `score` | Inside the month's mapped and scored results (`month_result`). |
| `period` | `month`. |
| `published_document` | Not needed: no PDFs (owner, 2 Nov 2026). |
| `tracked_item`, `tracked_item_event` | `comment` (explanations, data queries, actions). Other kinds (change requests, definition items) when their feature is built. |
| `risk_acceptance`, `onboarding_answer`, `app_user`, `access_log` | Not built yet. Each becomes one table when its feature is. |
| `audit_log` | `event_log`, plus the rule that nothing is ever edited. |

## Querying results

Results are stored as one document per run, which keeps the model small but makes questions like "every Red SE-05 across all months" harder in SQL. If Tech Risk or the auditors want that, add a read-only view over `month_result` that looks like a table; nothing else has to change.
