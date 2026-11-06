# Jira issues (feed `defects`)

**Provider:** Tech Risk, from Jira Data Center. **File:** `jira_issues.csv`, made by `tools/jira_export.py`. **Owner decisions, 3 Nov 2026.** Feeds TE-03 Defect rate (planned, not scored yet) and the delivery figures (shown, not scored).

## Making the file

1. Set two environment variables: `JIRA_URL` (your Jira's address, e.g. `https://jira.yourco.com`) and `JIRA_TOKEN` (your personal access token). For Jira Cloud, also set `JIRA_EMAIL` and add `--cloud`.
2. Run `python tools/jira_export.py --jql 'project in (PAY, TRD) AND updated >= "2026-07-01"'`. JQL is Jira's search language: put in it the projects you want. Pull a little more than the month, so issues created earlier and closed this month are in it.
3. Optional: `--defect-types` (default `Bug,Defect`), `--story-points-field`, `--severity-field` and `--env-field` (the custom-field IDs for story points, severity and the environment a defect was found in; every Jira numbers them differently).
4. It writes three files to `jira_out/`. **Upload `jira_issues.csv`** on Data sources, feed "Jira issues". The other two (`jira_transitions.csv`, every status change; `jira_monthly_summary.csv`) are for your own checks; TRUST doesn't read them.

The export only reports what Jira has. **TRUST works out the figures from the dates**, so the rules can change without exporting again.

## Columns

`issue_key`, `project`, `issue_type`, `is_defect`, `priority`, `severity`, `found_in_env`, `status`, `status_category`, `resolution`, `created_at`, `first_in_progress_at`, `resolved_at`, `closed_by`, `closed_by_email`, `closed_by_username`, `reopen_count`, `story_points`. Other columns in the file (summary, assignee, the export's own lead times) are dropped at upload. Names are read in any capitals.

## What TRUST does with it

- **Who owns an issue:** the team of the **person who closed it** (the last move into a Done status), not the assignee (owner, 3 Nov 2026). If a defect is reopened and someone else closes it, the second person owns it. Found in HR by work email, then Jira username = SAM_ACCOUNT; then the nearest family owner above them. No match: **Not yet mapped** (shown, never scored).
- **Defect:** `is_defect` from the export; when it is blank, issue type Bug or Defect.
- **For each family, issues closed in the month:** issues closed, defects closed, defects reopened at least once, story points closed, median lead time (created to closed), median cycle time (first In Progress to closed) and median days to fix a defect.
- **Firm-wide** (nobody has closed these yet, so no team): defects opened in the month, and defects open at month-end.
- **Checks at upload:** junk is refused (not a Jira issues file, every row unusable). Warnings, acknowledged before the lock: rows with no or a repeated `issue_key`, dates that aren't dates, closed issues with nobody recorded as closing them, a month with nothing closed.

## Open

- Switching TE-03 on as a scored metric (owner decision). Before that: which defects count as **production** defects (the environment field or a label), and whether a defect counts in the month it was raised or closed. The denominator is TCC production releases.
- Which delivery figures, if any, go on the scorecard (adding a metric is an owner decision).
