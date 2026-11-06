"""Join files at scoring time (DEVELOPER_GUIDE.md rule 0: uploads never join; scoring joins whatever is loaded).

Postmortems and action items (doc 15): only action items have an owner, so the chain is
    assignee email -> HR -> team -> family   (the action's family)
    action -> incident_id                    (each incident takes the families of its actions)
An incident with no actions falls back to its user_stakeholders (SAM_ACCOUNT -> HR), then to
UNATTRIBUTED, shown on Firm position as "Not yet mapped" (D-73). Nothing is dropped.
"""
from collections import defaultdict

UNATTRIBUTED = "UNATTRIBUTED"
SHARED = "shared:"           # a group of people whose lead leads several families (owner, 6 Nov 2026)


def _lookup(table, key):
    """Accept a dict or a function for the HR lookups; a missing table means 'not loaded yet'."""
    if table is None or key is None:
        return None
    return table(key) if callable(table) else table.get(key)


def link_actions_to_incidents(actions, postmortems=None, family_of_email=None, family_of_sam=None):
    """Place every action and incident with a family, from whatever is loaded.

    actions:        rows from intake.actions.read (required; this is the file with people on it)
    postmortems:    rows from intake.postmortems.read, or None if that file isn't loaded
    family_of_email: email -> family_id (built from HR + the team-to-family mapping), or None
    family_of_sam:   SAM_ACCOUNT -> family_id, for the incident fallback, or None

    Returns dict(actions=[...], incidents={incident_id: {...}}, notes=[...]).
    """
    notes = []
    pm_by_incident = defaultdict(list)
    for p in postmortems or []:
        pm_by_incident[p["incident_id"]].append(p)

    if postmortems is None:
        notes.append("postmortem file not loaded: every action is counted (scope can't be checked yet)")
    if family_of_email is None:
        notes.append("HR not loaded: every action shows as Not yet mapped until it is")

    placed, not_in_pm = [], []
    for a in actions:
        fam = _lookup(family_of_email, a.get("assignee_email")) or UNATTRIBUTED
        inc = a.get("incident_id")
        if postmortems is None:
            in_scope, why = True, "postmortem file not loaded"
        elif inc not in pm_by_incident:
            # The postmortem file lists the true critical incidents, so an action whose incident
            # isn't there is out of scope (this replaces the owner's hand filtering), and listed.
            in_scope, why = False, "incident not in the postmortem file"
            not_in_pm.append(a["item_ref"])
        elif not any(p["in_scope"] for p in pm_by_incident[inc]):
            in_scope, why = False, "incident is DEFCON 0"
        else:
            in_scope, why = True, "in scope"
        # The incident's rating (Critical / SWE / None = not rated), when the postmortem file is loaded.
        pms_a = pm_by_incident.get(inc, [])
        rating = ("SWE" if any(p.get("risk_class") == "SWE" for p in pms_a)
                  else "critical" if any(p.get("risk_class") == "critical" for p in pms_a) else None)
        placed.append({**a, "family_id": fam, "in_scope": in_scope, "scope_reason": why,
                       "incident_rated": (rating is not None) if pms_a else None, "incident_class": rating,
                       "placed_by": "assignee email" if fam != UNATTRIBUTED else None})
    if not_in_pm:
        notes.append(f"{len(not_in_pm)} {'action belongs' if len(not_in_pm) == 1 else 'actions belong'} to an incident "
                     f"not in the postmortem file (left out of UN-02, listed): {', '.join(not_in_pm[:10])}")

    # Each incident takes the families of all its actions (an incident can belong to several families).
    fams_by_incident = defaultdict(set)
    for a in placed:
        if a.get("incident_id"):
            fams_by_incident[a["incident_id"]].add(a["family_id"])

    incidents = {}
    from collections import Counter
    actions_of = Counter(a.get("incident_id") for a in placed)      # counted once, not per incident (speed)
    for inc in set(pm_by_incident) | set(fams_by_incident):
        fams = fams_by_incident.get(inc, set()) - {UNATTRIBUTED}
        via = "action assignees" if fams else None
        if not fams:
            # No placed actions: fall back to the people named on the postmortem (SAM_ACCOUNTs).
            for p in pm_by_incident.get(inc, []):
                for sam in p.get("user_stakeholders", []):
                    f = _lookup(family_of_sam, sam)
                    if f:
                        fams.add(f)
            via = "user_stakeholders" if fams else None
        pms = pm_by_incident.get(inc, [])
        incidents[inc] = {
            "incident_id": inc,
            "families": sorted(fams) or [UNATTRIBUTED],
            "placed_by": via,
            "in_postmortem_file": bool(pms),
            "in_scope": any(p["in_scope"] for p in pms) if pms else None,
            "postmortems": len(pms),
            # Critical or SWE (UN-01): the most severe class on any of the incident's postmortems.
            "risk_class": ("SWE" if any(p.get("risk_class") == "SWE" for p in pms)
                           else "critical" if any(p.get("risk_class") == "critical" for p in pms) else None),
            # When the incident ended: the primary postmortem's end_datetime, else the earliest one (UN-01 month).
            "end_datetime": (next((p.get("end_datetime") for p in pms if p.get("is_primary") and p.get("end_datetime")), None)
                             or min((p["end_datetime"] for p in pms if p.get("end_datetime")), default=None)),
            "actions": actions_of[inc],
        }
    unplaced = sorted(i for i, v in incidents.items() if v["families"] == [UNATTRIBUTED])
    incident_notes = []     # about the postmortems file, so they are shown on that file, not on Action items
    if unplaced and family_of_email is not None:
        incident_notes.append(f"{len(unplaced)} {'incident' if len(unplaced) == 1 else 'incidents'} could not be placed with a family "
                     f"(shown as Not yet mapped): {', '.join(unplaced[:10])}")
    return dict(actions=placed, incidents=incidents, notes=notes, incident_notes=incident_notes)


