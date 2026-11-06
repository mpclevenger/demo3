# Feed: postmortems and postmortem actions (UN-02, possibly UN-01)

Status: **layouts received from owner 1 Nov 2026; owner answers recorded below (D-80); placing route decided 2 Nov 2026 (owner): assignee → action item → incident(s).** Open: closed date (owner asking), unfiltered action export. Pairs with `13_hr_dataset.md` (HR `Email - Work` is the join key to provider files). Numbered 15 because 14 is reserved for the TCC layout.

## What the owner sent

Two CSV exports from the incident management portal.

- **Postmortem file** = every incident from the portal export, one row per postmortem; an incident can have more than one (`postmortem_is_primary` marks the main one). DEFCON 0 rows are not real incidents and never have postmortems.
- **Action items file** = actions from those postmortems. **Today the owner filters it by hand** (correlates action `incident_id` to the postmortem file). TRUST does this itself at scoring (below).

**Each file uploads on its own** (DEVELOPER_GUIDE.md rule 0): neither needs the other, or HR. Both are read through `config/column_maps.json` ("postmortems", "actions"): headers case-insensitive and fuzzy, dates through the shared date reader, extra columns ignored, a missing column is a note and only the metric that needs it shows No data.

DEFCON mapping as given: 1, 2 = SWE; 3, 4, 5 = critical; 0 = false alarm / duplicate / awareness; "Not Available" = cannot determine. (`incident_defcon_type` has a typo "critial" — normalised on load.)

## Owner answers (1–2 Nov 2026)

| # | Question | Answer |
|---|---|---|
| Q1 | Attribution | **Only action items have an owner, so everything is placed through employees: assignee → action item → incident(s)** (2 Nov 2026). Assignee email → HR `Email - Work` → manager → family |
| Q2 | Which incidents are in scope | **Anything that is not DEFCON 0** — including "Not Available". **Changed 2 Nov 2026:** incidents with no rating (Not Available or blank) are shown, never hidden, but kept out of every score (UN-01 count and UN-02 rate). **Ratings are assigned by an SRE team member, not the incident owner** (owner, 2 Nov 2026), so a family can't lower its UN-02 rate by leaving a rating blank |
| Q3 | Status mapping | Monitoring and Read-only become a new status, **Tracking**, which **counts as open** (can go overdue) |
| Q4 | Closed date | Owner is asking the provider |
| Q6 | Several postmortems per incident | **All of them** count, not only the primary (confirmed) |
| Q7 | What is an RPD | **A change ticket.** It does not give an app ID |
| Q8 | Approval on cancelled actions | **None** in the portal, so every cancelled action is left out of the rate and counted separately |
| Q10 | "Sev1/2" wording | **No change** — do not reword to "true critical incidents" |
| — | UN-01 source (2 Nov 2026) | **There is no incidents file. UN-01 = a unique count of Critical and SWE `incident_id`s in the postmortem file** (SWE = DEFCON 1–2, Critical = 3–5; DEFCON 0 out; Not Available / blank not counted and listed). Metric renamed **"Critical and SWE incidents"** (owner, 2 Nov: match the file's risk criteria; replaces Q10's "Sev1/2" wording), placed like everything else (action assignees, then `user_stakeholders`). Month = `end_datetime` (working rule). A count until the app inventory gives "per 10 apps"; shown, not scored |
| — | UN-02 exclusion wording | **Approved and changed** (see Dictionary change) |

Not yet answered: Q5 (unfiltered action export).

## Placing with a family: assignee → action item → incident(s) (decided 2 Nov 2026)

Done at **scoring**, from whatever is loaded (`backend/trust/linking.py`), and redone every time the month is scored:

