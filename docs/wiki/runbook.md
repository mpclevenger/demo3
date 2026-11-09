# Runbook for Tech Risk

What to do each month, in order. The reasons are in [how a month works](how-a-month-works.md). Almost everything is done on the website: **Data sources** to upload, **This month** to update the scorecard, answer queries, lock and reopen ([how](deployment.md#running-a-month-on-the-website)). The same steps exist as commands: `python manage.py …`. On the platform, `bin/trust …` is a shortcut for the same commands.

**Every month stands alone.** You can load, score and lock any month, in any order, with whatever files you have. Nothing waits for an earlier month or for another file ([scoring rules](scoring-rules.md)).

**Timing is a guide.** Providers usually send their files in the first week after month end, and Tech Risk locks a week or two later. TRUST has no business calendar and enforces no dates: a file can be uploaded, and a month locked, whenever you are ready.

Before you start each month: check that you have the HR file, the product family owners file and the app inventory you mean to use, and that you know who at each provider to contact (the contact list is still to be supplied; see [data sources](data-sources/README.md)).

## Set the tolerance thresholds (calibrate)

Done once, and again each quarter when Tech Risk reviews them. A *tolerance threshold* is the pair of numbers that sets a metric's colours: the Green tolerance (the edge of Green) and the Red limit (the edge of Red). Until you freeze them, TRUST works them out afresh each month from that month's own family results (the "prevailing median"). Calibrating pools several months you have already scored (say July to October 2026), works out the thresholds for each metric on the prevailing median, and freezes them in `config/thresholds.json`. Real policy thresholds are never touched.

- [ ] Score each month you want to use (`python manage.py score YYYY-MM`). A month that isn't scored is refused.
- [ ] Look first. This changes nothing: `python manage.py calibrate 2026-07 2026-08 2026-09 2026-10`. It prints, per metric, how many family results were used, the Green tolerance, the Red limit and the Amber band. A metric with fewer than 5 results is not set, and the table says why.
- [ ] When Tech Risk agrees, set them: `python manage.py calibrate 2026-07 2026-08 2026-09 2026-10 --write --by "Your Name"`. This edits `config/thresholds.json` (other settings and notes stay as they are).
- [ ] Deploy, then **Update the scorecard** for each open month. Locked months keep their sealed figures.

## 1. Upload the provider files

Open **Data sources**. Do this as each file arrives, in any order.

- [ ] Keep the original on the SharePoint site and copy its link.
- [ ] Choose the month, choose the input file, paste the link if you have one, type your name (it is recorded) and press **Upload**.
- [ ] Read the result. TRUST checks each file the moment it arrives, on its own, with no other file needed.
  - **Refused**: the file is empty, the month is locked, or it is junk (it can't be read, it isn't this feed's file, every row is unusable, or the HR file has nobody in the CTO's line). Nothing is stored; the reasons are shown and logged. Fix the file and upload again.
  - **Stored**: TRUST keeps only the columns it uses (the HR file only the CTO's line), with the fingerprint of the file as received. **Warnings** are shown straight away. A warning does not stop the file; it must be acknowledged before the lock (step 4).
  - If a column TRUST needs couldn't be found, the result says so. Fix the column name in `config/column_maps.json`, deploy, and **upload the file again**, because TRUST only kept the columns it found ([how](data-sources/README.md#change-a-column-name)).
- [ ] A corrected file for the same feed and month replaces the earlier one at once, with no approval. Upload as often as needed; both are kept.
- [ ] Upload does not change any score. Scoring is a separate step.

## 2. Update the scorecard

On **This month**, press **Update the scorecard**. It reads the newest file of every feed, places every row with a product family, scores the month and publishes the page.

- It **runs in the background**. The button answers at once, the page says "Updating…" and reloads when it is done. With real files it can take a minute or more.
- **One update per month at a time.** Lock waits for it.
- **Recent activity** shows "started updating", "finished updating" or "update stopped with a problem" (with the step and the reason). If an update stops because the app restarted, the month is freed at once: press the button again.
- Update again whenever something changes: a file added or replaced, a setting changed.
- Rows that couldn't be placed with a family show as **Not yet mapped** on Firm position. A large or new share means an HR or owners-file problem.
- Read the mapping **notes**. They say when a field a metric needs is not in the file (that metric shows **No data**) and list any rows set aside, each with its reason. Decide whether to ask the provider to add the field.

## 3. Queries and explanations

- [ ] Tell family leads their page is ready. They read it, add explanations (a comment on a metric, a building block or the whole family) and raise data queries.
- [ ] Answer each **data query** on **This month** and close it when settled. Comments never change a score.
- [ ] If a file is corrected, upload it and **Update the scorecard** again.
- [ ] Spot-check big moves on the watch list (automatic Red rules are off for now, owner 9 Nov 2026).

## 4. Check, acknowledge and lock

- [ ] Open **Validation checks** (Tech Risk's own page). It says whether the month is ready to lock: files received, scorecard up to date, warnings acknowledged, rows placed with families, tolerance thresholds in place, locked and sealed. Below that is one table of the month's files, and the thresholds, the calculation record and the activity.
- [ ] On **This month**, read each **warning from the checks** and **acknowledge** it (add a reason if useful). The lock refuses while any warning is unacknowledged. A warning whose wording changes needs acknowledging again.
- [ ] Choose **Lock** and confirm. Locking is by hand; there is no lock on a set date. The lock refuses if:
  - the month isn't scored, or was mapped again after it was scored;
  - a newer file arrived after the last update ("update the scorecard first");
  - a warning isn't acknowledged;
  - an update is running.
- [ ] What the lock does: it **seals** the month with fingerprints of the scored result, every file used, the settings and the comments (shown in the **Lock record** on This month), and **freezes the month's page as shown**. From then on uploads and updates for the month are refused. Comments after the lock are marked "received after lock" and never change the figures.
- [ ] TRUST makes no PDFs. For a paper copy, open the page, choose **Print view** and use the browser's own Print.

## 5. If something has to change after the lock

A locked month never changes silently. Choose **Reopen** on **This month** and type the reason. The reason is kept in the record, and the earlier seal stays in the activity log. The month is open again. Upload the corrected file, **Update the scorecard**, acknowledge any new warnings, and **Lock** again. There is no separate restatement process: reopening stands in for it.

Requests to change the metric dictionary (a definition, a new metric, a retirement) are saved under **Metric dictionary → Proposals**. The Head of Tech Risk decides there. An approval is a record only: the dictionary text and any scoring change are made in the code, with the owner's agreement.

## Retention runs by itself

The platform's scheduler add-on runs `python manage.py retention --write` once a month. It removes every month older than the 24 kept (the current month and the 23 before it), locked or not, and any mapping or scoring run that isn't the newest of its month once it is over 30 days old. One line in Recent activity says what went. To see what the next run would remove, without removing it, run `python manage.py retention` (a dry run). Details: [deployment](deployment.md#retention).

## Which database the commands use

On the platform every command uses the Postgres add-on (`DATABASE_URL`, set by the add-on); nothing is kept on the app's disk. On a laptop with no `DATABASE_URL`, everything goes in the `store/` folder. Details: [deployment](deployment.md).

**TEST is a separate app with its own database** and made-up data; nothing done there touches production, and nothing in production is made up. If TEST's data gets in a mess, reset its database and upload the made-up files again with `tools/upload_test_data.py` ([the TEST environment](deployment.md#the-test-environment)).

## When a file is missing or late

| Situation | Do this |
|---|---|
| A provider's file hasn't come | Chase the provider. Upload it when it arrives; the month is still open. TRUST does not mark files late. |
| A provider doesn't send this month | Lock without it. The metrics that depend on it show **No data**; the building block says how many metrics it is based on; no change arrow is shown for that family or the firm. Nothing is carried over from last month. |
| No other files loaded (for example SCA on its own) | Upload it anyway. Its numbers show on Data sources and Firm position as **Not yet mapped**. When HR, the owners file or the repo list arrive, upload them and update the scorecard; the rows are placed with families then. |
| No earlier month loaded | Score the month anyway. No change arrows, trends or Chronic Red are shown until earlier months are scored. |
| It arrives after the lock | A locked month refuses uploads. **Reopen** with a reason, upload the file, **Update the scorecard**, and **Lock** again. |
| The provider's file changes (columns renamed, reordered, added, other date format) | The file still uploads. If a field TRUST needs can't be found, update the feed's column map to the new header, **upload the file again** and update the scorecard. The new file is the layout now. |
| The original on SharePoint was edited | The fingerprint of what you uploaded no longer matches the original. Get the original back, or upload the edited file as the new version and say why. |

## Who to ask

Provider contacts are placeholders until the owner supplies the list. The first line of each [data source page](data-sources/README.md) names the provider; the contact line says "to be supplied".

## Change a metric

Everything about a metric except the counting itself lives in **`config/metrics.json`**, one section per metric (owner, 8 Nov 2026).

| To change | Edit in `config/metrics.json` | Also |
|---|---|---|
| A known limitation | `known_limits`: add a line `{"limit": "...", "mitigation": "...", "status": "Partly mitigated"}`, or delete one. None listed = no section on the card | Nothing else |
| Risks it watches | `card.risks`: the risk file names (without `.yaml`) from `config/risks/`, copies of the risk assessment engine's risk files | Add or replace the risk file in `config/risks/` |
| Card text (population, exclusions, when it counts) | `card` | Nothing else |
| Whether it's live | `status`: `Measured`, `In progress`, `Planned` or `Coming soon` (anything but Measured counts in no score) | A metric moving to Measured needs its counting code first |
| Name or formula labels | `name`, `numerator_label`, `denominator_label` | Nothing else |
| Phrases on the family page | `wording` (`outstanding` = what's short, `counts` = "n of d …") | Nothing else |
| Which files it needs | `counting.files` | |
| **How it is counted** | `counting` describes it | The metric's function in `backend/trust/measure.py`, and its test |
| Tolerance threshold | (not here) | `config/thresholds.json`; ask the owner first |

After an edit: run `python -m pytest -q tests` (it catches a broken file), then deploy.

- **Wording, cards, known limitations, risks and status** show on the site as soon as it is deployed, for every month.
- **A change to how a metric is counted** shows only after **Update the scorecard** is pressed for each month (Tech Risk, This month). Until then the site shows the old numbers under the new wording, so update every open month straight after deploying. Locked months keep their sealed numbers until reopened and updated.

Any scoring change is the owner's decision first (DEVELOPER_GUIDE).

