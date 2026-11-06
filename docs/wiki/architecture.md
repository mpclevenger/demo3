# Architecture

Pictures first, then notes. Every picture has its Mermaid source (`.mmd`) next to a drawn `.svg` in `diagrams/`. The diagrams are kept outside this repo for now, so the picture links below stay broken until they are copied in. There is no tool that redraws them or checks them: edit the source and redraw by hand.

Contents: [system context](#system-context) · [deployment](#deployment) · [data flow](#data-flow) · [access](#access) · [lock and reopen](#lock-and-reopen) · [storage](#storage)

## System context

Who and what TRUST talks to. Source: [context.mmd](diagrams/context.mmd).

![TRUST in its surroundings](diagrams/context.svg)

- Providers do not log in. They send files to Tech Risk, who upload them (there is no provider API in v1, D-83).
- Who can get in is handled by the company's **access add-on container** in front of TRUST, **not Entra** (owner, 2 Nov 2026). See [access](#access).
- TRUST keeps a copy of every file, cut down to the columns it uses (HR also to the CTO's line), with the hash of the file as received (owner, 2 Nov 2026); the SharePoint link is still recorded.
- The month becomes official at the lock; the site is the main channel, nothing is posted elsewhere (D-102). TRUST makes no PDFs: people print from the screens with their browser's own Print (owner, 2 Nov 2026).

## Deployment

Where each piece runs. Source: [deployment.mmd](diagrams/deployment.mmd). Setup steps and variables are in [deployment](deployment.md).

![Where TRUST runs](diagrams/deployment.svg)

- TRUST runs as one app built with the Heroku Python buildpack, with Postgres as an add-on (`DATABASE_URL`, one login for now). The website and the one-off commands both use it; nothing is kept on the app's disk. Details: [deployment](deployment.md).
- No Chromium is needed: TRUST draws no PDFs.

## Data flow

### Overview

From a file to a number. Source: [data-flow-overview.mmd](diagrams/data-flow-overview.mmd).

![From a provider file to a number](diagrams/data-flow-overview.svg)

### Per source

Which file feeds which metric, and which files place items in a family. Source: [data-flow-sources.mmd](diagrams/data-flow-sources.mmd). **It must list every feed**; onboarding a new source is not finished until it is updated (D-105; [adding a source](data-sources/README.md#adding-a-source-or-a-providers-file-changing)).

![Which file feeds which metric](diagrams/data-flow-sources.svg)

Each feed has its own page in [data sources](data-sources/README.md).

## Access

**Changed 2 Nov 2026 (owner): access is not Entra.** The company offers an add-on container that sits in front of TRUST and handles who can get in. TRUST has **no sign-in of its own**: no login page, no Entra, no OIDC, no tokens or claims to check. Don't build one.

The earlier sign-in design (Entra `oidc` and `proxy` modes, the employee-ID claim, the sign-in diagrams) is **superseded**. The add-on identifies each person by **`user_id`, which is their SAM_ACCOUNT** in HR (owner, 2 Nov 2026).

**Roles are worked out on TRUST's side** (owner, 3 Nov 2026), in `backend/trust/access.py`, from two request headers the add-on passes: the person's SAM_ACCOUNT and their AD groups. Which headers, and which AD groups give which role, are set in `config/access.json`. Family leads and members are worked out from the product family owners file and HR (`user_id` to the HR row to the family; [doc 13 §2](../design/13_hr_dataset.md)). While `user_header` in `config/access.json` is empty, TRUST runs open. There is no row-level security in the database: the roles are enforced by the application. Which role may see and do what is on [roles and permissions](roles-and-permissions.md); setting it up is in [deployment](deployment.md#access).

## Lock and reopen

A month's life: open, then locked, and open again if it is reopened. Source: [lock-states.mmd](diagrams/lock-states.mmd). The steps in words: [how a month works](how-a-month-works.md).

![A month from open to locked, and reopened](diagrams/lock-states.svg)

- A month is either `open` or `locked`. There is no preview state and no restatement.
- **Lock** is by hand on This month (`backend/trust/lock.py`). It seals fingerprints of the scored result, the files used, the settings and the comments, and freezes the page as shown. A locked month refuses upload, map and score.
- **Reopen** needs a reason and is logged. The earlier seal stays in `event_log`.
- The rules are kept by the application. Nothing in the database stops a change on its own: the tables are append-only by convention, and only a month's status (by lock and reopen) and the published page are ever changed.
- No documents are drawn at lock (no PDFs, owner 2 Nov 2026).

Month overview, for reference. Source: [month-flow.mmd](diagrams/month-flow.mmd).

![One month, from files to the official record](diagrams/month-flow.svg)

## Storage

TRUST keeps 13 tables (plus `schema_migration`) in the Postgres add-on, set up by migrations `0001` to `0010` in `migrations/`. The list, with what each holds and what may change, is in [doc 11](../design/11_data_model_v2.md) and in [deployment](deployment.md#the-tables). Without a database (a laptop, tests) the same things are kept in the `store/` folder (`backend/trust/storage.py` chooses). There are no per-source schemas and no database diagrams: the model is small enough to read as a table.

## Security in one paragraph

Who can get in is the access add-on container's job. Inside TRUST there is **one database login**, the one the add-on gives (`DATABASE_URL`); separate logins per job are not used yet ([deployment](deployment.md#database-logins)). Roles are worked out by the application from the add-on's headers (above), not by the database. Item-level evidence (the items behind each family's numbers) leaves TRUST only through `backend/trust/evidence.py`, and item views and downloads are logged in `event_log`. Every page is sent with `Cache-Control: no-store`.
