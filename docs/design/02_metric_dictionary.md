# TRUST Scorecard — Metric Dictionary (v0.6 DRAFT)

> **Owner, 8 Nov 2026: the live definitions are in `config/metrics.json`** (the cards the site shows, known limits, status). This document keeps the reasoning and history; where the two differ, the file is what the site uses.

> **v0.6 (3 Nov 2026): brought in line with what v1 actually measures.** Section 0 describes the nine metrics TRUST measures today, as the code counts them, and wins over anything later in this document. The dictionary holds 20 metrics. The other 11 are not measured: ten are **planned** (TR-01, TR-03, DA-01, RE-02, SE-03, SE-04, SE-05, SE-06, TE-03, TE-04) and one is **coming soon** (UN-03). Their cards (Section 3) are the design, not yet checked against real data. TR-02, RE-01 and RE-03 were added to the measured set on 4 Nov 2026, and TR-01 on 6 Nov 2026 (so ten measured, nine planned besides UN-03); their cards are in Section 3 under their building blocks. Made-up starting values ("proposed" thresholds) are removed: a planned metric gets its tolerance thresholds when it is measured. The live page (Metric dictionary) shows the same wording as this document.

> "A product our clients can trust is Traceable, Resilient, Uninterrupted, Secure, and Tested."

> **Owner, 4 Nov 2026: the five letters are replaced by six building blocks of TRUST.** A building block groups related metrics under one question and carries a risk category from the firm's risk register. Metric IDs (TR-01, SE-06 and so on) do not change. Security (SEC, Cyber): SE-01 to SE-05. Resiliency (RES, Operational): RE-01 to RE-03. Stability (STA, Operational): UN-01 to UN-03. Releases (REL, Change): TE-01 to TE-04 and TR-02. Accountability (ACC, Strategic): TR-01, TR-03. Modernization (MOD, Obsolescence): SE-06. Wherever a metric section below says "letter", read the building block that holds the metric.

| Item | Value |
|---|---|
| Document | 02_metric_dictionary.md |
| Version | v0.6 DRAFT (supersedes v0.5) |
| Status | Draft, not yet approved. For approval by the Head of Tech Risk. |
| Where it lives | The live page's dictionary (`frontend/index.html`, inline data) and this document say the same thing. Change both in the same commit. |
| Basis | Owner decisions to 3 Nov 2026 and the code in `backend/trust/` (`measure.py`, `score_month.py`, `intake/`). The latest owner decision wins on any conflict. |
| Terms | "Tolerance threshold" means the Green tolerance and the Red limit together. "Prevailing median" means the middle family's result that month. |

---

## 0. What v1 measures (as built, 3 Nov 2026)

### 0.1 Shared rules as built

- **Where the numbers come from.** Tech Risk uploads each provider's own export on the website. Each file loads on its own. TRUST places every row with a family through HR (the person's manager chain) and the product family owners file, then counts per family. Rows it can't place are shown as "Not yet mapped" and never scored.
- **Every month stands alone.** Nothing is rolled up over several months.
- **Tolerance thresholds.**
  - **Policy:** a fixed Green tolerance and Red limit from `config/thresholds.json`. None of the measured metrics today (TE-01 moved to the prevailing median, owner 8 Nov 2026).
  - **Prevailing median:** worked out afresh each month from that month's family results. Green tolerance = the median family. Red limit = the median plus or minus the Amber band. The band is 1.5 × the usual spread between families (the middle half, once 4 or more families have a result) and never less than 5 percentage points (UN-01: 1 incident). Fewer than 5 families with a result (setting `min_families_for_threshold`, owner 4 Nov 2026): no threshold, and the metric shows "No tolerance threshold yet" and isn't scored that month. TE-02, UN-01, UN-02, SE-01 and SE-02 use it.
  - **Calibration (owner, 3 Nov 2026):** the prevailing median is used once to set the tolerance thresholds, pooling several real months (`python manage.py calibrate`), and they are then fixed and reviewed each quarter by Tech Risk. Until a metric is calibrated it is worked out each month as above.
  - There are no threshold versions or approval records yet. The thresholds have not been through formal approval.
- **Status.** Green tolerance is inclusive; the Red limit is exclusive; between the two is Amber. Judged on the value rounded to 1 decimal. A metric scores by its colour (Green 100, Amber 50, Red 0), not by how far it is from a line: just past the Red limit scores the same 0 as far past it.
- **Behind peers.** **Off for now (owner, 8 Nov 2026; setting `behind_peers_flag` in `config/thresholds.json`):** every measured metric uses the prevailing median, which already compares each family with the median. When switched on, it applies only to metrics with a Policy tolerance threshold: a family at least 15 percentage points worse than the median family, with at least 5 families scored. It adds a watch-list entry only. Prevailing-median metrics are not flagged, because their colour already compares each family with the median.
- **Minimum population.** UN-02 needs at least 3 open actions per family (owner: stays 3, 4 Nov 2026); below that the result is "Low confidence" (shown, not scored). Every other measured metric is scored from the first item.
- **Nothing to measure.** UN-02 with no open actions is Green (0%) (D-100), shown as "Green, nothing open" so it isn't read as a checked result (owner, 4 Nov 2026). UN-01 with no incidents is a count of 0. TE-01, TE-02, SE-01 and SE-02 with nothing to count are not scored.
- **Time.** New York time throughout.

### 0.2 The nine measured metrics

