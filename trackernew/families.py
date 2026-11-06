"""Read the product family owners file on its own (feed "hr_mapping"; owner, 2 Nov 2026).

One line per family, as a CSV:
    Product Family | Owner Email(s) | Band
or as JSON (product_line_owners.json; owner, 3 Nov 2026):
    [{"product_line": "Payments", "owner_email": "a.lead@company.com"}, ...]
    A product line with more than one lead: repeat it with each lead, or give owner_email as a list or a
    comma-separated string. "band" is optional (product when missing). The JSON is turned into the CSV's
    three columns at upload (to_csv), so everything after that is the same for both.
    Owner Email(s): several owners comma-separated in the one cell.
    Band: "product" or "platform" (any case), as on the prototype's screens. Blank or anything
          else -> product, with a note.

Upload never needs HR. At mapping, each owner is found in HR and everyone who reports up to
them belongs to that family (backend/trust/linking.py, families_from_owners).
"""
import re

import csv
import io

from .common import column_map, emails_in, get_field, loads_tolerant, map_columns, read_table

FIELDS = {"Product Family": ("Product Family", "family", "product family name", "product_line", "product line"),
          "Owner Email(s)": ("Owner Email(s)", "owner emails", "owner email", "owners", "owner_email", "lead_email", "leads"),
          "Band": ("Band", "type", "family type", "product or platform")}
BANDS = ("product", "platform")


def family_id(name):
    """A stable id from the family name: 'Order Routing & Risk' -> 'order-routing-risk'."""
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def is_json(raw_bytes):
    head = (raw_bytes or b"").lstrip()[:1]
    return head in (b"[", b"{")


def to_csv(raw_bytes):
    """The JSON owners file as the CSV's three columns (Product Family, Owner Email(s), Band).
    Accepts a list of entries, or an object holding one. Raises ValueError when it isn't JSON."""
    try:
        doc = loads_tolerant(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as err:
        raise ValueError(f"not readable as JSON: {err}")
    if isinstance(doc, dict):                       # {"product_lines": [...]} or similar: use the first list
        doc = next((v for v in doc.values() if isinstance(v, list)), [doc])
    if not isinstance(doc, list):
        raise ValueError("the JSON isn't a list of product lines")
    cmap = column_map("hr_mapping", FIELDS)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(list(FIELDS))
    for item in doc:
        if not isinstance(item, dict):
            w.writerow(["", "", ""])                # kept as a row so the reader sets it aside with a reason
            continue
        val = lambda f: get_field(item, f, cmap[f])
        emails = val("Owner Email(s)")
        emails = ", ".join(str(e) for e in emails) if isinstance(emails, list) else ("" if emails is None else str(emails))
        w.writerow([str(val("Product Family") or "").strip(), emails, str(val("Band") or "").strip()])
    return out.getvalue().encode("utf-8")


def read(raw_bytes):
    """Returns dict(rows=[{family_id, family, owner_emails}], set_aside, notes, summary). CSV or JSON."""
    notes, set_aside, rows, seen = [], [], [], {}
    if is_json(raw_bytes):
        raw_bytes = to_csv(raw_bytes)
    headers, table = read_table(raw_bytes)
    col = map_columns(headers, column_map("hr_mapping", FIELDS), notes)
    g = lambda r, f: (r.get(col[f], "") if col[f] else "").strip()

    owner_of = {}
    for i, r in enumerate(table, start=2):
        name = g(r, "Product Family")
        if not name:
            set_aside.append(dict(row=i, reason="no Product Family"))
            continue
        fid = family_id(name)
        emails = emails_in(g(r, "Owner Email(s)"))
        band_raw = g(r, "Band")
        band = next((b for b in BANDS if b == band_raw.strip().lower()), None)
        if band is None:
            band = "product"
            if band_raw:                      # blank is fine (band is optional); a wrong word is worth a note
                notes.append(f"'{name}': band {band_raw!r} is not product or platform; product is used")
        if fid in seen:
            # The same family on two lines: join their owners rather than drop one.
            rows[seen[fid]]["owner_emails"] = list(dict.fromkeys(rows[seen[fid]]["owner_emails"] + emails))
            # several lines = several leads (owner, 3 Nov 2026): expected, so no note
            continue
        if not emails:
            notes.append(f"'{name}' has no owner email; nobody can be placed in it yet")
        seen[fid] = len(rows)
        rows.append({"family_id": fid, "family": name, "band": band, "owner_emails": emails})
        for e in emails:
            owner_of.setdefault(e, []).append(name)

    # A lead of several families is fine (owner, 6 Nov 2026): their people count for each (see linking).
    # band is optional (owner, 3 Nov 2026): a missing band means product, without a note to acknowledge every month
    summary = dict(families=len(rows), owners=sum(len(x["owner_emails"]) for x in rows), set_aside=len(set_aside))
    return dict(rows=rows, set_aside=set_aside, notes=notes, summary=summary)
