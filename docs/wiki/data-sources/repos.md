# GitHub repos (feed `repos`)

**Provider:** Tech Risk, from GitHub Enterprise Server. **File:** CSV made by `tools/github_repo_export.py`. **Owner decisions, 3 Nov 2026.** Feeds TR-02, **scored from 4 Nov 2026** (owner; switched on in `config/thresholds.json` `switched_on`), and places Checkmarx repos with families (SE-01, SE-02).

## Making the file

Run `python tools/github_repo_export.py`. It uses `tools/github_client.py`, which reads two settings from the computer it runs on: `GITHUB_HOST` (the server, e.g. `github.yourcompany.com`) and `GITHUB_TOKEN` (a token with `repo` and `read:org`); `GITHUB_CA_BUNDLE` if the company certificate isn't trusted. `python tools/github_client.py` checks the connection. GitHub allows a set amount of API use per hour; when it runs low the export waits for the hourly reset and carries on by itself (leave the window open). `ORG` in the script says which orgs: blank = every org the token's account belongs to (Repo then reads `org/repo`), one name = just that org, or a list of names. It writes `repos.csv`: one row per repo, with the main branch's protection settings as GitHub has them (branch protection and rulesets combined) and the recent human committers. Upload it on Data sources. If your GitHub version rejects `rulesets`, set `INCLUDE_RULESETS = False`; if the query times out, lower `PAGE_SIZE`.

The export only reports settings. **TRUST decides what passes**, so the rules can change without exporting again.

## Columns

`Repo`, `Url`, `Archived`, `Fork`, `Empty`, `DefaultBranch`, `PushedAt`, `LastDefaultBranchCommit`, `ProtectionSource`, `BranchProtected`, `RequiredApprovals`, `LastPushApprovalRequired`, `ForcePushAllowed`, `DeletionsAllowed`, `AdminEnforced`, `BypassAllowed`, `StaleReviewsDismissed`, `CodeOwnerReviewRequired`, `StatusChecksRequired`, `CodeOwnersFile`, `LastHumanCommitterEmail`, `LastHumanCommitterLogin`, `LastHumanCommitDate`, `TopCommitterEmail`, `TopCommitterLogin`, `TopCommitterShare`, `HumanCommitsSampled`. Names and values are read in any capitals; true/false as True, yes, 1 and so on.

## What TRUST does with it

- **Hygiene checks (one point each):** main branch protected; review required (1 or more approvals); independent approval (the last push approved by someone else); history can't be rewritten (no force push, no deletion); no one can skip the rules (admins held to them, no bypass). Checks 2 to 5 need the protection, so an unprotected repo scores 0 of 5. A blank setting counts as not set and is listed. Shown, not scored: CODEOWNERS file, required status checks, stale approvals dismissed.
- **Active:** not archived, not a fork, and a push or main-branch commit in the 90 days before the end of the month (setting `repo_active_days`).
- **Owner and family:** the human with the **most of the last 20 main-branch commits**, a tie going to the most recent (owner, 3 Nov 2026; setting `repo_owner_rule` `most_commits`; `last_commit` = the last human committer instead). Found in HR by **email address only**: the commit's email must match the person's HR work email (owner, 4 Nov 2026; setting `repo_match_by` `email`; `email_then_login` also tries GitHub login = SAM_ACCOUNT). Then the nearest family owner above them. No match, or no human committer: **Not yet mapped** (shown, never scored). The upload and mapping notes say why repos have no human committer (empty, archived, forks, or only bots in the last 20 commits) and give the first 5 names with "and N more". Bots and service accounts are never owners. Anyone who owns 20 or more active repos is listed for a check (setting `repo_owner_flag_count`).
- **Family figure:** checks passed ÷ checks possible across its active repos, with the count of repos failing each check and the list of repos with no main-branch protection (family page only, not the CTO view).
- **Checks at upload:** junk is refused; everything listed above is a warning, acknowledged before the lock.

## Open

- TR-02 switched on (owner, 4 Nov 2026): judged against the median family (needs 5 families with a result); each repo shows on the family page as '4 of 5 checks' with the checks it fails, and repos with an unprotected main branch are named. To switch off: remove `TR-02` from `switched_on` in `config/thresholds.json`.
- Which source platforms are in scope (OD-10). TR-01 (repo to application) comes from the app inventory's service repos (owner, 6 Nov 2026; [app inventory](app_inventory.md)).

## Checkmarx repos take their GitHub repo's family (owner, 4 Nov 2026)

When the month has both the GitHub repo file and a Checkmarx SAST or SCA file, each Checkmarx repo is matched to a GitHub repo and takes that repo's family, so SE-01 and SE-02 can score per family. The match is tried in this order: the **same full name**; the **same repo name** after the last `/` (Checkmarx's `leading/reponame` finds GitHub's `org/reponame`); a **close spelling** of the repo name at setting `checkmarx_match_min` (0.9; case and punctuation are always ignored, and the numbers in the name must be the same). A repo name shared by several GitHub repos is matched on the leading part if that settles it, otherwise left unmatched: never guessed. The mapping result lists how many matched each way, every close match with its score, the unmatched names, and matched repos whose GitHub owner has no family. Upload both files for the month, then **Update the scorecard**.