| ID | Metric | Better when | Result | Threshold basis | Population (in short) | Month |
|---|---|---|---|---|---|---|
| TE-01 | Change ticket adoption | Higher | % of deployed production changes that went through TCC | Prevailing median | Deployed TCC and Non-TCC changes | Month the ticket was created |
| TE-02 | Release revert rate (7 days) | Lower | % of production releases backed out | Prevailing median | Deployed TCC releases with a known outcome | Month the 7-day window ends |
| UN-01 | Critical and SWE incidents | Lower | Count of unique incidents (until the app inventory gives "per 10 apps") | Prevailing median, band at least 1 incident | Postmortem file, DEFCON 1–5 | Month the incident ended |
| UN-02 | Postmortem actions overdue rate | Lower | % of open actions past their due date | Prevailing median | Actions open at month-end | Snapshot at month-end |
| SE-01 | Checkmarx SAST pass rate | Higher | % of scanned repos passing Cyber's SAST policy | Prevailing median | Repos in the month's SAST export | The month's export |
| SE-02 | Checkmarx SCA pass rate | Higher | % of scanned repos passing Cyber's SCA policy | Prevailing median | Repos in the month's SCA export | The month's export |
| TR-02 | Repo good-hygiene rate | Higher | % of hygiene checks passed (5 per active repo) | Prevailing median | Active repos placed with the family through their owner | The month's GitHub export |
| RE-01 | Tier 0/1 DR test completed (12 months) | Higher | % of Tier 0/1 apps with a successful DR test in the 12 months to month-end | Prevailing median | Tier 0/1 apps in the ITDR application file | 12 months to month-end |
| RE-03 | Resiliency testing completion (passed) | Higher | % of Tier 0 to 2 apps with a successful DR test or tabletop exercise in the 12 months to month-end | Prevailing median | Tier 0 to 2 apps in the ITDR application file | 12 months to month-end |

UN-03 (client incidents) is **Coming soon**: there is no source for client incidents yet. It is left out of every score.

### 0.3 Cards for the measured metrics

#### TE-01 Change ticket adoption
*Owner, 8 Nov 2026: was "approved before deployment" (TCC changes only, Policy 80 / 60). Now the share of all deployed changes that went through TCC, judged against the prevailing median.*
- **Risk it watches:** every production change should go through TCC, the firm's change control route. A change made outside TCC skips its review and approval steps, so unreviewed changes can reach production. This is the core program-change control.
- **Value:** deployed changes through TCC ÷ all deployed changes (TCC + Non-TCC) × 100.
- **Population:** production changes deployed in the month, from both the TCC and the Non-TCC exports, counted in the month the ticket was created. A change counts as through TCC when it is in the TCC export, Standard changes included. Non-TCC changes count as deployed when their Status is Completed, Resolved, Monitoring or Client. A change in both exports counts once, as TCC.
- **Exclusions:** TCC changes with no production deployment recorded; Non-TCC changes with a status that doesn't mean deployed.
- **Needs:** both exports for the month. With only one, the metric shows No data (not a false 100%).
- **Time basis:** counted in the month the change ticket was created (TCC: the last deployment date is used only when the created date is blank; Non-TCC: the last updated date). TE-02 counts releases later, when their 7-day window closes, so the two can cover different changes in one month.
- **Minimum population:** scored from the first item. **Nothing to measure:** no deployed changes, not scored.
- **Scoring:** prevailing median (needs at least 5 families with a result).
- **Limitations:**

| Limitation | Mitigation | Status |
|---|---|---|
| Going through TCC doesn't show that a change was approved before it was deployed. | None yet in this metric. The TCC file still carries the approval time. | No mitigation yet |
| The Non-TCC export has no deployment date. | Month from Created Date, the same rule as TCC (Q-NTCC-01). | Partly mitigated |
| Which Non-TCC statuses mean deployed isn't confirmed. | Working rule: Completed, Resolved, Monitoring, Client (Q-NTCC-02). | Partly mitigated |
| A Non-TCC change with no author email can't be placed with a family. | Shown as Not yet mapped on the firm page, never hidden. | Partly mitigated |
| A change could appear in both exports. | Counted once, as TCC, and listed. | Mitigated |
| Many deployments can be linked to one general ticket. | None yet. | No mitigation yet |

#### TE-02 Release revert rate (7 days)
- **Risk it watches:** releases that have to be backed out point to weak pre-production testing, and bad releases that reach production can affect clients.
- **Value:** releases reverted ÷ releases with a known outcome × 100.
- **Population:** production releases through TCC whose 7-day revert window ended in the month. Reverted means the overall outcome is 40, 50, 60 or 90 (backed out, including a backout started by the client).
- **Exclusions:** outcome 95 (obsoleted). Outcome 99 (unknown) and a blank outcome are left out of the rate and counted separately.
- **Time basis:** the month the 7-day window ends (last deployment + 7 days): a release on 28 September counts in October.
- **Automatic Red rule (owner, 3 Nov 2026):** any release with client impact makes the family's result Red that month, whatever the rate, and caps the Releases block at 49.
- **Minimum population:** scored from the first item. **Nothing to measure:** no releases, not scored.
- **Scoring:** prevailing median.
- **Limitations:**

| Limitation | Mitigation | Status |
|---|---|---|
| Releases late in a month haven't finished their 7-day window. | Each release counts in the month its window ends. | Mitigated |
| A release with an unknown or blank outcome can't be judged. | Left out of the rate and counted separately (not yet shown on the page). | Partly mitigated |
| A low rate can mean good testing, or fixing forward. | Read together with UN-01. No count of quick fixes yet. | Partly mitigated |
| Bundling changes into fewer releases shrinks the count. | None yet. | No mitigation yet |

#### UN-01 Critical and SWE incidents
- **Risk it watches:** Critical and SWE incidents are the most direct sign that clients have felt an outage or serious degradation of service.
- **Result:** a count of unique incidents per family (until the app inventory allows "per 10 apps").
- **Population:** unique incidents (`incident_id`) in the postmortem file rated Critical (DEFCON 3–5) or SWE (DEFCON 1–2) that ended in the month, placed with families through their postmortem action assignees, or the people named on the postmortem.
- **Exclusions:** DEFCON 0. Incidents rated Not Available or blank are listed for follow-up, not counted.
- **Time basis:** by `end_datetime`, the only date in the export. An incident with no end time is listed, not counted. An incident with actions in several families counts once in each, and once firm-wide.
- **Minimum population:** scored from the first item. **Nothing to measure:** a count of 0, scored like any other count.
- **Scoring:** prevailing median of the counts; Amber band at least 1 incident. Not flagged as behind peers.
- **Limitations:**

| Limitation | Mitigation | Status |
|---|---|---|
| A plain count is harder on large families. | Temporary: becomes a rate per 10 apps when the app inventory arrives (owner, 3 Nov 2026). | Partly mitigated |
| An incident's rating can be lowered. | Ratings come from the incident process (set by SRE). No count of lowered ratings yet. | Partly mitigated |
| Several incidents can be merged into one. | None yet. | No mitigation yet |
| An incident with no rating or no end time can't be counted. | Listed for follow-up, not hidden. | Partly mitigated |

