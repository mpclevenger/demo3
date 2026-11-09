"""Read one Non-TCC change export on its own (QUESTION_BANK R-TCC-13). Feeds TE-01: changes outside TCC (owner, 8 Nov 2026).

Upload never needs any other file. Placing a change with a family (Author Email -> HR) and the
check against the TCC file (Q-NTCC-06) happen at mapping.

The file has open questions, so the counting flags below are WORKING RULES taken from the
proposals in QUESTION_BANK, each marked with its question. Every original value is kept, so a
changed answer only changes the rule, never the load.
"""
from .common import column_map, emails_in, map_columns, norm, parse_when, read_table

# Built-in names (12 columns). The owner's names in config/column_maps.json ("ntcc") come first.
FIELDS = {f: (f,) for f in ("RPD ID", "RPD Link", "Status", "RPD Category", "Created Date (UTC)",
                            "Last updated (UTC)", "Author", "Author Email", "Department", "L4 director")}

# Q-NTCC-02 (proposal, to confirm with Change Management): these statuses mean deployed.
DEPLOYED_STATUSES = ("Completed", "Resolved", "Monitoring", "Client")


def read(raw_bytes):
    """Read a Non-TCC export. Returns dict(rows, set_aside, notes, working_rules, summary)."""
    notes, set_aside, rows, seen = [], [], [], set()
    headers, table = read_table(raw_bytes)
    col = map_columns(headers, column_map("ntcc", FIELDS), notes)
    g = lambda r, f: (r.get(col[f], "") if col[f] else "").strip()

    statuses = set()
    for i, r in enumerate(table, start=2):
        rid = g(r, "RPD ID").replace(",", "")
        if not rid:
            set_aside.append(dict(row=i, reason="no RPD ID"))
            continue
        if rid in seen:
            set_aside.append(dict(row=i, rpd=rid, reason="same RPD ID twice; first kept"))
            continue
        seen.add(rid)
        status = g(r, "Status")
        statuses.add(status or "(blank)")
        created = parse_when(g(r, "Created Date (UTC)"))
        updated = parse_when(g(r, "Last updated (UTC)"))
        when = created or updated
        deployed = any(norm(status) == norm(s) for s in DEPLOYED_STATUSES)
        emails = emails_in(g(r, "Author Email"))
        rows.append({
            "rpd_id": rid,
            "link": g(r, "RPD Link") or None,
            "status": status or None,
            "category": g(r, "RPD Category") or None,
            "created": created.isoformat() if created else None,
            "last_updated": updated.isoformat() if updated else None,
            "author": g(r, "Author") or None,
            # Q-NTCC-05 (proposal a): blank Author Email -> Not yet mapped. No name matching.
            "author_email": emails[0] if emails else None,
            "department": g(r, "Department") or None,
            "l4_director": g(r, "L4 director") or None,
            # Working rules (QUESTION_BANK proposals, to confirm):
            "deployed": deployed,                                              # Q-NTCC-02
            # Q-NTCC-01 (owner, 2 Nov): month = Created Date; Last updated only if Created Date is blank
            "month": (when.strftime("%Y-%m") if (deployed and when) else None),
            "month_from": ("Created Date" if created else "Last updated" if updated else None) if deployed else None,
            "approved": False,                                                 # Q-NTCC-04: never approved (kept for the record)
        })

    fallback = [x["rpd_id"] for x in rows if x["month_from"] == "Last updated"]
    if fallback:
        notes.append(f"{len(fallback)} deployed {'change has' if len(fallback) == 1 else 'changes have'} no Created Date; "
                     f"month taken from Last updated instead: {', '.join(fallback[:10])}")
    no_email = [x["rpd_id"] for x in rows if not x["author_email"]]
    if no_email:
        notes.append(f"{len(no_email)} {'change has' if len(no_email) == 1 else 'changes have'} no Author Email "
                     f"and will show as Not yet mapped: {', '.join(no_email[:10])}")
    notes.append("Working rules until Change Management answers: deployed = Status is " + ", ".join(DEPLOYED_STATUSES)
                 + " (Q-NTCC-02); month = Created Date, or Last updated if that is blank (Q-NTCC-01; there is no deployment date); "
                   "never counted as approved (Q-NTCC-04).")
    summary = dict(changes=len(rows), deployed=sum(x["deployed"] for x in rows), set_aside=len(set_aside),
                   statuses=sorted(statuses))
    return dict(rows=rows, set_aside=set_aside, notes=notes, summary=summary,
                working_rules={"deployed_statuses": list(DEPLOYED_STATUSES), "month_from": "Created Date (UTC), else Last updated (UTC)",
                               "approved": False, "questions": ["Q-NTCC-01", "Q-NTCC-02", "Q-NTCC-04", "Q-NTCC-05"]})
