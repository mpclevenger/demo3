"""Read the Jira issues file on its own (feed "defects"; owner, 3 Nov 2026). Feeds TE-03 (planned) and
the delivery figures (shown, not scored).

The file is jira_issues.csv from tools/jira_export.py (Jira Data Center): one row per issue, any type,
with its dates and the person who closed it. TRUST, not the export, works out the month's figures from
the dates, so the rules can change without exporting again.

Owner, 3 Nov 2026: an issue belongs to the team of the person who CLOSED it (the last move into a
Done-category status), not the assignee. That person is found in HR at mapping: work email first,
then Jira username = SAM_ACCOUNT. No match: Not yet mapped.

For a month (New York time, like every feed):
  closed in the month   resolved_at in the month (placed with the closer's family)
  opened in the month   created_at in the month (firm-wide: nobody has closed it yet)
  open at month-end     created by the end of the month, not resolved by then (firm-wide)
"""
import statistics

from .common import as_bool, column_map, map_columns, parse_when, read_table

FIELDS = {f: (f,) for f in (
    "issue_key", "project", "issue_type", "is_defect", "priority", "severity", "found_in_env",
    "status", "status_category", "resolution", "created_at", "first_in_progress_at", "resolved_at",
    "closed_by", "closed_by_email", "closed_by_username", "reopen_count", "story_points")}
NEEDED = ("issue_key", "issue_type", "created_at", "resolved_at", "closed_by_email", "closed_by_username")
UNMATCHED = "UNATTRIBUTED"   # the same "Not yet mapped" every feed uses
DEFECT_TYPES = ("bug", "defect")


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def read(raw_bytes):
    """Returns dict(rows, set_aside, notes, summary). Dates are ISO strings (New York if no timezone)."""
    notes, set_aside, rows, seen = [], [], [], set()
    cmap = column_map("defects", FIELDS)
    headers, table = read_table(raw_bytes, 1, cmap)
    col = map_columns(headers, cmap, notes)
    g = lambda r, f: (r.get(col[f], "") if col[f] else "").strip()
    missing = [f for f in NEEDED if col[f] is None]
    if missing:
        notes.append(f"No column for {', '.join(missing)}: the figures that need it can't be worked out")

    bad_dates, no_closer = {}, []
    for i, r in enumerate(table, start=2):
        key = g(r, "issue_key")
        if not key:
            set_aside.append(dict(row=i, reason="no issue_key"))
            continue
        if key.upper() in seen:
            set_aside.append(dict(row=i, reason=f"issue '{key}' is on more than one row; first kept"))
            continue
        seen.add(key.upper())
        when = {}
        for f in ("created_at", "first_in_progress_at", "resolved_at"):
            when[f] = parse_when(g(r, f))
            if g(r, f) and when[f] is None:
                bad_dates.setdefault(f, []).append(key)
        itype = g(r, "issue_type")
        flag = as_bool(g(r, "is_defect")) if g(r, "is_defect") else None
        is_defect = flag if flag is not None else itype.lower() in DEFECT_TYPES
        email, user = g(r, "closed_by_email").lower() or None, g(r, "closed_by_username").lower() or None
        if when["resolved_at"] and not (email or user):
            no_closer.append(key)
        reopens = _num(g(r, "reopen_count"))
        rows.append({
            "issue_key": key, "project": g(r, "project") or None, "issue_type": itype or None,
            "is_defect": is_defect, "priority": g(r, "priority") or None, "severity": g(r, "severity") or None,
            "found_in_env": g(r, "found_in_env") or None, "status": g(r, "status") or None,
            "status_category": g(r, "status_category").lower() or None, "resolution": g(r, "resolution") or None,
            "created_at": when["created_at"].isoformat() if when["created_at"] else None,
            "first_in_progress_at": when["first_in_progress_at"].isoformat() if when["first_in_progress_at"] else None,
            "resolved_at": when["resolved_at"].isoformat() if when["resolved_at"] else None,
            "closed_by": g(r, "closed_by") or None, "closed_by_email": email, "closed_by_username": user,
            "reopen_count": int(reopens) if reopens is not None else 0,
            "story_points": _num(g(r, "story_points")),
        })

    show = lambda names: ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
    for f, names in bad_dates.items():
        notes.append(f"{f} isn't a date for {len(names)} {'issue' if len(names) == 1 else 'issues'} ({show(names)})")
    if no_closer:
        notes.append(f"{len(no_closer)} closed {'issue has' if len(no_closer) == 1 else 'issues have'} nobody "
                     f"recorded as closing {'it' if len(no_closer) == 1 else 'them'}, so no team ({show(no_closer)})")
    summary = dict(issues=len(rows), defects=sum(x["is_defect"] for x in rows),
                   closed=sum(bool(x["resolved_at"]) for x in rows), set_aside=len(set_aside))
    return dict(rows=rows, set_aside=set_aside, notes=notes, summary=summary)


