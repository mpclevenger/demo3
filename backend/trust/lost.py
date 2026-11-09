"""Lost and Found (owner, 9 Nov 2026).

Items no source file could place with a family are listed on the Lost and found page (Governance), with why
each wasn't placed and who or what it names. A family lead, or Tech Risk, claims one for a family; Tech Risk
approves or returns the claim. At every Update, approved claims place their items (`apply_claims`, called from
mapping), in every later month the item appears in. A claim never overrides a source file: only an item that
is still unplaced takes its claim. Tech Risk can release an approved claim, which undoes it from the next Update.

Only items that would count in a metric if they were placed are listed: deployed changes, open in-scope
postmortem actions, active GitHub repos, Checkmarx projects, ITDR applications at Tier 0-2 and rated
Critical/SWE incidents.
"""
from .linking import UNATTRIBUTED

# feed -> what an item is called, its key field, the metrics it would count in
KINDS = {
    "tcc": ("Change (TCC)", "ticket_id", ["TE-01", "TE-02"]),
    "ntcc": ("Change outside TCC", "rpd_id", ["TE-01"]),
    "actions": ("Postmortem action", "item_ref", ["UN-02"]),
    "postmortems": ("Incident", "incident_id", ["UN-01"]),
    "repos": ("GitHub repo", "repo", ["TR-01", "TR-02"]),
    "cx_sast": ("Checkmarx SAST project", "key", ["SE-01"]),
    "cx_sca": ("Checkmarx SCA project", "key", ["SE-02"]),
    "itdr": ("ITDR application", "ref", ["RE-01", "RE-03"]),
}
TIERS = (0, 1, 2)


def _lost(x):
    return (x.get("family_id") or UNATTRIBUTED) == UNATTRIBUTED


def _rows(feeds, feed):
    """The rows of one feed that would count in a metric, as (key, row)."""
    f = feeds.get(feed) or {}
    if feed == "postmortems":
        for inc, v in (f.get("incidents") or {}).items():
            if v.get("in_scope") is not False and v.get("in_postmortem_file", True) and v.get("risk_class"):
                yield inc, v
        return
    key = KINDS[feed][1]
    for x in f.get("rows") or []:
        if feed == "tcc" and not x.get("deployed"):
            continue
        if feed == "ntcc" and (not x.get("deployed") or x.get("also_in_tcc")):
            continue
        if feed == "actions" and not (x.get("open") and x.get("in_scope", True)):
            continue
        if feed == "repos" and not x.get("active"):
            continue
        if feed == "itdr" and x.get("recovery_tier") not in TIERS:
            continue
        if x.get(key):
            yield str(x[key]), x


def _why(feed, x, in_hr):
    """Why a row wasn't placed, in plain words."""
    def person(email, who):
        if not email:
            return f"No {who} email in the file"
        if email.lower() not in in_hr:
            return f"The {who} ({email}) isn't in the HR file's technology line"
        return f"The {who} ({email}) has no product family owner above them in HR"
    if feed in ("tcc", "ntcc"):
        return person(x.get("author_email"), "author")
    if feed == "actions":
        return person(x.get("assignee_email"), "assignee")
    if feed == "repos":
        return ("No person found among its recent commits" if not x.get("owner_email")
                else person(x.get("owner_email"), "repo owner"))
    if feed in ("cx_sast", "cx_sca"):
        return ("No matching GitHub repo" if not x.get("gh_repo")
                else f"Its GitHub repo ({x['gh_repo']}) isn't placed with a family")
    if feed == "itdr":
        a = (x.get("business_product_area") or "").strip()
        return (f"Business Product Area '{a}' doesn't match a family, and no app in the app inventory places it"
                if a else "No Business Product Area, and no app in the app inventory places it")
    if feed == "postmortems":
        return "None of its postmortem actions is placed with a family, and nobody named on the postmortem is"
    return "Not placed"


def _names(feed, x):
    """Who or what the item names, so a family can recognise it."""
    if feed in ("tcc", "ntcc"):
        return ", ".join(v for v in (x.get("author"), x.get("author_email")) if v)
    if feed == "actions":
        return ", ".join(v for v in (x.get("assignees_raw") or x.get("assignee_email"), x.get("incident_id") and f"incident {x['incident_id']}") if v)
    if feed == "repos":
        return ", ".join(v for v in (x.get("owner_email"), x.get("owner_login")) if v)
    if feed in ("cx_sast", "cx_sca"):
        return x.get("gh_repo") or ""
    if feed == "itdr":
        return ", ".join(v for v in (x.get("application_name"), x.get("tier_label"), x.get("business_product_area")) if v)
    if feed == "postmortems":
        return f"{x.get('risk_class')} incident" + (f", {x.get('postmortems')} postmortem(s)" if x.get("postmortems") else "")
    return ""


def items(mapped):
    """Every lost item in a mapped month: [{feed, kind, item, names, why, metrics, link}]."""
    feeds = (mapped or {}).get("feeds") or {}
    in_hr = {(p.get("email") or "").lower() for p in (feeds.get("hr") or {}).get("people") or []}
    out = []
    for feed, (kind, _key, metrics) in KINDS.items():
        for key, x in _rows(feeds, feed):
            lost = x.get("families") in (None, [], [UNATTRIBUTED]) if feed == "postmortems" else _lost(x)
            if lost:
                out.append({"feed": feed, "kind": kind, "item": key, "names": _names(feed, x), "why": _why(feed, x, in_hr),
                            "metrics": metrics, "link": x.get("link") or x.get("url") or None})
    return out


def apply_claims(feeds, claims):
    """Place each still-unplaced item that has an approved claim. Returns (ids of the claims used, a note or None).
    The newest approved claim on an item wins (a later claim replaces an earlier one only once the earlier one is
    released, because the page allows one open or approved claim per item)."""
    approved = {}
    for c in claims or []:
        if c.get("status") == "approved":
            approved[(c["feed"], str(c["item"]))] = c
    if not approved:
        return [], None
    used = []
    for feed in KINDS:
        if feed == "postmortems":
            continue
        for key, x in _rows(feeds, feed):
            c = approved.get((feed, key))
            if c and _lost(x):
                x["family_id"] = c["family_id"]
                x["claimed"] = c["id"]
                used.append(c["id"])
    # incidents: a claim on the incident itself, else the families of its claimed actions
    incs = (feeds.get("postmortems") or {}).get("incidents") or {}
    for store in (incs, (feeds.get("actions") or {}).get("incidents") or {}):
        for inc, v in store.items():
            if v.get("families") not in (None, [], [UNATTRIBUTED]):
                continue
            c = approved.get(("postmortems", str(inc)))
            fams = {c["family_id"]} if c else {a["family_id"] for a in (feeds.get("actions") or {}).get("rows") or []
                                               if a.get("incident_id") == inc and a.get("claimed")}
            if fams:
                v["families"] = sorted(fams)
                v["claimed"] = c["id"] if c else True
                if c and store is incs:
                    used.append(c["id"])
    used = sorted(set(used))
    note = (f"For information: Lost and Found: {len(used)} {'item' if len(used) == 1 else 'items'} placed by approved claims "
            f"(claims {', '.join(map(str, used[:20]))}{' and more' if len(used) > 20 else ''})") if used else None
    return used, note
