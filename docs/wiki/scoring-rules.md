# Scoring rules in plain words

How a number becomes a colour, a building block score and a TRUST score. (A building block is a group of related metrics that answers one question, such as "Can we recover critical systems?". Owner, 4 Nov 2026: an earlier five-group scheme was replaced by six building blocks. Metric IDs such as TR-01 and SE-06 did not change.) Each rule names the decision that set it (D-nn, in ARCH_REVIEW §6, kept outside this repo). Where a number is a setting, it is in `config/thresholds.json` (the `settings` page is kept outside this repo).
The code is in `backend/trust/`: `scoring.py` (blocks, caps, TRUST), `score_month.py` (judges each metric and scores a month), `measure.py` (counts per family), `calibrate.py` (sets thresholds) and `publish.py` (change arrows, trends and the watch list).

**Every month stands alone (owner decision, 2 Nov 2026).** Any month can be loaded and scored on its own, in any order, with whatever files have arrived. Nothing is refused because an earlier month, an earlier quarter or another file is missing. History only adds extras (change arrows, trends, Chronic Red); when it is not there, those extras are simply not shown.

**Vocabulary.** A metric has a *tolerance threshold*: a **Green tolerance** (the edge of Green) and a **Red limit** (the edge of Red). Amber is in between.

## Statuses of one metric for one family

The first rule that applies decides, in this order (`backend/trust/score_month.py`):

1. **No data**: the provider sent nothing this month, or the file arrived without a column this metric needs. The metric is left out; nothing is carried over (D-76).
2. **Information only**: shown, never scored (TE-04, AI-assisted commits).
3. **Not Tier 0/1** (built 4 Nov 2026, owner): every Resiliency metric (RE-01, RE-02, RE-03) for a family with no Tier 0 or 1 application in the ITDR application file. The whole Resiliency block is then Not Tier 0/1, not scored, and TRUST comes from the other blocks. This includes RE-03, even when the family has Tier 2 applications. These families are left out of the Resiliency medians. Only when the ITDR application file is loaded for the month; without it the tier isn't known and nothing changes.
4. **Nothing to count**: not scored (N/A), except UN-02 and SE-03, where *nothing open is Green* (0%, 100 points) with no other condition (D-100).
5. **Low confidence**: fewer items than the metric's minimum. The value is shown but not scored, and is left out of the prevailing median and the typical-family comparison (D-100).
6. **Pass/fail metrics** (SE-04 CyberArk vaulting, SE-05 SailPoint governance), counted in accounts or apps: Green when every eligible item is done, Amber when any is not, **Red when any Tier 0/1 item is not (Red wins)**. Points stay 100 / 50 / 0. No tolerance thresholds; left out of the prevailing median (D-50). Without an app inventory, no item is treated as Tier 0/1.
7. **Rate metrics** are compared with the tolerance thresholds (Green at or better than the Green tolerance, Red beyond the Red limit, Amber between; Green edge inclusive, Red edge strict, D-07). Then three "Red wins" rules apply:
   - SE-01 / SE-02: a failing repo on a Tier 0/1 app with an overdue Emergency, Critical or High finding makes the family Red (D-85).
   - **Automatic Red rules**: an overdue critical secret (SE-03) or an end-of-life component on a Tier 0/1 internet-facing app (SE-06) makes the metric Red **and caps its block** (see caps).
   - TE-02: a deployed change with client impact makes TE-02 Red for that month, whatever the revert rate. It is a status rule, so no cap (D-92).

## Prevailing median and the usual spread between families

Many tolerance thresholds come from what the families usually achieve rather than a fixed number (`backend/trust/score_month.py`; `calibrate.py` for freezing).