#### UN-02 Postmortem actions overdue rate
- **Risk it watches:** incidents recur when the actions agreed after a postmortem are left unfinished.
- **Value:** open actions past their due date ÷ actions open at month-end × 100.
- **Population:** postmortem actions still open at month-end on incidents in the postmortem file that aren't DEFCON 0. Tracking (Monitoring or Read-only) counts as open. Overdue means the due date (ETA) is before month-end; an action with no ETA is due 30 days after it was created. Status is as at the export.
- **Exclusions:** done and cancelled actions; actions created after month-end. Actions on incidents with no rating are shown beside the result but kept out of the score.
- **Time basis:** snapshot of open actions at month-end. The file has no closed date, so the "open plus closed during the month" denominator (O-5) can't be applied yet.
- **Minimum population:** 3 open actions per family (below that: Low confidence, shown but not scored). **Nothing to measure:** no open actions, Green (0%).
- **Scoring:** prevailing median.
- **Limitations:**

| Limitation | Mitigation | Status |
|---|---|---|
| No closed date, so late closures during the month are missed. | Snapshot of open actions only, until the provider adds a closed date. | Partly mitigated |
| Due dates can be moved out. | None yet. | No mitigation yet |
| Actions can be cancelled without the fix being made. | None yet. | No mitigation yet |
| A postmortem with no actions leaves nothing to be overdue. | None yet. | No mitigation yet |

#### SE-01 Checkmarx SAST pass rate / SE-02 Checkmarx SCA pass rate
- **Risk it watches:** SE-01, exploitable flaws in our own code left open past their fix deadline. SE-02, known-vulnerable open-source libraries left in use past their fix deadline.
- **Value:** repos passing Cyber's Checkmarx policy ÷ repos in the month's export × 100.
- **Population:** repos in the month's Checkmarx SAST (SE-01) or SCA (SE-02) export. A repo passes when Cyber's policy marks it compliant. Cyber's policy sets the fix deadlines, not TRUST. Repos reach a family through the repo list and app inventory; until those arrive, every repo shows as Not yet mapped and families have no result.
- **Exclusions:** false positives and approved, unexpired exceptions are handled in Cyber's policy before a repo is marked; TRUST does not filter them again.
- **Time basis:** the compliance status in the month's export.
- **Planned, not yet applied:** Red when a repo on a Tier 0/1 app has an overdue Emergency, Critical or High finding.
- **Minimum population:** scored from the first item. **Nothing to measure:** no scanned repos, not scored.
- **Scoring:** prevailing median. (OD-02's 5% Green tolerance is not used: owner, 3 Nov, thresholds always come from the month's data.)
- **Limitations:**

| Limitation | Mitigation | Status |
|---|---|---|
| False positives, exceptions and lowered severities are decided in Cyber's policy. | Accepted: TRUST uses the policy result and does not re-check findings. | Partly mitigated |
| Repos left out of scanning never reach the count. | None yet. Scan coverage needs the repo list. | No mitigation yet |

---

## 1. Shared rules (design, for the planned metrics)

Section 0.1 wins where the two differ. Superseded points are marked.

**1.1 Unit and roll-up.** *Superseded for v1:* providers don't submit numerators per team; TRUST reads each provider's export and counts (0.1). The design rule stays for later direct feeds (v2): items are placed with families, the "Not yet mapped" row is shown and counted in firm-wide totals, but never scored and never counted in the median.

**1.2 Scoring by tolerance threshold.** Every scored metric has a **Green tolerance** and a **Red limit**, except the two pass/fail metrics (SE-04, SE-05; see 1.13):
- The Green tolerance is **inclusive**; the Red limit is **exclusive**. Anything between the two is Amber.
- Higher-better: Green if value ≥ G; Red if value < R. Lower-better: Green if value ≤ G; Red if value > R.
- Status is judged on the **displayed value, rounded to 1 decimal**.
- A tolerance threshold comes from policy or an SLA where one exists. Otherwise it is the prevailing median, *worked out afresh each month from that month's results (owner, 3 Nov 2026; replaces quarterly recalibration, O-8)*. Where a policy sets the tolerance threshold, the policy wins (D-08).

**1.3 Behind-peers flag.** A family is flagged when it is at least the metric's gap (15 percentage points for % metrics) worse than the median family, with at least 5 families scoreable. It adds a watch-list entry only; it never changes colour or points. *As built: only metrics with a Policy tolerance threshold are flagged* (0.1). Pass/fail metrics carry no flag.

**1.4 Overrides and caps (make worse only).**
- SE-03: any overdue Emergency or Critical secret makes the metric Red.
- SE-06: any EOL component on an app that is both Tier 0/1 and internet-facing makes the metric Red.
- TE-02 (built): any release with client impact makes the metric Red.
- An override Red caps its building block at 49.
- Any Red metric caps its block at 79 (D-28, O-15). Any Red block caps TRUST at 79.
- The caps (49, 79, 79) are settings in `config/thresholds.json` (owner, 3 Nov 2026), so they can be adjusted later.

**1.5 Zero denominator.** "Best" only when the provider confirms coverage; otherwise N/A with "No coverage". *As built: see 0.1, Nothing to measure.*

**1.6 Minimum population.** Below the minimum the status is **Low confidence**: shown, not scored, flagged. *As built: UN-02 3; every other measured metric 1.* Each planned card states its own proposed minimum.

**1.7 Status precedence.** Info only, DNR, Not Tier 0/1, Not assessed, zero-denominator rule, Low confidence, Scoreable. Overrides apply after the tolerance threshold status.

**1.8 Accepted risk (D6).** Follows the firm's risk acceptance process (risk register entry, expiry, second-line concurrence, CTO approval). It never turns a metric Green. *Not built in v1: there are no accepted-risk records yet.*

**1.9 Vulnerability findings (SE-03 design).** Overdue = an Emergency, Critical or High finding older than its SLA, counted from first detection; the clock persists across rescans; expired exceptions count as overdue. Denominator: open at as_of plus closed during the month (O-5). *SE-01/02 as built use Cyber's Checkmarx policy result per repo instead (0.3).*

