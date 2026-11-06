# Roles and permissions

For the person setting up access before go-live. TRUST has no sign-in of its own: the company's **access add-on container** in front of it decides who gets in (owner, 2 Nov 2026). This page says which roles TRUST needs, what each may see and do, and what TRUST needs from the add-on to enforce it. It replaces the Entra-based design in [doc 10](../design/10_identity_and_access.md).

Status: **built on TRUST's side, 3 Nov 2026** (`backend/trust/access.py`, `config/access.json`). Explicit roles come from **AD groups** (owner, 3 Nov 2026). It switches on when the add-on passes the person's SAM_ACCOUNT and AD groups and Tech Risk names those headers in `config/access.json` ([deployment](deployment.md#access)). Until then anyone past the add-on can do everything, and the page says so.

## The roles

| Role | Who | In one line |
|---|---|---|
| **CTO and leadership** | The CTO and the leaders below them | Read the whole scorecard. Change nothing, and comment nowhere: comments are made on family pages and flow up. |
| **Tech Risk** | Anyone in the Tech Risk team | Run the month: upload, update, acknowledge warnings, answer queries, lock and reopen. See everything. |
| **Head of Tech Risk** | One person (and a named deputy) | Everything Tech Risk can do; approves family delegates. |
| **Family lead** | The owners named in the product family owners file, and their delegates | Their own family: read, drill into the items, download, explain, query. |
| **Family member** | People in a family's line in HR | Their own family: read and comment. |
| **Auditor** | Named auditors, for the length of an engagement | Read everything, including the lock record and activity. No downloads, no changes. |

**How a person gets a role:**
- Explicit roles (CTO and leadership, Tech Risk, Head of Tech Risk, Auditor) come from **AD groups** named in `config/access.json` (owner, 3 Nov 2026). Who is in each group, and auditors' end dates, are managed in AD.
- **Family lead** and **family member** can be worked out by TRUST from files it already has. The product family owners file names each family's owners by email; the HR file gives each person's SAM_ACCOUNT and who they report to. A family's members are everyone under its owners in HR (the same "nearest owner above" rule that places their work with the family). Nobody keeps these lists by hand, and they follow HR every month.
- **Delegates** (owner, 3 Nov 2026: allowed): a family's AD group in `family_lead_groups` gives its members the lead's rights for that family; adding someone to the group is the approval.

## What each role may do

Y = yes · own = their own family only · N = no

| | CTO and leadership | Tech Risk | Head of Tech Risk | Family lead | Family member | Auditor |
|---|---|---|---|---|---|---|
| **Seeing** | | | | | | |
| CTO view and Firm position | Y | Y | Y | Y | Y | Y |
| A family's page | Y | Y | Y | own | own | Y |
| Other families' pages | Y | Y | Y | N (the firm's typical value only) | N | Y |
| Item detail ("What's driving it"), with people's names | Y | Y | Y | own | own | Y |
| Download a family's items (CSV; every download is logged with the name typed on the page) | N | Y | Y | own | N | **N** |
| Metric dictionary and Method pages | Y | Y | Y | Y | Y | Y |
| Data dictionary (every file TRUST reads, its checks and its data contract) | Y | Y | Y | Y | Y | Y |
| Data sources, This month, Validation checks | N | Y | Y | N | N | Y (read only) |
| Activity log and lock record | N | Y | Y | N | N | Y |
| **Doing** | | | | | | |
| Explain a score, raise a data query or action (family pages only) | N | Y (marked from Tech Risk) | Y | own | own | N |
| Comment on the CTO view or Firm position | N | N | N | N | N | N |
| Reply to and close queries and actions | N | Y | Y | own (reply only) | N | N |
| Upload files, acknowledge warnings | N | Y | Y | N | N | N |
| Update the scorecard | N | Y | Y | N | N | N |
| Lock a month | N | Y | Y | N | N | N |
| Reopen a month (with a reason) | N | Y | Y | N | N | N |
| Approve a family delegate | N | N | Y | N | N | N |
| Request a change to a metric, propose a new metric or a retirement (saved under Metric dictionary → Proposals) | N | Y | Y | N | N | N |
| Ask to onboard a data source, or for a new version of its data contract (Data dictionary → Onboard a data source) | Y | Y | Y | Y | Y | N |
| Decide a data contract request (approve = formal, or return with a reason; owner, 4 Nov 2026) | N | Y | Y | N | N | N |
| Decide on a proposal (approve, return, decline). Approving records the decision only; the change itself is made separately with the owner's agreement | N | N | Y | N | N | N |
| Change settings, column names, tolerance thresholds | N | Y, through a code change and deploy | Y | N | N | N |

Database access (the Postgres add-on's login) is separate from all of these: platform administrators only, and every use logged by the platform.

**Sub-teams.** Family pages and the drill-down group a family's people into sub-teams. Which HR column names the sub-teams is a setting, `subteam_hr_column` in `config/settings.json` (owner, 3 Nov 2026: configurable; Department for now, Supervisory Organization also works). Item detail shows each item's person by name.

## What TRUST needs from the access add-on

1. **Who the person is, on every request:** their SAM_ACCOUNT (`user_id`) in a request header.
2. **Their AD groups** in another header (names or `CN=...` distinguished names, separated by a comma unless set otherwise).
3. **Both headers removed** if a browser tries to send its own, so nobody can claim to be someone else.

Tech Risk then puts the two header names and the AD groups for each role in `config/access.json` and deploys.

## Wiring it up: checklist for whoever sets up access

Everything on TRUST's side is built and tested (`tests/test_access.py`). Wiring it up is configuration, not code.

1. **Agree the two header names** with the add-on's owner: one carries the person's SAM_ACCOUNT, the other their AD groups. Confirm the add-on **removes both headers if a browser sends its own**. Without that, anyone could claim to be someone else.
2. **Get the AD group names** for each role: CTO and leadership, Tech Risk, Head of Tech Risk, Auditor. Optionally, get groups per family for delegates. Family leads and members need no group: they come from the product family owners file and HR.
3. **Try it locally first.** Copy `config/access.json`, fill in the header names and groups, and point `TRUST_ACCESS` at the copy. Run the site, then send the headers yourself, for example `curl -H "X-User: jdoe" -H "X-Groups: TRUST-TR" localhost:8000/`. Check each role sees what [the table above](#what-each-role-may-do) says. In a browser, a header-setting extension does the same job.
4. **Warn people, then deploy.** Fill in `config/access.json` (`user_header`, `groups_header`, `groups`), commit and deploy. **From that moment, anyone not in a mapped group and not placed in a family is turned away, you included if your own group is missing.** Make sure the Tech Risk group is right before deploying.
5. **Check on the live site:** the banner saying "open" is gone; the page names who you are; a family lead sees only their family's detail; an auditor gets the read-only banner.
6. **To undo:** empty `user_header` in `config/access.json` and deploy. TRUST goes back to open mode. No data is touched either way.

## How TRUST enforces it (built 3 Nov 2026)

- **Who you are** comes from the header; the name recorded on every change is the person's HR name and account, not a typed name.
- **What you're sent:** CTO and leadership, Tech Risk, Head of Tech Risk and auditors get every family. Family leads and members get every family's scores and colours (the CTO view and Firm position are for everyone) but only their own family's numbers, reasons, comments and item detail; file details are left out.
- **Every change and download is checked** against the table above, with a plain reason when refused. Family leads reply to queries but don't close them. Proposals: Tech Risk proposes and may withdraw; only the Head of Tech Risk approves, returns or declines.
- **Logged:** item-detail views (`view`) and downloads (`download`), with who, when and which family.
- **The page:** shows who you are instead of the role choice; the "view as" choice stays for Tech Risk only. Auditors see the Tech Risk pages with a read-only banner. Family roles can open the CTO view and Firm position as well as their own family's page.
- **No access** (no header, or no matching group and not placed in a family): a plain page saying to ask Tech Risk.

## Owner decisions (3 Nov 2026)

1. **Lock:** anyone in Tech Risk. (Read as covering reopen too; say if reopen should be the Head of Tech Risk only.)
2. **Family members:** yes, in v1: view their own family and add comments.
3. **Delegates:** allowed.
4. **Leadership:** the CTO and everyone else can see the CTO view. **Nobody comments on the CTO page**: people comment on their own family's page, and that flows up.
5. **Item detail:** shows people's names in the drill-down; sub-teams on family pages come from a configurable HR column (Department for now).
6. **Auditors:** read only, no downloading.