- **Prevailing median**: the middle value across families for a metric (one decimal, D-02). Only scoreable families count, and Low-confidence families are left out (D-100).
- **Which metrics.** The median sets **both** limits for TR-01, TR-02, UN-02, SE-06, TE-02, TE-03 and the pass rates SE-01 and SE-02; it sets the **Red limit only** for TR-03 and SE-03, where Green stays at policy (D-99, D-85). RE-01 and RE-03 use the median too (owner, 4 Nov 2026), from Tier 0/1 families only; TE-01 stays on fixed policy values; RE-02 and UN-03 aren't scored yet. (Of the metrics named here, only TR-02, SE-01, SE-02, TE-02, UN-01, UN-02, RE-01 and RE-03 are measured today; the rest are planned.) **UN-01** uses the median of the families' counts (owner, 3 Nov 2026), with an Amber band of at least 1 incident.
- **Usual spread between families**: the distance between the family a quarter of the way along and the family three quarters of the way along (the interquartile range). The **Amber band is 1.5 times that spread, never less than 5 points** (5 per 100 releases for TE-03). Green is at or better than the median; Amber is up to one band worse; Red is beyond (D-103, D-07). The two numbers are settings.
- **Policy floor**: where a policy Green exists, Green is the **stricter** of the median and the policy value (D-08, D-99).
- **Red limit only metrics** (TR-03, SE-03): if the median would leave no Amber step (a median of 100% against a policy Green of 95%), the band is measured from the policy Green instead (TR-03: Red below 90%) (D-104).
- **Which month the median comes from.** The month being scored. A median from an earlier quarter is **not** used, and no history is ever required. The only way a threshold stops following the month's data is `calibrate --write` (below), which freezes it in `config/thresholds.json`.
- **How a status reason reads** (wording only): Green "At or below the prevailing median (Green tolerance: at most 0.5 incidents)"; Amber "Above the prevailing median, within the Amber band of 1.5 incidents (Red limit: more than 2 incidents)"; Red "More than the Amber band of 1.5 incidents above the prevailing median (Red limit: more than 2 incidents)". Percentages show points and %; counts show their unit; whole numbers have no ".0".
- **Each input file is its own submission** in `data.json` (`period.submissions[]`): `feed`, `id` (month-feed), its own numbered notes, and its own `unattributed_pct` (share not yet mapped to a family, from the metrics that read that file; null if none does). The provider-level `period.unattributed_pct` stays.
- **Few families**: the median is **always calculated from the data**, from whichever families have a result, however few (owner, 3 Nov 2026: no static starting values). With fewer than 4 families there is no usual spread to measure, so the Amber band is its minimum (5 points; 1 incident for UN-01). With no family results there is no threshold and the metric isn't scored.
- **Set once, then frozen (owner, 3 Nov 2026).** The prevailing median is used only to **set** the tolerance thresholds, one time, from several real months pooled together (every family's scored result in those months, at least 5 results per metric). The Green tolerance and Red limit are then written into `config/thresholds.json` as fixed values, with when and from what they were set, who approved them (Tech Risk) and "review: quarterly". From then on a family's colour no longer moves because its peers moved. Each quarter, Tech Risk looks at them again and sets them afresh if needed. **Until a metric has been set this way, its thresholds are still worked out each month from that month's own data**, as described above. Locked months keep the figures they were sealed with. How to do it: [runbook](runbook.md#set-the-tolerance-thresholds-calibrate) (`python manage.py calibrate`; without `--write` it only shows the result).
- The engine only **proposes** new thresholds; the Head of Tech Risk approves them (D-15). A month can be scored and previewed before approval; the proposed values are used and marked so.

## Item allowance for small families

TR-03 (apps confirmed), TR-01 and TR-02 (repos mapped, repos in good hygiene) have an **item allowance** of 2. A family no more than 2 items short is **Amber rather than Red**; it turns Red only when it is more than 2 items short **and** beyond the Amber band. Example: 14 of 16 apps confirmed is 87.5%, below a Red limit of 90%, but only 2 apps short, so Amber (D-104). The 2 is a per-metric setting.

## Building blocks, caps and TRUST

`backend/trust/scoring.py` (`block()`, `family()`, `block_codes()`, `BLOCKS`, `average_trust()`).

- **Points**: Green 100, Amber 50, Red 0. A block score is the **weighted average** of its scored metrics (weights 1 to 3, default 1; D-58), rounded to a whole number, half up (D-04).
- **Building blocks** (owner, 4 Nov 2026; they replace the earlier five-group scheme). Each block answers one question and carries a risk category from the firm's risk register (Cyber, Data, Model, Change, Obsolescence, Operational, Strategic, Vendor):
  - **Security** (SEC, Cyber): "Do we fix exposures before they're exploited?" SE-01, SE-02, SE-03, SE-04, SE-05.
  - **Resiliency** (RES, Operations): "Can we recover critical systems?" RE-01, RE-02, RE-03.
  - **Stability** (STA, Operations): "Do our clients get reliable service?" UN-01, UN-02, UN-03.
  - **Releases** (REL, Change): "Do we change production safely?" TE-01, TE-02, TE-03, TE-04 and TR-02 (repo good-hygiene).
  - **Accountability** (ACC, Strategic): "Do we know what we own, and who owns it?" TR-01 (scored since 6 Nov 2026: repos linked to a confirmed app in the app inventory), TR-03 and DA-01 (data ownership, risk category Data).
  - **Modernization** (MOD, Obsolescence): "Are we running technology that's still supported?" SE-06.
  - Blocks for Data, Model and Vendor will be added when their metrics arrive. Adding a block is a data edit in the page's data block (`blocks` list in `frontend/index.html`; each metric has a `block` field), not a code change.
- **Caps** (D-28): any Red metric caps its block at **79**, so a block is never Green with a Red metric (O-15); a Red **automatic Red rule** caps it at **49** (built today: TE-02, any release with client impact, owner 3 Nov 2026; planned: SE-03 overdue critical secret, SE-06 end-of-life on a Tier 0/1 internet-facing app); any Red block caps the family's TRUST at **79**. For percentages, a worked-out Red limit never goes below 0% or above 100%. A tolerance threshold worked out from the prevailing median needs at least 5 families with a result (setting `min_families_for_threshold`, owner 4 Nov 2026); with fewer, the metric shows "No tolerance threshold yet" and isn't scored that month. UN-02 needs at least 3 open actions per family (`low_confidence_below_items`; owner, 4 Nov 2026: stays 3). The three numbers are settings (`caps` in `config/thresholds.json`, owner 3 Nov 2026), named `automatic_red_block` (49), `red_metric_block` (79) and `red_block_trust` (79) (owner, 4 Nov 2026). Change, deploy, then update the month. Each month records the caps it was scored with, and locked months keep theirs.
- **Family TRUST** is the average of its blocks' capped scores, rounded half up. **Any scored block is enough** (owner, 4 Nov 2026; it was 3): a TRUST score from fewer than 6 blocks says so on the family page ("Average of 2 building blocks (4 not scored)"). With no scored block it shows "Insufficient data".
- **Coverage is a setting** (`coverage` in `config/thresholds.json`, owner 4 Nov 2026): `block_min_share` 0 = a block scores from any one scored metric (it was 0.5, half of the metrics that arrived); `trust_min_blocks` 1 = TRUST from any scored block (it was 3). To go back: 0.5 and 3, deploy, then update the month. Each month records the rules it was scored with; locked months keep theirs.
- **No trend flags on thin scores** (owner, 4 Nov 2026): Sharp drop and Declining are skipped when this month's or the compared month's TRUST rests on fewer than 3 blocks, so a file arriving or not doesn't look like a fall.
- **Bands**: 80 and above Green, 50 to 79 Amber, below 50 Red.
- **Missing data** (D-76): a block is scored from the metrics that arrived and says how many ("1 of 6 metrics"). The coverage rule (`block_min_share`) is counted on the metrics that arrived. A family or the firm with missing data shows **no change arrow**, is never "most improved", and drops out of the sharp-drop and declining checks for the affected block.
- **Rounding** (D-04): Decimal with ROUND_HALF_UP everywhere, no floating point. Block scores and TRUST are whole numbers; values have one decimal.

## Changes and trends

- The change arrow compares with the **previous month if it has been scored**. If it has not (the first month loaded, or a gap), no arrow is shown. That is never an error.
- Trend lines show only the months that have been scored.

## Firm figures

The code is in `backend/trust/score_month.py`. Each firm metric adds numerators and denominators over **every family and the items not placed in any family**, and is judged against the same tolerance thresholds, with no minimum population. An automatic Red rule that fired for any family holds for the firm too (owner, 4 Nov 2026). **Firm building blocks and TRUST** are then scored from those firm results exactly as a family's are (owner, 4 Nov 2026; before that, Firm TRUST was the average of the family TRUST scores, which is still recorded as `firm_trust_average` for comparison). The change since last month is shown only when both months are scored and neither has missing data. "Most improved" is the largest positive TRUST change among families with no missing data.

## Watch list

The code is `_watch` in `backend/trust/publish.py`, which works out the list for a month from its neighbours. A fixed order of kinds, each listing families in display order. Kinds that need earlier months (New Red, Chronic Red, Sharp drop, Declining) are skipped when those months are not scored. The kinds built today are the first five below and Behind peers; Overdue action and Data quality are not in the list yet (overdue actions and missing data show elsewhere on the page).

1. **Automatic Red**: a metric Red because of an automatic Red rule.
2. **New Red**: Red now, not Red last month (only when last month is scored).
3. **Chronic Red**: Red for 3 months in a row (D-03; also on the family page).
4. **Sharp drop**: TRUST down 10 points or more with at least 2 metrics worse (not with missing data).
5. **Declining**: a block that fell two months in a row (D-06).
6. **Overdue action**: an action still open past its due date.
7. **Behind peers**: a value worse than the typical family by more than the metric's gap. A flag only; never changes a colour or points.
8. **Data quality**: a provider that sent nothing, or a file that arrived with a required column missing. Items that belong to no family (data not yet mapped) are firm-wide and are seen by Tech Risk and auditors only (D-103).

No setting limits the length of the list. A family comment, a data query or a closed action before the lock date counts as an explanation of an item (D-94, D-95).

## Counts and wording

Counts carry units ("7 reverts out of 92 releases"), never a bare ratio (D-45). Thresholds are always called the Green tolerance and the Red limit (see the vocabulary rules in [DEVELOPER_GUIDE.md](../../DEVELOPER_GUIDE.md)). Trend words compare with the prior month while only two months exist, and with the prior quarter from three months on (D-84, D-106).

## What the scoring step measures today

What `python manage.py score YYYY-MM` does (the same as **Update the scorecard** on This month). `measure.py` counts per family, `score_month.py` judges and scores, and `scoring.py` holds the block, cap and TRUST rules above.

**Measured today: 10 metrics.** TE-01, TE-02, UN-01, UN-02, SE-01 and SE-02 are always counted; TR-01, TR-02, RE-01 and RE-03 are counted and scored because they are listed under `switched_on` in `config/thresholds.json`. Every other metric is planned (UN-03 is coming soon) and is left out of its block.

| Metric | Counted | Notes |
|---|---|---|
| TE-01 | TCC changes approved before deployment ÷ deployed TCC changes | Month = ticket created date (owner, 2 Nov). **TE-01 and TE-02 can cover different changes in the same month, on purpose:** each change is counted when its answer is known (approval: the ticket; revert: 7 days after release). The dictionary says this in plain words for both. **Changes outside TCC are left to TE-06** (owner, 2 Nov), which is not on the scorecard yet, so the Non-TCC file is not counted here |
| TE-02 | Reverts (outcome 40/50/60/90) ÷ deployed TCC changes with a known outcome | **Each release counts in the month its 7-day revert window ends** (`last deployment` + 7 days; owner, 2 Nov 2026), so a release on 28 Sep counts in October. 99 and blank outcomes are out of the rate; 95 is out. Any change with client impact (Status = Client) makes it Red (R-TCC-12). `Outcome recorded at` (7-day window) is not used yet |
| UN-01 | **Count** of unique **Critical and SWE** incidents (`incident_id`) in the postmortem file that ended in the month | Owner, 2 Nov 2026: there is no incidents file; the count follows the file's risk criteria: SWE = DEFCON 1–2, Critical = DEFCON 3–5. DEFCON 0 is out; "Not Available" or blank (no rating) is **shown per family but not counted** (owner, 2 Nov 2026: never hidden, never in the score). An incident counts once in each family its actions (or `user_stakeholders`) place it in, and once firm-wide. Month = `end_datetime` (the only date in the file; working rule); no end date = listed, not counted. **Scored** against the prevailing median of the families' counts that month (owner, 3 Nov 2026); a family with no incident counts 0; Amber band at least 1 incident. Becomes "per 10 apps" when the app inventory arrives |
| UN-02 | Overdue ÷ actions open at month-end | No closed date in the file yet, so "closed during the month" can't be added (doc 15). In-scope incidents only. **Actions on an incident with no rating** (DEFCON Not Available or blank) are **shown, not scored** (owner, 2 Nov 2026): counted separately and named on the result. Nothing open = Green (D-100); 1–2 actions = Low confidence, not scored |
| TR-01 | Active repos linked to at least one confirmed app in the app inventory ÷ active repos | **Scored from 6 Nov 2026** (owner; `switched_on`). GitHub repo file + app inventory, both needed. The inventory's `service_repo` is matched to the GitHub repo like Checkmarx. A repo's family = its owner's, as for TR-02. Linked to no app: doesn't count; a repo shared by several apps counts (owner, 6 Nov 2026). Prevailing median |
| TR-02 | Hygiene checks passed ÷ checks possible (5 per active repo) | **Scored from 4 Nov 2026** (owner; `switched_on` in `config/thresholds.json`). A repo's family = its owner's (the human with the most of the last 20 commits, found in HR by email). Prevailing median |
| RE-01 | Tier 0 and 1 applications with a completed DR test (date from Comments) in the 12 months to month-end ÷ those applications | **Scored from 4 Nov 2026** (owner; was BIA completion). DR tests only, tabletops don't count. Same two files as RE-03. Prevailing median |
| RE-03 | Tier 0, 1 and 2 applications with a successful DR test or tabletop exercise in the 12 months to month-end ÷ those applications | **Scored from 4 Nov 2026** (owner; `switched_on`). ITDR application file + DR tests file, both needed. Family = the family of the app inventory app it is linked to by name (owner, 6 Nov 2026), else its Business Product Area's (same for RE-01 and Tier 0/1). Prevailing median (the 95 / 80 placeholder is no longer used) |
| UN-03 | **Coming soon** (owner, 2 Nov 2026) | Client incidents. There is no source yet. Shown as "Coming soon" and left out of every score: not counted as missing data, and not in the Stability block |
| SE-01, SE-02 | Repos passing ÷ repos scanned | Repos reach a family through the GitHub repo file (owner, 4 Nov 2026): each Checkmarx repo is matched to a GitHub repo (same full name, then the same repo name after the last '/', then a close spelling at `checkmarx_match_min` 0.9 with the same numbers) and takes the family of that repo's owner. No match: Not yet mapped, counted firm-wide only. The Tier 0/1 Red rule needs the app inventory too |

**Tolerance thresholds** come from `config/thresholds.json` (owner-editable; score again after a change):

- *Policy* metrics (TE-01 80 / 60): fixed values.
- *Prevailing median* metrics (TE-02, UN-02, SE-01, SE-02, UN-01): the Green tolerance is the median of the families' results **for that month** (a known limitation of every month standing alone, accepted by the owner 2 Nov 2026: a family's colour can change because its peers changed); the Red limit is the Green tolerance ± the Amber band (1.5 × the usual spread between families, at least 5 points; D-103). Each month stands alone. Low-confidence results are left out of the median.
- **Always calculated from the month's data** (owner, 3 Nov 2026): no static starting values. The median comes from whichever families have a result, however few; with no results, the metric isn't scored.

**Not built yet:** the Tier 0/1 Red rules for SE-01/SE-02 and the pass/fail metrics (they need to know which application each repo or account belongs to, which neither ITDR file says). (Item detail, comments and the manual lock are built.)

**Families** come from the product family owners file. **Their tier comes from the ITDR application file** (owner, 4 Nov 2026): the Resiliency row under All metrics on the family page says "X Tier 0/1 apps out of Y apps" (Y = every application placed with the family, any tier, TBC or none; owner, 4 Nov 2026: not in the header under the family name). A family with at least one Tier 0 or 1 application is Tier 0/1. Applications not placed with a family (Business Product Area not matched) count for nobody. Without the ITDR file for the month nothing is shown.

**Follow-up (owner, 4 Nov 2026):** the DR tests file has its own Tier column, which sometimes disagrees with the ITDR application file. TRUST always uses the **ITDR application file's tier**; every difference is a warning on the mapping result (acknowledged before the month is locked). Ask ITDR to line the two files up, and decide with them which file is the source of truth for a tier.