**1.10 Time basis.** Snapshot metrics: month-end, New York time. Flow metrics: events in the calendar month. *Rolling 3-month windows (UN-01, UN-03) are not used: every month stands alone (owner, 2 Nov 2026).*

**1.11 Inventories.** Tier 0/1 classification comes only from the ITDR register. Per-app denominators use the month-end inventory snapshot. *Not yet received.*

**1.12 Data quality.** *As built:* each upload is checked on its own; junk is refused, warnings are shown and must be acknowledged before the lock; TRUST keeps a copy of every file with its SHA-256 fingerprint, who uploaded it and when. *Data contracts (definition versions, firm totals per submission) are a v2 item, for direct feeds (owner, 3 Nov 2026).*

**1.13 Pass/fail metrics (D-50).** SE-04 and SE-05 are counted in accounts or apps: Green when every eligible item is covered, Amber when any is not, Red when one belonging to a Tier 0/1 app is not. No tolerance thresholds, no behind-peers flag. Written as a count with units, for example "63 of 69 accounts vaulted".

---

## 2. Metric summary table

Status: **Measured** (scored today), **Coming soon** (no source yet) or **Planned** (designed, no data feed yet). Planned metrics have no tolerance threshold until they are measured; "Policy" names the standard expected to set it.

| ID | Metric | Provider | Better when | Unit | Status | Tolerance threshold |
|---|---|---|---|---|---|---|
| TR-01 | Repo mapping rate | Tech Risk (GitHub export) + Arch (app inventory) | Higher | % of active repos linked to a confirmed app | Scored (owner, 6 Nov 2026) | Prevailing median |
| TR-02 | Repo good-hygiene rate | Tech Risk (GitHub export) | Higher | % of hygiene checks passed (5 per active repo) | Scored (owner, 4 Nov 2026) | Prevailing median |
| TR-03 | Application confirmation rate | Arch | Higher | % of owned apps | Planned | Not set (Policy: app inventory standard) |
| DA-01 | Data ownership rate | Data governance (source to be confirmed) | Higher | % of datasets used | Planned (owner, 4 Nov 2026) | Not set |
| RE-01 | Tier 0/1 DR test completed (12 months) | ITDR | Higher | % of Tier 0/1 apps in the ITDR application file | Scored (owner, 4 Nov 2026) | Prevailing median |
| RE-02 | Resiliency testing coverage | ITDR | Higher | % of Tier 0/1 apps | Planned | Not set (Policy: ITDR standard) |
| RE-03 | Resiliency testing completion, passed | ITDR | Higher | % of Tier 0-2 apps in the ITDR application file | Scored (owner, 4 Nov 2026) | Prevailing median |
| UN-01 | Critical and SWE incidents | Ops | Lower | Incidents (count) | **Measured** | Prevailing median |
| UN-02 | Postmortem actions overdue rate | Ops | Lower | % of actions open at month-end | **Measured** | Prevailing median |
| UN-03 | Client incidents | Ops | Lower | — | Coming soon | Not set |
| SE-01 | Checkmarx SAST pass rate | Cyber | Higher | % of scanned repos | **Measured** | Prevailing median |
| SE-02 | Checkmarx SCA pass rate | Cyber | Higher | % of scanned repos | **Measured** | Prevailing median |
| SE-03 | Secrets E/C/H overdue rate | Cyber | Lower | % of E/C/H secret findings | Planned | Not set; override: any overdue Emergency/Critical secret = Red |
| SE-04 | CyberArk vaulting | IAM (Cyber) | More vaulted | Accounts (count) | Planned | Pass/fail (1.13) |
| SE-05 | SailPoint governance | IAM (Cyber) | More governed | Apps (count) | Planned | Pass/fail (1.13) |
| SE-06 | EOL components (platform-hosted) | Hosting platform | Lower | % of platform-hosted apps | Planned | Not set; override: Tier 0/1 internet-facing app with EOL = Red |
| TE-01 | Change ticket adoption | Change | Higher | % of deployed changes through TCC | **Measured** | Prevailing median |
| TE-02 | Release revert rate (7 days) | Change | Lower | % of production releases | **Measured** | Prevailing median |
| TE-03 | Defect rate | Change | Lower | Defects per 100 releases | Planned | Not set |
| TE-04 | AI-assisted commits rate | Change (GHES data) | n/a | % of commits | Planned | Information only, no threshold |

---

## 3. Metric cards by building block

These are the cards for the metrics that have no card in section 0.3. Three of them are measured and scored: TR-02, RE-01 and RE-03. The others are the design for metrics not measured yet: their wording has not been checked against real data, and the limitations and counter-measures listed are planned along with the metric. The blocks and their metrics are as on the live page. The old group names are history, in the notes at the top of this document.

### Security (SEC; provider: Cyber; SE-04 and SE-05 IAM)

SE-01 and SE-02 are measured (0.3).

#### SE-03 Secrets E/C/H overdue rate
- **Why it matters:** A secret exposed in code gives direct access to systems. It needs the fastest remediation of any finding type.
- **Numerator:** open Emergency/Critical/High secret findings at as_of past their SLA, excluding approved unexpired exceptions. "Remediated" means rotated or revoked, not only removed from code (OD-22).
- **Denominator:** open E/C/H secret findings at as_of, plus those closed during the month (O-5).
- **Override:** any overdue Emergency or Critical secret makes the metric Red, and the block is capped at 49.
- **Zero denominator:** Best only if secret scanning is enabled on every active repo of the family; otherwise N/A.
- **Min population (proposed):** 1.
- **Source system:** secret scanning tool (to confirm).
- **Limitations / gaming risks:** closing a finding without rotating the secret; marking real secrets as false positives; downgrading to High to avoid the override.
- **Planned counter-measures:** closures evidenced by rotation; counts of downgrades, false positives and exceptions.
- **Open items:** OD-20, OD-21, OD-22.

