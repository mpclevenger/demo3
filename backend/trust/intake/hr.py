"""Read the firm-wide HR file and keep only the CTO's reporting line (doc 13).

Upload of this feed never needs any other file. Manager links are resolved across the whole
file first, so chains through any part of the firm work; then only the person named by the
setting hr_root_sam_account and everyone below them is kept. Nobody else is returned or stored.
"""
import re
from collections import defaultdict

from .common import as_bool, column_map, map_columns, read_table

# Fields TRUST loads (doc 13 section 1), with alternative names seen or expected.
# These are only defaults: the owner sets the real column names in config/column_maps.json ("hr").
FIELDS = {
    "SAM_ACCOUNT": ("sam account", "samaccountname", "employee id"),
    "Worker": ("worker name", "name"),
    "Email - Work": ("work email", "email"),
    "Workers Manager": ("worker's manager", "manager"),
    "Supervisory Organization": ("sup org",),
    "Department": ("dept",),
    # Owner, 3 Nov 2026: kept for now, CTO's line only, for the EU regulatory impact assessment; to be replaced
    # by a per-team summary from HR (doc 13 §10). Not shown anywhere yet.
    "Location Address - Country": ("country", "location country"),
    "Top Level Supervisory": ("top level sup org",),
    "Executive Level Supervisory": ("exec level supervisory",),
    "Worker Type": (),
    "Position Worker Type": (),
    "Is Manager": (),
    "Number of Direct Reports": ("direct reports",),
    "VP or Higher": (),
    "Management reporting level from top": ("reporting level",),
}

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _name(s):
    """Names are matched after trimming spaces and ignoring case (doc 13 section 4)."""
    return " ".join(str(s or "").split()).casefold()


def _int(s):
    s = re.sub(r"[,\s]", "", str(s or ""))
    return int(s) if s.lstrip("-").isdigit() else None


def _paren(s):
    """'SupOrg Name (Manager Name)' -> 'manager name'."""
    m = re.search(r"\(([^()]*)\)\s*$", str(s or ""))
    return _name(m.group(1)) if m else None


