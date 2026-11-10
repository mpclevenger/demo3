# Risk assessments (feed `risk_assessments`)

**What it is.** The risk assessment engine's results (owner, 9 Nov 2026): how exposed each assessed group is to
each risk **before any controls** (its inherent risk). The engine works this out from its drivers: questionnaire
answers and data-based checks. For now the results come to TRUST as a CSV.

**Layout** (one row per assessed group per risk; column names can be changed in `config/column_maps.json`):

| Column | What it holds |
|---|---|
| `Group` | The group the assessment was done on, usually an L4 ("Analytics"). |
| `Departments` | The HR Departments the group covers, separated by `;`. They match HR's Department column. |
| `Assessment date` | Any common date format. |
| `Risk ID` | The engine's risk ID, e.g. `air.cyber.01`. Metrics link to risks by this ID (`card.risks` in `config/metrics.json`); the risk files are in `config/risks/` (one file per domain, e.g. `air.cyber.yaml`, several risks inside). |
| `Applicable` | Blank or yes = counted; no or `NOT_APPLICABLE` = left out. |
| `Likelihood`, `Impact` | `LOW`, `MEDIUM`, `HIGH` or `CRITICAL`, any case. |
| `Drivers` | Optional: why, in plain words, e.g. the triggered drivers and their commentary, separated by `|`. |

**Elevated (proposed rule, owner 9 Nov 2026; to confirm with the Head of Tech Risk).** A risk is Elevated when
likelihood is High or Critical, and impact is High or Critical. Shown as "proposed" on the page.

**How it reaches a family.** Each group's departments are matched to HR's Department column (the same matching
as ITDR product areas, setting `area_match_min`); the group belongs to every family its departments land in. A
family takes the **highest** rating on each risk among its groups, and the page names the group behind it.
Groups that match no family are listed on the mapping result.

**Months.** Assessments aren't monthly: a month with no file uses the newest earlier upload and says which month
it came from. Retention (24 months) eventually removes the month an old file was uploaded in; by then the
assessment is long stale. An assessment older than 12 months is flagged on the page.

**Where it shows.** An "Inherent risk" section on each family page (Elevated risks first, the group behind each,
the drivers, the metrics that watch it) and an "Elevated for" line on each linked metric's dictionary card.
**It changes no score.** Stricter tolerance thresholds for Elevated families are a later phase (shown first as
"would be"; see the design note).

**Contact.** Tech Risk (risk assessment engine).
