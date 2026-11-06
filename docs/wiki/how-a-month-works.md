# How a month works

TRUST turns provider files into one official, locked scorecard each month. This page follows one month from the first file to the lock, and to a reopen if something must change.
The picture is [month-flow](diagrams/month-flow.svg) ([source](diagrams/month-flow.mmd)); the diagrams are kept outside this repo.

![One month, from files to the official record](diagrams/month-flow.svg)

Words in *italics* are explained in the glossary (kept outside this repo). Rules are in [scoring rules](scoring-rules.md). The jobs, in order, are in the [runbook](runbook.md). The tables are listed in [doc 11](../design/11_data_model_v2.md).

**Every file and every month stands alone (owner decision, 2 Nov 2026).** Each file uploads on its own with no other file present, and upload only keeps the file. Files are read and joined by mapping (steps 2 and 3), which can be re-run at any time. A month can be loaded, scored and locked on its own, in any order, with whatever files have arrived. Earlier months only add change arrows and trends.

**A month is either open or locked.** Nothing else. Open means files can be uploaded and the scorecard updated. Locked means the month is sealed and refuses changes until it is reopened.

## The steps

| # | Step | Who | What happens | Where it lives |
|---|---|---|---|---|
| 1 | **Upload** | Tech Risk | A provider's file is uploaded for a month (Data sources page, or `python manage.py upload`), in any order. The file is checked **on its own** at once: junk (unreadable, the wrong file, every row unusable) is refused and not stored; anything else is kept, with its warnings shown (owner, 3 Nov 2026). What is kept is the file **cut down to the columns TRUST uses** (the HR file also to the CTO's line), with the SHA-256 fingerprint of the file as received, its name, size, who uploaded it, when, and the SharePoint link (owner, 2 Nov 2026). | `backend/trust/store.py`, `checks.py`; tables `submission`, `kept_file`; the ITDR application and DR tests files also go into `itdr_application` and `dr_test` |
| 2 | **Map** | Tech Risk, any time | Reading the kept files with the current column map and settings. Re-run it after fixing a column name, loading HR, or changing a setting; nothing is uploaded again. TRUST reads the provider's file as it is, through the feed's column map, written from the real file ([doc 17 §3](../design/17_intake_architecture.md)). A row without its own key is **set aside** and listed with its reason. A field a metric needs that is not in the file means that metric shows No data. Checks that need two files (an action's incident in the postmortem file, people and apps found) run here, only when both files are loaded, as warnings. | `backend/trust/mapping.py`, `intake/`; table `month_result` (kind `mapped`) |
| 3 | **Place with families** | part of mapping | Done fresh every time mapping runs, from whatever files are loaded. Every item is placed with a person or an app, then a team, then a *product family*. Anything that cannot be placed, including when HR, the owners file or the inventory has not been uploaded yet, is **Not yet mapped**. It is counted and shown on the Firm position page, never dropped (D-73). | `backend/trust/linking.py`, `mapping.py` |
| 4 | **Score** | Tech Risk | Adds the items up per family and metric (`measure.py`), sets each status, then building blocks, family TRUST, firm figures (the firm is scored from its pooled results, owner 4 Nov 2026) and changes (when the previous month is scored). Each run is saved and never edited, with the git commit and a hash of the settings it used. Uploading a file does **not** re-score the month. Nine metrics are measured today (see [scoring rules](scoring-rules.md)). | `backend/trust/score_month.py`, `scoring.py`; table `month_result` (kind `scored`) |
| 5 | **Publish** | with the update | Puts every scored month into the page's data, with change arrows, trends and the *watch list* worked out from the neighbouring months. The website builds its page from this on every visit. | `backend/trust/publish.py`; table `published_file` |
| 6 | **Review** | families, Tech Risk | Steps 2 to 5 together are **Update the scorecard** on This month. It runs in the background, one update per month at a time. Family leads read their own page, add explanations and raise data queries. Tech Risk answers queries, and **acknowledges** each warning from the checks. Comments never change a score. | `backend/trust/jobs.py`, `lock.py`; tables `comment`, `warning_ack`, `event_log` |
| 7 | **Lock** | Tech Risk | **By hand on This month** (owner, 3 Nov 2026); there is no lock on a set date. The lock refuses if the month isn't scored, if a newer file arrived after the last update, if a warning isn't acknowledged, or if an update is running. It **seals** fingerprints of the scored result, the files, the settings and the comments, and **freezes the month's page as shown**. The month then refuses uploads and updates. Months can be locked in any order. | `backend/trust/lock.py`; table `month` |
| 8 | **Printing** | anyone, any time | **TRUST makes no PDFs** (owner, 2 Nov 2026; replaces the PDFs at lock in D-102, which caused bad problems). The CTO view and each family page have a **Print view** button that lays the page out for paper with every section expanded; people then use their browser's own Print (Ctrl+P, or Cmd+P on a Mac) to print or save. Printing any page with the browser also opens every collapsed section first. A table sorted on screen (by clicking a column head) prints in that order, with the sorted column marked. The locked month's official record is its data in TRUST. | `frontend/index.html` (Print view, print styles) |
| 9 | **Reopen** | Tech Risk | A locked month never changes silently. **Reopen** needs a reason, which is kept in the record, and the earlier seal stays in the activity log. The month is open again: upload the corrected file, update the scorecard, and lock again. There is no separate restatement process; reopening stands in for it. | `backend/trust/lock.py`; tables `month`, `event_log` |

Once a month is older than 24 months, **retention** removes it (locked or not) and drops older runs of newer months. The scheduler add-on runs it monthly ([deployment](deployment.md#retention)).

## The timeline

Providers usually send in the first week after month end, families review their page the week after, and Tech Risk locks soon after that. The CTO view is then the pre-read for the leadership meeting. This is a guide for the current month, not a gate: TRUST has no business calendar and enforces no dates, and historical months can be loaded at any time.

A provider that sends nothing has its metrics shown as **No data**: nothing is carried over from last month (D-76). TRUST does not mark files as late; see the [runbook](runbook.md#when-a-file-is-missing-or-late) for what to do.

## Data contracts

Once a feed's data contract is approved on the Data dictionary page (formal = approved; owner, 4 Nov 2026), two things hold every month: the upload check compares the file's columns with the contract and warns on any difference (acknowledged before the lock, like any other warning), and the scoring step uses the file only for the metrics the contract lists; any other metric that reads it shows No data with the reason. A new contract version, approved by Tech Risk, lifts both. Contracts are kept in the table `data_contract`.

## What can go wrong, and what TRUST does

| Situation | What TRUST does |
|---|---|
| The provider's file has its own column names, order or date format | That is normal: the file is the layout. TRUST reads it through the feed's column map, written from the real file. |
| A field a metric needs is not in the file | The file loads. Only that metric shows **No data** this month, with a note naming the field. |
| Some rows cannot be read | The file is accepted; those rows are set aside with a reason; the warning must be acknowledged on This month before the lock. If **every** row is unusable, the file is refused at upload. |
| The file is junk (unreadable, the wrong file) | Refused at upload with the reasons, and not stored. The attempt is in the activity log. |
| The same file is uploaded again | Same bytes: "already received", no change. A different file for the same feed and month replaces the accepted one at once, with no approval; both are kept and the replacement is noted (D-92). |
| A file is uploaded with no other files loaded (e.g. SCA alone) | It loads. Upload never looks at other files. Its rows show as Not yet mapped until HR, the owners file, the inventory and the repo list are loaded and the month is updated again. |
| No earlier month is loaded | The month is scored on its own. Change arrows, trends and Chronic Red appear once earlier months are scored. |
| HR, the owners file or the inventory is replaced | Update the scorecard again; every file is re-placed with the new ones. Nothing needs re-uploading. |
| A column name or a setting is changed | A column name: fix it in the column map and **upload the file again** (TRUST only kept the columns it found), then update. A setting: update the scorecard; for the HR file's CTO setting, upload HR again. |
| A month is already locked | Uploads and updates are refused. Reopen it with a reason. |
| The original on SharePoint is edited after upload | The fingerprint recorded at upload no longer matches the original. Get the original back, or upload the edited file as the new version. |

## Where to go next

- The rules behind steps 3 and 4: [scoring rules](scoring-rules.md), [data sources](data-sources/README.md).
- The tables behind each step: [doc 11](../design/11_data_model_v2.md) and [deployment](deployment.md#the-tables).
- The jobs, in order: [runbook](runbook.md).
