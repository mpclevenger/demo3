"""Step 3a, MEASURE: count each metric per family from a mapped month (store/mapped/<month>.json).

Only counting happens here: numerator, denominator and the facts a Red-wins rule needs. Statuses,
tolerance thresholds and scores are worked out in step 3b (backend/trust/score_month.py).

Metrics with a reader today: TE-01, TE-02 (TCC), UN-01 (postmortems), UN-02 (actions, postmortems),
SE-01 (Checkmarx SAST), SE-02 (Checkmarx SCA), TR-01 (GitHub repos + app inventory), TR-02 (GitHub repos),
RE-01 and RE-03 (ITDR applications + DR tests); TR-01, TR-02, RE-01 and RE-03 count only when switched on
(setting switched_on, owner 4 Nov 2026; TR-01 6 Nov 2026). Every other metric is "not received" until its feed
has a layout and a reader. UN-03 (client incidents) is "Coming soon": no source yet (owner, 2 Nov 2026).

TE-01 is TCC changes only (owner, 2 Nov 2026): changes outside TCC (the Non-TCC file) belong to TE-06,
which is not on the scorecard yet.

UN-01 is a plain count for now (owner, 2 Nov 2026): there is no incidents file, so it is the unique
Critical and SWE incident_ids in the postmortem file. Its dictionary rate is "per 10 apps", which needs the app inventory.

Each result: {"numerator", "denominator", "items", **facts}. A family with no items gets
denominator 0. Rows not placed with a family are counted under UNATTRIBUTED ("Not yet mapped").
"""
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .linking import UNATTRIBUTED

NY = ZoneInfo("America/New_York")

# Which feed each measured metric needs before it counts as received (others are optional).
NEEDS = {"TE-01": "tcc", "TE-02": "tcc", "UN-01": "postmortems", "UN-02": "actions",
         "SE-01": "cx_sast", "SE-02": "cx_sca", "TR-02": "repos", "RE-01": "dr_tests", "RE-03": "dr_tests",
         "TR-01": "repos"}
NEEDS_ALSO = {"RE-01": "itdr", "RE-03": "itdr",   # both need the ITDR application file and the DR tests file
              "TR-01": "app_inventory"}           # GitHub repos and the app inventory (owner, 6 Nov 2026)

# Metrics counted only once switched on in config/thresholds.json "switched_on" (owner, 4 Nov 2026).
SWITCHABLE = ("TR-01", "TR-02", "RE-01", "RE-03")

# RE-03 (owner, 4 Nov 2026): applications at these ITDR recovery tiers need a passed test in the last 12 months,
# and a successful DR test (production or not) or a successful tabletop exercise counts.
RE03_TIERS = (0, 1, 2)
RE03_DAYS = 365
# RE-01 (owner, 4 Nov 2026; was "BIA completion"): Tier 0 and 1 applications with a completed DR test (the date in
# its Comments) in the last 12 months. DR tests only, production or not; tabletop exercises don't count.
RE01_TIERS = (0, 1)

# Shown as "Coming soon" and left out of every score until a source is agreed (owner, 2 Nov 2026).
COMING_SOON = {"UN-03": "Client incidents: coming soon. There is no source for client incidents yet."}

# Counted, not rated, until the app inventory gives the "per 10 apps" denominator: metric -> unit shown.
COUNT_ONLY = {"UN-01": "Critical or SWE incidents"}
COUNT_ONE = {"UN-01": "Critical or SWE incident"}     # the same unit, for a count of 1


def month_end(month):
    """First instant after the month, New York time (the snapshot point for 'open at month-end')."""
    y, m = (int(x) for x in month.split("-"))
    return datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=NY)


def _when(iso):
    return datetime.fromisoformat(iso) if iso else None


def _blank():
    return {"numerator": 0, "denominator": 0, "items": []}


