# HR dataset — input file and how it maps (1 Nov 2026, updated 2 Nov 2026)

Status: **owner answers applied (1 Nov 2026), D-79; changed 2 Nov 2026 (owner): the HR file is firm-wide, and only the CTO and everyone reporting up to him is loaded (§3).** Feeds `snapshot` (kind = hr), `hr_mapping` (11 §1), `hr_membership` and `app_user.employee_id` (10 §9). The original file stays on SharePoint (D-97). Only the columns marked *Load*, for people in the CTO's reporting line, go into the database.

The HR file uploads on its own, with no other file present (DEVELOPER_GUIDE.md rule 0).

## 1. Fields

The provider's real file is the layout (doc 17 §3). These are the 22 columns as the owner described them; the feed's column map is written from the real header row, and headers are matched case-insensitively and fuzzily. A field TRUST needs that is not in the file is a note naming the field; the file still loads.

| # | Field | Format | Use | Load? |
|---|---|---|---|---|
| 1 | Worker | name text | Display name. Also the name to match when resolving manager names (§4) | Load |
| 2 | Email - Work | first.last@company.com | **Join key to provider files** (owner: "common value to link the datasets"). Stored lower-case | Load |
| 3 | Length of Service - Worker - By Tenure Category | 6 bands | Not needed | No |
| 4 | Time in Job Profile | "X year(s), X month(s), X day(s)" | Not needed | No |
| 5 | Workers Manager | name text, same format as Worker | Manager link, resolved to the manager's own row (§4) | Load (resolved to an ID) |
| 6 | Supervisory Organization | "SupOrg Name (Manager Name)" | Team label shown on pages; cross-check for #5. **Also places app inventory apps** (owner, 6 Nov 2026): the second part of an app's `app_org_hierarchy` is matched to the name without "(Manager Name)", and the app goes to the family most of that organization's people are in ([app inventory](../wiki/data-sources/app_inventory.md)) | Load |
| 7 | Top Level Supervisory | "TopSupOrg Name (Manager Name)" | Groups teams on the mapping template; tie-break (§4). | Load |
| 8 | Executive Level Supervisory | e.g. "Technology (Manager Name)" | Tie-break and a cross-check note (§5) | Load |
| 9 | Department | text | **Sub-team label on family pages and in the drill-down** (owner, 3 Nov 2026), chosen by the setting `subteam_hr_column` (Department, or Supervisory Organization). **Also places ITDR applications** (owner, 3 Nov 2026): an application whose Business Product Area matches a Department (exactly, or closely enough for the setting `area_match_min`) goes to the family most of that department's people are in; a tie places nothing and is listed | Load |
| 10 | Worker Type | Employee / Contingent | Shown in the access review | Load |
| 11 | Position Worker Type | 8 values (Regular, Agency contractor, …) | Shown in the access review | Load |
| 12 | Location Address - Country | e.g. United States of America, United Kingdom | **Kept for now (owner, 3 Nov 2026), for the EU regulatory impact assessment; technology (the CTO's line) only; shown nowhere yet. See §10.** UK and EU rows are personal data under GDPR, so the aim is to replace it with a per-team summary | Load (temporarily) |
| 13 | Time Type | Full / Part time | Not needed | No |
| 14 | SBU | "(number) SBU name" | Not needed for v1 | No |
| 15 | Is Manager | Yes / blank | Cross-check (§5) | Load |
| 16 | Number of Direct Reports | number | Cross-check: should equal the direct reports we resolve (§5) | Load |
| 17 | VP or Higher | Yes / blank | Possible source for leadership access (O-4). Owner to decide later | Load (flag only) |
| 18 | Is VP | Yes / blank | Not needed beyond #17 | No |
| 19 | Is SVP/EVP | Yes / blank | Not needed beyond #17 | No |
| 20 | Management reporting level from top | number | Tie-break (§4) | Load |
| 21 | organization level from top | number | Not needed | No |
| 22 | SAM_ACCOUNT | unique employee ID | **Primary key** | Load |

15 of the 22 columns are loaded (13, plus Department and, temporarily, Country, from 3 Nov 2026), and only for people in the CTO's reporting line. Yes/No-style values are read in any case (Yes, Y, TRUE, 1).

## 2. Keys

- **Which column:** in the real file, the SAM column is **the one whose name ends in `SAM_Acct`** (owner, 3 Nov 2026; `"*SAM_Acct"` first in `config/column_maps.json`). It is used for every match to a person (mapping, family leads, the add-on's `user_id`), never Employee ID.
- **Person** = `SAM_ACCOUNT`, compared case-insensitively (AD account names are case-insensitive).
- **Access** is handled by the company's add-on container in front of TRUST, **not Entra** (owner, 2 Nov 2026). TRUST has no sign-in of its own. The add-on identifies each person by **`user_id`, which is their SAM_ACCOUNT** (owner, 2 Nov 2026). So anyone signed in can be matched to their row in HR (case-insensitive), and from there to their family, if per-person views are wanted later.
- **Sub-team** = the value of the HR column named by the setting `subteam_hr_column` (owner, 3 Nov 2026: Department for now; Supervisory Organization also works). It groups a family's people on family pages and in the drill-down.
- **Email** = second key, used to attribute provider items to a person and so to a team.

## 3. Firm-wide file, CTO's reporting line only (owner, 2 Nov 2026)

The HR file is the **whole firm**. TRUST keeps only the CTO and everyone who reports up to him, directly or through any number of managers.

- **Setting `hr_root_sam_account`** holds the CTO's SAM_ACCOUNT. Tech Risk sets it (and changes it if the CTO changes). It is matched case-insensitively.
- At load, TRUST finds that person in the file, then walks **down** the manager links (§4) and keeps every row it reaches. Everyone else in the file is **not loaded**: not stored, not shown, not counted (data minimisation).
- The CTO's row is the top of the chain; whoever the CTO reports to is not needed.
- **The upload result says** how many rows were in the file, how many were kept under the CTO, and how many were left out (and the same notes as mapping, e.g. unresolved manager names).
- **If the setting is empty, or that SAM_ACCOUNT is not in the file:** the upload is recorded but nothing of the file is kept, and the result says plainly "set the CTO's SAM_ACCOUNT (`hr_root_sam_account`) and upload the file again" or "SAM_ACCOUNT xxx is not in this file". Nothing else is affected.
- **The file is cut down at upload (owner, 2 Nov 2026).** Only the kept people and the 15 loaded columns are stored; everyone else in the firm, and the 7 columns not loaded, are never stored. The hash of the file as received is still recorded (to match the SharePoint original). So **changing the CTO setting, or fixing an HR column name in the column map, needs the HR file uploaded again**: the people and columns that weren't kept can't be recovered from the store.
- If the setting is empty, or that SAM_ACCOUNT isn't in the file, **nothing** of the file is kept; the upload says so.

## 4. Manager link (resolve by name within the file)

Every manager has their own row in the file (owner confirmed). So `Workers Manager` is matched to `Worker`, and that row gives the manager's SAM_ACCOUNT and email. The match is done across the **whole file** before the CTO filter, so links through any part of the firm resolve; then only the CTO's line is kept.

1. **Match:** exact after trimming spaces and ignoring case.
2. **If two or more people share the name** (more likely firm-wide): keep only the candidates whose reporting level (#20) is one above the worker's and who sit in the same Top Level Supervisory (#7), then the same Executive Level Supervisory (#8). The match stands only if exactly one candidate remains.
3. **Cross-check:** the resolved manager's name should appear in the "(Manager Name)" part of the worker's Supervisory Organization (#6). A mismatch is a note, listed.
4. **Anything unresolved** (no match, or still more than one candidate): that person's link stops there, so they and anyone under them are not reached from the CTO and are not loaded. They are **listed on the upload result** (name and SAM_ACCOUNT only) so Tech Risk can raise them with HR. Nothing is guessed.

## 5. Checks at upload (this file only)

| Check | Result |
|---|---|
| Fields TRUST needs found (case-insensitive, fuzzy header match) | Note naming any not found |
| `hr_root_sam_account` set and found in the file | If not: file recorded, no people loaded, plain note (§3) |
| SAM_ACCOUNT blank | Row set aside, listed |
| SAM_ACCOUNT duplicated | Both rows set aside, listed (a person must be one row) |
| Email blank or malformed, for a kept person | Note per row: the person is kept, but their provider items can't be placed and show as Not yet mapped |
| Email duplicated among kept people | Note, listed; the first is used |
| Manager name doesn't resolve (§4) | That branch is not reached from the CTO; listed |
| A loop in the manager chain | The loop is broken where it is found; listed |
| Resolved manager matches the "(Manager Name)" in Supervisory Organization (the person's own name also counts, for team leads) | Note, listed |
| Resolved direct-report count = `Number of Direct Reports` | Note, listed |
| `Is Manager` = Yes exactly when direct reports > 0 | Note |
| People whose Executive Level Supervisory names the CTO's organisation but who were not reached from the CTO | Note with the count and list (likely a broken manager link) |
| Number kept vs last month's HR file (when that month is loaded) | Note when the change is above the setting (catches a partial extract) |

The direct-report cross-check gives auditors an independent check that the hierarchy was rebuilt correctly. Placing people with families (the product family owners file, §8) happens at mapping, not upload; anyone not placed shows as Not yet mapped.

## 6. Effect on earlier designs

- 10 §8 "Contractors without employee IDs": **replaced**. Contingent workers have a SAM_ACCOUNT (owner confirmed). They take part like employees.
- 10 §9.3 `hr_membership.team_key` = the nearest mapped manager in the chain, walked using the resolved manager links.
- 11 §1 `hr_mapping`: **replaced by the product family owners file** (§8). Families are no longer mapped team by team; each family names its owners, and everyone under an owner belongs to that family.
- 11 §11 `app_user`: no sign-in in TRUST (access is the company's add-on container, owner 2 Nov 2026). If people are matched to roles later: the add-on's `user_id` = SAM_ACCOUNT, matched case-insensitively.
- New setting `hr_root_sam_account` (text, no default; Tech Risk sets it).
- Replaced: the earlier "file must be Technology only" check (FAIL) and "exactly one root" check. The CTO setting defines the scope instead.

## 7. Owner answers

1. Manager link: map `Workers Manager` to `Worker`; every manager has their own row. → §4.
2. ~~Entra employee-ID claim = SAM_ACCOUNT~~: **replaced 2 Nov 2026**: access is not Entra; the company's add-on container handles it, and identifies people by `user_id` = SAM_ACCOUNT.
3. Scope (changed 2 Nov 2026): the file is **firm-wide**; keep the CTO (set by SAM_ACCOUNT) and everyone reporting to him. → §3.
4. Contingent workers have a SAM_ACCOUNT: **yes**. → §6.
5. Column names and formats: as described in §1; the real file is the layout.

Left for later (not blocking): whether "VP or Higher" grants leadership read access (O-4).

**To do when moving to the real file:** `SAM_ACCOUNT` (and possibly other columns) is not the exact column name in the real HR file. Put the real names in `config/column_maps.json` under `"hr"` ([how](../wiki/data-sources/README.md#change-a-column-name)) and check the upload result shows every field found.

## 8. Product family owners file (owner, 2 Nov 2026)

This is how people are placed with product families. It replaces the team-to-family mapping template.

**The file** (feed `hr_mapping`, uploaded by Tech Risk on its own like every feed) is **`product_line_owners.json`** (owner, 3 Nov 2026) or the older CSV; both work.

```json
[{"product_line": "Payments", "owner_email": "alex.moreno@example.com"},
 {"product_line": "Payments", "owner_email": "sam.lee@example.com"},
 {"product_line": "Cloud platform", "owner_email": "dana.cto@example.com", "band": "platform"}]
```

- **More than one lead** (owner, 3 Nov 2026: some product lines have several): repeat the product line with each lead, or give `owner_email` as a list or comma-separated. The leads are combined.
- **`band`** is optional: `product` when missing, with no note.
- At upload the JSON is turned into the CSV's three columns below, so everything after that is the same.

The CSV: one line per product family.

| Product Family | Owner Email(s) | Band |
|---|---|---|
| Payments | alex.moreno@example.com, sam.lee@example.com | product |
| Cloud platform | dana.cto@example.com | platform |

- **Owner Email(s):** one or more work emails, **comma-separated in the one cell** (semicolons work too).
- **Band:** `product` or `platform`, as on the prototype's screens (9 product families, 4 platform ones). Any case. Blank is read as `product`; any other word is read as `product`, with a note.
- Column names come from `config/column_maps.json` (`"hr_mapping"`), matched case-insensitively and fuzzily.

**How people are placed** (at mapping, `linking.families_from_owners`; **confirmed by the owner, 2 Nov 2026**):

1. Each owner email is found in HR (`Email - Work`).
2. A person belongs to the family of **the nearest owner above them, or themselves**, walking up the manager chain. A family owner inside another family's tree starts their own family from there down.
3. Every provider row then follows its person: an action's assignee email, a change's Author email → that person → their family.

**What is never guessed** (each shows as Not yet mapped, with a note):

- An owner email that isn't in HR (or isn't in the CTO's line).
- A person with no family owner above them.
- A family with no owner email: nobody can be placed in it yet.
- (Not a problem: the same family on several lines, one per lead. Its leads are combined, with no note.)

**A lead of several families (owner, 6 Nov 2026).** When one person is listed as the lead of two or more families, the people under them count for **each** of those families: whoever is listed as the lead is what the data rolls up to, so the same numbers show for each family until the data is made more granular. How it works: those people are placed in one shared group (`shared:` + the family ids), and at scoring every one of the lead's families gets the group's results added to its own (`score_month.expand_shared`). The firm counts the group **once**, so firm results don't change. Rows that already say which family they belong to stay with that family only (for example an ITDR application whose Business Product Area is the family's name), so those families can still differ. Each family is counted in the prevailing median, so a lead of three families counts three times there. The mapping result has a "For information" note naming the lead and their families (nothing to acknowledge).


### Reporting on level-3 teams instead (owner, 3 Nov 2026)

The scorecard normally reports on **product families** from this file. For now the owner may also run it on **HR teams**: setting **`team_grouping`** in `config/settings.json`, `product_family` (the default) or `l3`.

- **`l3`:** every person whose `Management reporting level from top` is **3** (setting `l3_level`) leads a team named after them, and everyone reporting up to them is rolled into it (`linking.families_from_level`). The owners file isn't used while this is on.
- **Not yet mapped:** people above level 3 (the CTO and their direct reports), and anyone with no level-3 person above them, are listed on the mapping result and Firm position, never scored.
- Two level-3 leads with the same name are kept apart (their SAM_ACCOUNT is added).
- Each month's mapped result records which grouping it used (`team_grouping`), so a locked month shows how it was grouped.
- To switch: change the setting, deploy, then Update the scorecard. Nothing is uploaded again.

## 9. Build notes

- Reader: `backend/trust/intake/hr.py`, `read(file_bytes, hr_root_sam_account)`; `minimise(...)` cuts the file down at upload (called by `store.upload`). Column names from `config/column_maps.json` (`"hr"`), with built-in defaults as fall-back. Tests: `tests/test_hr.py` on a made-up firm-wide file (`tests/fixtures/hr_firmwide.csv`).
- Family owners: `backend/trust/intake/families.py` (reader) and `backend/trust/linking.py` `families_from_owners` (placing). Tests: `tests/test_families.py` (`tests/fixtures/family_owners.csv`) and `tests/test_upload_then_map.py`.
- Returns only the kept people, with the 15 loaded fields plus `manager_sam`; columns not loaded are never returned.

## 10. Follow-up: country data and EU regulatory impact (owner, 3 Nov 2026)

**Decision (built 3 Nov 2026).** Keep `Location Address - Country` for now, so Tech Risk can assess the impact of EU regulations. **Technology only:** the column is kept for the CTO's line, like everything else in the HR file; the rest of the firm is still never stored.

**Why it is temporary.** A named person's country is personal data, and the UK and EU rows fall under GDPR. TRUST needs the picture per team ("Payments: 70% US, 20% UK, 10% Germany"), not who sits where. So the plan is to **decouple country from the HR file**:

1. **Ask HR for a per-team summary instead of person by person**: one row per team and country, with a headcount or percentage. It becomes its own small feed, uploaded and checked on its own like every other source; TRUST stops keeping country per person once it arrives.
2. **Small-number suppression.** On a small team, "1 person in Germany" points to someone. Ask HR to suppress or round counts below about 5 (for example "fewer than 5").
3. **Team names must match.** HR's teams in the summary must use the same column TRUST uses for sub-teams on family pages (owner choosing it: Department, Supervisory Organization or another HR column), or TRUST can't join the summary to families. Settle the sub-team column first, then make the request to HR.

**Owner to follow up:**

- [ ] Which EU regulations are in scope (for example DORA or NIS2), and whether the assessment needs the country of the **people**, of the **teams**, or of the **systems and data** (those are different sources).
- [ ] Whether the country view appears on the scorecard, or is for Tech Risk's assessment only.
- [ ] Choose the sub-team column (above).
- [ ] Request the per-team country summary from HR, with small-number suppression and the same team names.
- [ ] Record the temporary per-person retention and its end (when the HR summary arrives) as a decision, with its purpose.

**Built (3 Nov 2026):** the Country column is kept in the HR cut-down (CTO's line only) and on each person in the mapped month (`country`); it is shown nowhere yet, until the owner decides where. **Still to do** when the HR summary feed arrives: add a reader for it and drop the per-person column.

