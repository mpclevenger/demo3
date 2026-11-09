"""Read the AD owner groups file on its own (feed "app_owner_members"; owner, 6 Nov 2026).

The file comes from tools/expand_owner_groups.ps1, run on a Windows desktop with the AD module. For each
app_owner_email in the app inventory it says what that email is in Active Directory and, for a group,
every member (nested groups included):

    owner_email | owner_kind | group_sam | member_sam | member_email | member_name | member_enabled | included | reason

    owner_kind: group, person, not found, ambiguous, or another AD object type.
    included: Yes for an enabled person; No (with the reason) for disabled accounts, service accounts,
        empty groups and emails not found. Only included members are used.

TRUST keeps only owner_email, owner_kind, group_sam, member_sam, member_email and included (the rest is
dropped at upload). Big distribution lists, nested groups included, can make this file hundreds of thousands
of rows, so it is read one line at a time into a compact list per owner email (found 6 Nov 2026: reading it
as a table ran the web process out of memory), and its rows are not saved with the mapped month.

At mapping (backend/trust/intake/app_links.py) an owner email found in HR is a person; otherwise its
included members here are matched to HR (SAM_ACCOUNT, then email). Anything left is Not yet mapped.
"""
import csv
import io
import sys

from .common import as_bool, column_map, map_columns

FIELDS = {"owner_email": ("owner_email", "owner email", "group email"),
          "owner_kind": ("owner_kind", "owner kind", "kind"),
          "group_sam": ("group_sam", "group"),
          "member_sam": ("member_sam", "samaccountname", "member sam"),
          "member_email": ("member_email", "member mail", "mail"),
          "included": ("included",)}


def _lines(raw_bytes):
    """The file's rows one at a time, without holding the whole file as text or as a table."""
    enc = "utf-16" if raw_bytes[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    head = raw_bytes[:4096].decode(enc, errors="replace")
    first = head.splitlines()[0] if head.strip() else ""
    delim = max(",;\t|", key=first.count) if first else ","
    try:
        raw_bytes[:200000].decode(enc)
    except UnicodeDecodeError:
        enc = "cp1252"                                       # an Excel export on Windows
    text = io.TextIOWrapper(io.BytesIO(raw_bytes), encoding=enc, errors="replace", newline="")
    return csv.reader(text, delimiter=delim)


def read(raw_bytes):
    """Returns dict(members={owner_email: [(member_sam, member_email, group_sam)]}, kinds={owner_email: kind},
    set_aside, notes, summary). Only included members are kept; left-out ones are counted."""
    notes, set_aside, members, kinds = [], [], {}, {}
    if not raw_bytes or not raw_bytes.strip():
        raise ValueError("This file is empty.")
    lines = _lines(raw_bytes)
    headers = next(lines, [])
    while headers and not any(h.strip() for h in headers):
        headers = next(lines, [])
    headers = [h.strip() for h in headers]
    cmap = column_map("app_owner_members", FIELDS)
    col = map_columns(headers, cmap, notes)
    pos = {f: headers.index(col[f]) if col[f] in headers else None for f in FIELDS}
    intern, left_out, n_rows = sys.intern, 0, 0

    def g(r, f):
        i = pos[f]
        return r[i].strip() if i is not None and i < len(r) else ""

    for i, r in enumerate(lines, start=2):
        if not any(c.strip() for c in r):
            continue
        n_rows += 1
        email = g(r, "owner_email").lower()
        if not email:
            if len(set_aside) < 200:
                set_aside.append(dict(row=i, reason="no owner_email"))
            continue
        email = intern(email)
        kinds.setdefault(email, intern(g(r, "owner_kind").lower() or "unknown"))
        sam = g(r, "member_sam").lower()
        inc = g(r, "included")
        if not sam:
            continue
        if not (as_bool(inc) if inc else True):
            left_out += 1
            continue
        members.setdefault(email, []).append(
            (intern(sam), intern(g(r, "member_email").lower()) or None, intern(g(r, "group_sam")) or None))
    counts = {}
    for k in kinds.values():
        counts[k] = counts.get(k, 0) + 1
    if counts.get("not found"):
        notes.append(f"{counts['not found']} owner {'email was' if counts['not found'] == 1 else 'emails were'} not found "
                     "in AD; apps owned only by them stay Not yet mapped unless the email is a person in HR")
    if left_out:
        notes.append(f"For information: {left_out} {'member was' if left_out == 1 else 'members were'} left out by the "
                     "script (disabled or service accounts)")
    summary = dict(rows=n_rows, owner_emails=len(kinds), by_kind=counts,
                   members=sum(len(v) for v in members.values()), left_out=left_out, set_aside=len(set_aside))
    return dict(members=members, kinds=kinds, rows=[], set_aside=set_aside, notes=notes, summary=summary)


def from_rows(rows):
    """The same compact form from a list of row dicts (tests and older callers)."""
    members, kinds = {}, {}
    for x in rows:
        e = x["owner_email"]
        kinds.setdefault(e, x.get("owner_kind") or "unknown")
        if x.get("member_sam") and x.get("included", True):
            members.setdefault(e, []).append((x["member_sam"], x.get("member_email"), x.get("group_sam")))
    return dict(members=members, kinds=kinds)


def keep(raw_bytes):
    """Cut the file down at upload, one line at a time (big files): only the six columns TRUST reads, only the
    members it will use (included), and one row for each owner email with none, so 'not found' stays known.
    Returns (csv_bytes or None, info) like common.keep_columns."""
    lines = _lines(raw_bytes)
    headers = [h.strip() for h in next(lines, [])]
    notes = []
    col = map_columns(headers, column_map("app_owner_members", FIELDS), notes)
    pos = {f: headers.index(col[f]) if col[f] in headers else None for f in FIELDS}
    info = {"columns_kept": [col[f] for f in FIELDS if col[f]],
            "columns_dropped": [h for h in headers if h and h not in {col[f] for f in FIELDS}],
            "fields_not_found": [f for f in FIELDS if not col[f]]}
    if not info["columns_kept"]:
        return None, info
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([col[f] or f for f in FIELDS])
    seen, left_out = set(), 0
    for r in lines:
        if not any(c.strip() for c in r):
            continue
        cells = [r[pos[f]].strip() if pos[f] is not None and pos[f] < len(r) else "" for f in FIELDS]
        email, inc, sam = cells[0].lower(), cells[5], cells[3]
        use = bool(sam) and (as_bool(inc) if inc else True)
        if not use:
            left_out += bool(sam)
            if email in seen:
                continue
        seen.add(email)
        if not use:
            cells[3] = cells[4] = ""                  # kept only to record what the email is in AD
            cells[5] = "No"
        w.writerow(cells)
    info["members_left_out"] = left_out
    return buf.getvalue().encode("utf-8"), info
