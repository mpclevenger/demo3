"""The items behind a family's numbers, in plain words: for the drill-down ("What's driving it") and
the CSV download of a family's items (owner, 3 Nov 2026).

Each item says what it is (a change, an action, an incident, a repo), who and which team it belongs to
(HR supervisory organization), the dates that matter, and what it means for the metric.
"""
import csv
import io

from . import config

# What the items are called and what type they are: counting.items_name / item_type in config/metrics.json.
_COUNTING = {mid: x["counting"] for mid, x in config.metrics().items() if x.get("counting")}
NAMES = {mid: c["items_name"] for mid, c in _COUNTING.items() if c.get("items_name")}




def _day(v):
    return str(v)[:10] if v else ""


def describe(mid, it):
    """-> dict(result, concern, date, date_label): concern = this item is what pulls the metric down."""
    if mid == "TE-01":
        ok = it.get("through_tcc")
        return dict(result="Through TCC" if ok else "Outside TCC (Non-TCC change)",
                    concern=not ok, date=_day(it.get("created")), date_label="Created")
    if mid == "TE-02":
        res = "Reverted" if it.get("revert") else "Not reverted"
        if it.get("client_impact"):
            res += "; client impact"
        return dict(result=res, concern=bool(it.get("revert") or it.get("client_impact")),
                    date=_day(it.get("deployed")), date_label="Deployed")
    if mid == "UN-02":
        due = _day(it.get("due"))
        res = ("Overdue" if it.get("overdue") else "Open, not yet due") + (f" (due {due})" if due else "")
        if it.get("due_from_blank_eta"):
            res += "; no ETA, so due 30 days after it was created"
        return dict(result=res, concern=bool(it.get("overdue")), date=due, date_label="Due")
    if mid == "UN-01":
        return dict(result="SWE incident (DEFCON 1-2)" if it.get("class") == "SWE" else "Critical incident (DEFCON 3-5)",
                    concern=True, date=_day(it.get("ended")), date_label="Ended")
    if mid in ("SE-01", "SE-02"):
        ok = it.get("passed")
        return dict(result="Passes the policy" if ok else "Fails the policy", concern=not ok, date="", date_label="")
    if mid == "TR-01":
        n = it.get("n_apps", 0)
        res = ("Mapped to one app" if n == 1 else "Not mapped to an app in the app inventory" if n == 0
               else f"Mapped to {n} apps")
        return dict(result=res, concern=n == 0, date="", date_label="")
    if mid == "TR-02":
        n, of, failed = it.get("passed_checks", 0), it.get("of", 5), it.get("failed") or []
        res = f"{n} of {of} checks" + (f"; fails: {', '.join(failed)}" if failed else "")
        if not it.get("protected"):
            res += "; main branch not protected"
        return dict(result=res, concern=bool(failed), date="", date_label="")
    if mid in ("RE-01", "RE-03"):
        ok = it.get("passed")
        res = (f"{it.get('test_kind')} completed" if ok else
               f"No {'DR test' if mid == 'RE-01' else 'successful test'} in the last 12 months") + \
              (f" ({it['tier']})" if it.get("tier") else "")
        return dict(result=res, concern=not ok, date=_day(it.get("tested_on")), date_label="Tested" if ok else "")
    return dict(result="", concern=False, date="", date_label="")


def family_items(scored, fid):
    """Every item for one family in a scored month, described, in metric order."""
    out = []
    for mid in sorted((scored.get("items") or {}).get(fid, {})):
        for it in scored["items"][fid][mid]:
            d = describe(mid, it)
            out.append({"metric": mid, "metric_name": NAMES.get(mid, mid), "item": it.get("id"),
                        "result": d["result"], "needs_attention": d["concern"],
                        "person": it.get("person") or "", "team": it.get("team") or "",
                        "date_label": d["date_label"], "date": d["date"],
                        "incident": it.get("incident") or "", "detail": it.get("comment") or "",
                        "app": "; ".join(it.get("apps") or []), "app_owners": ", ".join(it.get("app_owners") or []),
                        "link": it.get("link") or ""})
    return out


