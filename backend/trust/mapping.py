"""Step 2, MAP: read the stored files for a month and place their rows with people and families.

Re-run it as often as you like: after fixing a column name in config/column_maps.json, after HR or
the team-to-family mapping arrives, after changing config/settings.json. It reads the files kept
by step 1 (backend/trust/store.py), so nothing is ever uploaded twice. It never refuses: a file
that can't be read, a missing column or an unplaced row all become plain notes.

Output: store/mapped/<YYYY-MM>.json, which step 3 (scoring) reads.
"""
from collections import defaultdict
import json

from . import config, linking, lost, storage, store
from .intake import risk_assessments
from .intake import (actions, app_inventory, app_links, checkmarx, defects, dr_tests, families, hr, itdr, ntcc,
                     owner_groups, postmortems, repos, tcc)

# Each feed with a reader. Feeds without one yet are recorded as "received, no reader yet".
READERS = {
    "hr": lambda raw, e, s: hr.read(raw, s.get("hr_root_sam_account", "")),
    "hr_mapping": lambda raw, e, s: families.read(raw),
    "cx_sast": lambda raw, e, s: checkmarx.read(raw, "SAST", e["uploaded_at"]),
    "cx_sca": lambda raw, e, s: checkmarx.read(raw, "SCA", e["uploaded_at"]),
    "tcc": lambda raw, e, s: tcc.read(raw),
    "ntcc": lambda raw, e, s: ntcc.read(raw),
    "postmortems": lambda raw, e, s: postmortems.read(raw),
    "actions": lambda raw, e, s: actions.read(raw),
    "itdr": lambda raw, e, s: itdr.read(raw),
    "dr_tests": lambda raw, e, s: dr_tests.read(raw),
    "repos": lambda raw, e, s: repos.read(raw),
    "defects": lambda raw, e, s: defects.read(raw),
    "app_inventory": lambda raw, e, s: app_inventory.read(raw, s),
    "app_owner_members": lambda raw, e, s: owner_groups.read(raw),
    "risk_assessments": lambda raw, e, s: risk_assessments.read(raw),
}
# Files that stay current until a newer one arrives (owner, 9 Nov 2026): a month with none uses the newest earlier
# upload, and says which month it came from. Risk assessments aren't done monthly.
CARRY_FORWARD = ("risk_assessments",)


def _carried(feed, month):
    """(entry, raw, from month) for the newest upload of a feed in an earlier month, else None."""
    for m in sorted((x for x in storage.upload_months() if x < month), reverse=True):
        got = store.latest(m).get(feed)
        if got and got[1] is not None:
            return got[0], got[1], m
    return None


def settings():
    """Owner-editable settings; see backend/trust/config.py."""
    return config.settings()


