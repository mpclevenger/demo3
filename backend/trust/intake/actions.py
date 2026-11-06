"""Read one postmortem action items export on its own (doc 15). Feeds UN-02.

Action items are the only file in this pair with a person on them, so they carry the link to a
family: assignee email -> HR -> team -> family. That join happens at scoring
(backend/trust/linking.py). Upload never needs the postmortem file or HR.
"""
import re

from .common import add_days, column_map, emails_in, map_columns, norm, parse_when, read_table

# Built-in names (doc 15, 16-column export). The owner's names in config/column_maps.json ("actions") come first.
FIELDS = {f: (f,) for f in ("Type", "ActionItemLink", "Severity", "Created", "ETA", "Assignees",
                            "ActionCategory", "Status", "SBU", "PostmortemLink", "incident_id")}

# Status mapping (owner, 1 Nov 2026), matched case-insensitively. Anything not listed counts as Open
# and is noted, so a new portal status never drops an action.
STATUS = {"completed": "Done", "resolved": "Done", "cancelled": "Cancelled", "canceled": "Cancelled",
          "monitoring": "Tracking", "readonly": "Tracking"}
KNOWN_OPEN = {"todo", "queued", "pending", "unassigned", "inprogress", "hold", "review", "qa", "client", ""}

BLANK_ETA_DAYS = 30            # blank ETA -> overdue 30 days after Created (OD-18)
HYPERLINK = re.compile(r'=\s*HYPERLINK\(\s*"([^"]*)"\s*[,;]\s*"([^"]*)"\s*\)', re.I)


def parse_link(cell):
    """'=HYPERLINK("https://jira/ABCD-1234","JIRA:ABCD-1234")' -> (url, 'JIRA:ABCD-1234').
    A plain value (export saved as values only) is kept as the label with no URL."""
    s = str(cell or "").strip()
    m = HYPERLINK.match(s)
    if m:
        return m.group(1) or None, m.group(2).strip() or None
    return (s if s.lower().startswith("http") else None), (s or None)


def read(raw_bytes):
    """Read an action items export. Returns dict(rows, set_aside, notes, no_data_metrics, summary).

    Raises ValueError only when the file cannot be read as text at all.
    """
    notes, set_aside, rows, seen = [], [], [], set()
    headers, table = read_table(raw_bytes)
    col = map_columns(headers, column_map("actions", FIELDS), notes)
    g = lambda r, f: (r.get(col[f], "") if col[f] else "").strip()
    no_data = ["UN-02"] if col["Status"] is None or (col["ETA"] is None and col["Created"] is None) else []
    if no_data:
        notes.append("UN-02 will show No data: the file needs Status and a due date (ETA or Created)")
    if col["Assignees"] is None:
        notes.append("no Assignees column: every action will show as Not yet mapped")

    new_status, bad_dates = set(), []
    for i, r in enumerate(table, start=2):
        url, label = parse_link(g(r, "ActionItemLink"))
        key = (label or url or "").strip()
        if not key:
            set_aside.append(dict(row=i, reason="no action item link or ID"))
            continue
        if norm(key) in seen:
            set_aside.append(dict(row=i, item=key, reason="same action listed twice; first kept"))
            continue
        seen.add(norm(key))

        raw_status = g(r, "Status")
        status = STATUS.get(norm(raw_status))
        if status is None:
            status = "Open"
            if norm(raw_status) not in KNOWN_OPEN:
                new_status.add(raw_status)
        created = parse_when(g(r, "Created"))
        eta = parse_when(g(r, "ETA"))
        for f, v in (("Created", created), ("ETA", eta)):
            if g(r, f) and v is None:
                bad_dates.append(f"{key} ({f})")
        due = eta or add_days(created, BLANK_ETA_DAYS)
        assignees = emails_in(g(r, "Assignees"))

        rows.append({
            "item_ref": key,                                # e.g. JIRA:ABCD-1234
            "item_type": g(r, "Type") or (key.split(":", 1)[0] if ":" in key else None),
            "url": url,                                     # source link
            "severity": g(r, "Severity") or None,           # info only
            "category": g(r, "ActionCategory") or None,
            "status_raw": raw_status or None,
            "status": status,                               # Done / Cancelled / Tracking / Open
            "open": status in ("Open", "Tracking"),         # Tracking counts as open (owner, 1 Nov)
            "created": created.isoformat() if created else None,
            "eta": eta.isoformat() if eta else None,
            "due": due.isoformat() if due else None,
            "due_from_blank_eta": eta is None and due is not None,
            # The person who places this action with a family: first assignee listed (proposed default).
            "assignee_email": assignees[0] if assignees else None,
            "all_assignee_emails": assignees,
            "assignees_raw": g(r, "Assignees") or None,
            "incident_id": g(r, "incident_id") or None,     # links to the postmortem file at scoring
            "postmortem_link": g(r, "PostmortemLink") or None,
            "sbu": g(r, "SBU") or None,
        })

    if new_status:
        notes.append(f"statuses not in the mapping, counted as Open: {', '.join(sorted(new_status))}")
    if bad_dates:
        notes.append(f"{len(bad_dates)} dates that aren't dates (left blank): {', '.join(bad_dates[:10])}")
    no_email = [x["item_ref"] for x in rows if not x["assignee_email"]]
    if no_email:
        notes.append(f"{len(no_email)} {'action has' if len(no_email) == 1 else 'actions have'} no assignee email "
                     f"and will show as Not yet mapped: {', '.join(no_email[:10])}")
    summary = dict(actions=len(rows), set_aside=len(set_aside),
                   open=sum(x["open"] for x in rows), cancelled=sum(x["status"] == "Cancelled" for x in rows),
                   done=sum(x["status"] == "Done" for x in rows), with_assignee=sum(bool(x["assignee_email"]) for x in rows))
    return dict(rows=rows, set_aside=set_aside, notes=notes, no_data_metrics=no_data, summary=summary)
