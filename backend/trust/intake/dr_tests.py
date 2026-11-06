"""Read the completed DR tests file on its own (feed "dr_tests"; layout from the owner, 3 Nov 2026).

One row per test, columns:

    Tier | Name | Business Area | ITDR Lead | Type of Test | When | Status | Comments

    Tier: as in the ITDR application file (Tier 0 to Tier 5, or TBC).
    Name: the application's name, as in the ITDR application file (not always clean; tidied the same way).
    Business Area: not always filled in.
    ITDR Lead: who led the test, kept as written.
    Type of Test (owner, 3 Nov 2026): Open = a DR test in production (live); Closed = a DR test that
              doesn't touch production (UAT, test); TTX = a tabletop exercise, which is NOT a DR test.
              Anything else is kept as written and listed, and counts as neither.
    When: MM/DD/YYYY (an Excel date works too). The date of a tabletop exercise (owner, 3 Nov 2026).
    Status: Successful, or blank. Blank means it hasn't been performed (owner, 3 Nov 2026).
    Comments: usually "DR Test completed on 14th March 2026" (any capitals): for a DR test this is the
              last time it was performed (owner, 3 Nov 2026). Some say "TTX: Tabletop exercise completed".

performed_on: when it was last performed, only when Status is Successful: a DR test's date from its
comment, a tabletop exercise's date from When. Anything that contradicts this is listed.

Every file stands alone (DEVELOPER_GUIDE.md rule 1): this file uploads without the ITDR application file.
When both are loaded, mapping links each test to an application by name (match_applications).
The rows go into the dr_test table at upload. Nothing here is scored: RE-03 is still planned.
"""
import re

from .common import column_map, map_columns, parse_when, read_table
from .itdr import NOT_GIVEN, tidy, tier_of

FIELDS = {"Tier": ("Tier", "Recovery Tier", "ITDR Tier"),
          "Name": ("Name", "Application Name", "Application"),
          "Business Area": ("Business Area", "Business Product Area", "Product Area"),
          "ITDR Lead": ("ITDR Lead", "Lead", "DR Lead"),
          "Type of Test": ("Type of Test", "Test Type", "Type"),
          "When": ("When", "Test Date", "Date"),
          "Status": ("Status", "Result", "Outcome"),
          "Comments": ("Comments", "Comment", "Notes")}
HEADER_ROWS = 2                 # read like the ITDR file: a two-row header is joined, a one-row header still works
TYPES = {"open": "Open", "closed": "Closed", "ttx": "TTX", "tabletop": "TTX", "tabletop exercise": "TTX"}
# What each type is (owner, 3 Nov 2026): (kind, environment).
KIND = {"Open": ("DR test", "Production (live)"), "Closed": ("DR test", "Non-production (UAT, test)"),
        "TTX": ("Tabletop exercise", None)}
DR_TEST, TABLETOP = "DR test", "Tabletop exercise"
SUCCESSFUL, NOT_PERFORMED = "Successful", "Not performed"


def comment_date(text):
    """'DR Test completed on 14th March 2026' -> that date (New York). None if the comment gives no date."""
    m = re.search(r"\bon\s+(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]+),?\s+(\d{4})", str(text or ""), re.I)
    return parse_when(f"{m.group(1)} {m.group(2).title()} {m.group(3)}") if m else None


