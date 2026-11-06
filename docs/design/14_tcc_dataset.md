# 14 — TCC change export (TE-01, TE-02)

Layout as given by the owner, 1 Nov 2026 (pasted text). Decisions are in `QUESTION_BANK.md` (L-TCC, R-TCC, Q-TCC) and ARCH_REVIEW D-82, D-86, D-87. **2 Nov 2026 (owner):** the file uploads on its own with no other file; the real file is the layout; column names live in `config/column_maps.json`.

**What it is.** One row per change ticket, CSV, uploaded by Tech Risk to the dashboard. Shows who raised, reviewed, approved and deployed each change, the outcome and its compliance status. Deleted, cancelled and read-only RPDs are left out. A separate **Non-TCC** export covers changes that didn't use TCC (12 columns, R-TCC-13).

**Export options (fixed by the tool):** change type (TCC / Non-TCC); date range from 1 July; the range applies to created date or planned deployment date (R-TCC-01; **owner, 2 Nov 2026:** TRUST places each deployed change in the month its ticket was **created**, so export by created date); change category (planned, emergency, standard).

## Columns (33, in six groups) — names confirmed by the owner (3 Nov 2026); read tolerantly (doc 17 §3)

Names and values are matched whatever their capitals, spaces and punctuation. The confirmed names are first in `config/column_maps.json` (`tcc`); the earlier names (Ticket ID, Ticket Link, last deployment) still work as fall-backs. Known values (Status, Change Category, Risk Score, Resolved, Pre-Deploy Compliant, Fully Compliant) are stored in one standard spelling; anything else is kept and listed.

Headers are matched case-insensitively and fuzzily through the column map; order does not matter; extra columns are ignored. Dates are read in any common format, not only the formats listed below.

| # | Column | Format / values | Loaded? |
|---|---|---|---|
| **Change details (12)** | | | |
| 1 | RPD ID | numeric — **key** | Load |
| 2 | RPD Link | URL | Load (source link) |
| 3 | Title | text | No (free text) |
| 4 | Status | Client, Completed, Hold, Monitoring, Pending, Resolved, Unassigned | Load (decides in/out, R-TCC-04; Client = client impact) |
| 5 | Change Category | Emergency, Planned, Standard | Load |
| 6 | Risk Score | Standard Change, NO / LOW / MEDIUM / HIGH / EXTREME risk, blank | Load |
| 7 | Created date (UTC) | usually MM/DD/YYYY HH:MM:SS AM/PM | Load — **decides the TE-01 month** for a deployed change (owner, 2 Nov 2026) |
| 8 | Author | name | Load |
| 9 | Author email | email — **join key to HR `Email - Work`** (the Author decides the team) | Load |
| 10 | Assignees | names, `;` delimited | Load |
| 11 | Department | text | Load (cross-check) |
| 12 | L4 director | name | Load (cross-check) |
| **Deployment schedule (3)** | | | |
| 13 | Planned Start | usually MM/DD/YYYY HH:MM:SS AM/PM | Load |
| 14 | Planned End | usually MM/DD/YYYY HH:MM:SS AM/PM | Load |
| 15 | Actual Last Deployment | usually YYYY-MM-DDTHH:MM:SS.####### (blank = not deployed) | Load — decides whether the change is deployed; **TE-02 month = month of this + 7 days** (owner, 2 Nov 2026). TE-01's month comes from #7 |
| **Reviews and approvals (10)** | | | |
| 16 | Implementer | free-form: name, email, AD group or comma list (L-TCC-03) | Load |
| 17 | Peer reviewer | free-form, as above | Load |
| 18 | Peer review outcome | 10 PASS w/o findings · 20 PASS with adjustments · 40 FAIL missing fixes · 50 FAIL significant issues · 90 NOT reviewed · 95 obsoleted/withdrawn · 99 filled in later | Load |
| 19 | Confirmed Risk Rating | numeric or blank (code list requested, Q-TCC-03) | Load |
| 20 | Overall Change Approval | numeric, blank, "OBSOLETED -- by other change", "REJECTED -- cancelled" (code list requested, Q-TCC-03) | Load |
| 21 | SBU Engineering Head Approver | always empty | No (R-TCC-03) |
| 22 | Stakeholder Approvers | always empty | No (R-TCC-03) |
| 23 | Go/No-Go Meeting | a date, or blank | Load |
| 24 | Go/No-Go Outcome | numeric or blank (code list requested, Q-TCC-03) | Load |
| 25 | Install Window | always null | No (R-TCC-03) |
| **Deployment outcome (2)** | | | |
| 26 | Overall outcome | SRE-calculated: 00 PASS no issues · 10 PASS minor issue · 40 FAIL backed out, no issues · 50 FAIL backed out, minor issues · 60 FAIL backed out, significant issues · 90 FAIL backout initiated by client · 95 obsoleted/withdrawn · 99 UNKNOWN | Load — TE-02 (40/50/60/90 = revert; 99 own count, out of rate; 95 out) |
| 27 | Resolved | Yes / No | Load |
| **Compliance (3)** | | | |
| 28 | Pre-Deploy Compliant | Yes, No, N/A | Load (cross-check only, Q-TCC-12) |
| 29 | Fully Compliant | Yes; Obsoleted/Withdrawn; No; No (Outcome marked as Unknown); Not Yet (Pending Deployment); No (Peer review not completed); No (Outcome marked as Unknown; Peer review not completed) | Load (cross-check only) |
| 30 | Fields Missing | `;` delimited list | Load (info) |
| **Audit trail timestamps (3)** | | | |
| 31 | Peer Review Recorded At (UTC) | a date-time or blank | Load |
| 32 | Approval Recorded At (UTC) | a date-time or blank | Load — TE-01 approved before deployment |
| 33 | Outcome Recorded At (UTC) | a date-time or blank | Load — TE-02 7-day window |