def families_from_owners(people, family_rows):
    """Place every HR person with a product family through the family owners file.

    people:      rows from intake.hr.read (sam_account, email, manager_sam)
    family_rows: rows from intake.families.read (family_id, family, owner_emails)

    Each owner is found in HR by email. A person belongs to the family of the **nearest owner
    above them, or themselves**, walking up the manager chain. Nobody is guessed: an owner not in
    HR, or a person with no owner above them, leaves that person UNATTRIBUTED (Not yet mapped), and
    the notes say why.

    **A lead of several families (owner, 6 Nov 2026):** the people under them are placed in one shared
    group (family_id SHARED + the family ids joined by '+'), and every one of the lead's families gets
    that group's results, so the same numbers show for each until the data is made more granular. The
    firm counts the group once (score_month.expand_shared).

    Returns dict(family_of_sam, family_of_email, families, shared={group id: [family ids]}, notes).
    """
    notes = []
    by_email = {p["email"]: p for p in people if p.get("email")}
    by_sam = {p["sam_account"]: p for p in people}

    owns = {}                    # owner SAM -> the families they lead, in file order
    for f in family_rows:
        for e in f["owner_emails"]:
            p = by_email.get(e)
            if p is None:
                notes.append(f"{f['family']}: owner {e} isn't in the HR file (or isn't in the CTO's line)")
                continue
            owns.setdefault(p["sam_account"], [])
            if f["family_id"] not in owns[p["sam_account"]]:
                owns[p["sam_account"]].append(f["family_id"])
    owner_family, shared = {}, {}
    for sam, fids in owns.items():
        if len(fids) == 1:
            owner_family[sam] = fids[0]
        else:
            g = SHARED + "+".join(sorted(fids))
            owner_family[sam], shared[g] = g, sorted(fids)

    family_of_sam, unplaced = {}, []
    for sam in by_sam:
        cur, steps, fam, seen = sam, 0, None, set()
        while cur and cur not in seen:
            seen.add(cur)
            if cur in owner_family:
                fam = owner_family[cur]
                break
            cur = by_sam[cur]["manager_sam"] if cur in by_sam else None
            steps += 1
        if fam:
            family_of_sam[sam] = fam
        else:
            unplaced.append(sam)

    names = {f["family_id"]: f["family"] for f in family_rows}
    for sam, fids in owns.items():
        if len(fids) > 1:
            notes.append(f"For information: {sam} leads {len(fids)} families ({', '.join(names[x] for x in fids)}), so the "
                         "people under them count for each of these families: their numbers are the same in each "
                         "until the data says which family each item belongs to")
    if unplaced:
        notes.append(f"{len(unplaced)} {'person has' if len(unplaced) == 1 else 'people have'} no family owner above them "
                     f"(Not yet mapped): {', '.join(sorted(unplaced)[:15])}{' …' if len(unplaced) > 15 else ''}")
    family_of_email = {p["email"]: family_of_sam[p["sam_account"]] for p in people
                       if p.get("email") and p["sam_account"] in family_of_sam}
    counts = {}
    for f in family_of_sam.values():
        for x in shared.get(f, [f]):
            counts[x] = counts.get(x, 0) + 1
    families = [{**f, "people": counts.get(f["family_id"], 0)} for f in family_rows]
    return dict(family_of_sam=family_of_sam, family_of_email=family_of_email, families=families, shared=shared,
                notes=notes)