def read(raw_bytes):
    """Returns dict(rows=[...], set_aside, notes, summary). Each row: application_name, recovery_tier,
    tier_label, business_area, itdr_lead, test_type, kind, environment, test_date (When, YYYY-MM-DD or
    None), status, performed_on, comments, comment_date, ttx_in_comment."""
    notes, set_aside, rows = [], [], []
    cmap = column_map("dr_tests", FIELDS)
    headers, table = read_table(raw_bytes, HEADER_ROWS, cmap)
    col = map_columns(headers, cmap, notes)
    g = lambda r, f: (r.get(col[f], "") if col[f] else "")

    lists = {k: [] for k in ("no_comment_date", "no_when", "blank_but_completed", "type_vs_comment", "no_type")}
    odd_types, odd_status, odd_tiers, bad_date, no_area, seen = {}, {}, {}, {}, 0, {}
    for i, r in enumerate(table, start=2):
        name = tidy(g(r, "Name"))
        if not name:
            set_aside.append(dict(row=i, reason="no Name"))
            continue
        tier, label = tier_of(g(r, "Tier"))
        if label is None:
            odd_tiers.setdefault(tidy(g(r, "Tier")), []).append(name)
            label = NOT_GIVEN
        type_raw = tidy(g(r, "Type of Test"))
        test_type = TYPES.get(type_raw.lower().rstrip(".")) if type_raw else None
        if type_raw and test_type is None:
            odd_types.setdefault(type_raw, []).append(name)
            test_type = type_raw
        if not type_raw:
            lists["no_type"].append(name)
        kind, environment = KIND.get(test_type, (None, None))
        when_raw = tidy(g(r, "When"))
        when = parse_when(when_raw)
        if when_raw and when is None:
            bad_date.setdefault(when_raw, []).append(name)
        status_raw = tidy(g(r, "Status"))
        status = SUCCESSFUL if status_raw.lower() == "successful" else (NOT_PERFORMED if not status_raw else status_raw)
        if status_raw and status != SUCCESSFUL:
            odd_status.setdefault(status_raw, []).append(name)
        comments = tidy(g(r, "Comments"))
        cdate = comment_date(comments)
        ttx_note = bool(re.search(r"\bTTX\b|tabletop", comments, re.I))
        dr_note = bool(re.search(r"\bDR\s+test\b", comments, re.I))

        performed_on = None
        if status == SUCCESSFUL and kind == DR_TEST:
            performed_on = cdate
            if cdate is None:
                lists["no_comment_date"].append(name)
        elif status == SUCCESSFUL and kind == TABLETOP:
            performed_on = when
            if when is None:
                lists["no_when"].append(name)
        if status == NOT_PERFORMED and re.search(r"\bcompleted\b", comments, re.I):
            lists["blank_but_completed"].append(name)
        if (kind == DR_TEST and ttx_note) or (kind == TABLETOP and dr_note):
            lists["type_vs_comment"].append(f"{name} ({test_type}, comment: '{comments[:60]}')")

        area = tidy(g(r, "Business Area"))
        if not area:
            no_area += 1
        key = (name.lower(), test_type, when.date() if when else None)
        if key in seen:
            notes.append(f"{name}: the same test ({test_type or 'no type'}, {when_raw or 'no date'}) is on more than "
                         "one row; each is kept")
        seen[key] = i
        rows.append({"application_name": name, "recovery_tier": tier, "tier_label": label,
                     "business_area": area or None, "itdr_lead": tidy(g(r, "ITDR Lead")) or None,
                     "test_type": test_type, "kind": kind, "environment": environment,
                     "test_date": when.date().isoformat() if when else None, "status": status,
                     "performed_on": performed_on.date().isoformat() if performed_on else None,
                     "comments": comments or None, "comment_date": cdate.date().isoformat() if cdate else None,
                     "ttx_in_comment": ttx_note})

    show = lambda names: ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
    n = lambda k, one, many: f"{len(lists[k])} {one if len(lists[k]) == 1 else many}"
    for raw, names in odd_tiers.items():
        notes.append(f"Tier '{raw}' isn't Tier 0 to Tier 5 or TBC ({show(names)}); kept as 'Not given'")
    for raw, names in odd_types.items():
        notes.append(f"Type of Test '{raw}' isn't Open, Closed or TTX ({show(names)}); kept as written, "
                     "counted as neither a DR test nor a tabletop exercise")
    if lists["no_type"]:
        notes.append(f"{n('no_type', 'row has', 'rows have')} no Type of Test ({show(lists['no_type'])}); "
                     "counted as neither a DR test nor a tabletop exercise")
    for raw, names in odd_status.items():
        notes.append(f"Status '{raw}' isn't Successful or blank ({show(names)}); kept as written, not counted as performed")
    for raw, names in bad_date.items():
        notes.append(f"When '{raw}' isn't a date ({show(names)})")
    if lists["no_comment_date"]:
        notes.append(f"{n('no_comment_date', 'successful DR test has', 'successful DR tests have')} no completed "
                     f"date in the comment, so when it was performed isn't known ({show(lists['no_comment_date'])})")
    if lists["no_when"]:
        notes.append(f"{n('no_when', 'successful tabletop exercise has', 'successful tabletop exercises have')} no "
                     f"date in When ({show(lists['no_when'])})")
    if lists["blank_but_completed"]:
        notes.append(f"{n('blank_but_completed', 'row has', 'rows have')} a blank Status (not performed) but a "
                     f"comment saying completed ({show(lists['blank_but_completed'])})")
    if lists["type_vs_comment"]:
        notes.append(f"Type of Test and comment disagree for {n('type_vs_comment', 'row', 'rows')}: "
                     f"{'; '.join(lists['type_vs_comment'][:5])}{'…' if len(lists['type_vs_comment']) > 5 else ''}")
    blank_status = sum(1 for x in rows if x["status"] == NOT_PERFORMED)
    if blank_status:
        notes.append(f"{blank_status} {'row has' if blank_status == 1 else 'rows have'} no Status: not performed")

    by_type = {}
    for x in rows:
        by_type[x["test_type"] or "Not given"] = by_type.get(x["test_type"] or "Not given", 0) + 1
    ok = lambda k: sum(1 for x in rows if x["kind"] == k and x["status"] == SUCCESSFUL)
    summary = dict(rows=len(rows), dr_tests=sum(1 for x in rows if x["kind"] == DR_TEST),
                   dr_tests_performed=ok(DR_TEST),
                   tabletop_exercises=sum(1 for x in rows if x["kind"] == TABLETOP),
                   tabletop_exercises_performed=ok(TABLETOP), not_performed=blank_status, by_type=by_type,
                   applications=len({x["application_name"].lower() for x in rows}),
                   no_business_area=no_area, set_aside=len(set_aside))
    return dict(rows=rows, set_aside=set_aside, notes=notes, summary=summary)


