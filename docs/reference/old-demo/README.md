# Kept from the old Streamlit demo (reference only)

The old demo (`trust-demo/trust_demo/`) was retired on 3 Nov 2026. These three files were kept because nothing else holds them:

- `trust_demo/scoring.py`: the only working code for rules the live back end doesn't do yet. These are the **behind-peers flag** (median of families, gap per metric), **Sharp drop** (TRUST down 10 or more points with at least 2 metrics worse), **Declining** letters (fell two months in a row), the **Override red**, **Overdue action** and **Data quality** watch items, **most improved**, and the watch list's **priority order and cap of 10**.
- `tests/test_scoring.py`: 32 rule tests (classification edges, threshold versions, zero denominators, Low confidence, Not Tier 0/1, rolling windows, carry-forward, caps, peers, trends, the watch list). Use them as a source of cases when the live scoring tests are written.
- `trust_demo/models.py`: only so the two files above run.

Run them on their own: `cd docs/reference/old-demo && python -m pytest -q tests` (32 pass). The main test run doesn't include them.

**These follow the old v0.4 rules, not today's.** They have no O-15 letter cap at 79, no pass/fail rule for SE-04/SE-05, no "every month stands alone" rule, and fixed thresholds instead of the prevailing median. Check every rule against [scoring rules](../../wiki/scoring-rules.md) before reusing it, and ask the owner before any scoring change (DEVELOPER_GUIDE.md).

Two design ideas from the demo that weren't kept as code:

- **Auditor evidence pack**: one CSV per month with a row per metric and submission. It held the threshold version used and who approved it, the file's hash, row count and uploader, reconciliation to the source, the validation result, the lock record and the code version. It also had a "verify hashes" button that recomputed each file's hash.
- **Threshold impact preview**: before a threshold change was approved, it showed which families' status would change in the month it takes effect, and refused changes that would reach back into a locked month.