def _cell(v):
    """Excel runs a cell starting with = + - @ (or tab/CR) as a formula; provider text could do that, so quote it."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


COLUMNS = (("metric", "Metric"), ("metric_name", "Metric name"), ("item", "Item"), ("result", "What it shows"),
           ("needs_attention", "Needs attention"), ("person", "Person"), ("team", "Team"),
           ("date_label", "Date is"), ("date", "Date"), ("incident", "Incident"), ("detail", "Detail"),
           ("app", "App"), ("app_owners", "App owners"), ("link", "Link"))


def to_csv(rows, month, family_name):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"TRUST items for {family_name}, {month}. Each row is one item behind the family's numbers."])
    w.writerow([label for _, label in COLUMNS])
    for r in rows:
        w.writerow([_cell("Yes" if r.get(k) is True else "No" if r.get(k) is False else r.get(k)) for k, _ in COLUMNS])
    return "﻿" + buf.getvalue()           # the byte-order mark makes Excel read names with accents correctly


# ---- evidence.json: the shape the page's drill-down reads (EV[month][family][metric]) ----

TYPES = {mid: c["item_type"] for mid, c in _COUNTING.items() if c.get("item_type")}
NO_TEAM = ("NO-TEAM", "Not placed with a team")
NO_APP = "NO-APP"                  # the page shows it as "Not mapped to an app"


def _by_app(mid, items):
    """The drill-down's "By app / repo" bars (owner, 6 Nov 2026): items counted under the app(s) the app inventory
    links them to. Shown only once at least one item has an app; an item on two apps counts under each."""
    if not any(it.get("apps") for it in items):
        return []
    apps = {}
    for it in items:
        for name in it.get("apps") or [NO_APP]:
            a = apps.setdefault(name, {"app_id": name, "num": 0, "den": 0, "override": False})
            if mid == "TR-02":
                a["num"] += it.get("passed_checks", 0)
                a["den"] += it.get("of", 5)
            else:
                a["num"] += _in_numerator(mid, it)
                a["den"] += 1
    return sorted(apps.values(), key=lambda a: (a["app_id"] == NO_APP, -a["den"], a["app_id"]))


def _in_numerator(mid, it):
    """Whether an item is in the metric's numerator: the item field named by counting.numerator_field in
    config/metrics.json (e.g. through_tcc, revert, passed). TR-02 counts a repo with no failed check; a metric
    with no field (UN-01, a count) counts every item."""
    if mid == "TR-02":
        return not it.get("failed")
    field = _COUNTING.get(mid, {}).get("numerator_field")
    return bool(it.get(field)) if field else True


def _days_overdue(it, month_end):
    import datetime
    due = _day(it.get("due"))
    if not (it.get("overdue") and due):
        return None
    try:
        return (month_end - datetime.date.fromisoformat(due)).days
    except ValueError:
        return None


def page_evidence(scored, month):
    """{family: {metric: entry}} for one scored month, in the format the drill-down reads."""
    import datetime
    y, m = map(int, month.split("-"))
    month_end = datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
    out = {}
    for fid, by_metric in (scored.get("items") or {}).items():
        for mid, items in by_metric.items():
            teams, rows = {}, []
            for it in items:
                key, name = (it.get("team_key"), it.get("team")) if it.get("team_key") else NO_TEAM
                t = teams.setdefault(key, {"team_key": key, "team_name": name or key, "num": 0, "den": 0})
                inn = _in_numerator(mid, it)
                if mid == "TR-02":          # counted in checks, like the family's figure (5 per repo)
                    t["num"] += it.get("passed_checks", 0)
                    t["den"] += it.get("of", 5)
                else:
                    t["num"] += inn
                    t["den"] += 1
                d = describe(mid, it)
                rows.append({"item_id": it.get("id"), "item_type": TYPES.get(mid, "item"),
                             "app_id": "; ".join(it.get("apps") or []) or None,
                             "team_key": key, "severity": it.get("class") if mid == "UN-01" else None,
                             "opened_at": _day(it.get("created")) or None, "due_at": _day(it.get("due")) or None,
                             "days_overdue": _days_overdue(it, month_end), "status_at_as_of": it.get("status"),
                             "in_denominator": True, "in_numerator": inn,
                             "tag": d["result"] + (f" · {it['person']}" if it.get("person") else ""),
                             "person": it.get("person"), "link": it.get("link"),
                             "attributes": {"app_owners": ", ".join(it["app_owners"])} if it.get("app_owners") else {}})
            out.setdefault(fid, {})[mid] = {
                "by_team": sorted(teams.values(), key=lambda t: (-t["den"], t["team_name"])), "by_app": _by_app(mid, items),
                "items": rows, "n_items": len(rows), "excluded_count": 0}
    return out