#### SE-04 CyberArk vaulting (pass/fail)
- **What it tells you (owner-approved wording):** Vaulting privileged accounts in CyberArk may give rotated credentials, session recording and a record of who used them, which could lead to better-controlled privileged access. Vaulting alone does not show the access was appropriate.
- **Result:** eligible privileged accounts owned by the family that are vaulted, out of all eligible accounts, written as a count, for example "63 of 69 accounts vaulted".
- **Scoring (1.13):** Green when every eligible account is vaulted; Amber when any is not; Red when an account belonging to a Tier 0/1 app is not.
- **Eligibility:** set centrally by the IAM standard (OD-23).
- **Source system:** CyberArk plus the privileged account discovery source (to confirm).
- **Limitations / gaming risks:** accounts reclassified as non-privileged; incomplete discovery; hard-to-attribute ownership.
- **Planned counter-measures:** central eligibility; counts of accounts reclassified out and discovery coverage.
- **Open items:** OD-23.

#### SE-05 SailPoint governance (pass/fail)
- **What it tells you (owner-approved wording):** Apps governed in SailPoint can have certifiable access reviews and automated joiner-mover-leaver processing. Being in SailPoint makes those controls possible, not certain: whether reviews are completed and leavers are removed is tested separately.
- **Result:** eligible apps owned by the family that are governed in SailPoint, out of all eligible apps, written as a count, for example "21 of 23 apps governed".
- **Scoring (1.13):** Green when every eligible app is governed; Amber when any is not; Red when a Tier 0/1 app is not.
- **Eligibility:** set centrally by the IAM standard (OD-24).
- **Source system:** SailPoint plus the app inventory.
- **Limitations / gaming risks:** an app marked "SSO-only" to become ineligible; governed with no certification campaign.
- **Planned counter-measures:** central eligibility; counts of eligibility changes and governed apps with no certification in 12 months.
- **Open items:** OD-24.

### Resiliency (RES; provider: ITDR)

