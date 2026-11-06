"""Read the app inventory on its own (feed "app_inventory"; layout from the owner, 6 Nov 2026).

One row per application service: an application with three services is on three rows. TRUST keeps:

    app_id, app_name, app_status, app_department, app_sbu, app_org_hierarchy, app_owner_raw,
    app_owner_type, app_owner_email, service_id, service_name, service_owner_email, service_repo

Dropped at upload and never stored (owner, 6 Nov 2026): bcp_tier and bcp_tier_source (being retired;
the ITDR application file is the only tier source), itdr_match and unmapped_reasons.

    app_id: the inventory's own id. It does not match the ITDR file's Ref, so ITDR is linked by name.
    app_status: only "confirmed" counts as an active application (setting app_active_statuses).
    app_org_hierarchy: always "This > That > Other"; the second part ("That") is the group used to place
        the app with a family (HR Supervisory Organization, at mapping: backend/trust/intake/app_links.py).
    app_owner_email: often a distribution list, not a person; resolved at mapping through HR, then the
        AD group members file (feed app_owner_members).
    service_repo: the service's repo, matched to the GitHub repo file at mapping (a close match is fine).

Nothing here is scored. The inventory gives the drill-down its "By app / repo" view.
"""
import re

from .common import column_map, emails_in, map_columns, norm, read_table

FIELDS = {"app_id": ("app_id", "app id", "application id"),
          "app_name": ("app_name", "app name", "application name"),
          "app_status": ("app_status", "app status", "status"),
          "app_department": ("app_department", "department"),
          "app_sbu": ("app_sbu", "sbu"),
          "app_org_hierarchy": ("app_org_hierarchy", "org hierarchy", "app_org_heirarchy"),
          "app_owner_raw": ("app_owner_raw", "owner raw"),
          "app_owner_type": ("app_owner_type", "owner type"),
          "app_owner_email": ("app_owner_email", "owner email", "app owner email"),
          "service_id": ("service_id", "service id"),
          "service_name": ("service_name", "service name"),
          "service_owner_email": ("service_owner_email", "service owner email"),
          "service_repo": ("service_repo", "service repo", "repo")}
ACTIVE_STATUSES = ("confirmed",)       # default for the setting app_active_statuses (owner, 6 Nov 2026)


def tidy(text):
    return re.sub(r"[\s ​]+", " ", str(text or "")).strip()


def org_group(path):
    """The second part of 'This > That > Other' (owner, 6 Nov 2026), or None when there is no second part."""
    parts = [tidy(p) for p in str(path or "").split(">")]
    return parts[1] or None if len(parts) > 1 else None


def active_statuses(settings):
    v = (settings or {}).get("app_active_statuses")
    if isinstance(v, str):
        v = [v]
    if isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v) and v:
        return tuple(x.strip().lower() for x in v)
    return ACTIVE_STATUSES


def read(raw_bytes, settings=None):
    """Returns dict(rows=[app], set_aside, notes, summary). One app per app_id, with its services:

    {app_id, app_name, status, active, department, sbu, org_hierarchy, org_group, owner_raw, owner_type,
     owner_emails, services: [{service_id, service_name, service_owner_email, service_repo}]}
    """
    notes, set_aside, apps, by_id = [], [], [], {}
    cmap = column_map("app_inventory", FIELDS)
    headers, table = read_table(raw_bytes, 1, cmap)
    col = map_columns(headers, cmap, notes)
    g = lambda r, f: tidy(r.get(col[f], "") if col[f] else "")
    active = active_statuses(settings)

    differs, no_group = {}, []
    for i, r in enumerate(table, start=2):
        app_id = g(r, "app_id")
        if not app_id:
            set_aside.append(dict(row=i, reason="no app_id", application=g(r, "app_name")))
            continue
        service = {"service_id": g(r, "service_id") or None, "service_name": g(r, "service_name") or None,
                   "service_owner_email": g(r, "service_owner_email").lower() or None,
                   "service_repo": g(r, "service_repo") or None}
        key = norm(app_id)
        if key in by_id:
            a = by_id[key]
            for field, val in (("app_name", g(r, "app_name")), ("org_hierarchy", g(r, "app_org_hierarchy")),
                               ("owner_raw", g(r, "app_owner_raw")), ("status", g(r, "app_status"))):
                if val and a[field] and val != a[field]:
                    differs.setdefault(field, []).append(app_id)
            if any(service.values()):
                a["services"].append(service)
            continue
        status = g(r, "app_status")
        path = g(r, "app_org_hierarchy")
        grp = org_group(path)
        if not grp:
            no_group.append(app_id)
        a = {"app_id": app_id, "app_name": g(r, "app_name") or app_id, "status": status or None,
             "active": status.lower() in active, "department": g(r, "app_department") or None,
             "sbu": g(r, "app_sbu") or None, "org_hierarchy": path or None, "org_group": grp,
             "owner_raw": g(r, "app_owner_raw") or None, "owner_type": g(r, "app_owner_type") or None,
             "owner_emails": emails_in(g(r, "app_owner_email").lower()),
             "services": [service] if any(service.values()) else []}
        by_id[key] = a
        apps.append(a)

    show = lambda v: ", ".join(dict.fromkeys(v[:8])) + (f", and {len(set(v)) - 8} more" if len(set(v)) > 8 else "")
    for field, ids in differs.items():
        notes.append(f"{len(set(ids))} {'app has' if len(set(ids)) == 1 else 'apps have'} a different {field} on "
                     f"different service rows; the first row's is used: {show(ids)}")
    live = [a for a in apps if a["active"]]
    if no_group:
        notes.append(f"{len(no_group)} {'app has' if len(no_group) == 1 else 'apps have'} no second part in "
                     f"app_org_hierarchy ('This > That > Other'), so the org can't place {'it' if len(no_group) == 1 else 'them'}: "
                     f"{show(no_group)}")
    no_owner = [a["app_id"] for a in live if not a["owner_emails"]]
    if no_owner:
        notes.append(f"{len(no_owner)} active {'app has' if len(no_owner) == 1 else 'apps have'} no app_owner_email: "
                     f"{show(no_owner)}")
    by_status = {}
    for a in apps:
        by_status[a["status"] or "(blank)"] = by_status.get(a["status"] or "(blank)", 0) + 1
    others = {k: v for k, v in by_status.items() if k.lower() not in active}
    if others:
        notes.append("For information: only apps with app_status " + " or ".join(f"'{s}'" for s in active)
                     + " count as active; left out: " + ", ".join(f"{v} {k}" for k, v in sorted(others.items())))
    summary = dict(apps=len(apps), active_apps=len(live), service_rows=sum(len(a["services"]) for a in apps),
                   by_status=by_status, no_org_group=len(no_group), set_aside=len(set_aside))
    return dict(rows=apps, set_aside=set_aside, notes=notes, summary=summary)