def map_month(month, by="command line"):
    """Map every stored file for a month. Returns the mapped result (also saved). Refuses a locked month."""
    store._check(store.FEEDS[0], month)
    storage.ensure_open(month)
    s = settings()
    uploads = store.latest(month)
    feeds, notes = {}, []

    for feed in store.FEEDS:
        carried_from = None
        if feed not in uploads and feed in CARRY_FORWARD:
            got = _carried(feed, month)
            if got:
                uploads[feed], carried_from = (got[0], got[1]), got[2]
        if feed not in uploads:
            feeds[feed] = {"status": "not received"}
            continue
        entry, raw = uploads[feed]
        if raw is None:      # received, but nothing kept (the HR file before the CTO setting was set)
            feeds[feed] = {"status": "received, not kept", "file": entry["original_name"],
                           "original_sha256": entry.get("original_sha256"),
                           "uploaded_at": entry["uploaded_at"], "uploaded_by": entry["uploaded_by"],
                           "notes": entry.get("notes", [])}
            continue
        base = {"status": "mapped", "file": entry["original_name"], "sha256": entry["sha256"],
                "original_sha256": entry.get("original_sha256"),
                "uploaded_at": entry["uploaded_at"], "uploaded_by": entry["uploaded_by"]}
        if carried_from:
            base["carried_from"] = carried_from
        reader = READERS.get(feed)
        if reader is None:
            feeds[feed] = {**base, "status": "received, no reader yet",
                           "notes": ["This feed's layout hasn't been given yet; the file is kept and will be mapped once it has."]}
            continue
        try:
            result = reader(raw, entry, s)
        except ValueError as err:              # the file can't be read at all: say so, carry on with the rest
            feeds[feed] = {**base, "status": "could not be read", "notes": [str(err)]}
            continue
        feeds[feed] = {**base, **result}

    # Place rows with people and families, from whatever is loaded (DEVELOPER_GUIDE.md rule 0).
    people = feeds.get("hr", {}).get("people") or []
    email_to_sam = {p["email"]: p["sam_account"] for p in people if p.get("email")}
    family_rows = feeds.get("hr_mapping", {}).get("rows")
    family_of_sam = family_of_email = None
    # Which teams to report on (owner, 3 Nov 2026): product families from the owners file (the default),
    # or, with setting team_grouping = "l3", each level-3 person's org from HR, the owners file not used.
    team_grouping = linking.grouping(s)
    if not people:
        notes.append("HR not loaded (or no people kept): everything shows as Not yet mapped.")
    if team_grouping == "l3":
        level = linking.l3_level(s)
        notes.append(f"Teams this month: each level-{level} person in HR and everyone under them (setting team_grouping "
                     "= l3). The product family owners file isn't used while this is on.")
        if people:
            placed = linking.families_from_level(people, level)
            family_of_sam, family_of_email = placed["family_of_sam"], placed["family_of_email"]
            family_rows = placed["families"]
            feeds.setdefault("hr_mapping", {"feed": "hr_mapping", "status": "not used (level-3 teams)"})
            feeds["hr_mapping"]["families"] = placed["families"]
            feeds["hr_mapping"].setdefault("notes", []).extend(placed["notes"])
            for p in people:
                p["family_id"] = family_of_sam.get(p["sam_account"], linking.UNATTRIBUTED)
    elif family_rows is None:
        notes.append("Product family owners file not loaded: people are found in HR, but every row shows as "
                     "Not yet mapped until it is.")
    elif people:
        placed = linking.families_from_owners(people, family_rows)
        family_of_sam, family_of_email = placed["family_of_sam"], placed["family_of_email"]
        feeds["hr_mapping"]["families"] = placed["families"]
        feeds["hr_mapping"]["shared"] = placed["shared"]          # leads of several families (owner, 6 Nov 2026)
        feeds["hr_mapping"].setdefault("notes", []).extend(placed["notes"])
        for p in people:   # show each kept person's family on the HR result
            p["family_id"] = family_of_sam.get(p["sam_account"], linking.UNATTRIBUTED)

    # ITDR applications placed with families by Business Product Area: a family name, or an HR Department
    # whose people are mostly in one family; close spellings accepted above area_match_min (owner, 3 Nov 2026). DR tests then take their application's family.
    if feeds.get("itdr", {}).get("rows") is not None and family_rows is not None:
        fam = itdr.match_families(feeds["itdr"]["rows"], family_rows,
                                  people if family_of_sam is not None else None, itdr.area_match_min(s))
        feeds["itdr"]["families"] = {k: fam[k] for k in ("placed", "not_placed", "exact", "fuzzy",
                                                         "by_family_name", "by_department")}
        itdr_area = (fam["notes"], family_rows, people if family_of_sam is not None else None, itdr.area_match_min(s))
    else:
        itdr_area = None

    # Repos placed with families through their committer (owner, 3 Nov 2026) and the TR-02 hygiene figures
    # (planned metric, not scored yet). Without HR or the owners file every repo is Not yet mapped.
    if feeds.get("repos", {}).get("rows") is not None:
        placed_repos = repos.place_and_score(feeds["repos"]["rows"], month, people, family_of_sam or {}, s)
        feeds["repos"]["hygiene"] = {k: v for k, v in placed_repos.items() if k != "notes"}
        feeds["repos"].setdefault("notes", []).extend(placed_repos["notes"])
        # Checkmarx repos take the family of the GitHub repo they match (owner, 4 Nov 2026), so SE-01 / SE-02
        # can reach families. Without the GitHub file for the month they stay Not yet mapped.
        for cx in ("cx_sast", "cx_sca"):
            if feeds.get(cx, {}).get("rows") is not None:
                m = repos.match_checkmarx(feeds[cx]["rows"], feeds["repos"]["rows"], repos.checkmarx_match_min(s))
                feeds[cx]["repo_match"] = {k: v for k, v in m.items() if k != "notes"}
                feeds[cx].setdefault("notes", []).extend(m["notes"])

    # Jira issues placed with the family of the person who closed them (owner, 3 Nov 2026), and the month's
    # defect and delivery figures (TE-03 planned, not scored yet). Without HR or the owners file: Not yet mapped.
    if feeds.get("defects", {}).get("rows") is not None:
        placed_jira = defects.place_and_measure(feeds["defects"]["rows"], month, people, family_of_sam or {})
        feeds["defects"]["figures"] = {k: v for k, v in placed_jira.items() if k != "notes"}
        feeds["defects"].setdefault("notes", []).extend(placed_jira["notes"])

    # App inventory (owner, 6 Nov 2026): family from the org (golden source), else its owners' HR family; owners
    # through HR, then the AD owner groups file; linked to ITDR by name and to GitHub repos by service repo.
    # Not scored: it gives the drill-down its apps and owners. Runs after Checkmarx is matched to GitHub repos.
    if feeds.get("app_inventory", {}).get("rows") is not None:
        linked = app_links.link(
            feeds["app_inventory"]["rows"], people if family_of_sam is not None else [],
            feeds.get("app_owner_members") if "members" in (feeds.get("app_owner_members") or {}) else None,
            (feeds.get("itdr") or {}).get("rows"),
            (feeds.get("repos") or {}).get("rows"),
            [(feeds.get(cx) or {}).get("rows") for cx in ("cx_sast", "cx_sca")], s)
        feeds["app_inventory"]["placed"] = {k: linked[k] for k in ("summary", "by_family")}
        feeds["app_inventory"].setdefault("notes", []).extend(linked["notes"])
        if linked["itdr_notes"]:
            feeds["itdr"].setdefault("notes", []).extend(linked["itdr_notes"])
    # Business Product Area notes, written only now (owner, 6 Nov 2026): an application the app inventory placed
    # doesn't need an area, so the notes cover only the applications still to be placed by their area.
    if itdr_area is not None:
        notes, frows, ppl, amin = itdr_area
        rows = feeds["itdr"]["rows"]
        by_inv = [r for r in rows if (r.get("family_match") or {}).get("how") == "app inventory"]
        if by_inv:
            rest = [dict(r) for r in rows if (r.get("family_match") or {}).get("how") != "app inventory"]
            notes = itdr.match_families(rest, frows, ppl, amin)["notes"] if rest else []
            placed = sum(1 for r in rows if r.get("family_id"))
            feeds["itdr"]["families"].update(placed=placed, not_placed=len(rows) - placed, by_inventory=len(by_inv))
            notes = [f"For information: {len(by_inv)} of {len(rows)} ITDR applications were placed by the app inventory; "
                     f"{placed - len(by_inv)} by Business Product Area; {len(rows) - placed} not placed"] + notes
        feeds["itdr"].setdefault("notes", []).extend(notes)

    # The AD members aren't saved with the mapped month: they can be hundreds of thousands of rows, and each app
    # already carries its owners (6 Nov 2026: the web process ran out of memory).
    for k in ("members", "kinds"):
        (feeds.get("app_owner_members") or {}).pop(k, None)

    # DR tests linked to ITDR applications by name, when both files are loaded (owner, 3 Nov 2026).
    if feeds.get("dr_tests", {}).get("rows") is not None and feeds.get("itdr", {}).get("rows") is not None:
        link = dr_tests.match_applications(feeds["dr_tests"]["rows"], feeds["itdr"]["rows"])
        feeds["dr_tests"]["linked_to_applications"] = {k: link[k] for k in ("matched", "not_matched", "tier_differs")}
        feeds["dr_tests"].setdefault("notes", []).extend(link["notes"])


    act_rows = feeds.get("actions", {}).get("rows")
    pm_rows = feeds.get("postmortems", {}).get("rows")
    if pm_rows is not None and act_rows is None:
        # Postmortems alone: incidents are placed through user_stakeholders only (UN-01).
        link = linking.link_actions_to_incidents([], pm_rows, family_of_email, family_of_sam)
        feeds["postmortems"]["incidents"] = link["incidents"]
        feeds["postmortems"].setdefault("notes", []).extend(link["incident_notes"])
    if act_rows is not None:
        link = linking.link_actions_to_incidents(act_rows, pm_rows, family_of_email, family_of_sam)
        if pm_rows is not None:
            feeds["postmortems"]["incidents"] = link["incidents"]
            feeds["postmortems"].setdefault("notes", []).extend(link["incident_notes"])
        # Also record whether each assignee was found in HR at all, so Tech Risk can see who is missing.
        for a in link["actions"]:
            a["assignee_in_hr"] = a.get("assignee_email") in email_to_sam
        feeds["actions"]["rows"] = link["actions"]
        feeds["actions"]["incidents"] = link["incidents"]
        feeds["actions"].setdefault("notes", []).extend(link["notes"])

    # Cross-file check (Q-NTCC-06): a change in both TCC and Non-TCC is counted once, as TCC.
    tcc_ids = {x["ticket_id"] for x in feeds.get("tcc", {}).get("rows") or []}
    ntcc_rows = feeds.get("ntcc", {}).get("rows")
    if ntcc_rows is not None and tcc_ids:
        both = [x["rpd_id"] for x in ntcc_rows if x["rpd_id"] in tcc_ids]
        for x in ntcc_rows:
            x["also_in_tcc"] = x["rpd_id"] in tcc_ids
        if both:
            feeds["ntcc"].setdefault("notes", []).append(
                f"{len(both)} {'change is' if len(both) == 1 else 'changes are'} in both TCC and Non-TCC; counted once, "
                f"as TCC: {', '.join(both[:10])}")

    # Every row that names a person gets that person's family (or UNATTRIBUTED), so scoring only counts.
    for feed, key in (("tcc", "author_email"), ("ntcc", "author_email")):
        for x in feeds.get(feed, {}).get("rows") or []:
            x["family_id"] = (family_of_email or {}).get(x.get(key)) or linking.UNATTRIBUTED
    # The person and their team (HR supervisory organization), for the item detail families drill into.
    # A person's sub-team within the family: the HR column named by the setting subteam_hr_column
    # (owner, 3 Nov 2026: Department by default; Supervisory Organization also works).
    col = (s.get("subteam_hr_column") or "Department").strip()
    field = {"department": "department", "supervisory organization": "sup_org"}.get(col.lower())
    if field is None:
        notes.append(f"subteam_hr_column '{col}' isn't one TRUST keeps (Department or Supervisory Organization); "
                     "using Department.")
        field = "department"
    who = {p["email"]: (p.get("worker"), p.get(field), p.get(field)) for p in people if p.get("email")}
    for feed, key in (("tcc", "author_email"), ("ntcc", "author_email"), ("actions", "assignee_email"),
                      ("repos", "owner_email")):
        for x in feeds.get(feed, {}).get("rows") or []:
            x["person"], x["team"], x["team_key"] = who.get(x.get(key), (None, None, None))

    # Risk assessments (owner, 9 Nov 2026): each assessed group (usually an L4) is placed by its departments, which
    # match HR's Department column; a group belongs to every family its departments land in. A family takes the
    # highest rating on each risk among its groups (risk_assessments.by_family).
    ra = feeds.get("risk_assessments") or {}
    if ra.get("rows") is not None:
        groups = {}
        for x in ra["rows"]:
            groups.setdefault(x["group"], set()).update(x["departments"])
        probes = [{"ref": g, "business_product_area": d} for g, ds in groups.items() for d in sorted(ds)]
        fams_of = {g: set() for g in groups}
        if probes and family_rows is not None and people:
            itdr.match_families(probes, family_rows, people if family_of_sam is not None else None, itdr.area_match_min(s))
            for pr in probes:
                if pr.get("family_id"):
                    fams_of[pr["ref"]].add(pr["family_id"])
        ra["by_family"] = risk_assessments.by_family(ra["rows"], {g: sorted(f) for g, f in fams_of.items()})
        ra["groups"] = [{"group": g, "departments": sorted(groups[g]), "families": sorted(fams_of[g]),
                         "assessed_on": max((x["assessed_on"] or "" for x in ra["rows"] if x["group"] == g), default="") or None}
                        for g in sorted(groups)]
        lost_groups = [g["group"] for g in ra["groups"] if not g["families"]]
        if lost_groups:
            ra.setdefault("notes", []).append(
                f"{len(lost_groups)} assessed group{'s' if len(lost_groups) != 1 else ''} not placed with a family "
                f"(none of their departments matched HR's Department column): {', '.join(lost_groups[:5])}"
                f"{' and more' if len(lost_groups) > 5 else ''}")
        if ra.get("carried_from"):
            ra.setdefault("notes", []).append(f"For information: no risk assessment file this month; using the one "
                                              f"uploaded for {ra['carried_from']}.")

    # Lost and Found (owner, 9 Nov 2026): approved claims place items no source file placed. A claim never
    # overrides a file, and carries over to every month mapped after it is approved.
    claims_used, claim_note = lost.apply_claims(feeds, storage.claims())
    if claim_note:
        notes.append(claim_note)

    # Who each item belongs to, for the drill-down (owner, 9 Nov 2026): the person's name, SAM_ACCOUNT and work
    # email, with their L4 and L3 managers from the HR manager chain. Changes: the author. Actions: the assignee.
    # Repos: the repo owner. Checkmarx: the matched GitHub repo's owner, else the app owners. ITDR applications:
    # the app owners. Incidents: the assignees of the incident's actions in each family.
    whos = linking.who_table(people, linking.l3_level(s))
    of = lambda sams=(), emails=(): linking.who_of(whos, sams, emails, email_to_sam)
    for feed, key in (("tcc", "author_email"), ("ntcc", "author_email"), ("actions", "assignee_email"),
                      ("repos", "owner_email")):
        for x in feeds.get(feed, {}).get("rows") or []:
            x["who"] = of(emails=[x.get(key)])
    repo_owner = {r["repo"]: r.get("owner_email") for r in feeds.get("repos", {}).get("rows") or []}
    for cx in ("cx_sast", "cx_sca"):
        for x in feeds.get(cx, {}).get("rows") or []:
            x["who"] = of(emails=[repo_owner.get(x.get("gh_repo"))]) if repo_owner.get(x.get("gh_repo")) \
                else of(sams=x.get("app_owner_sams") or [])
    for x in feeds.get("itdr", {}).get("rows") or []:
        x["who"] = of(sams=x.get("app_owner_sams") or [])
    incs = (feeds.get("postmortems") or {}).get("incidents")
    if incs:
        by_inc = defaultdict(list)
        for a in feeds.get("actions", {}).get("rows") or []:
            if a.get("incident_id") and a.get("assignee_email"):
                by_inc[(a["incident_id"], a.get("family_id"))].append(a["assignee_email"])
        for inc, v in incs.items():
            v["who_by_family"] = {f: of(emails=by_inc.get((inc, f), [])) for f in v.get("families") or []}

    out = {"month": month, "settings_used": s, "team_grouping": team_grouping, "feeds": feeds, "notes": notes,
           "claims_used": claims_used,
           "received": sorted(f for f, v in feeds.items() if v["status"] != "not received")}
    storage.save_month("mapped", month, out, by)
    storage.log("map", by, month, f"{len(out['received'])} files read")
    return out
