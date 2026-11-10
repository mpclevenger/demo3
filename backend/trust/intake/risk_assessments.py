"""Read the risk assessment results on their own (feed "risk_assessments"; owner, 9 Nov 2026).

The risk assessment engine works out each assessed group's inherent risk (before controls) from its drivers:
questionnaire answers and data-based checks. For now its results come to TRUST as a CSV, one row per group per
risk (owner, 9 Nov 2026):

    Group | Departments | Assessment date | Risk ID | Applicable | Likelihood | Impact | Drivers

    Group:            the group the assessment was done on, usually an L4 ("Analytics").
    Departments:      the HR Departments the group covers, separated by ; (they match HR's Department column).
    Assessment date:  any common date format.
    Risk ID:          the engine's risk ID, e.g. air.cyber.01 (metrics link to risks by this ID).
    Applicable:       blank or yes = applicable; no / NOT_APPLICABLE = not applicable (left out).
    Likelihood, Impact: LOW, MEDIUM, HIGH or CRITICAL, any case ("Med" and "Crit" are read too).
    Drivers:          optional plain text: why, e.g. the triggered drivers and their commentary, separated by |.

Column names are in config/column_maps.json (feed "risk_assessments"), so a real file with other names can be
matched. Nothing about the group's people, headcount or processes is read.

Elevated (proposed rule, owner 9 Nov 2026; to confirm with the Head of Tech Risk): likelihood is HIGH or CRITICAL
and impact is HIGH or CRITICAL. Only applicable risks count.
"""
from .common import column_map, map_columns, parse_when, read_table

FIELDS = {"Group": ("Group", "business unit", "business_unit", "group name", "team", "assessed group"),
          "Departments": ("Departments", "department", "selected scope", "score_departments", "scope"),
          "Assessment date": ("Assessment date", "assessment_date", "assessed on", "date"),
          "Risk ID": ("Risk ID", "risk_id", "risk", "id"),
          "Applicable": ("Applicable", "applicability"),
          "Likelihood": ("Likelihood", "inherent likelihood"),
          "Impact": ("Impact", "inherent impact"),
          "Drivers": ("Drivers", "drivers triggered", "triggered drivers", "rationale", "why")}
NEEDED = ("Group", "Risk ID", "Likelihood", "Impact")
LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_ALIASES = {"MED": "MEDIUM", "MODERATE": "MEDIUM", "CRIT": "CRITICAL", "VERY HIGH": "CRITICAL", "HI": "HIGH", "LO": "LOW"}


def level(v):
    """'high' -> 'HIGH'; 'Med' -> 'MEDIUM'; anything else -> None."""
    t = " ".join(str(v or "").replace("_", " ").split()).upper()
    return t if t in LEVELS else _ALIASES.get(t)


def elevated(likelihood, impact):
    """The proposed rule (owner, 9 Nov 2026): likelihood HIGH or CRITICAL, and impact HIGH or CRITICAL."""
    return likelihood in ("HIGH", "CRITICAL") and impact in ("HIGH", "CRITICAL")


def _applicable(v):
    t = str(v or "").strip().lower().replace("_", " ")
    return t not in ("no", "n", "false", "0", "not applicable", "n/a", "na")


def read(raw_bytes):
    """Returns dict(rows=[{group, departments, assessed_on, risk_id, likelihood, impact, elevated, drivers}],
    set_aside, notes, summary). Not-applicable risks are counted, not kept."""
    notes, set_aside, rows, seen = [], [], [], set()
    headers, table = read_table(raw_bytes, fields=FIELDS)
    col = map_columns(headers, column_map("risk_assessments", FIELDS), notes)
    missing = [f for f in NEEDED if not col.get(f)]
    if missing:
        notes.append(f"Column{'s' if len(missing) > 1 else ''} not found: {', '.join(missing)}. "
                     "Without them no risk can be read.")
    g = lambda r, f: (r.get(col[f], "") if col.get(f) else "").strip()
    not_applicable = 0
    for i, r in enumerate(table, start=2):
        group, rid = g(r, "Group"), g(r, "Risk ID")
        if not group or not rid:
            set_aside.append(dict(row=i, reason="no Group" if not group else "no Risk ID"))
            continue
        if not _applicable(g(r, "Applicable")):
            not_applicable += 1
            continue
        li, im = level(g(r, "Likelihood")), level(g(r, "Impact"))
        if li is None or im is None:
            set_aside.append(dict(row=i, reason=f"likelihood or impact isn't LOW, MEDIUM, HIGH or CRITICAL "
                                                f"({g(r, 'Likelihood') or 'blank'} / {g(r, 'Impact') or 'blank'})"))
            continue
        if (group.lower(), rid.lower()) in seen:
            set_aside.append(dict(row=i, reason=f"{rid} for {group} appears twice; the first row is used"))
            continue
        seen.add((group.lower(), rid.lower()))
        when = parse_when(g(r, "Assessment date"))
        rows.append({"group": group, "departments": [d.strip() for d in g(r, "Departments").replace(",", ";").split(";") if d.strip()],
                     "assessed_on": when.date().isoformat() if when else None, "risk_id": rid,
                     "likelihood": li, "impact": im, "elevated": elevated(li, im),
                     "drivers": [d.strip() for d in g(r, "Drivers").split("|") if d.strip()]})
    groups = sorted({x["group"] for x in rows})
    no_date = sorted({x["group"] for x in rows if not x["assessed_on"]})
    if no_date:
        notes.append(f"No assessment date for {', '.join(no_date[:5])}{' and more' if len(no_date) > 5 else ''}: "
                     "TRUST can't say how fresh it is.")
    summary = {"rows": len(rows), "groups": len(groups), "elevated": sum(x["elevated"] for x in rows),
               "not_applicable": not_applicable, "set_aside": len(set_aside)}
    return {"rows": rows, "set_aside": set_aside, "notes": notes, "summary": summary}


def _worse(a, b):
    """The more serious of two assessments of one risk: Elevated first, then the higher of likelihood/impact."""
    key = lambda x: (x["elevated"], max(LEVELS.index(x["likelihood"]), LEVELS.index(x["impact"])),
                     min(LEVELS.index(x["likelihood"]), LEVELS.index(x["impact"])))
    return a if key(a) >= key(b) else b


def by_family(rows, families_of_group):
    """{family id: {risk id: the most serious assessment among its groups}} (owner, 9 Nov 2026: a family takes
    the highest rating among its groups, and the page names the group behind it)."""
    out = {}
    for x in rows:
        for fid in families_of_group.get(x["group"]) or []:
            cur = out.setdefault(fid, {}).get(x["risk_id"])
            out[fid][x["risk_id"]] = x if cur is None else _worse(cur, x)
    return out
