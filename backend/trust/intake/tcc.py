"""Read one TCC change export on its own (doc 14). Feeds TE-01 and TE-02.

Upload never needs any other file. Each change ticket becomes one row with its dates read in
whatever format the file uses, its codes read case-insensitively, and simple flags the scoring
step will count. Placing a change with a family (Author email -> HR) happens at scoring.

Column names confirmed by the owner, 3 Nov 2026 (RPD ID, RPD Link, Actual Last Deployment, ...): they are
first in config/column_maps.json. Names and values are matched whatever their capitals (and spaces and
punctuation), and known values are stored in one standard spelling.
"""
from .common import add_days, column_map, leading_code, map_columns, norm, parse_when, read_table

# Built-in names: the 29 columns TRUST loads (doc 14). The owner's names in
# config/column_maps.json ("tcc") come first.
FIELDS = {f: (f,) for f in (
    "Ticket ID", "Ticket Link", "Status", "Change Category", "Risk Score", "Created date (UTC)",
    "Author", "Author email", "Assignees", "Department", "L4 director",
    "Planned start", "Planned end", "last deployment",
    "Implementer", "Peer reviewer", "Peer review outcome", "confirmed risk rating",
    "overall change approval", "Go/No-Go meeting", "Go/no-go outcome",
    "Overall outcome", "Resolved", "Pre-Deploy Compliant", "Fully Compliant", "Fields Missing",
    "peer review recorded at (UTC)", "Approval recorded at (UTC)", "Outcome recorded at (UTC)")}

# Which metric needs which fields: if one is missing, that metric shows No data for the month.
NEEDS = {"TE-01": ("Ticket ID", "last deployment", "Approval recorded at (UTC)"),
         "TE-02": ("Ticket ID", "last deployment", "Overall outcome", "Outcome recorded at (UTC)")}

# Known values, matched case-insensitively. Anything else is kept and noted.
STATUSES = ("Client", "Completed", "Hold", "Monitoring", "Pending", "Resolved", "Unassigned")
RISK_SCORES = ("Standard Change", "NO risk", "LOW risk", "MEDIUM risk", "HIGH risk", "EXTREME risk")
YES_NO = ("Yes", "No")
PRE_DEPLOY = ("Yes", "No", "N/A")
FULLY_COMPLIANT = ("Yes", "Obsoleted/Withdrawn", "No (Outcome marked as Unknown)", "Not Yet (Pending Deployment)", "No",
                   "No (Peer review not completed)", "No (Outcome marked as Unknown; Peer review not completed)")
CATEGORIES = ("Emergency", "Planned", "Standard")
OUTCOMES = {"00", "10", "40", "50", "60", "90", "95", "99"}
REVERT = {"40", "50", "60", "90"}           # backed out (90 = backout initiated by client)
DATE_FIELDS = ("Created date (UTC)", "Planned start", "Planned end", "last deployment", "Go/No-Go meeting",
               "peer review recorded at (UTC)", "Approval recorded at (UTC)", "Outcome recorded at (UTC)")


def _canon(value, known):
    """Return the known spelling of value (any case), or None."""
    return next((k for k in known if norm(k) == norm(value)), None)


