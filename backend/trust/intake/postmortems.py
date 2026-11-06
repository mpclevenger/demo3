"""Read one postmortems export on its own (doc 15). Feeds UN-02 scope and coverage.

Postmortems have no owner on them. An incident is placed with a family through its action items'
assignees (backend/trust/linking.py, at scoring). Upload never needs the action file or HR.
"""
from .common import as_bool, column_map, map_columns, norm, parse_when, read_table

# Built-in names (doc 15). The owner's names in config/column_maps.json ("postmortems") come first.
FIELDS = {
    "incident_id": ("incident_id",), "SBU": ("SBU",), "end_datetime": ("end_datetime",),
    "Incident type": ("Incident type",), "Incident Defcon": ("Incident Defcon",),
    "incident_defcon_type": ("incident_defcon_type",), "postmortem_conducted": ("postmortem_conducted",),
    "user_stakeholders": ("user_stakeholders",),
    "postmortem_id": ("postmoretm_id", "postmortem_id"),   # the export spells it "postmoretm_id"
    "postmortem_is_primary": ("postmortem_is_primary",), "action_items_total": ("action_items_total",),
}

# DEFCON type words, normalised (the export has the typo "critial").
DEFCON_TYPES = {"critical": "critical", "critial": "critical", "swe": "SWE", "falsealarm": "false alarm",
                "duplicate": "duplicate", "awareness": "awareness", "cannotdetermine": "cannot determine"}


def read(raw_bytes):
    """Read a postmortems export. Returns dict(rows, set_aside, notes, summary).

    One row per postmortem; an incident can have several (all count, owner 1 Nov). In scope =
    any incident that is not DEFCON 0, including blank and "Not Available" (owner, 1 Nov).
    """
    notes, set_aside, rows, seen = [], [], [], set()
    headers, table = read_table(raw_bytes)
    col = map_columns(headers, column_map("postmortems", FIELDS), notes)
    g = lambda r, f: (r.get(col[f], "") if col[f] else "").strip()
    if col["Incident Defcon"] is None:
        notes.append("no Incident Defcon column: every incident is treated as in scope")

    for i, r in enumerate(table, start=2):
        inc = g(r, "incident_id")
        if not inc:
            set_aside.append(dict(row=i, reason="no incident_id"))
            continue
        pm = g(r, "postmortem_id") or None
        key = (norm(inc), pm)
        if key in seen:
            set_aside.append(dict(row=i, incident=inc, reason="same incident and postmortem listed twice; first kept"))
            continue
        seen.add(key)

        defcon_raw = g(r, "Incident Defcon")
        defcon = int(defcon_raw) if defcon_raw.isdigit() else None        # "Not Available" / blank -> None
        dtype_raw = g(r, "incident_defcon_type")
        dtype = next((v for k, v in DEFCON_TYPES.items() if k in norm(dtype_raw)), dtype_raw or None)
        # Risk class for UN-01 (owner, 2 Nov 2026: Critical and SWE incidents). DEFCON 1-2 = SWE,
        # 3-5 = critical (mapping as given); the type column is used when the number isn't there.
        if defcon in (1, 2) or (defcon is None and dtype == "SWE"):
            risk_class = "SWE"
        elif defcon in (3, 4, 5) or (defcon is None and dtype == "critical"):
            risk_class = "critical"
        else:
            risk_class = None                                              # DEFCON 0, cannot determine, blank
        end = parse_when(g(r, "end_datetime"))
        if g(r, "end_datetime") and end is None:
            notes.append(f"{inc}: end_datetime '{g(r, 'end_datetime')}' isn't a date (left blank)")
        total = g(r, "action_items_total").replace(",", "")
        rows.append({
            "incident_id": inc,
            "postmortem_id": pm,
            "is_primary": as_bool(g(r, "postmortem_is_primary")),
            "defcon": defcon,
            "defcon_raw": defcon_raw or None,
            "defcon_type": dtype,
            "in_scope": defcon != 0,
            "risk_class": risk_class,                    # "critical", "SWE" or None                     # DEFCON 0 is out; blank / Not Available are in
            "incident_type": g(r, "Incident type") or None,
            "postmortem_conducted": as_bool(g(r, "postmortem_conducted")),
            "end_datetime": end.isoformat() if end else None,
            "action_items_total": int(total) if total.isdigit() else None,
            "sbu": g(r, "SBU") or None,
            # Fallback for placing an incident that has no actions (SAM_ACCOUNTs). Mapping key only, never shown.
            "user_stakeholders": [s.strip().lower() for s in g(r, "user_stakeholders").replace(";", ",").split(",") if s.strip()],
        })

    incidents = {x["incident_id"] for x in rows}
    summary = dict(postmortems=len(rows), incidents=len(incidents), set_aside=len(set_aside),
                   in_scope_incidents=len({x["incident_id"] for x in rows if x["in_scope"]}),
                   defcon0_incidents=len({x["incident_id"] for x in rows if not x["in_scope"]}))
    return dict(rows=rows, set_aside=set_aside, notes=notes, summary=summary)
