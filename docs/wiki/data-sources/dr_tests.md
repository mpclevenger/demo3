# DR tests (feed `dr_tests`)

**Provider:** ITDR. **File:** Excel (`.xlsx`) or a CSV export. **Layout from the owner, 3 Nov 2026.** One row per DR test or tabletop exercise.

## What the file looks like

| Column | What's in it |
|---|---|
| Tier | As in the [ITDR application file](itdr.md): Tier 0 to Tier 5, or TBC. |
| Name | The application's name, as in the ITDR application file. |
| Business Area | Not always filled in. |
| ITDR Lead | Who led the test. |
| Type of Test | Open = a DR test in production (live). Closed = a DR test that doesn't touch production (UAT, test). TTX = a tabletop exercise, which is **not** a DR test (owner, 3 Nov 2026). |
| When | MM/DD/YYYY. The date of a tabletop exercise. |
| Status | Successful, or blank. Blank means it hasn't been performed (owner, 3 Nov 2026). |
| Comments | Usually "DR Test completed on 14th March 2026" (sometimes a capital C): the last time the DR test was performed (owner, 3 Nov 2026). Some say "TTX: Tabletop exercise completed". |

The column names (and close spellings) are in `config/column_maps.json` under `dr_tests`. A one-row or two-row header both work.

## What TRUST does with it

- **Name.** Tidied like the ITDR file (extra spaces and line breaks). Blank: the row is set aside.
- **Tier.** Read like the ITDR file; blank or not a tier is kept as **Not given** and listed.
- **Type of Test.** Open and Closed are **DR tests** (production, and UAT or test); TTX is a **tabletop exercise**, kept apart and never counted as a DR test. Any case is fine. Anything else, or a blank, is kept as written, listed, and counted as neither.
- **When.** Read as MM/DD/YYYY (an Excel date works too). Not a date: listed.
- **Status.** Successful in any case. Blank is **Not performed**. Anything else is kept as written, listed, and not counted as performed.
- **When it was last performed** (only when Status is Successful): a DR test from the date in its comment ("completed on 14th March 2026"), a tabletop exercise from When. A successful DR test with no date in its comment, or a successful tabletop exercise with no When, is listed.
- **Listed for a look:** a blank Status with a comment saying completed; a Type of Test that disagrees with the comment (a DR test whose comment says TTX, or the other way round).
- **Kept as a table.** At upload, the tests go into the table `dr_test`, tied to the upload. A new file for the month becomes the current list; the earlier one is kept.
- **Linked to the ITDR applications** when both files are loaded for the month (each still uploads on its own). The link is by name, ignoring case and extra spaces. A near spelling isn't guessed: names not found in the ITDR file are listed, and so are tests whose tier differs from the ITDR file. **The ITDR application file's tier is always used** (owner, 4 Nov 2026); this file's Tier is read and checked, never used for scoring.
- **Checks.** Junk is refused; everything listed above is a warning, acknowledged before the month is locked.

## What it feeds

**RE-01 is scored from it too (owner, 4 Nov 2026):** Tier 0 and 1 applications with a completed **DR test** (Status Successful, completion date in Comments) in the 12 months to month-end; tabletops don't count. Prevailing median. (RE-01 was BIA completion; ITDR has no BIA date.)

**RE-03 is scored from it (owner, 4 Nov 2026; switched on in `config/thresholds.json` `switched_on`):** an application in the ITDR application file at Recovery Tier 0, 1 or 2 passes when this file has a successful DR test (Open or Closed) or a successful tabletop exercise for it, dated in the 12 months to month-end (a DR test's date = the date in its comment; a tabletop's = When). Family = the application's Business Product Area. Judged against the median family (needs 5 families with a result). Needs both files for the month.

## Open

- **Follow-up (owner, 4 Nov 2026):** the DR tests file has its own Tier column, which sometimes disagrees with the ITDR application file. TRUST always uses the **ITDR application file's tier**; every difference is a warning on the mapping result (acknowledged before the month is locked). Ask ITDR to line the two files up, and decide with them which file is the source of truth for a tier.
- Answered (owner, 3 Nov 2026): TTX is not a DR test; a blank Status means not performed; a DR test's last date is in its comment, a tabletop exercise's is When.
- Each test also gets its application's family through the ITDR link (when the application's Business Product Area matches a family). A name on two ITDR rows isn't guessed.
- For RE-03 (scored): whether a Closed (non-production) DR test counts the same as an Open (production) one, and whether tabletop exercises are shown alongside.