def read(raw_bytes):
    """Read a TCC export. Returns dict(rows, set_aside, notes, no_data_metrics, summary).

    Raises ValueError only when the file cannot be read as text at all.
    """
    notes, set_aside, rows, seen = [], [], [], set()
    headers, table = read_table(raw_bytes)
    col = map_columns(headers, column_map("tcc", FIELDS), notes)
    g = lambda r, f: (r.get(col[f], "") if col[f] else "").strip()
    no_data = sorted(m for m, fs in NEEDS.items() if any(col[f] is None for f in fs))
    for m in no_data:
        missing = [f for f in NEEDS[m] if col[f] is None]
        notes.append(f"{m} will show No data: the file has no column for {', '.join(missing)}")

    unknown = {"Status": set(), "Change Category": set(), "Overall outcome": set(), "Risk Score": set(),
               "Resolved": set(), "Pre-Deploy Compliant": set(), "Fully Compliant": set()}

    def known(field, values, r):
        """The value in its standard spelling (any capitals in the file); anything else kept as it is and noted."""
        raw = g(r, field)
        hit = _canon(raw, values)
        if raw and not hit:
            unknown[field].add(raw)
        return hit or raw or None
    bad_dates = {}
    for i, r in enumerate(table, start=2):
        tid = g(r, "Ticket ID")
        if not tid or not tid.replace(",", "").isdigit():
            set_aside.append(dict(row=i, ticket=tid or None, reason="Ticket ID blank or not a number"))
            continue
        tid = tid.replace(",", "")
        if tid in seen:
            set_aside.append(dict(row=i, ticket=tid, reason="same Ticket ID twice; first kept"))
            continue
        seen.add(tid)

        when = {}
        for f in DATE_FIELDS:
            raw = g(r, f)
            when[f] = parse_when(raw)
            if raw and when[f] is None:
                bad_dates.setdefault(f, []).append(tid)   # value kept blank, row still loads

        status = _canon(g(r, "Status"), STATUSES)
        if g(r, "Status") and not status:
            unknown["Status"].add(g(r, "Status"))
        category = _canon(g(r, "Change Category"), CATEGORIES)
        if g(r, "Change Category") and not category:
            unknown["Change Category"].add(g(r, "Change Category"))
        outcome = leading_code(g(r, "Overall outcome"))
        if g(r, "Overall outcome") and outcome not in OUTCOMES:
            unknown["Overall outcome"].add(g(r, "Overall outcome"))

        deployed_at = when["last deployment"]
        approved_at = when["Approval recorded at (UTC)"]
        approval = g(r, "overall change approval")
        rows.append({
            "ticket_id": tid,
            "link": g(r, "Ticket Link") or None,
            "status": status or g(r, "Status") or None,
            "category": category or g(r, "Change Category") or None,
            "risk_score": known("Risk Score", RISK_SCORES, r),
            "author": g(r, "Author") or None,
            "author_email": g(r, "Author email").lower() or None,   # joins to HR at scoring
            "department": g(r, "Department") or None,
            "l4_director": g(r, "L4 director") or None,
            "implementer": g(r, "Implementer") or None,
            "peer_reviewer": g(r, "Peer reviewer") or None,
            "peer_review_outcome": leading_code(g(r, "Peer review outcome")),
            "overall_change_approval": approval or None,
            "overall_outcome": outcome,
            "resolved": known("Resolved", YES_NO, r),
            "pre_deploy_compliant": known("Pre-Deploy Compliant", PRE_DEPLOY, r),
            "fully_compliant": known("Fully Compliant", FULLY_COMPLIANT, r),
            **{f"{norm(f)}": (when[f].isoformat() if when[f] else None) for f in DATE_FIELDS},
            # Simple flags the scoring step counts (doc 14; owner decisions 1 Nov 2026).
            "deployed": deployed_at is not None,
            "deploy_month": deployed_at.strftime("%Y-%m") if deployed_at else None,   # New York time; info only
            # Owner, 2 Nov 2026: a deployed change counts in the month its ticket was CREATED
            # (same rule as Non-TCC). last deployment only if Created date is blank.
            "month": ((when["Created date (UTC)"] or deployed_at).strftime("%Y-%m") if deployed_at else None),
            "month_from": (("Created date" if when["Created date (UTC)"] else "last deployment") if deployed_at else None),
            # TE-02 (owner, 2 Nov 2026): a release counts in the month its 7-day revert window ends,
            # i.e. the month of last deployment + 7 days (New York).
            "te02_month": add_days(deployed_at, 7).strftime("%Y-%m") if deployed_at else None,
            "client_impact": status == "Client",
            "revert": outcome in REVERT,
            "outcome_unknown": outcome == "99",            # own count, out of the revert rate
            "obsoleted": outcome == "95",                  # out
            # Approved before deployment: Standard changes count as approved; otherwise an approval
            # value that isn't obsoleted/rejected, recorded before the deployment. Code list still
            # to come (Q-TCC-03), so this is the working rule.
            "approved_before_deploy": bool(deployed_at) and (
                category == "Standard" or (
                    bool(approval) and not approval.upper().startswith(("OBSOLETED", "REJECTED"))
                    and approved_at is not None and approved_at < deployed_at)),
        })

    for f, tids in bad_dates.items():
        notes.append(f"{len(tids)} {'ticket has' if len(tids) == 1 else 'tickets have'} a '{f}' that isn't a date "
                     f"(left blank): {', '.join(tids[:10])}{' …' if len(tids) > 10 else ''}")
    for f, vals in unknown.items():
        if vals:
            notes.append(f"unexpected {f} values kept as they are: {', '.join(sorted(vals)[:10])}")
    deployed = [x for x in rows if x["deployed"]]
    fallback = [x["ticket_id"] for x in deployed if x["month_from"] == "last deployment"]
    if fallback:
        notes.append(f"{len(fallback)} deployed {'ticket has' if len(fallback) == 1 else 'tickets have'} no Created date; "
                     f"month taken from last deployment instead: {', '.join(fallback[:10])}")
    summary = dict(tickets=len(rows), deployed=len(deployed), set_aside=len(set_aside),
                   reverts=sum(x["revert"] for x in deployed),
                   approved_before_deploy=sum(x["approved_before_deploy"] for x in deployed),
                   client_impact=sum(x["client_impact"] for x in deployed),
                   months=sorted({x["month"] for x in deployed}))
    return dict(rows=rows, set_aside=set_aside, notes=notes, no_data_metrics=no_data, summary=summary)