def match_applications(tests, apps):
    """Link each test to an ITDR application by name (tidied, any case). Only when both files are loaded.

    Returns dict(matched=n, not_matched=[names], tier_differs=[...], notes=[...]). Names are matched
    exactly after tidying; a near spelling is not guessed, it is listed so the files can be lined up.
    """
    by_name = {}
    for a in apps:
        by_name.setdefault(a["application_name"].lower(), []).append(a)
    matched, missing, tier_differs = 0, [], []
    for t in tests:
        hits = by_name.get(t["application_name"].lower())
        if not hits:
            missing.append(t["application_name"])
            continue
        matched += 1
        t["itdr_ref"] = hits[0]["ref"] if len(hits) == 1 else None
        t["family_id"] = hits[0].get("family_id") if len(hits) == 1 else None     # the application's family
        if len(hits) == 1 and hits[0]["tier_label"] != t["tier_label"]:
            tier_differs.append(f"{t['application_name']} ({t['tier_label']} here, {hits[0]['tier_label']} in the "
                                "ITDR application file)")
    missing = list(dict.fromkeys(missing))
    notes = []
    if missing:
        notes.append(f"{len(missing)} {'application' if len(missing) == 1 else 'applications'} in the DR tests file "
                     f"{'isn' if len(missing) == 1 else 'aren'}'t in the ITDR application file by name: "
                     f"{', '.join(missing[:8])}{'…' if len(missing) > 8 else ''}")
    if tier_differs:
        # Owner, 4 Nov 2026: the ITDR application file's tier is used; the difference is a warning to follow up
        # with ITDR (acknowledged before the lock, like every mapping note).
        notes.append(f"Tier differs from the ITDR application file for {len(tier_differs)} "
                     f"{'test' if len(tier_differs) == 1 else 'tests'}: TRUST uses the ITDR application file's tier. "
                     f"Ask ITDR to line the two files up: {'; '.join(tier_differs[:5])}"
                     f"{f' and {len(tier_differs) - 5} more' if len(tier_differs) > 5 else ''}")
    return dict(matched=matched, not_matched=missing, tier_differs=tier_differs, notes=notes)
