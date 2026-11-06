# Deployment

How TRUST is put on the platform and kept safe. It is built with the **Heroku Python buildpack** and runs as one app (a container), with **Postgres as an add-on** to it (owner, 2 Nov 2026). The picture is [deployment](diagrams/deployment.svg) ([source](diagrams/deployment.mmd)); the diagrams are kept outside this repo.

![Where TRUST runs](diagrams/deployment.svg)

## The pieces

| Piece | What it is |
|---|---|
| The app | Built by the Python buildpack from the repo. The website is `backend/trust/web.py` (Flask) run by gunicorn: it shows the published scorecard and takes uploads, updates, comments, lock and reopen (below). The same steps are also commands (`bin/trust`). |
| Postgres add-on | The database attached to the app. It gives the app its connection string in **`DATABASE_URL`**. Everything TRUST keeps goes there: the cut-down files, the upload register, each month's mapped and scored results, and the published page ([tables](#the-tables)). |
| Access add-on | **The company's add-on container in front of TRUST handles who can get in** (owner, 2 Nov 2026). It is **not Entra**, and TRUST has no sign-in of its own. See [access](#access). |
| SharePoint | The link to each original file is recorded. TRUST also keeps its own copy, cut down to the columns it uses, with the hash of the file as received (owner, 2 Nov 2026). |

There is **no CI** and there are **no PDFs** (owner decisions, 2 Nov 2026): nothing runs tests on deploy, and there is no Chromium or document folder.

**Why the database and not the app's disk.** The app's own disk is wiped every time it restarts (at least once a day, and on every deploy), and one-off commands run on a separate copy of the app that the website can't see. So TRUST keeps nothing on disk when `DATABASE_URL` is set. Without it (on a laptop, in tests) everything goes in the `store/` folder instead.

## What the buildpack uses

All in the top folder of the repo:

| File | What it does |
|---|---|
| `requirements.txt` | What the buildpack installs: Flask, gunicorn and the Postgres driver (`psycopg`), each at an exact version. The back end uses Python's standard library plus `openpyxl`, to read Excel files (the ITDR application and DR tests files). `requirements-dev.txt` adds pytest for running the tests locally. |
| `.python-version` | The Python version: `3.13`. |
| `Procfile` | How the app starts (below). |
| `bin/trust` | Runs a TRUST command from anywhere: `bin/trust map 2026-10`. Use it for one-off commands on the platform. |
| `migrations/` | Numbered SQL files that set up the tables. **Append-only**: never edit one that has run; add a new numbered file instead. |

## The Procfile

Two lines. **They work without a shell** (4 Nov 2026): the platform runs each line directly, so there are no `VAR=value` prefixes or `${...}` in them. A line like `PYTHONPATH=backend python …` fails there with exit code 127 ("not found").

- `web: gunicorn wsgi:app --worker-class gthread --threads 4 --timeout 60 --access-logfile -`: the website. It uses threads (4 per worker) so one long upload doesn't block the health check. `wsgi.py` (top of the repo) finds the code in `backend/` by itself; `gunicorn trust.web:app` on its own fails with "No module named 'trust'". Gunicorn reads `PORT` (set by the platform) and `WEB_CONCURRENCY` (how many workers; the platform sets it by dyno size) from the environment itself.
- `release: python manage.py migrate`: `manage.py` finds the code in `backend/` by itself. It runs on every deploy, before the new version takes traffic. It sets up or updates the tables from `migrations/` and is safe to repeat. If a migration that already ran has been edited, it stops the deploy and names the file. It also stops if the database isn't UTF-8 (hosted Postgres add-ons are), and if TRUST's tables are already there but it has no record of building them (for example, SQL run by hand): start from an empty database instead.

## Deploying

