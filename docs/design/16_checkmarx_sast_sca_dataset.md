# 16 — Checkmarx SAST and SCA files (SE-01, SE-02)

Status: **D-81, scoring superseded by D-85 (owner, 1 Nov 2026)** — repo pass/fail, family % passing vs the prevailing median, Tier 0/1 Red rule kept. **2 Nov 2026 (owner):** each file uploads on its own with no other file; the real file is the layout and is read tolerantly (doc 17 §3); the violations list in the comment is **comma-separated**.

## 1. What we receive

Two **JSON** files a month from Cyber, as given by the owner: `final_checkmarx_sast_report.json` (SE-01) and `final_checkmarx_sca_report.json` (SE-02; the file has also arrived as `final_checkmarx_sca_report 1.json`). Same shape:

```json
{"importer": "checkmarx",
 "data": [{"key": "reponame/anothername",
           "measurements": [{"name": "checkmarx-sast-policy-compliant",
                             "value": true,
                             "comment": "Compliant. No SAST findings detected."}]}]}
```

- One entry in `data` per scanned repo. `key` = `org/repo` on GHES.
- `value` = true when compliant, false when not (owner confirmed the sample's `true` on a NON-COMPLIANT row was a typo).
- `name`: `checkmarx-sast-policy-compliant` in the SAST file and `checkmarx-sca-policy-compliant` in the SCA file (owner, 2 Nov 2026). Intake still lets **the feed the file is uploaded to decide SAST or SCA**, so a different name never stops a load.
- The aging policy uses **our SLAs** (Emergency 3, Critical 15, High 30 days from first detection).
- **As-of date** (owner, 2 Nov 2026): **the report date in the file when Cyber gives one** (`report_as_of`, read by the same date reader as every feed); **otherwise the upload date**. Today's files have no report date, so the upload date is used. A report date that isn't a date is noted and the upload date is used.
- No finding IDs, no closed-in-month items, no exceptions or false positives, no list of repos not scanned (requested from Cyber, §5).

### Reading the JSON tolerantly

- **Trailing commas are accepted** (the samples have `},` before `]`), as are a byte-order mark and blank lines.
- Keys are matched case-insensitively and fuzzily (`Key`, `measurement`, `Comments` all work).
- If a repo has more than one measurement, the one whose name or comment mentions this feed's type (SAST or SCA) is used; otherwise the first.
- `value` read as true/false in any form (true, "true", "TRUE", 1, "yes").

### Comment patterns (read case-insensitively and loosely)

Matched ignoring case, extra spaces and punctuation, and allowing the known spelling "exeed" as well as "exceed"; backticks around `X/Y` are optional. **The violations list is comma-separated** ("2 CRITICAL, 8 MEDIUM"); a semicolon is accepted too.

| Pattern | Read as |
|---|---|
| `Compliant. No <SAST\|SCA> findings detected.` | Pass; 0 open findings |
| `COMPLIANT All N <SAST\|SCA> findings are within acceptable aging thresholds for their security levels.` | Pass; N open, 0 overdue |
| ``NON-COMPLIANT `X/Y` <SAST\|SCA> findings exeed their aging thresholds. Violations: a CRITICAL, b MEDIUM.`` | Fail; X overdue of Y open (to confirm with Cyber); overdue count per severity |

The samples carry `#` placeholders where the numbers go (`#/#`, `All #`); a number that can't be read is left blank and the repo still counts as pass or fail.

## 2. Scoring rule (D-85)

Each repo is pass/fail. The family's result is the **% of scanned repos passing**, banded against the **prevailing median across families** (Green at or above; Amber up to 15 points below; Red beyond). **Red wins** when a repo on a **Tier 0/1 app** has an overdue **Emergency, Critical or High** finding. Full rule: `02_metric_dictionary.md` SE-01/SE-02 and [scoring rules](../wiki/scoring-rules.md).

Placing (at scoring, from whatever is loaded): **built 4 Nov 2026 (owner): each Checkmarx repo is matched to a repo in the GitHub repo file** (same full name; else the same repo name after the last '/', so `leading/reponame` finds `org/reponame`; else a close spelling at setting `checkmarx_match_min`, 0.9, with the same numbers in the name; a name shared by several GitHub repos is never guessed) **and takes the family of that GitHub repo's owner**. Every close match, every Checkmarx repo with no match and every repo whose GitHub owner has no family is listed on the mapping result. Planned: repo → app through the repo list (TR-01); tier from the app inventory (O-11). **Without those files the SAST and SCA files still upload and their counts show** (Data sources page; Firm position as Not yet mapped). Score again once the repo list and inventory are in.

Not scored: a family with no scanned repos is "Not scored — nothing in scope". Repos mapped to the family but absent from the file are an info counter; they don't fail the metric.

## 3. Wording (drafts — owner to approve)

- Result (D-45): "41 of 48 repos meet the SAST aging policy" / "… SCA aging policy".
- Focus card (D-41): "7 of 48 repos have SAST findings past their deadline — Bring the 7 back within policy (2 on Tier 0/1 apps)". Phrase parts: `noun_one` repo, `noun_many` repos, `verb_one` has, `verb_many` have.
- Red line: "Red: a Tier 0/1 app has an Emergency, Critical or High finding past its deadline."
- What it tells you (draft): "A repo meets the aging policy when no finding is open past its deadline (Emergency 3, Critical 15, High 30 days). A pass shows findings are being fixed on time; it does not show the code is free of flaws, and repos that weren't scanned aren't counted here."

## 4. Checks at upload (this file only)

| Check | If it fails |
|---|---|
| File can be read as JSON (trailing commas allowed) and has a list of repos | Refused at upload if not (owner, 3 Nov 2026); an empty list is kept, with a warning |
| `importer` is checkmarx | Note only |
| `key` present | Repo set aside and listed |
| Same `key` twice | Later entry set aside and listed |
| Comment matches a pattern (§1) | Pass/fail from `value`, counts blank, note listing the repo |
| `value` agrees with the comment | Note, listed; **the comment decides** |
| NON-COMPLIANT: 0 < X ≤ Y and X = sum of violations | Note, listed; the repo still counts as failing |
| As-of date | The file's report date if it has a readable one; otherwise the upload date. An unreadable report date is noted |

No check looks at any other file.

## 5. Request to Cyber (sent by the owner)

Part 1: a report date, per repo the numbers as their own fields (`open_findings`, `overdue_findings`, overdue by severity), and a coverage list of every in-scope repo with scan status and last successful scan. Part 2, later: one entry per finding (stable finding ID, severity, first detected, due, status, closed at, false positive, exception ref/expiry; SCA adds vulnerability ID). Questions: how Emergency appears in Checkmarx; whether `X/Y` = overdue / all open.

## 6. Build notes

- Reader: `backend/trust/intake/checkmarx.py`, `read(file_bytes, kind, uploaded_at)`; returns `as_of` (the file's report date, else the upload time in New York), `as_of_source` and `report_date`. Upload time comes from the shared `upload_time` helper.
- `metric_version.scoring_method = rate` with a prevailing-median tolerance threshold set (gap 15 pp) plus a status rule `t01_overdue_ech → Red`.
- Evidence item type `repo` with attributes `compliant`, `overdue_count`, `open_count`, `overdue_ech`.