def read(raw_bytes, root_sam):
    """Read an HR file. root_sam is the setting hr_root_sam_account (the CTO's SAM_ACCOUNT).

    Returns dict(people=[...], set_aside=[...], notes=[...], summary=...). Raises ValueError only
    when the file cannot be read as text at all.
    """
    notes, set_aside = [], []
    headers, rows = read_table(raw_bytes)
    col = map_columns(headers, column_map("hr", FIELDS), notes)
    g = lambda r, f: r.get(col[f], "") if col[f] else ""

    # 1. One row per person, keyed by SAM_ACCOUNT (case-insensitive).
    by_sam, dup = {}, set()
    for i, r in enumerate(rows, start=2):
        sam = g(r, "SAM_ACCOUNT").strip().lower()
        if not sam:
            set_aside.append(dict(row=i, reason="no SAM_ACCOUNT"))
            continue
        if sam in by_sam:
            dup.add(sam)
        by_sam.setdefault(sam, []).append((i, r))
    for sam in dup:  # a person must be one row; both copies are set aside
        for i, _ in by_sam.pop(sam):
            set_aside.append(dict(row=i, sam=sam, reason="SAM_ACCOUNT appears more than once"))
    people = {sam: rs[0][1] for sam, rs in by_sam.items()}

    summary = dict(rows_in_file=len(rows), kept=0, left_out=len(rows), set_aside=len(set_aside))
    root = (root_sam or "").strip().lower()
    if not root:
        notes.append("Set the CTO's SAM_ACCOUNT (hr_root_sam_account) and score again; no people loaded.")
        return dict(people=[], set_aside=set_aside, notes=notes, summary=summary)
    if root not in people:
        notes.append(f"SAM_ACCOUNT '{root_sam}' is not in this file; no people loaded.")
        return dict(people=[], set_aside=set_aside, notes=notes, summary=summary)

    # 2. Resolve every manager name to a person, across the whole file.
    by_name = defaultdict(list)
    for sam, r in people.items():
        by_name[_name(g(r, "Worker"))].append(sam)
    manager_of, unresolved = {}, []
    for sam, r in people.items():
        if sam == root:
            continue  # the CTO is the top; who they report to is not needed
        mname = _name(g(r, "Workers Manager"))
        cands = [c for c in by_name.get(mname, []) if c != sam] if mname else []
        if len(cands) > 1:  # same name: narrow by level, then org (doc 13 section 4 step 2)
            lvl = _int(g(r, "Management reporting level from top"))
            for f in ("Top Level Supervisory", "Executive Level Supervisory"):
                narrowed = [c for c in cands
                            if (lvl is None or _int(g(people[c], "Management reporting level from top")) == lvl - 1)
                            and _name(g(people[c], f)) == _name(g(r, f))]
                if narrowed:
                    cands = narrowed
                if len(cands) == 1:
                    break
        if len(cands) == 1:
            manager_of[sam] = cands[0]
        else:
            unresolved.append(sam)

    # 3. Walk down from the CTO. A person reached twice (a loop) is kept once.
    reports = defaultdict(list)
    for sam, mgr in manager_of.items():
        reports[mgr].append(sam)
    kept, stack = [], [root]
    seen = {root}
    while stack:
        cur = stack.pop()
        kept.append(cur)
        for child in reports.get(cur, []):
            if child in seen:
                notes.append(f"manager chain loops at {child}; broken there")
                continue
            seen.add(child)
            stack.append(child)

    # 4. Build the kept people (loaded columns only) and the cross-check notes.
    out, emails = [], defaultdict(list)
    mismatch_paren, mismatch_count = [], []
    for sam in kept:
        r = people[sam]
        mgr = manager_of.get(sam)
        email = g(r, "Email - Work").strip().lower()
        if not EMAIL.match(email):
            notes.append(f"{sam}: work email blank or not an email; their items will show as Not yet mapped")
            email = ""
        if email:
            emails[email].append(sam)
        # The "(Manager Name)" in a Supervisory Organization is usually the person's manager, or the
        # person themselves when they lead that team; either is fine.
        if mgr and _paren(g(r, "Supervisory Organization")) not in (None, _name(g(people[mgr], "Worker")), _name(g(r, "Worker"))):
            mismatch_paren.append(sam)
        declared = _int(g(r, "Number of Direct Reports"))
        if declared is not None and declared != len(reports.get(sam, [])):
            mismatch_count.append(f"{sam} ({declared} in file, {len(reports.get(sam, []))} found)")
        out.append({
            "sam_account": sam,
            "worker": g(r, "Worker"),
            "email": email or None,
            "manager_sam": mgr,
            "sup_org": g(r, "Supervisory Organization"),
            "department": g(r, "Department"),
            "country": g(r, "Location Address - Country"),
            "top_level_sup_org": g(r, "Top Level Supervisory"),
            "exec_level_sup_org": g(r, "Executive Level Supervisory"),
            "worker_type": g(r, "Worker Type"),
            "position_worker_type": g(r, "Position Worker Type"),
            "is_manager": as_bool(g(r, "Is Manager")) or False,
            "direct_reports": _int(g(r, "Number of Direct Reports")),
            "vp_or_higher": as_bool(g(r, "VP or Higher")) or False,
            "reporting_level": _int(g(r, "Management reporting level from top")),
        })
    for email, sams in emails.items():
        if len(sams) > 1:
            notes.append(f"work email {email} is shared by {', '.join(sams)}; the first is used")
    if mismatch_paren:
        n = len(mismatch_paren)
        notes.append(f"{n} {'person' if n == 1 else 'people'}: manager differs from the name in their Supervisory Organization ({', '.join(mismatch_paren[:20])})")
    if mismatch_count:
        notes.append("direct-report count differs: " + "; ".join(mismatch_count))

    # People who look like they belong under the CTO but weren't reached (likely a broken manager link).
    root_exec = _name(g(people[root], "Executive Level Supervisory"))
    missed = [s for s in people if s not in seen and root_exec and _name(g(people[s], "Executive Level Supervisory")) == root_exec]
    if missed:
        notes.append(f"{len(missed)} {'person shares' if len(missed) == 1 else 'people share'} the CTO's Executive Level Supervisory but {'was' if len(missed) == 1 else 'were'} not reached: "
                     + ", ".join(sorted(missed)[:20]) + (" …" if len(missed) > 20 else ""))
    unresolved_in_scope = [s for s in unresolved if s in missed]
    if unresolved_in_scope:
        notes.append("manager name could not be matched for: " + ", ".join(sorted(unresolved_in_scope)[:20]))

    summary.update(kept=len(out), left_out=len(rows) - len(out) - len(set_aside))
    return dict(people=out, set_aside=set_aside, notes=notes, summary=summary)


def minimise(raw_bytes, root_sam):
    """Cut the firm-wide HR file down to what TRUST may keep (owner, 2 Nov 2026; doc 13 section 3):
    only the CTO and everyone reporting up to them, and only the columns TRUST loads.

    Returns (kept_csv_bytes or None, result). None means nothing may be kept: the CTO setting is
    empty, or that SAM_ACCOUNT is not in the file. The result is what read() found, so the upload
    can show the same notes and counts.
    """
    import csv
    import io

    result = read(raw_bytes, root_sam)
    if not result["people"]:
        return None, result
    headers, rows = read_table(raw_bytes)
    col = map_columns(headers, column_map("hr", FIELDS), [])
    keep_cols = [col[f] for f in FIELDS if col.get(f)]
    kept = {p["sam_account"].lower() for p in result["people"]}
    sam_col = col["SAM_ACCOUNT"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(keep_cols)
    for r in rows:
        if (r.get(sam_col) or "").strip().lower() in kept:
            w.writerow([r.get(c, "") for c in keep_cols])
    return buf.getvalue().encode("utf-8"), result