1. Create the app with the Python buildpack, and attach the Postgres add-on. Check that `DATABASE_URL` now appears in the app's settings (config vars). **Don't copy it anywhere else**: it contains the database password.
2. Push the repo (the `main` branch). The buildpack installs `requirements.txt`, then the release line sets up the tables.
3. Open the app. Before anything is published it shows the real site for the current month, with no data: every score reads "Not scored yet" and Data sources lists the files still to come (owner, 4 Nov 2026). While there are no families it opens on Tech Risk, where files are uploaded. **The month list** shows every month with a score, every month with uploaded files (as "Not scored yet" until it is updated) and always the current month, so a month's files can go in before it is scored; uploading for a month not in the list reloads the page on that month. The site opens on the oldest open month that has a score, else the newest scored month. **The page is always the one deployed now**: the website builds it from `frontend/index.html` on every visit, with the published data in it, so a new deploy shows at once. `/healthz` answers `ok` when the app can reach the database (for the platform's health check).
4. Set the CTO's SAM_ACCOUNT in `config/settings.json` (`hr_root_sam_account`) before the first HR upload. Optional: `code_repo_url` (the repo's address on GitHub Enterprise Server) makes every metric card link to the code behind the metric, lines highlighted, at the deployed commit (`SOURCE_VERSION` when the platform sets it, else `code_ref`, default `main`). The settings and column maps are files in the repo, so a change to them is a commit and a deploy.

## The TEST environment

TEST is a **second app built from the same code**, with its own Postgres add-on, so people can try the scorecard before the real files exist (owner, 4–5 Nov 2026). The code never differs between the two apps, and **the app itself holds no made-up data and no seeding step**: the made-up files are written by a script on a laptop and uploaded to TEST like any provider file. Production never sees them.

| Config var | On TEST | On production |
|---|---|---|
| `TRUST_ENV` | `test` (shows the **TEST · synthetic data** badge and banner) | not set (badge reads **Live data**) |
| `TRUST_HR_ROOT_SAM_ACCOUNT` | `cto.demo` (the made-up CTO; overrides `hr_root_sam_account` in `config/settings.json`) | not set |

Filling TEST, from the repo folder on a laptop:

1. `python tools/make_test_data.py --out demo-files` writes three months (August to October 2026) of made-up provider files for eight made-up families into `demo-files/<month>/`, from a fixed random seed (same files every time), plus `manifest.json` and a `README.txt`. Options: `--months 2026-07 2026-08 …`, `--families 10`, `--seed 3`.
2. `python tools/upload_test_data.py --site https://<the TEST app> --folder demo-files` uploads every file through the normal upload (with its checks) and presses Update the scorecard for each month, waiting for each to finish. Standard library only. If roles are on, run it from somewhere the identity add-on lets through, or pass the add-on's headers with `--header "Name: value"` (uploads need the Tech Risk role). `--no-update` uploads only; `--months 2026-10` does one month.
3. Lock the months on This month if the locked look is wanted. To start TEST again from nothing: reset its database on the platform (this loses everything on TEST), deploy, and run step 2 again.

What the files show: every measured metric has Green, Amber and Red across the families; Payments has a client-impact change in October (TE-02 Red by the automatic rule); Client portal has no Tier 0/1 application; the planned metrics stay planned (they have no source). The one warning per month to acknowledge is real (DR tests with no Status).

## Running a month on the website

Everything is done on the website (owner, 3 Nov 2026). Anyone who gets past the access add-on can do it; they type their name, which is recorded on every upload, update, comment, lock and reopen (and remembered in their browser).

