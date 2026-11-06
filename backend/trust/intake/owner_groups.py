"""Read the AD owner groups file on its own (feed "app_owner_members"; owner, 6 Nov 2026).

The file comes from tools/expand_owner_groups.ps1, run on a Windows desktop with the AD module. For each
app_owner_email in the app inventory it says what that email is in Active Directory and, for a group,
every member (nested groups included):

    owner_email | owner_kind | group_sam | member_sam | member_email | member_name | member_enabled | included | reason

    owner_kind: group, person, not found, ambiguous, or another AD object type.
    included: Yes for an enabled person; No (with the reason) for disabled accounts, service accounts,
        empty groups and emails not found. Only included members are used.

At mapping (backend/trust/intake/app_links.py) an owner email found in HR is a person; otherwise its
included members here are matched to HR (SAM_ACCOUNT, then email). Anything left is Not yet mapped.
"""
from .common import as_bool, column_map, map_columns, read_table

FIELDS = {"owner_email": ("owner_email", "owner email", "group email"),
          "owner_kind": ("owner_kind", "owner kind", "kind"),
          "group_sam": ("group_sam", "group"),
          "member_sam": ("member_sam", "samaccountname", "member sam"),
          "member_email": ("member_email", "member mail", "mail"),
          "member_name": ("member_name", "displayname", "member name"),
          "member_enabled": ("member_enabled", "enabled"),
          "included": ("included",),
          "reason": ("reason",)}


def read(raw_bytes):
    """Returns dict(rows=[{owner_email, owner_kind, group_sam, member_sam, member_email, member_name,
    included, reason}], set_aside, notes, summary)."""
    notes, set_aside, rows = [], [], []
    cmap = column_map("app_owner_members", FIELDS)
    headers, table = read_table(raw_bytes, 1, cmap)
    col = map_columns(headers, cmap, notes)
    g = lambda r, f: str(r.get(col[f], "") if col[f] else "").strip()
    for i, r in enumerate(table, start=2):
        email = g(r, "owner_email").lower()
        if not email:
            set_aside.append(dict(row=i, reason="no owner_email"))
            continue
        inc = g(r, "included")
        rows.append({"owner_email": email, "owner_kind": g(r, "owner_kind").lower() or None,
                     "group_sam": g(r, "group_sam") or None, "member_sam": g(r, "member_sam").lower() or None,
                     "member_email": g(r, "member_email").lower() or None, "member_name": g(r, "member_name") or None,
                     "included": as_bool(inc) if inc else bool(g(r, "member_sam")), "reason": g(r, "reason") or None})
    owners = {x["owner_email"] for x in rows}
    kinds = {}
    for e in owners:
        k = next((x["owner_kind"] for x in rows if x["owner_email"] == e), None) or "unknown"
        kinds[k] = kinds.get(k, 0) + 1
    left_out = sum(1 for x in rows if x["member_sam"] and not x["included"])
    if kinds.get("not found"):
        notes.append(f"{kinds['not found']} owner {'email was' if kinds['not found'] == 1 else 'emails were'} not found "
                     "in AD; apps owned only by them stay Not yet mapped unless the email is a person in HR")
    if left_out:
        notes.append(f"For information: {left_out} {'member was' if left_out == 1 else 'members were'} left out by the script "
                     "(disabled or service accounts)")
    summary = dict(owner_emails=len(owners), by_kind=kinds,
                   members=sum(1 for x in rows if x["member_sam"] and x["included"]), left_out=left_out,
                   set_aside=len(set_aside))
    return dict(rows=rows, set_aside=set_aside, notes=notes, summary=summary)