def te01(feeds, month):
    """Prod deployments through TCC in the month (by ticket created date): approved before deployment ÷ all.

    Owner, 2 Nov 2026: changes outside TCC are left to TE-06, so the Non-TCC file is not counted here."""
    out = defaultdict(_blank)
    for x in feeds.get("tcc", {}).get("rows") or []:
        if x["deployed"] and x["month"] == month:
            r = out[x["family_id"]]
            r["denominator"] += 1
            r["numerator"] += bool(x["approved_before_deploy"])
            r["items"].append({"id": x["ticket_id"], "source": "TCC", "approved": bool(x["approved_before_deploy"]),
                               "person": x.get("person"), "team": x.get("team"), "team_key": x.get("team_key"), "created": x.get("createddateutc"),
                               "deployed": x.get("lastdeployment"), "link": x.get("link")})
    return out


def te02(feeds, month):
    """Prod releases (TCC) reverted: outcome 40/50/60/90 ÷ releases with a known outcome.

    Owner, 2 Nov 2026: each release counts in the month its 7-day revert window ends (last deployment
    + 7 days), so a month's figure only includes releases whose window has closed.

    Outcome 99 is its own count, out of the rate (R-TCC-11); 95 is out; a blank outcome is out and counted.
    Any change with client impact makes the metric Red (R-TCC-12), so it is counted here too.
    """
    out = defaultdict(lambda: {**_blank(), "unknown_outcome": 0, "no_outcome": 0, "client_impact": 0})
    for x in feeds.get("tcc", {}).get("rows") or []:
        if not (x["deployed"] and x.get("te02_month") == month):
            continue
        r = out[x["family_id"]]
        r["client_impact"] += bool(x["client_impact"])
        if x["outcome_unknown"]:
            r["unknown_outcome"] += 1
        elif x["obsoleted"]:
            continue
        elif not x.get("overall_outcome"):
            r["no_outcome"] += 1
        else:
            r["denominator"] += 1
            r["numerator"] += bool(x["revert"])
            r["items"].append({"id": x["ticket_id"], "revert": bool(x["revert"]), "client_impact": bool(x["client_impact"]),
                               "outcome": x.get("overall_outcome"), "person": x.get("person"), "team": x.get("team"), "team_key": x.get("team_key"),
                               "deployed": x.get("lastdeployment"), "link": x.get("link")})
    return out


def un02(feeds, month):
    """Postmortem actions open at month-end that are overdue ÷ open at month-end.

    No closed date in the action file yet (doc 15, finding 1), so 'closed during the month' can't be
    added; status is as at export time. Tracking counts as open. A blank ETA is due 30 days after created.
    Only actions whose incident is in scope (in the postmortem file, not DEFCON 0) count. Actions on an
    incident with no rating (Not Available or blank) are counted separately and shown, not scored (owner, 2 Nov 2026).
    """
    end = month_end(month)
    out = defaultdict(lambda: {**_blank(), "unrated_open": 0, "unrated_overdue": 0})
    for a in feeds.get("actions", {}).get("rows") or []:
        created = _when(a.get("created"))
        if not a.get("open") or not a.get("in_scope", True) or (created and created >= end):
            continue
        due = _when(a.get("due"))
        overdue = bool(due and due < end)
        r = out[a.get("family_id") or UNATTRIBUTED]
        if a.get("incident_rated") is False:
            # Owner, 2 Nov 2026: an incident with no rating (DEFCON Not Available or blank) is shown,
            # never hidden, but kept out of the score.
            r["unrated_open"] += 1
            r["unrated_overdue"] += overdue
            continue
        r["denominator"] += 1
        r["numerator"] += overdue
        r["items"].append({"id": a["item_ref"], "overdue": overdue, "due_from_blank_eta": a.get("due_from_blank_eta"),
                           "incident": a.get("incident_id"), "due": a.get("due"), "status": a.get("status"),
                           "person": a.get("person"), "team": a.get("team"), "team_key": a.get("team_key"), "link": a.get("url")})
    return out


