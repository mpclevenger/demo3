# App inventory (feed `app_inventory`)

**Provider:** Arch. **File:** CSV (`.csv`). **Layout from the owner, 6 Nov 2026.**

## What the file looks like

The header is row 1. From row 2, **one row per application service**. An application with three services is on three rows.

TRUST keeps these 13 columns:

| Column | What's in it | What TRUST uses it for |
|---|---|---|
| app_id | The inventory's own id for the application. | Joins an application's service rows. It does not match the ITDR file's Ref. |
| app_name | The application's name. | Linking to ITDR by name. Shown in the drill-down. |
| app_status | For example `confirmed`. | Decides if the application is active. |
| app_department | The application's department. | Kept for reference. |
| app_sbu | The application's business unit (SBU). | Kept for reference. |
| app_org_hierarchy | A path like `This > That > Other`. | The second part places the application with a family. |
| app_owner_raw | The owner as the inventory wrote it. | Kept for reference. |
| app_owner_type | The kind of owner. | Kept for reference. |
| app_owner_email | The owner's email. Often a distribution list, not a person. | Finding the owners. |
| service_id | The service's id. | Identifies the service. |
| service_name | The service's name. | Identifies the service. |
| service_owner_email | The service owner's email. | Kept with the service. |
| service_repo | The service's code repository. | Linking to a GitHub repo. |

**Dropped at upload and never stored:** `bcp_tier`, `bcp_tier_source`, `itdr_match` and `unmapped_reasons`. `bcp_tier` and `bcp_tier_source` are being retired. The [ITDR application file](itdr.md) is the only source of a tier. The column names (and close spellings) are in `config/column_maps.json` under `app_inventory`.

## What TRUST does with it

- **One app per `app_id`.** Its service rows are gathered under it. If rows disagree on the name, org path, owner or status, the first row's value is used and the difference is listed. A row with no `app_id` is set aside.
- **Active app.** Only `app_status` **confirmed** counts (setting **`app_active_statuses`**). Other applications are counted on the upload result but not placed or linked.
- **Family.** The inventory is the golden source. At mapping, for each active app:
  1. the second part of `app_org_hierarchy` is matched to an HR **Supervisory Organization**, with the "(Manager Name)" part removed;
  2. that organization goes to the family **most of its people** are in (a tie places nothing and is listed);
  3. **only when that places nothing**, the app takes the family most of its owners are in, from HR.

  Names are compared ignoring case, spaces, punctuation and word order. An exact match wins. Otherwise the closest name scoring at least **`app_org_match_min`** is used (0.85 to start).
- **Owners.** An `app_owner_email` found in HR is a person. If not, it is probably an AD group, and its members come from the [AD owner groups file](app_owner_members.md), matched to HR by SAM_ACCOUNT, then email. Anyone left is **Not yet mapped**.
- **ITDR.** `app_id` does not map to ITDR, so `app_name` is matched to the ITDR Application Name: exact first, else the closest at **`app_itdr_match_min`** (0.9 to start). A name used on more than one Ref is not linked.
- **GitHub repos.** `service_repo` is tied to a GitHub repo with the same matching as Checkmarx, at **`app_repo_match_min`** (0.9 to start).
- **The match settings.** All three are in `config/settings.json`. 1.0 means exact only. A lower number is looser. They run from 0.5 to 1.
- **Nothing is guessed.** Every close match is listed with its score. Two close names for different things are too close to call: nothing is chosen and it is listed.
- **Checks.** Junk is refused (not a CSV file, none of the columns, every row unusable). Warnings must be acknowledged before the month is locked. Notes starting **"For information:"** don't need acknowledging.

## What it feeds

It adds an **App** and **App owners** view to the drill-down items for TR-02, SE-01, SE-02, RE-01 and RE-03:

- the **By app / repo** bars;
- an **App** column on the items, with the app owners under each item;
- **App** and **App owners** columns in the family CSV download.

**Used in scoring (owner, 6 Nov 2026):**

- **TR-01 Repo mapping rate** (switched on): active repos linked to at least one confirmed app ÷ active repos, per family. A repo linked to no app doesn't count; a repo shared by several apps counts, and shows under each of its apps in the drill-down.
- **ITDR placement:** an ITDR application linked to an inventory app takes the app's family, so RE-01, RE-03 and the family's Tier 0/1 status follow it ([ITDR](itdr.md)). Unlinked applications keep their Business Product Area's family. Setting `itdr_family_from_inventory` false switches this off.

Not used (owner to decide later): UN-01 per 10 apps, TR-03, and placing repos for TR-02 and Checkmarx by the inventory.