29 columns loaded, 4 not (Title and the three empty columns). The original file stays on SharePoint (D-97).

## Intake checks at upload (this file only; doc 17 §4)

- **File:** columns found through `config/column_maps.json` ("tcc"), case-insensitively and fuzzily. A missing column is a **note** naming it; the file still loads. If RPD ID or Actual Last Deployment can't be found, TE-01 and TE-02 show **No data** for the month; if only Approval Recorded At is missing, TE-01 shows No data; if only Overall outcome or Outcome Recorded At is missing, TE-02 shows No data. A missing Author email column doesn't stop any metric: the changes show as Not yet mapped until it is found. Extra columns are ignored.
- **Rows:** RPD ID blank or not a number → row set aside and listed; a duplicate RPD ID → the later row is set aside and listed; a date that can't be read in any common format → that value is blank and noted, the row is kept; Status, Change Category, Risk Score, Resolved, Pre-Deploy Compliant, Fully Compliant and Overall outcome are read in any case (`completed`, `PLANNED`), and an outcome written with its label (`90 FAIL backout initiated by client`) is read as its code; other values are kept and noted; blank Author email → kept, Not yet mapped (shown on Firm position).
- **Cross-file (at scoring, not upload):** a RPD ID that also appears as a Non-TCC RPD ID is a warning, listed; the change is counted once, as TCC (Q-NTCC-06). It runs only when both files are loaded.
- **Time:** all dates without a timezone are read as New York time until Q-TCC-15 is answered (L-TCC-04). A deployed change's month is the New York month of `Created date`; if that is blank, of `Actual Last Deployment`, with a note.

## Working rules used by the reader (until the code lists arrive)

- **Approved before deployment (TE-01):** a Standard change counts as approved; otherwise `Overall Change Approval` has a value that doesn't start with OBSOLETED or REJECTED, and `Approval Recorded At` is before `Actual Last Deployment`. Replace once the approval code list arrives (Q-TCC-03).
- **Revert (TE-02):** Overall outcome 40, 50, 60 or 90. 99 is its own count, out of the rate; 95 is out. **Month (owner, 2 Nov 2026):** the month the 7-day revert window ends, i.e. `Actual Last Deployment` + 7 days.
- **Client impact:** Status = Client (owner, 1 Nov: TE-02 turns Red that month; Q-TCC-16 still open on detection).
- **TE-01 (owner, 2 Nov 2026):** TCC changes only; changes outside TCC (the Non-TCC file) are left to TE-06.

## Build notes

- Reader: `backend/trust/intake/tcc.py`, `read(file_bytes)`. Column names from `config/column_maps.json` ("tcc"). Tests: `tests/test_tcc.py` on a made-up export (`tests/fixtures/tcc_export.csv`).
- Each ticket row carries `month` (TE-01; from Created date; `month_from` says which date was used), `te02_month` (TE-02; last deployment + 7 days), `deploy_month` (info only) and the flags `deployed`, `approved_before_deploy`, `revert`, `outcome_unknown`, `obsoleted`, `client_impact`; the scoring step counts them per family.

## Non-TCC export (12 columns, R-TCC-13)

Changes that didn't go through TCC. **Owner, 2 Nov 2026: these belong to TE-06, not TE-01**; TE-06 is not on the scorecard yet, so the file is uploaded and read but not counted anywhere today. (Before: every deployed Non-TCC change counted in TE-01 as not approved.) Uploads on its own, with no other file; column names in `config/column_maps.json` ("ntcc").

Columns: RPD ID (key), RPD Link, Title (not loaded), Status (11 options incl. blank), RPD Category, Created Date (UTC), Last updated (UTC), Author, Author Email (not always filled in), Assignees (not loaded), Department, L4 director.

**Working rules until Change Management answers** (QUESTION_BANK proposals; the reader keeps every original value, so a different answer changes only the rule):

| Question | Working rule |
|---|---|
| Q-NTCC-01: no deployment date | **Owner, 2 Nov 2026:** the month is taken from **Created Date** for deployed changes (it doesn't move when the ticket is edited). If Created Date is blank, Last updated is used, with a note. A change raised in one month and deployed the next counts in the month it was raised. **TCC uses the same rule** |
| Q-NTCC-02: which statuses mean deployed | Completed, Resolved, Monitoring, Client (any case). Everything else, and blank, = not deployed |
| Q-NTCC-04: always "not approved"? | Yes: no deployed Non-TCC change counts as approved |
| Q-NTCC-05: blank Author Email | Not yet mapped (no matching by name) |
| Q-NTCC-06: in both files | Counted once, **as TCC**; checked at mapping when both files are loaded, and listed |

Upload checks (this file only): no RPD ID → set aside; same RPD ID twice → later row set aside; dates through the shared date reader (blank if unreadable, noted). The mapping result repeats the working rules so nobody reads the counts as final.

Build: `backend/trust/intake/ntcc.py`; tests `tests/test_ntcc.py` (`tests/fixtures/ntcc_export.csv`). Changes (TCC and Non-TCC) are placed with families at mapping: Author Email → HR → nearest family owner (doc 13 §8).
