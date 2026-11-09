# ITDR applications (feed `itdr`)

**Provider:** ITDR. **File:** Excel (`.xlsx`); a CSV export of the same sheet also works. **Layout from the owner, 3 Nov 2026.**

## What the file looks like

The header is merged over rows 1 and 2. From row 3, one row per application:

| Column | Name | What's in it |
|---|---|---|
| A | Ref | A number: the register's own id for the application. |
| B | Application Name | Free text. Not always clean. |
| C | Business Product Area | Not always filled in. |
| D | Recovery Tier | Tier 0, Tier 1, Tier 2, Tier 3, Tier 4, Tier 5 or TBC. Tier 0 is the most critical, Tier 5 the least. |

Other columns are dropped at upload. The column names (and close spellings) are in `config/column_maps.json` under `itdr`.

## What TRUST does with it

- **Header.** Rows 1 and 2 are read as one header when that finds more of the expected columns than row 1 alone; otherwise row 2 is data. So a file sent with a one-row header still works.
- **Ref.** Blank, not a number, or already used on an earlier row: the row is set aside with the reason (the first row with a Ref is kept). Excel's `12.0` reads as 12.
- **Application Name.** Extra spaces, line breaks and non-breaking spaces are tidied; nothing else is changed. Blank: the row is set aside. Two Refs with the same name are both kept and listed.
- **Business Product Area.** Blank is kept as blank and counted, for information only: an application the [app inventory](app_inventory.md) places doesn't need an area (owner, 6 Nov 2026). The warnings about blank or unmatched areas are written during the update, after the inventory has placed what it can, so they list only the applications still not placed.
- **Recovery Tier.** Read loosely (`Tier 1`, `tier1`, `T1`, `1`). `TBC` (or TBD) stays TBC. Blank, or anything that isn't a tier (for example "Tier 6"), is kept as **Not given** and listed by Ref. Never guessed.
- **Kept as a table.** At upload, the applications go into the table `itdr_application` (one row per application, tied to the upload). A new file for the month becomes the current list; the earlier one is kept. Without a database they are kept next to the file in `store/`.
- **Family** (owner, 3 Nov 2026). At mapping, when the product family owners file is loaded, Business Product Area places the application:
  1. if it is a family's name, with that family;
  2. if it is an HR **Department**, with the family **most of that department's people** are in (a tie places nothing and is listed).

  The names won't always match exactly, so TRUST compares them ignoring case, spaces, punctuation and word order, and allows shortened and misspelt words ("Retail Bankng Tech." matches "Retail Banking Technology" at 0.94). An exact match wins; otherwise the closest name scoring at least the setting **`area_match_min`** in `config/settings.json` (0.85 to start; 1.0 = exact only; lower = looser) is used. **Every close match is listed with its score** on the result so it can be checked. A missing or extra word lowers the score ("Payments" against "Payments Operations" is 0.62), so those aren't matched at 0.85. Two names for different families scoring within 0.02 of each other are too close to call: nothing is chosen and it is listed. Blank areas, and areas not close enough to anything, are listed too. The DR tests for an application take its family.

  **The app inventory comes first (owner, 6 Nov 2026).** When the [app inventory](app_inventory.md) is loaded, an application linked to an inventory app by name takes **that app's family** instead; one not linked keeps its Business Product Area's family. Every application that changes family is listed (acknowledged before the lock), and so is one linked to apps in different families (it keeps its area's family). Its DR tests and the family's Tier 0/1 status follow. Setting `itdr_family_from_inventory` false goes back to Business Product Area only.
- **Checks.** Junk is refused (not an Excel or CSV file, none of the columns, every row unusable). Everything above is shown as a warning at upload and must be acknowledged before the month is locked.

## What it feeds

It gives the applications RE-03 is measured on (owner, 4 Nov 2026): every application at Recovery Tier 0, 1 or 2, placed with a family by its Business Product Area; see [DR tests](dr_tests.md). RE-01 (Tier 0 and 1, DR tests only) is measured on it too. RE-02 is still planned (it needs test-plan dates, which neither file has).

**It is the only source of a tier** (owner, 4 Nov 2026). The Resiliency row on each family page says how many of its applications are Tier 0/1 ("2 Tier 0/1 apps out of 9 apps"; not in the header under the family name). A family with no Tier 0 or 1 application is **Not Tier 0/1**: its Resiliency block is not scored (see [scoring rules](../scoring-rules.md)).

## Open

- The owner is updating the Business Product Areas so each one is close to a family name or an HR Department. Check the close matches listed after the first real upload, and raise or lower `area_match_min` if needed.
- **Follow-up (owner, 4 Nov 2026):** the DR tests file has its own Tier column, which sometimes disagrees with the ITDR application file. TRUST always uses the **ITDR application file's tier**; every difference is a warning on the mapping result (acknowledged before the month is locked). Ask ITDR to line the two files up, and decide with them which file is the source of truth for a tier.
- A family whose applications aren't placed (Business Product Area not matched) shows as Not Tier 0/1. Check the not-placed list before locking a month.
- The test-plan date that RE-02 needs is not in this file (RE-02 is planned). Completed tests come from the [DR tests file](dr_tests.md).
