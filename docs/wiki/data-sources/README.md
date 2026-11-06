# Data sources

One page per provider file (called a **feed**), 19 in all (the AD owner groups file added 6 Nov 2026; the DR tests file added 3 Nov 2026; owner, 2 Nov 2026: there is no incidents file and no client-issues file; UN-01 comes from the postmortem file, and UN-03, client incidents, is coming soon). Each page says what the file holds, its key, how every row is placed with a person, team and family, which metrics it feeds, who to contact, and its status.

**The provider's real file is the layout.** TRUST reads each file as the provider sends it, through the feed's **column map** (which real header gives each field TRUST needs). Where a page still lists a first-guess layout, the real file's header row replaces it. **Every file uploads on its own**: no feed needs any other feed to be loaded first. Real data is cleared to load (classification signed off 2 Nov 2026). **Provider contacts are placeholders** until the owner supplies the list.

**Data contracts (owner, 4 Nov 2026).** The website's **Data dictionary** page (Governance, everyone can see it) lists every feed with what it is, the columns TRUST reads, the metrics it feeds and the checks run on it. Anyone can ask to onboard a data source there; Tech Risk approves, and an approved contract is **formal**: TRUST may use the file only for the metrics the contract lists (any other metric that reads it shows No data with the reason until a new version is approved), and an upload whose columns differ from the contract gets a warning that must be acknowledged before the lock. A new version is asked for the same way. Stored in the `data_contract` table (migration 0009).