def un01(feeds, month):
    """Unique Critical and SWE incidents (incident_id) in the postmortem file that ended in the month
    (New York), per family. Owner, 2 Nov 2026: no incidents file; use a unique count of incident_id,
    matching the file's risk criteria: Critical (DEFCON 3-5) and SWE (DEFCON 1-2). DEFCON 0 and
    "Not Available" (cannot determine) are not counted; the cannot-determine ones are listed.

    An incident with actions in several families counts once in each of them, and once firm-wide.
    The month comes from end_datetime, the only date in the postmortem file (working rule); an incident
    with no end_datetime can't be placed in a month and is listed.
    """
    out = defaultdict(_blank)
    firm, no_date, undetermined = set(), [], []
    for inc, v in (feeds.get("postmortems", {}).get("incidents") or {}).items():
        if v.get("in_scope") is False or not v.get("in_postmortem_file", True):
            continue
        ended = _when(v.get("end_datetime"))
        if v.get("risk_class") is None:
            # In scope but not rated: shown per family, never hidden, not counted (owner, 2 Nov 2026).
            if ended is None:
                no_date.append(inc)
            elif ended.astimezone(NY).strftime("%Y-%m") == month:
                undetermined.append(inc)
                for fam in v["families"]:
                    out[fam].setdefault("unrated", 0)
                    out[fam]["unrated"] += 1
            continue
        if ended is None:
            no_date.append(inc)
            continue
        if ended.astimezone(NY).strftime("%Y-%m") != month:
            continue
        firm.add(inc)
        for fam in v["families"]:
            r = out[fam]
            r["numerator"] += 1
            r["items"].append({"id": inc, "class": v["risk_class"], "placed_by": v.get("placed_by"),
                               "ended": v.get("end_datetime")})
    out = dict(out)
    out["_firm"] = {"numerator": len(firm), "no_end_date": sorted(no_date), "not_critical_or_swe": sorted(undetermined)}
    return out


def checkmarx(feed, feeds, repo_family=None):
    """Repos passing the Checkmarx policy ÷ repos scanned. A repo reaches a family through the GitHub repo it
    matches (mapping sets family_id; owner, 4 Nov 2026); without the GitHub file it is Not yet mapped."""
    out = defaultdict(lambda: {**_blank(), "overdue_ech": 0})
    for x in feeds.get(feed, {}).get("rows") or []:
        fam = x.get("family_id") or (repo_family or {}).get(x["key"].lower(), UNATTRIBUTED)
        r = out[fam]
        r["denominator"] += 1
        r["numerator"] += bool(x["compliant"])
        r["overdue_ech"] += x.get("overdue_ech") or 0
        r["items"].append({"id": x["key"], "passed": bool(x["compliant"]), "comment": x.get("comment"),
                           "gh_repo": x.get("gh_repo"), "matched_by": x.get("matched_by"),
                           "apps": x.get("apps") or [], "app_owners": x.get("app_owners") or []})
    return out


def tr02(feeds):
    """Repo hygiene (owner, 3-4 Nov 2026): checks passed ÷ checks possible (5 per active repo) per family.
    A repo's family comes from its owner (mapping); repos whose owner isn't placed are Not yet mapped."""
    from .intake.repos import CHECKS
    out = defaultdict(_blank)
    for x in feeds.get("repos", {}).get("rows") or []:
        if not x.get("active"):
            continue
        r = out[x.get("family_id") or UNATTRIBUTED]
        r["denominator"] += len(CHECKS)
        r["numerator"] += x["passed"]
        r["items"].append({"id": x["repo"], "passed_checks": x["passed"], "of": len(CHECKS),
                           "failed": [name for k, name in CHECKS if not x["checks"][k]],
                           "protected": bool(x["checks"]["protected"]), "link": x.get("url"),
                           "person": x.get("person"), "team": x.get("team"), "team_key": x.get("team_key"),
                           "owner_email": x.get("owner_email"),
                           "apps": x.get("apps") or [], "app_owners": x.get("app_owners") or []})
    return out