For all RE metrics: the Tier 0/1 population comes only from the ITDR application file (the DR tests file's Tier is never used; a difference is a mapping warning, follow-up with ITDR, owner 4 Nov 2026); a family with no Tier 0/1 apps is "Not Tier 0/1" and is not scored on this block (the whole Resiliency block is Not Tier 0/1), RE-03 included (built 4 Nov 2026, owner); tier changes need ITDR sign-off; proposed minimum population 1.

#### RE-01 Tier 0/1 DR test completed (12 months)
*Redefined 4 Nov 2026 (owner): was "Tier 0/1 BIA completion"; ITDR has no BIA date, and the testing completed is what matters. A BIA metric would need a BIA date from ITDR (OD-14).*
- **Why it matters:** the most critical applications must show they can actually be recovered; a completed DR test in the last year is that evidence.
- **Numerator:** Tier 0 and 1 applications with a DR test (production or not) whose Status is Successful and whose Comments give a completion date in the 12 months to month-end. Tabletop exercises don't count.
- **Denominator:** Tier 0 and 1 applications in the ITDR application file, placed with the family by Business Product Area.
- **Source system:** ITDR application file + DR tests file (both needed for the month); tests linked to applications by name.
- **Tolerance threshold:** prevailing median (needs 5 families with a result).
- **Limitations:** Status and the Comments date are taken as given (no RTO/RPO result); a DR test with no date in its Comments can't count; names that differ between the files can't be linked (listed on the mapping result).
- **Relation to RE-03:** RE-03 is the broader view (Tier 0 to 2, tabletops count).

#### RE-02 Resiliency testing coverage
- **Why it matters:** A critical app without a documented recovery test plan cannot show that it can meet its RTO/RPO.
- **Numerator:** Tier 0/1 apps with a documented, current (approved) resiliency/DR test plan at as_of.
- **Denominator:** Tier 0/1 apps in the ITDR register at as_of.
- **Source system:** ITDR register / BCM tool.
- **Limitations:** a plan can exist on paper without being exercised (covered by RE-03).
- **Planned counter-measures:** count of plans not reviewed in 12 months.
- **Open items:** OD-14.

#### RE-03 Resiliency testing completion, passed (trailing 12 months)
*As built 4 Nov 2026 (owner): Tier 0, 1 and 2 applications in the ITDR application file with a successful DR test (production or not) or tabletop exercise dated in the 12 months to month-end; prevailing median. The text below is the original design.*
- **Why it matters:** A successful recovery test is the only evidence that recovery works within the agreed objectives.
- **Numerator:** Tier 0/1 apps with a resiliency/DR test completed in the 12 months ending at as_of and passed (RTO and RPO both met). A failed test followed by a passed retest in the window counts as passed.
- **Denominator:** Tier 0/1 apps requiring an annual test under the ITDR standard.
- **Zero denominator:** no Tier 0/1 apps, Not Tier 0/1; Tier 0/1 apps but none requiring a test, N/A ("No test due").
- **Source system:** ITDR register / BCM test records.
- **Limitations / gaming risks:** test scope can be narrowed to pass; an app can be marked as not requiring an annual test.
- **Planned counter-measures:** counts of failed tests and test-requirement flag changes; flag changes need ITDR sign-off.
- **Open items:** OD-15.

### Stability (STA; provider: Operations)

UN-01 and UN-02 are measured (0.3).

#### UN-03 Client incidents (coming soon)
- **Why it matters:** Problems that clients find before we do are a direct measure of trust from the client's side.
- **Status:** Coming soon. There is no source for client incidents yet (owner, 2 Nov 2026). Left out of every score.
- **Design (to revisit when a source exists):** client-reported issues attributed to a client-facing app owned by the family, per 10 client-facing apps; how-to questions and feature requests excluded (OD-19).

### Releases (REL; provider: Change Management; TR-02 from the GitHub export)

TE-01 and TE-02 are measured (0.3).

#### TR-02 Repo good-hygiene rate (owner decisions, 3 Nov 2026; scored since 4 Nov 2026)
- **Why it matters:** Basic repo protection is the precondition for traceable, reviewed change: every change to the main branch is reviewed by someone else, the history can't be rewritten, and nobody can skip the rules.
- **Value:** hygiene checks passed ÷ hygiene checks possible (5 per active repo) × 100, across the family's active repos. Each repo scores the checks it passes out of 5 (4 of 5 = 80%), so the family's value is the average repo score. *Replaces "repos meeting every check" (owner, 3 Nov 2026: partial credit, not all-must-pass).*
- **The 5 checks (one point each; OD-11 closed, owner 3 Nov 2026):**
  1. **Main branch protected:** branch protection or an active ruleset covers the default branch. Without it, checks 2 to 5 can't pass, so an unprotected repo scores 0 of 5.
  2. **Review required:** at least 1 approving review before merge.
  3. **Independent approval:** the most recent push must be approved by someone other than its pusher.
  4. **History can't be rewritten:** force pushes and branch deletion both blocked.
  5. **No one can skip the rules:** admins held to the rules and nobody has bypass rights.
  Shown, not scored: CODEOWNERS file present; required status checks; stale approvals dismissed.
- **Population:** active repos placed with the family through their **owner**: the human with the **most of the last 20 main-branch commits**, a tie going to the most recent (owner, 3 Nov 2026; setting `repo_owner_rule` `most_commits`; `last_commit` = the last human committer). The owner is found in HR by work email, then by GitHub login = SAM_ACCOUNT; then nearest family owner (doc 13 §8). No match, or no human committer: **Not yet mapped**, shown and never scored. Bots are never owners.
- **Active (OD-10 working rule):** not archived, not a fork, and a push or main-branch commit in the 90 days before month-end (setting `repo_active_days`).
- **Source:** `tools/github_repo_export.py` (GitHub GraphQL), uploaded as feed `repos`. The export reports settings; TRUST decides what passes (`backend/trust/intake/repos.py`).
- **Family page (owner, 3 Nov 2026):** lists the family's repos with no main-branch protection, because partial credit can hide them; not shown on the CTO view.
- **Limitations / gaming risks:** checks read configuration only (a required review can be rubber-stamped); settings are read when the export runs; ownership follows who made most of the last 20 commits, so heavy shared work can move repos (anyone owning 20 or more active repos is listed for a check, setting `repo_owner_flag_count`).
- **Open items:** OD-10 (platforms in scope). TR-02 is scored and sits in the Releases block.

#### TE-03 Defect rate
- **Why it matters:** Escaped production defects relative to release volume show how well testing works.
- **Numerator:** production defects raised in the month, attributed to a family app.
- **Denominator:** production releases in the month. **Rate:** defects per 100 releases.
- **Source system:** Jira Data Center, feed `defects` (`jira_issues.csv` from `tools/jira_export.py`; owner, 3 Nov 2026), plus TCC releases. **Attribution (owner, 3 Nov 2026):** the family of the person who closed the defect, found in HR by work email, then Jira username = SAM_ACCOUNT. Built up to mapping; not scored yet.
- **Still to decide before scoring:** which defects count as production defects (Jira's environment field or a label, `--env-field`), and whether a defect counts in the month it was raised or closed.
- **Limitations:** defects raised this month often come from earlier releases; under-logging; differing defect definitions; fewer, larger releases inflate the rate.
- **Planned counter-measures:** central defect definition; counts of raw defects and defects closed as "not a defect".
- **Open items:** OD-29.

#### TE-04 AI-assisted commits rate (information only)
- **Why it matters:** Shows how widely AI coding assistance is used, as context for change-risk and review practice. Not scored.
- **Numerator:** commits to default branches of active repos identified as AI-assisted (OD-30). **Denominator:** commits to default branches of active repos. **Exclusions:** bot commits.
- **Status:** information only; no tolerance threshold, no peer flag.
- **Limitations:** depends on self-declaration or telemetry, so the true rate is understated. It must not be read as better or worse.
- **Open items:** OD-30.

### Accountability (ACC; provider: Architecture; DA-01 data governance)

#### TR-01 Repo mapping rate (owner, 6 Nov 2026: switched on)
- **Why it matters:** If a repo is not mapped to an application, its code is outside every control that hangs off the app inventory.
- **Numerator:** active repos linked to **at least one confirmed app** in the app inventory (a repo shared by several apps counts; owner, 6 Nov 2026), through the inventory's `service_repo` (matched to the GitHub repo like Checkmarx: full name, then repo name, then a close spelling at `app_repo_match_min`).
- **Denominator:** active repos, placed with the family of the repo owner (as for TR-02).
- **Active:** as for TR-02 (not archived, not a fork, activity in 90 days).
- **Not counted:** a repo linked to no app (the drill-down lists them). Apps whose `app_status` isn't `confirmed` don't link a repo.
- **Needs:** the GitHub repo file and the app inventory for the month; otherwise not received.
- **Zero denominator:** not scored. **Min population:** 1 repo.
- **Threshold:** prevailing median, like TR-02.
- **Limitations:** a service repo written very differently from its GitHub name isn't linked (close matches are listed); archiving repos shrinks the denominator.
- **Open items:** none for v1 (OD-10 settled by the TR-02 working rule).

#### TR-03 Application confirmation rate
- **Why it matters:** An application inventory confirmed by its owners is the foundation for tiering, scoping (including SOX), and every per-app denominator.
- **Numerator:** apps owned by the family whose named owner confirmed the inventory record within the current confirmation cycle.
- **Denominator:** apps owned by the family in the inventory snapshot, active or in-build.
- **Exclusions:** decommissioned apps (counted as information).
- **Zero denominator:** N/A. **Min population (proposed):** 1.
- **Source system:** Arch app inventory (ServiceNow CMDB later).
- **Limitations / gaming risks:** a confirmation can be a single click; an app can be marked decommissioned to leave the denominator.
- **Planned counter-measures:** counts of apps decommissioned and apps that changed owner; Arch spot-checks.
- **Open items:** OD-12, OD-13.

#### DA-01 Data ownership rate (added by the owner, 4 Nov 2026; building block Accountability, risk category Data)
- **Why it matters:** Data with no named owner has nobody accountable for its quality, its access or how long it is kept. Knowing which datasets a family relies on, and who owns each, is the foundation for every data control.
- **Numerator:** datasets the family uses (database tables, files, feeds) that are recorded in the data inventory with a named, current owner.
- **Denominator:** datasets the family uses, as listed in the data inventory at month-end.
- **Exclusions:** datasets retired in the month (counted as information).
- **Zero denominator:** N/A. **Min population (proposed):** 3.
- **Source system:** data inventory, to be confirmed (OD-40). Until a file arrives the metric shows "planned, no source yet" and is left out of every score.
- **Limitations / gaming risks:** the inventory can name an owner who has left; a family can leave datasets off its list; "uses" needs a clear rule (read, write, or both).
- **Planned counter-measures:** owner must be a current person in HR; information counts of datasets added and retired; Tech Risk samples applications against the list.
- **Open items:** OD-40 (source, layout, meaning of "uses"), OD-31 (risk-register link).

### Modernization (MOD; provider: hosting platform)

#### SE-06 EOL components (platform-hosted)
- **Why it matters:** Components past vendor end-of-support no longer receive security fixes.
- **Numerator:** platform-hosted apps with at least one runtime, OS, framework or database component past its vendor end-of-support date.
- **Denominator:** platform-hosted apps owned by the family.
- **Scope:** apps on the in-house hosting platform only. The off-platform estate is shown as "Not assessed" with its app count.
- **Override:** any Tier 0/1 and internet-facing app with an EOL component makes the metric Red, and the block is capped at 49.
- **Source system:** hosting platform component inventory plus an EOL reference dataset (to confirm).
- **Limitations / gaming risks:** moving apps off-platform; EOL reference data lag; a wrong internet-facing flag.
- **Planned counter-measures:** counts of off-platform apps and moves; EOL exceptions shown; internet-facing flag confirmed in TR-03.
- **Open items:** OD-25, OD-26.

---

## 4. Control framework mapping

The CSF categories refer to NIST CSF 2.0 (Feb 2024). Scorecard metrics are not SOX controls: a Y means the metric gives a supporting indicator for that ITGC domain, not control evidence. ITGC domains: APD = access to programs and data; PC = program change; CO = computer operations; SDLC = program development.

| ID | Metric | NIST CSF 2.0 function / category (subcategory) | Internal policy/standard (to confirm) | SOX ITGC relevance |
|---|---|---|---|---|
| TR-01 | Repo mapping rate | IDENTIFY / ID.AM (ID.AM-02) | App inventory / CMDB standard; SDLC standard | Y — PC (completeness of the code population) |
| TR-02 | Repo good-hygiene rate | PROTECT / PR.PS (PR.PS-06); ID.AM (ID.AM-08) | Secure SDLC / source code management standard | Y — PC (peer review and branch protection) |
| TR-03 | Application confirmation rate | IDENTIFY / ID.AM (ID.AM-02); GOVERN / GV.RR (GV.RR-02) | App inventory / CMDB standard | Y — scoping (in-scope app population) |
| RE-01 | Tier 0/1 DR test completed (12 months) | ID.AM (ID.AM-05), ID.RA (ID.RA-04); GV.OC (GV.OC-04) | ITDR / BCM standard | N — operational resilience |
| RE-02 | Resiliency testing coverage | PR.IR (PR.IR-03); ID.IM (ID.IM-04) | ITDR / DR standard | N — operational resilience |
| RE-03 | Resiliency testing completion (passed) | ID.IM (ID.IM-02); RC.RP (RC.RP-01); PR.IR (PR.IR-03) | ITDR / DR standard | N — operational resilience |
| UN-01 | Critical and SWE incidents | RS.MA (RS.MA-03); PR.IR (PR.IR-03, PR.IR-04) | Incident management standard | Y (partial) — CO (incident management) |
| UN-02 | Postmortem actions overdue | RS.AN (RS.AN-03); ID.IM (ID.IM-03) | Incident / problem management standard | Y (partial) — CO (problem management) |
| UN-03 | Client incidents | Indirect: GV.OC (GV.OC-04); PR.IR (PR.IR-03) | Client service / incident standard | N |
| SE-01 | Checkmarx SAST pass rate | ID.RA (ID.RA-01, ID.RA-06); PR.PS (PR.PS-06) | Vulnerability management standard; AppSec standard | N — security (supporting) |
| SE-02 | Checkmarx SCA pass rate | ID.RA (ID.RA-01, ID.RA-06); PR.PS (PR.PS-02) | Vulnerability management standard; open-source usage standard | N — security (supporting) |
| SE-03 | Secrets overdue rate | PR.AA (PR.AA-01); ID.RA (ID.RA-01); DE.CM (DE.CM-09) | Secrets management standard | Y (partial) — APD |
| SE-04 | CyberArk vaulting | PR.AA (PR.AA-05, PR.AA-01); DE.CM (DE.CM-03) | PAM / IAM standard | Y — APD (privileged access) |
| SE-05 | SailPoint governance | PR.AA (PR.AA-01, PR.AA-05) | IAM / identity governance standard | Y — APD |
| SE-06 | EOL components | PR.PS (PR.PS-02); ID.AM (ID.AM-08), ID.RA (ID.RA-01) | Technology lifecycle / EOL standard | N — supporting CO |
| TE-01 | Change ticket adoption | ID.RA (ID.RA-07); PR.PS (PR.PS-01) | Change management standard | Y — PC (core: authorised changes) |
| TE-02 | Release revert rate | ID.RA (ID.RA-07); PR.PS (PR.PS-06); ID.IM (ID.IM-03) | Change mgmt / release standard | N — quality indicator (supporting PC) |
| TE-03 | Defect rate | PR.PS (PR.PS-06); ID.IM (ID.IM-03) | SDLC / testing standard | N — quality indicator (supporting SDLC) |
| TE-04 | AI-assisted commits (info) | PR.PS (PR.PS-06); GV.PO | AI acceptable use / secure coding standard | N |

### 4.1 Not covered in v1 (D5: no new metrics in v1)

| Area | Why it is not in v1 |
|---|---|
| User access review (UAR) completion | A core SOX APD control already tested by audit; needs campaign-to-family attribution. v2 candidate. |
| Leaver access removal timeliness | Needs an HR-to-identity join at account level. |
| Change segregation of duties | Needs deployer, author and approver identity joins. |
| Emergency change volume and retrospective approval | Not scored in v1. |
| Backup and restore testing | A SOX CO control, distinct from RE-03; data not ready. |
| Batch / job scheduling failures | Stays with ITGC testing. |
| Third-party / vendor risk | Assessments are vendor-level, not family-level. |
| Data protection | No family-attributable automated source yet. |
| MFA / authentication coverage | Mostly enforced centrally through SSO. |
| Logging and security monitoring coverage | Source in flux (SIEM migration). |
| Infrastructure / host vulnerabilities | Not attributed to families yet; a known gap in the Security block. |
| Cloud posture, DAST, penetration test findings | Uneven tool coverage; attribution not defined. |
| EOL off-platform estate | Shown as "Not assessed" on SE-06; full scope is v2. |
| Security awareness / training | A people metric, not product-team behaviour. |
| Capacity / performance (SLOs) | No consistent SLO practice yet. |
| Incident response exercises | Not attributable to families. |

---

## 5. Open definitions register

| # | Item | Metric(s) | Owner | State (3 Nov 2026) |
|---|---|---|---|---|
| OD-01 | Overdue denominator = open at month-end plus closed in the month (O-5). | SE-03, UN-02 | Scorecard owner | Decided; **not applicable yet** to UN-02 (no closed date in the file). SE-01/02 use Cyber's policy result instead. |
| OD-02 | SE-01/02 Green tolerance 5.0%. | SE-01, SE-02 | Scorecard owner, with the CISO | **Superseded** (owner, 3 Nov): prevailing median from the month's data. |
| OD-03 | TE-01 Green tolerance 80%; Red limit 60%. | TE-01 | Scorecard owner, with Change Mgmt | **Closed** (owner, 8 Nov 2026): TE-01 now uses the prevailing median. |
| OD-04 | Inclusive/exclusive convention. | All | Tech Risk | Built as stated in 1.2. |
| OD-05 | Reporting timezone America/New_York. | All | Tech Risk | Built. |
| OD-06 | Policy/standard references in Section 4. | All | Each provider, compiled by Tech Risk | Open |
| OD-07 | Behind-peers gap for non-% metrics. | UN-03, TE-03 | Tech Risk | Open (UN-01 not flagged) |
| OD-08 | How items are placed with families. | All | Each provider, with Tech Risk | Built for measured metrics (HR + family owners file; postmortem assignees). |
| OD-09 | Inventory snapshot source and flags. | TR-03, UN-01, UN-03, SE-05, SE-06 | Arch, with ITDR | Open |
| OD-10 | Definition of "active repo"; platforms in scope. | TR-01, TR-02, TE-04 | Arch | Working rule (owner, 3 Nov 2026): not archived, not a fork, activity in 90 days. Platforms: open |
| OD-11 | Freeze the repo hygiene checklist. | TR-02 | Arch | **Closed** (owner, 3 Nov 2026): 5 checks, one point each, partial credit |
| OD-12 | App confirmation cycle and attestation. | TR-03 | Arch | Open |
| OD-13 | Mandatory inventory flags. | TR-03 | Arch, with ITDR | Open |
| OD-14 | ITDR standard reference; test plan and BIA review definitions. | RE-01, RE-02 | ITDR | Open |
| OD-15 | RE-03 pass criteria and test scope. | RE-03 | ITDR | Open |
| OD-16 | Incident source and multi-family rule. | UN-01 | Ops | Built: postmortem file; counts once in each family (owner, 2 Nov). |
| OD-17 | Keep dry-run data for rolling windows. | UN-01, UN-03 | Tech Risk | **Closed**: no rolling windows. |
| OD-18 | Action scope, due-date changes, no-due-date rule. | UN-02 | Ops | Built: in-scope incidents, blank ETA due 30 days after created. Due-date change approval not checked (no data). |
| OD-19 | Client incident definition and source. | UN-03 | Ops, with Client Service | Open (Coming soon) |
| OD-20 | Finding fingerprint, re-open rule, SCA counting unit. | SE-03 | Cyber | Open (SE-01/02 use Cyber's policy) |
| OD-21 | Exception approval authority and duration. | SE-03, SE-06 | Cyber (CISO) | Open |
| OD-22 | Secret "remediated" = rotated/revoked. | SE-03 | Cyber | Open |
| OD-23 | CyberArk eligibility, discovery source, attribution. | SE-04 | IAM | Open |
| OD-24 | SailPoint eligibility and integration level. | SE-05 | IAM | Open |
| OD-25 | EOL reference source, internet-facing flag owner, exceptions. | SE-06 | Hosting platform, with Arch | Open |
| OD-26 | "Not assessed" status placement. | SE-06 | Tech Risk | Open |
| OD-27 | Emergency change treatment. | TE-01 | Change Mgmt | Open (emergency changes counted like any other) |
| OD-28 | Minimum population for change and scan metrics. | TE-01–03, SE-01/02 | Tech Risk | **Closed**: scored from the first item (UN-02 stays 3, owner 4 Nov). |
| OD-29 | Defect definition; whether a hotfix counts as a revert. | TE-02, TE-03 | Change Mgmt | Open (a hotfix is not a revert today) |
| OD-30 | AI-assisted commit detection. | TE-04 | Change Mgmt / Developer Platform | Open |

---

## 6. Change log

| Version | Date | Change summary | Approved by |
|---|---|---|---|
| v0.3 | — | Design brief baseline. | Not approved |
| v0.4 | 2026-10-30 | Owner decisions D1–D7: fixed tolerance thresholds, behind-peers flag, coverage rule for Best, one minimum-population rule, RE-03 passed tests only, central IAM eligibility, SE-06 "Not assessed", exceptions and SLA clock, rolling UN-01/UN-03, info counters, control mapping, OD-01 to OD-30. | Pending |
| v0.5 | 2026-10-31 | Worst-metric cap (D-28, O-15); SE-04/05 pass/fail (D-50); overdue denominator (O-5); quarterly recalibration (O-8); New York timezone; TR-02 breakdown (D-51). | Pending |
| v0.6 | 2026-11-03 | Brought in line with what v1 measures. New Section 0 for the six measured metrics, as the code counts them. Removed every made-up starting threshold; planned metrics have none until measured. Thresholds worked out each month (no quarterly recalibration); behind peers only for Policy thresholds; no rolling windows; minimum population 1 except UN-02 (3); SE-01/02 are Checkmarx pass rates; UN-01 is a count; UN-03 coming soon; data contracts moved to v2. Register states updated. TE-02 client impact is an automatic Red rule: block capped at 49 (owner, 3 Nov; the five letters became six building blocks on 4 Nov). Thresholds set once by calibration then fixed and reviewed quarterly; scoring by colour, not size of miss, stated. | Pending: Head of Tech Risk |