How the files flow into the numbers: [data flow per source](../architecture.md#per-source). What happens at upload and at scoring: [how a month works](../how-a-month-works.md).

| Feed | Provider | Metrics | Page |
|---|---|---|---|
| `hr` | HR | places items in families | [HR](hr.md) |
| `app_inventory` | Arch | TR-01; ITDR placement for RE-01, RE-03 and Tier 0/1 (owner, 6 Nov 2026). Places each confirmed app with a family (org hierarchy → HR Supervisory Organization, else its owners' family), finds its owners, links it to ITDR by name and to GitHub repos by service repo; the drill-down shows each item's app and owners. Later candidates (owner to decide): TR-03, UN-01 per 10 apps | [App inventory](app_inventory.md) |
| `app_owner_members` | Tech Risk (AD export) | Not scored: the members of app owner emails that are AD groups (nested groups included). Made by `tools/expand_owner_groups.ps1` | [AD owner groups](app_owner_members.md) |
| `hr_mapping` | Tech Risk | places people in product families: `product_line_owners.json` (`product_line`, `owner_email`, optional `band`; several leads per product line allowed) or the older CSV (`Product Family`, `Owner Email(s)`, `Band`); everyone under a lead in HR belongs to that family. Not used while `team_grouping` is `l3` (teams from HR level 3; owner, 3 Nov 2026) ([doc 13 §8](../../design/13_hr_dataset.md)) | [Product family owners](hr_mapping.md) |
| `repos` | Tech Risk (GitHub export) | TR-02 (scored from 4 Nov 2026): 5 hygiene checks per active repo, owner = the human with most of the last 20 commits, via HR (owner, 3 Nov 2026). Made by `tools/github_repo_export.py` | [GitHub repos](repos.md) |
| `tcc` | Change | TE-01, TE-02 | [TCC changes](tcc.md) |
| `ntcc` | Change | TE-06, not on the scorecard yet (owner, 2 Nov 2026: changes outside TCC are left out of TE-01). The file still uploads and is read ([doc 14](../../design/14_tcc_dataset.md#non-tcc-export-12-columns-r-tcc-13)) | [Non-TCC changes](ntcc.md) |
| `postmortems` | Ops | UN-02 (which incidents count); UN-01 (unique Critical and SWE `incident_id`s, owner 2 Nov 2026) | [Postmortems](postmortems.md) |
| `actions` | Ops | UN-02 | [Action items](actions.md) |
| `cx_sast` | Cyber | SE-01 | [Checkmarx SAST](cx_sast.md) (JSON) |
| `cx_sca` | Cyber | SE-02 | [Checkmarx SCA](cx_sca.md) (JSON) |
| `commits` | Change | TE-04 | [Commit counts (GHES)](commits.md) |
| `itdr` | ITDR | Which applications are Tier 0/1, for RE-01 and RE-03 (both scored from 4 Nov 2026) and RE-02 (planned: it needs test-plan dates). Excel, header over rows 1 and 2: `Ref`, `Application Name`, `Business Product Area`, `Recovery Tier`. Kept as the table `itdr_application` (owner, 3 Nov 2026) | [ITDR applications](itdr.md) |
| `dr_tests` | ITDR | Completed DR tests, for RE-01 and RE-03 (both scored from 4 Nov 2026): `Tier`, `Name`, `Business Area`, `ITDR Lead`, `Type of Test` (Open, Closed, TTX), `When`, `Status`, `Comments`. Kept as the table `dr_test`; linked to the ITDR applications by name (owner, 3 Nov 2026) | [DR tests](dr_tests.md) |
| `secrets` | Cyber | SE-03 | [Secrets findings](secrets.md) |
| `cyberark` | Cyber | SE-04 | [CyberArk accounts](cyberark.md) |
| `sailpoint` | Cyber | SE-05 | [SailPoint apps](sailpoint.md) |
| `hosting_eol` | Hosting platform | SE-06 | [Hosting platform components](hosting_eol.md) |
| `defects` | Tech Risk (Jira export) | TE-03 (planned) and delivery figures (shown, not scored): team = the person who closed the issue, via HR (owner, 3 Nov 2026). Made by `tools/jira_export.py` | [Jira issues](defects.md) |

Only the pages for `app_inventory`, `app_owner_members`, `repos`, `itdr`, `dr_tests` and `defects` are in this repo. The other pages in the table are kept outside this repo for now, so their links stay broken until they are copied in.

## Adding a source, or a provider's file changing

- [ ] **Header row.** Get the real file's header row (and a sample if useful). That is the layout.
- [ ] **Column map.** In `config/column_maps.json`, map each field TRUST needs to the real header (see [change a column name](#change-a-column-name)). Headers are matched case-insensitively and fuzzily anyway ([doc 17 §3](../../design/17_intake_architecture.md)); the map is for names too different to guess. Keep only the columns TRUST uses (D-83).
- [ ] **Intake.** Add a reader in `backend/trust/intake/` and register the feed in `backend/trust/store.py` (the feed list and the upload checks) and `backend/trust/mapping.py`. A **new** migration only if the feed needs its own table (never edit an applied one). Upload must not read any other feed.
- [ ] **Placing.** Decide how a row reaches a team and family at scoring (person to HR, or app to inventory, or repo to app) and what shows while those files are not loaded (Not yet mapped).
- [ ] **Page.** Update `docs/wiki/data-sources/CODE.md` and the table above.
- [ ] **Access.** If a role should see the new data differently, change `config/access.json` or `backend/trust/access.py`.
- [ ] **Commit** all of the above together.

## Change a column name

Every input file's column names (or JSON field names, for Checkmarx) are in one file you can edit: **`config/column_maps.json`**. It has an entry for all 19 feeds; feeds whose file hasn't arrived yet are empty. No code change is needed.

1. Open `config/column_maps.json`. Find the feed (for example `"hr"`) and the field TRUST needs (for example `"SAM_ACCOUNT"`).
2. Put the column name **exactly as it appears in the provider's file** first in the list. Keep the other names if you like; they are fall-backs.

   ```json
   "hr": {
     "SAM_ACCOUNT": ["Employee Login", "SAM_ACCOUNT"],
     ...
   }
   ```
   To match a column by **how its name ends**, start the name with `*`: `"*SAM_Acct"` finds `Worker_SAM_Acct` (and any other name ending in SAM_Acct, in any capitals). The HR file uses this: **the SAM column is the one whose name ends in `SAM_Acct`** (owner, 3 Nov 2026). If two columns end that way, neither is used and the upload result says so.
3. Save the file, then **upload the provider's file again** and map the month (`python manage.py map 2026-10`, or Update the scorecard on This month). The upload is needed because TRUST only keeps the columns it could find (owner, 2 Nov 2026); the same file is accepted again because the column map changed. The mapping result shows which column was used for each field.

Good to know:
- **Everything is case-insensitive**: the column names in the provider's file, the names you put in this file, and the feed and field names (`"hr"` or `"HR"`, `"SAM_ACCOUNT"` or `"sam_account"`). Spaces, underscores and dashes don't matter either (`Email - Work`, `email_work` and `EMAIL WORK` are the same). Close spellings are matched anyway and shown on the result, so you only need this file for names too different to guess.
- If TRUST can't find a column, the mapping result says so in plain words, names the field, and points to this file. The file still loads; only the metrics that need that field show No data.
- The file must stay valid JSON: names in double quotes, separated by commas. A trailing comma is fine. Keys starting with `_` (like `"_note"`) are notes for people and are ignored.
- The field names on the left (`"SAM_ACCOUNT"`, `"Worker"`, ...) are TRUST's own and must not be changed. Only the lists on the right are yours.

## What upload does with a file

Keep it, cut down to what TRUST uses. **Only what TRUST uses is kept** (owner, 2 Nov 2026): each file with a reader is cut down as it arrives to the columns (or JSON fields) TRUST uses; everything else is dropped and never stored. The hash of the file as received is still recorded. The HR file is cut down further, to the CTO and everyone reporting up to them (setting `hr_root_sam_account`); if that setting is empty or the person isn't in the file, nothing of it is kept. A file whose layout hasn't been given yet is kept as received until it has a reader. **A column TRUST couldn't find was dropped**, so after fixing its name in the column map, upload the file again (the upload result lists what wasn't found). A file with the same contents again (and the same column map) is "already received"; a different file for the same feed and month replaces it (both kept).

**Checked at upload, on its own** (owner, 3 Nov 2026): each file is read with its own feed's reader the moment it arrives, with no other file needed (`backend/trust/checks.py`). **Junk is refused and not stored**: a file that can't be read, that doesn't look like this feed's file (most of the fields TRUST needs aren't in it), where every row is unusable, or an HR file with nobody in the CTO's line. The attempt is logged with the reasons. Everything else is stored, with any warnings shown straight away; each warning must be acknowledged on This month before the month can be locked. A real file with no rows this month is kept, with a warning.

## What mapping does with a file

Mapping reads the kept files, and can be re-run at any time:

- Delimiter detected (comma, semicolon, tab, pipe); quoted fields may hold the delimiter.
- Headers matched to the column map: case-insensitive, then fuzzy; every fuzzy match is shown on the result.
- A field TRUST needs that the file does not have: the file loads, and only the metrics needing it show **No data**, with a note naming the field.
- Dates read the same way in every file: whatever format the file uses, fractions of a second of any length, `Z` as UTC, no timezone as New York. A date that can't be read is left blank and noted; the row still loads.
- Numbers read with or without thousands separators or a % sign.
- A row without its key is set aside and listed; the rest loads.
- Nothing about any other feed is checked.