1. **Upload** each file on **Data sources** (choose the input file, then **Upload**; pick the month the file is for). TRUST checks it at once: junk is refused with the reasons; otherwise it keeps only the columns it uses and shows what it kept and anything to look at. Before anything is published, the site's first page has its own small upload form.
2. **Update the scorecard** on **This month**: reads the newest file of every feed for the month, places every row with a family, scores it and publishes it. **It runs in the background** (owner, 4 Nov 2026): the button answers at once, the page says "Updating…" and checks every 3 seconds, then reloads when it's finished. With real files this can take a minute or more, which used to run past the platform's time limit and show a 503. Only one update per month runs at a time; Lock waits for it. Recent activity shows "started updating", "finished updating" (with how long it took) or "update stopped with a problem" (with the step and the reason; the full error is in the platform's logs). An update with no finish after 20 minutes (for example, a restart part-way) counts as stopped: press Update again.
3. **Acknowledge** each warning from the checks on **This month**, then **Lock**, when the month is right. Done by hand for now; a lock on a set date may come later. The lock refuses if a newer file arrived after the last update ("update the scorecard first"). Once locked, uploads and updates for that month are refused.
4. **Reopen** on **This month**, with a reason, if something has to change. Lock again when done.

Families add explanations, data queries and actions on their own page; Tech Risk answers queries on **This month**. Comments never change a score.

The same steps as commands (one-off on the platform: `heroku run bin/trust …`):

```bash
bin/trust upload tcc tcc_export.csv --month 2026-10 --by "Your Name" --link URL
bin/trust map 2026-10 --by "Your Name"
bin/trust score 2026-10 --by "Your Name"
bin/trust publish --by "Your Name"
bin/trust lock 2026-10 --by "Your Name"
bin/trust reopen 2026-10 --by "Your Name" --reason "Corrected TCC file"
```

A one-off command runs on the platform, so `upload` there needs the file on the platform; use the website for uploads.

### The website's addresses

| Address | What |
|---|---|
| `/` | The scorecard (or, before anything is published, the first upload page). |
| `/healthz` | `ok` when the app can reach the database (for the platform's health check). |
| `GET /api/month/<YYYY-MM>` | The newest upload per feed, the month's status, and its recent activity. |
| `GET /api/comments/<YYYY-MM>` | The month's comments. |
| `GET /api/items/<YYYY-MM>/<family>.csv` | A family's items for the month as a CSV file (the **Download my data** button on the family page). Cells Excel would run as formulas are quoted. |
| `/evidence.json` | The items behind every family's numbers, for the drill-down; written by each publish. |
| `GET /api/update/<month>/<job>` | How a background update is going: `running`, `finished`, `failed` or `stopped`. |
| `POST /api/upload`, `/api/update`, `/api/acknowledge`, `/api/lock`, `/api/reopen`, `/api/comments` | The changes. Each needs the person's name and the header `X-TRUST: 1`, which the page adds; a browser won't send it from another site without asking first, so another site can't make a change through someone's browser. Uploads are limited to `TRUST_MAX_UPLOAD_MB` (55). |

## The tables

The v1 data model has thirteen tables (plus `schema_migration`, TRUST's own bookkeeping) ([doc 11](../design/11_data_model_v2.md)), set up by `migrations/0001_kept_files_and_results.sql`, `0002_months_events_comments.sql`, `0003_warning_acknowledgements.sql` `0004_proposals_and_logging.sql`, `0005_log_item_views.sql`, `0006_itdr_applications.sql`, `0007_dr_tests.sql`, `0008_dr_test_kinds.sql`, `0009_data_contracts.sql` and `0010_retention.sql`. Every table and column has a description in the database (`COMMENT ON`).

| Table | What it holds |
|---|---|
| `submission` | Every upload, newest last per feed and month: who, when, file name, hash of the file as received, what was kept and not found, SharePoint link. |
| `kept_file` | Each uploaded file after it was cut down to what TRUST uses (HR: only the CTO's line), by the hash of what was kept. |
| `month` | A month's status (open or locked), who locked it and when, and the seal. |
| `month_result` | Every mapping and scoring run, with who ran it, the git commit and a hash of the settings. The newest is current. |
| `published_file` | What the website shows: `index.html`, `data.json`, `evidence.json`. |
| `event_log` | One line per upload (including refused ones), map, score, publish, acknowledgement, lock, reopen, comment, proposal, decision, item view and download, data contract, background update (started, finished, failed) and retention run. |
| `comment` | Families' explanations, data queries and actions, and the replies. |
| `warning_ack` | Who acknowledged each warning from the checks, when, and why. |
| `proposal` | A suggestion to change a metric's wording, add a metric or retire one, with who and when. Never edited. |
| `proposal_decision` | The answer to a proposal (approved, returned, declined or withdrawn), with the reason, who and when. A decision is a new row. |
| `itdr_application` | The ITDR application list: one row per application per upload (Ref, Application Name, Business Product Area, Recovery Tier). The newest upload for a month is the current list. |
| `dr_test` | Completed DR tests: one row per test per upload (tier, name, business area, ITDR lead, type, date, status, comment and the date read from it). The newest upload for a month is the current list. |
| `data_contract` | A request to onboard a data source (or a new version of one) and its decision: feed, version, provider, contact, what the file is, cadence, the columns TRUST may read, the metrics it may feed, status (draft, approved = formal, returned, withdrawn), who decided and when. Never edited; the decision columns are filled in once. |
| `schema_migration` | Which migration files have run, with the hash of each. |

Nothing in these tables is edited after it is written, except a month's status (by lock and reopen, each logged) and the published page.

## Database logins

The add-on gives **one** login, in `DATABASE_URL`, and TRUST uses it for everything. The earlier design's five separate logins (`trust_app`, `trust_engine`, `trust_intake`, `trust_signin`, `trust_auditor`), each with only the access its job needs, are **not used yet**: whether the add-on lets us create extra logins is still to be found out. Until then, keep the number of people who can see the app's settings small, because that login can read and change everything.

## Environment variables

| Variable | Used for | Notes |
|---|---|---|
| `DATABASE_URL` | The Postgres add-on's connection string. Set by the add-on. | When set, everything is kept in the database. Never put it in the repo, a ticket or a log. |
| `TRUST_DATABASE_URL` | The same, for local use when `DATABASE_URL` isn't set. | Optional. |
| `PORT`, `WEB_CONCURRENCY` | Set by the platform: the port to listen on, and how many website processes (set by the platform by dyno size). | |
| `TRUST_STORE_DIR` | Where things are kept when there is no database (default `./store`). | Local use and tests only. `store/` holds real data: never commit it. |
| `TRUST_SETTINGS`, `TRUST_THRESHOLDS`, `TRUST_ACCESS` | Other copies of `config/settings.json`, `config/thresholds.json` and `config/access.json`. | Optional. |
| `TRUST_COLUMN_MAPS` | Another copy of `config/column_maps.json`. | Optional. |
| `TRUST_GIT_SHA`, `SOURCE_VERSION` | The commit of the running code, recorded with every mapping and scoring run. `TRUST_GIT_SHA` wins; the platform sets `SOURCE_VERSION` at build time; without either, TRUST asks git. | Normally nothing to set. |
| `TRUST_MAX_UPLOAD_MB` | The largest upload the website accepts, in megabytes (default 55). | Optional. |
| `TRUST_ENV` | `test` marks the [TEST environment](#the-test-environment): the page carries the TEST badge and banner. | Never set on production. |
| `TRUST_HR_ROOT_SAM_ACCOUNT` | Overrides `hr_root_sam_account` from `config/settings.json`, so TEST can use the made-up CTO (`cto.demo`) with the same settings file as production. | TEST only. |
| `PG_BIN` | Folder with the Postgres 16 programs, for the tests that start a throwaway database. Default `/usr/lib/postgresql/16/bin`. | Development only. |

No sign-in variables and no document folder: access is the add-on container's job, and there are no PDFs (owner, 2 Nov 2026).

## Access

**The company's add-on container handles who can get in** (owner, 2 Nov 2026). It is **not Entra**, and nothing about it needs setting up inside TRUST.

- TRUST has **no sign-in of its own**: no login page, no OIDC, no tokens or claims to check, no session cookie. Don't build one.
- The earlier Entra design (`oidc` and `proxy` modes, the employee-ID claim) is **superseded**.
- The add-on identifies each person by **`user_id`, which is their SAM_ACCOUNT** in HR (owner, 2 Nov 2026).
- **Roles are on TRUST's side** (owner, 3 Nov 2026; `backend/trust/access.py`, settings in **`config/access.json`**). What the add-on's owner sets up: pass the SAM_ACCOUNT in a request header, and the person's AD groups in another, on every request, and **strip both headers if a browser sends its own**. What Tech Risk sets in `config/access.json`: the two header names, and which AD groups give CTO and leadership, Tech Risk, Head of Tech Risk and Auditor (optional: AD groups per family for delegates). Family leads and members are worked out from the owners file and HR. A `DOMAIN\user` or `user@domain` value and `CN=...` group names are understood; capitals don't matter.
- **While `user_header` is empty, TRUST runs open**: anyone past the add-on can do everything and types their name, and every page shows a banner saying so. **Once it is set, anyone not in a mapped group and not placed in a family is turned away** (warn people before the deploy; to undo, empty `user_header` and deploy again).
- With roles on, every page, data file, download and change is checked against [the roles page](roles-and-permissions.md); names are recorded from the account, not typed; family leads and members are sent only their own family's detail; item-detail views and downloads are logged.
- Every page is sent with `Cache-Control: no-store`, so scorecard data isn't kept in browser or proxy caches.

## Backups and retention

- **Back up the database.** Hosted Postgres add-ons usually have their own backups; check what this one does and how far back it goes before go-live.
- Keep **24 months** of everything (D-86): built, see [retention](#retention) below.
- TRUST keeps its own copy of each provider file, cut down (owner, 2 Nov 2026); keep the originals on SharePoint for the same period.

## Retention

Built 5 Nov 2026 (owner decisions). Two things grow in the database: every upload (the cut-down file and its rows), and **every Update of a month keeps a full copy of its mapped and scored results**. `python manage.py retention` keeps both in check:

- **Expired months.** TRUST keeps the current month and the 23 before it (24 in all, D-86). Anything older is removed whole: files, upload register, ITDR and DR-test rows, results, comments, warning acknowledgements, activity and the lock record. **Locked months go too**: the lock makes a month official, not permanent, and the originals stay on SharePoint. A kept file that a newer month also uses stays.
- **Old runs.** The newest run of each month is what the page and the lock use. Older runs are dropped once they are more than 30 days old.
- One line in the activity log (action `retention`) records what was removed, and the page is published again so its month list matches.

**It is a dry run unless you add `--write`.** `python manage.py retention` only lists what would go. The **scheduler add-on** runs `python manage.py retention --write` once a month (any day; the first of the month is fine); set it up with the app. A month with an update running is skipped and named. Options: `--months 24`, `--grace-days 30`, `--by "Name"`.

**Before the first real run, check the add-on's backups** (above): removal can't be undone from inside TRUST; the way back is the add-on's own restore.

## Gaps to close before go-live

- **Turn roles on**: the add-on's owner passes the SAM_ACCOUNT and AD groups headers; Tech Risk fills in `config/access.json` ([access](#access)). Until then anyone past the add-on can do everything.
- **Separate logins** with only the access each job needs, if the add-on allows them (see [database logins](#database-logins)).
- **Lock** is by hand on This month; a lock on a set date may come later. **Restatement** isn't built: Reopen stands in for it.
- What the database add-on's backups cover.
- **Memory:** a 30 MB HR file needs about 400 MB free in the web process while it is cut down. Check the app's memory size against the real HR file.
- **Settings in files.** `config/settings.json`, `column_maps.json` and `thresholds.json` change only with a deploy.
