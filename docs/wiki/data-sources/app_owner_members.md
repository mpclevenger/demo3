# AD owner groups (feed `app_owner_members`)

**Provider:** Tech Risk, made with `tools/expand_owner_groups.ps1`. **File:** CSV (`.csv`).

## Why it exists

Many `app_owner_email` values in the [app inventory](app_inventory.md) are group emails, not people. HR can't say who is in a group. Active Directory (AD) can. The script asks AD and writes the answer to one file.

## Making the file

Run it on a Windows desktop, in PowerShell.

1. You need the **RSAT ActiveDirectory module** (Microsoft's remote admin tools for AD).
2. Open the script and set `$Server` at the top: a domain controller or domain, for example `dc01.corp.example.com`. The script stops if it is empty.
3. Optionally set `$ServiceAccountPatterns`, a list of name patterns such as `"svc*"` or `"sa_*"`. Matching accounts are treated as service accounts.
4. Check `$InventoryPath`. It must point at the app inventory CSV (`.\app_inventory.csv` to start). `$OwnerColumn` and `$OutputPath` can stay as they are.
5. Run `.\expand_owner_groups.ps1`.

If Windows PowerShell says scripts are blocked, run it like this instead:

`powershell -ExecutionPolicy Bypass -File .\expand_owner_groups.ps1`

The script **only reads AD and writes one CSV** (`app_owner_members.csv`). It changes nothing in AD. Nested groups are included. Disabled and service accounts are left out, but still written with a reason.

## What the file looks like

One row per member of a group. A person, or an email AD can't place, gets one row.

| Column | What's in it |
|---|---|
| owner_email | The email from the inventory. |
| owner_kind | `group`, `person`, `not found`, `ambiguous` (more than one AD object has the email), or another AD object type. |
| group_sam | The group's SAM account name, for a group. |
| member_sam | The member's SAM account name. |
| member_email | The member's email. |
| member_name | The member's display name. |
| member_enabled | Whether the account is enabled. |
| included | `Yes` for an enabled person. `No` for disabled accounts, service accounts, empty groups and emails not found. |
| reason | Why a row is `No`, for example "disabled account". |

## What TRUST does with it

- **Upload it on its own** on Data sources. A row with no `owner_email` is set aside.
- **At mapping**, an owner email found in HR is a person, and this file isn't needed. Otherwise the **included** members are matched to HR by SAM_ACCOUNT, then email.
- **Owner email not found in AD** (and not a person in HR): **Not yet mapped**. The upload result counts these.
- **A group with no member in HR** also stays Not yet mapped.
- **Left-out members** (disabled or service accounts) are counted in a note starting "For information:", which doesn't need acknowledging.
- **Rerun it** when the inventory has new owner emails.