1. **Action → family.** The action's assignee email → HR `Email - Work` → manager (team key) → product family. Several assignees: the **first listed** places the action (all are kept). Emails are found anywhere in the cell (`Pat Kim <pat.kim@x.com>; sam.lee@x.com`), any case.
2. **Incident → families.** An incident takes **the families of all its actions' assignees**, so one incident can belong to several families.
3. **Incident with no placed actions.** Fall back to the employees named on the postmortem (`user_stakeholders`, SAM_ACCOUNT → HR). Still nothing: **UNATTRIBUTED**, shown on Firm position as Not yet mapped (D-73). Never dropped.
4. **Assignee not in HR** (leaver, shared mailbox, outside the CTO's line) or no assignee: the action is UNATTRIBUTED, listed.

What happens when a file isn't loaded:
- **HR not loaded:** actions and incidents load and count, all as Not yet mapped. Score again once HR is in.
- **Postmortem file not loaded:** every action counts (scope can't be checked yet), with a note.
- **Action file not loaded:** incidents load; they can only be placed through `user_stakeholders`.

## Scope (at scoring, when the postmortem file is loaded)

- An action is **in scope** when its incident is in the postmortem file and is not DEFCON 0. This replaces the owner's hand filtering, so it is repeatable and evidenced.
- An action whose incident is **not in the postmortem file** is left out of UN-02 and **listed** on the result.
- An action on a **DEFCON 0** incident is left out, with that reason.

## Status mapping (decided)

Status words are matched ignoring case and extra spaces.

| Our status | Portal statuses | In the rate? |
|---|---|---|
| Done | Completed, Resolved | No |
| Cancelled | Cancelled | No — counted separately (info counter) |
| Tracking | Monitoring, Read-only | **Yes, open** — can go overdue |
| Open | To Do, Queued, Pending, Unassigned, In Progress, Hold, Review, QA, Client, blank, any status not listed (noted) | Yes |

## Dictionary change (UN-02, approved 1 Nov 2026)

Applied in the prototype, both the dictionary card and the table:

- Exclusions: "Done, cancelled and accepted-risk actions (cancelled and accepted-risk counts shown separately). Tracking actions (Monitoring, Read-only) stay open. Actions with no due date are NOT excluded — overdue once 30 days old."
- Plain-language version: "Actions that are done, cancelled or accepted-risk (cancelled and accepted-risk actions are counted separately). Actions in Tracking (Monitoring or Read-only) stay open. Actions with no due date are not excluded and become overdue once 30 days old."
- "Sev1/2" wording left as is (Q10).
- Still to carry into `02_metric_dictionary.md`. (Data contracts are a v2 item, for direct data feeds; owner, 3 Nov 2026.)

## Mapping to the data model (11_data_model_v2)

| Our field | Action items file | Notes |
|---|---|---|
| item ID | ID from the `ActionItemLink` label (`RPD:…`, `JIRA:ABCD-1234`, `GITHUB:org/repo/issues/n`); `Type` | The `=HYPERLINK("url","label")` text is parsed; the URL is kept as the source link. If the export is saved as values only, the value is the ID and the URL is blank |
| opened | `Created` (usually M/D/YYYY, date only) | Shared date reader |
| due | `ETA` (usually M/D/YYYY) | Blank ETA → due 30 days after `Created` (OD-18) |
| status at month-end | `Status` | See Status mapping |
| severity | `Severity` | Info only, not used in scoring |
| incident / postmortem | `incident_id`, `PostmortemLink` | Links to the postmortem file at scoring. Actions from every postmortem of an incident count |
| person → family | `Assignees` (email) → HR `Email - Work` → manager → family | **Decided**: the only owner in this pair of files |
| — | `DaysLeftOrPastETA` | **Not used**: worked out on the export date, not month-end. Recomputed from the due date |

| Our field | Postmortem file | Notes |
|---|---|---|
| incident in scope | `Incident Defcon` ≠ 0 (blank / "Not Available" are in scope) | **Decided** |
| incident family | via its actions' assignees; fallback `user_stakeholders` (SAM_ACCOUNT → HR) | **Decided** (2 Nov). `user_stakeholders` is a mapping key only, never shown |
| coverage check for "Best" | `postmortem_conducted`, `end_datetime` (UTC) | "Every in-scope incident closed in the last 90 days has a postmortem" |
| reconciliation | `action_items_total` | Summary-equals-detail check (warning, at scoring, when both files are loaded): per postmortem, action rows in the action file = `action_items_total` |
| not loaded | `executive summary`, `contributing_factors`, `participants_employees`, `Status` (all null), `Originating RPDs` / `postmortem_rpd_id` | Not needed for the metric |

## Checks at upload (each file on its own)

| File | Check | Result |
|---|---|---|
| Actions | No link/ID | Row set aside, listed |
| Actions | Same action twice | Later row set aside, listed |
| Actions | Status not in the mapping | Counted as Open, noted |
| Actions | Created or ETA not a date | Left blank, noted; row kept |
| Actions | No assignee email | Kept; Not yet mapped, listed |
| Postmortems | No incident_id | Row set aside, listed |
| Postmortems | Same incident + postmortem twice | Later row set aside, listed |
| Postmortems | end_datetime not a date | Left blank, noted |
| Postmortems | No Incident Defcon column | Every incident treated as in scope, noted |

## Findings

1. **No closed date on actions.** D7/O-5 decided the denominator is open at month-end **plus closed during the month**, with a late closure counting as overdue. That needs a closed date — owner is asking. Without it we can only do overdue ÷ open.
2. **No app key on either file** (RPD is a change ticket, not an app). Actions are placed by assignee. App-level views and any Tier 0/1 use are not possible for this feed.
3. **Hand filtering replaced.** The scope filter now runs at scoring on the full action export (join on `incident_id`, DEFCON ≠ 0), so it is repeatable and evidenced. Actions whose incident is not in the postmortem file are listed.
4. **Due-date history is not in the file.** "Due-date moves count only if approved" cannot be checked. ETA changes month to month can be shown by comparing stored submissions (info counter), but not approval.
5. **Cancellations are unapproved** (Q8): a team can cancel an action to drop it from the rate. The cancelled count stays visible as the countermeasure.
6. **Snapshot timing.** Status is as at export time. The export must be taken at month-end 23:59 (or carry a status-as-of date), otherwise status drifts.
7. **UN-01 could use the postmortem file**, but it has no app ID, so "per 10 production app-months" can't be attributed.
8. Header typo `postmoretm_id`: accepted through the column map alongside `postmortem_id`; no change to the export needed.

## Build notes

- Readers: `backend/trust/intake/actions.py` and `backend/trust/intake/postmortems.py`, each `read(file_bytes)`. Linking: `backend/trust/linking.py`, `link_actions_to_incidents(actions, postmortems=None, family_of_email=None, family_of_sam=None)`.
- Tests: `tests/test_postmortems_actions.py` on made-up files (`tests/fixtures/actions_export.csv`, `postmortems_export.csv`), including linking with only the action file loaded.

## Still open

- Q4 closed date (owner asking provider).
- Q5 unfiltered action export.
- Is `user_stakeholders` filled before a postmortem exists (affects the fallback for incidents with no actions)?