GROUPINGS = ("product_family", "l3")


def grouping(settings):
    """Which teams the scorecard reports on (owner, 3 Nov 2026): setting team_grouping.
    product_family (the default) = the product family owners file; l3 = each level-3 person's org from HR."""
    g = str((settings or {}).get("team_grouping") or "product_family").strip().lower()
    return g if g in GROUPINGS else "product_family"


def l3_level(settings):
    v = (settings or {}).get("l3_level")
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else 3


def families_from_level(people, level=3):
    """Teams from HR alone (owner, 3 Nov 2026, setting team_grouping = l3).

    Every person whose "Management reporting level from top" is `level` leads a team named after them,
    and everyone reporting up to them (directly or not) is rolled into it. People above that level,
    or with no such person above them, are Not yet mapped and listed.

    Returns the same shape as families_from_owners, with `families` rows like the owners file's
    (family_id, family, band, owner_emails), so scoring, the page and family-lead access work unchanged.
    """
    from .intake.families import family_id
    notes = []
    by_sam = {p["sam_account"]: p for p in people}
    leads = [p for p in people if p.get("reporting_level") == level]
    team_of_lead, rows, used = {}, [], set()
    for p in sorted(leads, key=lambda x: (x.get("worker") or x["sam_account"]).lower()):
        name = p.get("worker") or p["sam_account"]
        fid = family_id(name)
        if fid in used:                                   # two leads with the same name: keep them apart
            fid = f"{fid}-{family_id(p['sam_account'])}"
            name = f"{name} ({p['sam_account']})"
        used.add(fid)
        team_of_lead[p["sam_account"]] = fid
        rows.append({"family_id": fid, "family": name, "band": "product",
                     "owner_emails": [p["email"]] if p.get("email") else [], "lead_sam": p["sam_account"]})
    if not leads:
        notes.append(f"Nobody in the HR file is at level {level} from the top, so no teams can be made "
                     "(check the HR column 'Management reporting level from top' and the setting l3_level)")
    family_of_sam, unplaced = {}, []
    for sam in by_sam:
        cur, seen, fam = sam, set(), None
        while cur and cur not in seen:
            seen.add(cur)
            if cur in team_of_lead:
                fam = team_of_lead[cur]
                break
            cur = by_sam[cur]["manager_sam"] if cur in by_sam else None
        if fam:
            family_of_sam[sam] = fam
        else:
            unplaced.append(sam)
    if unplaced:
        notes.append(f"{len(unplaced)} {'person isn\'t' if len(unplaced) == 1 else 'people aren\'t'} under a level-{level} lead "
                     f"(Not yet mapped): {', '.join(sorted(unplaced)[:15])}{' …' if len(unplaced) > 15 else ''}")
    family_of_email = {p["email"]: family_of_sam[p["sam_account"]] for p in people
                       if p.get("email") and p["sam_account"] in family_of_sam}
    counts = {}
    for f in family_of_sam.values():
        counts[f] = counts.get(f, 0) + 1
    families = [{**f, "people": counts.get(f["family_id"], 0)} for f in rows]
    return dict(family_of_sam=family_of_sam, family_of_email=family_of_email, families=families, notes=notes)