def _month_bounds(month):
    y, m = int(month[:4]), int(month[5:7])
    return parse_when(f"{y}-{m:02d}-01"), parse_when(f"{y + (m == 12)}-{(m % 12) + 1:02d}-01")


def _days(a, b):
    return (b - a).total_seconds() / 86400 if a and b else None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def place_and_measure(rows, month, people, family_of_sam):
    """Give each closed issue its closer's family and work out the month's figures (shown, not scored).

    Sets on each row: closer_sam, closer_matched_by, family_id (closed issues only).
    Returns dict(families={fid: {...}}, firm={...}, notes).
    """
    start, end = _month_bounds(month)
    by_email = {(p.get("email") or "").lower(): p["sam_account"].lower() for p in people if p.get("email")}
    sams = {p["sam_account"].lower() for p in people}
    fam = {k.lower(): v for k, v in (family_of_sam or {}).items()}
    when = lambda x, f: parse_when(x[f]) if x.get(f) else None

    notes, families, unmatched = [], {}, []
    closed = [x for x in rows if when(x, "resolved_at") and start <= when(x, "resolved_at") < end]
    for x in closed:
        sam, how = None, None
        if x["closed_by_email"] and x["closed_by_email"] in by_email:
            sam, how = by_email[x["closed_by_email"]], "email"
        elif x["closed_by_username"] and x["closed_by_username"] in sams:
            sam, how = x["closed_by_username"], "username = SAM_ACCOUNT"
        x["closer_sam"], x["closer_matched_by"] = sam, how
        x["family_id"] = fam.get(sam, UNMATCHED) if sam else UNMATCHED
        if x["family_id"] == UNMATCHED:
            unmatched.append(x["issue_key"])
        f = families.setdefault(x["family_id"], {"issues_closed": 0, "defects_closed": 0, "defects_reopened": 0,
                                                  "story_points_closed": 0.0, "_lead": [], "_cycle": [], "_dlead": []})
        lead = _days(when(x, "created_at"), when(x, "resolved_at"))
        cycle = _days(when(x, "first_in_progress_at"), when(x, "resolved_at"))
        f["issues_closed"] += 1
        f["story_points_closed"] += x["story_points"] or 0
        f["_lead"].append(lead)
        f["_cycle"].append(cycle)
        if x["is_defect"]:
            f["defects_closed"] += 1
            f["defects_reopened"] += x["reopen_count"] > 0
            f["_dlead"].append(lead)
    for f in families.values():
        f["median_lead_time_days"] = _median(f.pop("_lead"))
        f["median_cycle_time_days"] = _median(f.pop("_cycle"))
        f["median_defect_resolution_days"] = _median(f.pop("_dlead"))

    defects = [x for x in rows if x["is_defect"] and when(x, "created_at")]
    firm = {
        "defects_opened": sum(start <= when(x, "created_at") < end for x in defects),
        "defects_open_at_month_end": sum(when(x, "created_at") < end and
                                         not (when(x, "resolved_at") and when(x, "resolved_at") < end) for x in defects),
        "issues_closed": len(closed), "defects_closed": sum(x["is_defect"] for x in closed),
    }
    if rows and not closed:
        notes.append(f"No issue in the file was closed in {month}: check the export covers this month")
    if unmatched:
        notes.append(f"{len(unmatched)} {'issue' if len(unmatched) == 1 else 'issues'} closed in {month} by someone "
                     f"TRUST couldn't match to HR, so {'it is' if len(unmatched) == 1 else 'they are'} Not yet mapped: "
                     f"{', '.join(unmatched[:8])}{'…' if len(unmatched) > 8 else ''}")
    return dict(families=families, firm=firm, unmatched=len(unmatched), notes=notes)