def tr01(feeds):
    """Repo mapping rate (owner, 6 Nov 2026): active repos linked to at least one confirmed app in the app
    inventory (through its service_repo) ÷ active repos, per family. A repo's family is its owner's, as for
    TR-02. A repo shared by several apps counts as mapped, and counts for each of its apps in the drill-down."""
    out = defaultdict(_blank)
    for x in feeds.get("repos", {}).get("rows") or []:
        if not x.get("active"):
            continue
        r = out[x.get("family_id") or UNATTRIBUTED]
        apps = x.get("apps") or []
        r["denominator"] += 1
        r["numerator"] += bool(apps)
        r["items"].append({"id": x["repo"], "passed": bool(apps), "n_apps": len(apps), "link": x.get("url"),
                           "person": x.get("person"), "team": x.get("team"), "team_key": x.get("team_key"),
                           "owner_email": x.get("owner_email"), "apps": apps, "app_owners": x.get("app_owners") or []})
    return out


def re01(feeds, month):
    """Tier 0/1 DR test completed (owner, 4 Nov 2026): Tier 0 and 1 ITDR applications with a completed DR test
    in the 12 months to month-end ÷ those applications, per family. Tabletop exercises don't count."""
    from .intake.dr_tests import DR_TEST
    return _tested(feeds, month, RE01_TIERS, (DR_TEST,))


def re03(feeds, month):
    """Resiliency testing passed (owner, 4 Nov 2026): ITDR applications at Tier 0, 1 or 2 with a successful DR
    test or tabletop exercise in the 12 months to month-end ÷ those applications, per family. An application's
    family comes from its Business Product Area (mapping); its tests are linked by name."""
    from .intake.dr_tests import DR_TEST, TABLETOP
    return _tested(feeds, month, RE03_TIERS, (DR_TEST, TABLETOP))


def _tested(feeds, month, tiers, kinds):
    end = month_end(month).date()
    start = end - timedelta(days=RE03_DAYS)
    last = {}
    for t in feeds.get("dr_tests", {}).get("rows") or []:
        d = t.get("performed_on")                      # set only for a successful test (dr_tests.py)
        if t.get("itdr_ref") and d and t.get("kind") in kinds and start <= _date(d) < end:
            if t["itdr_ref"] not in last or d > last[t["itdr_ref"]][0]:
                last[t["itdr_ref"]] = (d, t["kind"])
    out = defaultdict(_blank)
    for a in feeds.get("itdr", {}).get("rows") or []:
        if a.get("recovery_tier") not in tiers:
            continue
        r = out[a.get("family_id") or UNATTRIBUTED]
        hit = last.get(a["ref"])
        r["denominator"] += 1
        r["numerator"] += bool(hit)
        r["items"].append({"id": a["application_name"], "ref": a["ref"], "tier": a.get("tier_label"),
                           "passed": bool(hit), "tested_on": hit[0] if hit else None,
                           "test_kind": hit[1] if hit else None,
                           "apps": a.get("apps") or [], "app_owners": a.get("app_owners") or []})
    return out


def _date(iso):
    from datetime import date
    return date.fromisoformat(str(iso)[:10])


def measure(mapped):
    """All measured metrics for a mapped month: {metric_id: {family_id: result}} plus which were received."""
    feeds, month = mapped["feeds"], mapped["month"]
    got = {f for f, v in feeds.items() if v.get("status") == "mapped"}
    counts = {
        "TE-01": te01(feeds, month),
        "TE-02": te02(feeds, month),
        "UN-01": un01(feeds, month),
        "UN-02": un02(feeds, month),
        "SE-01": checkmarx("cx_sast", feeds),
        "SE-02": checkmarx("cx_sca", feeds),
        "TR-01": tr01(feeds),
        "TR-02": tr02(feeds),
        "RE-01": re01(feeds, month),
        "RE-03": re03(feeds, month),
    }
    received = {m for m, feed in NEEDS.items() if feed in got and NEEDS_ALSO.get(m, feed) in got}
    return {"month": month, "received": received, "counts": {m: dict(v) for m, v in counts.items()}}
