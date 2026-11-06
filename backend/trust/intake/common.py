"""Shared helpers for reading provider files as they come.

Rules (DEVELOPER_GUIDE.md, doc 17 section 3): the provider's real file is the layout. Names are matched
case-insensitively and fuzzily, JSON may have trailing commas, and nothing here ever looks at
another feed's file.
"""
import difflib
import json
import re

# How close a name must be to count as a fuzzy match (setting header_fuzzy_min in the design).
FUZZY_MIN = 0.85


def norm(name):
    """Lower-case and drop spaces, underscores, hyphens and punctuation: 'Approval recorded at (UTC)' -> 'approvalrecordedatutc'."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def similarity(a, b):
    """How alike two names are, 0 to 1, ignoring case, spaces and punctuation; word order ignored too."""
    straight = difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()
    # Same words in another order: compare the sorted words.
    words = lambda s: "".join(sorted(re.findall(r"[a-z0-9]+", str(s).lower())))
    reordered = difflib.SequenceMatcher(None, words(a), words(b)).ratio()
    return max(straight, reordered)


def match_name(wanted, available, aliases=()):
    """Find which of the file's names gives the field `wanted`.

    Order: exact after normalising, then each alias in the order given, then fuzzy (similarity
    >= FUZZY_MIN, word order ignored). An alias starting with * means "the name ends with this"
    (owner, 3 Nov 2026: the HR column ending in SAM_Acct), e.g. '*SAM_Acct' finds 'Worker_SAM_Acct';
    if more than one name ends that way it is a tie. Returns (name or None, how) where how is
    'exact', 'alias', 'fuzzy', 'tie' or 'missing'. On a tie neither name is used, so nothing is guessed.
    """
    by_norm = {norm(a): a for a in available}
    for cand in (wanted, *aliases):
        if str(cand).startswith("*"):
            end = norm(cand[1:])
            ends = [a for a in available if end and norm(a).endswith(end)]
            if len(ends) == 1:
                return ends[0], "alias"
            if len(ends) > 1:
                return None, "tie"
            continue
        hit = by_norm.get(norm(cand))
        if hit is not None:
            return hit, ("exact" if cand == wanted else "alias")

    score = similarity
    plain = [c for c in (wanted, *aliases) if not str(c).startswith("*")]
    scored = sorted(((max(score(c, a) for c in plain), a) for a in available), reverse=True)
    if not scored or scored[0][0] < FUZZY_MIN:
        return None, "missing"
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None, "tie"
    return scored[0][1], "fuzzy"


def get_field(obj, wanted, aliases=(), notes=None):
    """Read one field from a dict using match_name. Fuzzy matches and ties are noted for the upload result."""
    if not isinstance(obj, dict):
        return None
    name, how = match_name(wanted, list(obj.keys()), aliases)
    if notes is not None and how in ("fuzzy", "tie"):
        msg = f"used '{name}' for {wanted}" if how == "fuzzy" else f"two names equally close to {wanted}; neither used"
        if msg not in notes:
            notes.append(msg)
    return obj.get(name) if name is not None else None


def loads_tolerant(text):
    """Parse JSON that may have trailing commas, a byte-order mark or blank lines.

    Trailing commas are removed only outside strings, so a comma inside a comment sentence is kept.
    """
    text = text.lstrip("﻿")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    out, in_str, esc = [], False, False
    for i, ch in enumerate(text):
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
        elif ch == ",":
            # Drop the comma if the next non-space character closes an object or list.
            rest = text[i + 1:].lstrip()
            if rest[:1] in ("]", "}") or rest == "":
                continue
            out.append(ch)
        else:
            out.append(ch)
    return json.loads("".join(out))


def _cell_text(v):
    """An Excel cell as text: 12.0 -> '12', a date -> its ISO form, blank -> ''."""
    import datetime
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return str(v)


def is_excel(raw_bytes):
    """True for an .xlsx workbook (a zip file), whatever the file is called."""
    return raw_bytes[:4] == b"PK\x03\x04"


def _excel_lines(raw_bytes):
    """The first worksheet of an .xlsx file as lists of text. Merged cells give their value to the top-left cell."""
    import io
    try:
        import openpyxl
    except ImportError as err:              # listed in requirements.txt; say so plainly if it is missing
        raise ValueError("This is an Excel file and the Excel reader (openpyxl) isn't installed.") from err
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    except Exception as err:                # a damaged or password-protected workbook
        raise ValueError(f"This Excel file can't be opened ({type(err).__name__}).") from err
    try:
        ws = wb.worksheets[0]
        return [[_cell_text(v).strip() for v in row] for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _looks_like_header(cells):
    """A second header row holds words, never a number (a data row's Ref is a number)."""
    filled = [c for c in cells if c.strip()]
    return not any(re.fullmatch(r"-?\d+(\.\d+)?", c.strip()) for c in filled)


def read_table(raw_bytes, header_rows=1, fields=None):
    """Read a delimited text file, or the first sheet of an Excel (.xlsx) file, as it comes.

    Text: detect the delimiter, ignore a byte-order mark. header_rows=2 is for files whose header is
    two rows (merged cells over rows 1 and 2): each column's name is the words from both rows, joined.
    The second row is only taken as header when that finds more of the expected columns (fields, the
    reader's column map) than the first row alone; without fields, when it has no numbers in it. So a
    file sent with a single header row still reads correctly.

    Returns (headers, rows) where rows are dicts keyed by the file's own headers.
    Raises ValueError only if the file cannot be read at all.
    """
    import csv
    import io

    if is_excel(raw_bytes):
        lines = [[c.strip() for c in r] for r in _excel_lines(raw_bytes)]
        lines = [r for r in lines if any(r)]
    else:
        if raw_bytes[:2] in (b"\xff\xfe", b"\xfe\xff"):          # Excel "Unicode Text" is UTF-16
            text = raw_bytes.decode("utf-16", errors="replace")
        else:
            try:
                text = raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw_bytes.decode("cp1252", errors="replace")  # Excel exports on Windows
        text = text.replace("\x00", "")        # a stray NUL can't be stored as JSON in the database
        if not text.strip():
            raise ValueError("This file is empty.")
        sample = text[:20000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            delim = dialect.delimiter
        except csv.Error:
            # Fall back to whichever candidate appears most in the header line.
            first = sample.splitlines()[0]
            delim = max(",;\t|", key=first.count)
        csv.field_size_limit(50_000_000)        # a long Jira description is still one cell
        try:
            reader = csv.reader(io.StringIO(text), delimiter=delim)
            lines = [r for r in reader if any(c.strip() for c in r)]
        except csv.Error as err:
            raise ValueError(f"This file can't be read as a table ({err}). Save it again as CSV (UTF-8) and upload it.")
    if not lines:
        raise ValueError("This file has no rows.")
    head = [h.strip() for h in lines[0]]
    used = 1
    if header_rows >= 2 and len(lines) > 1:
        second = list(lines[1]) + [""] * (len(head) - len(lines[1]))
        both = head + [""] * (len(second) - len(head))
        both = [" ".join(dict.fromkeys(x for x in (a.strip(), b.strip()) if x)) for a, b in zip(both, second)]
        if fields:
            found = lambda h: sum(1 for v in map_columns(h, fields, []).values() if v)
            two = found(both) > found(head)
        else:
            two = _looks_like_header(lines[1])
        if two:
            head, used = both, 2
    headers = head
    rows = []
    for cells in lines[used:]:
        cells = list(cells) + [""] * (len(headers) - len(cells))
        rows.append({h: cells[i].strip() for i, h in enumerate(headers) if h})
    return headers, rows


def column_map(feed, defaults):
    """The column names for one feed, from config/column_maps.json (owner-editable).

    The file says, for each field TRUST needs, which column name(s) the provider's file uses.
    Feed names and field names in the file are matched ignoring case, spaces and punctuation,
    like everything else; keys starting with "_" are notes and ignored; trailing commas are fine.
    Falls back to the built-in defaults for anything not in the file. Set TRUST_COLUMN_MAPS to
    use a different file. Returns {field: (names...)} for map_columns.
    """
    import os
    import pathlib

    path = pathlib.Path(os.environ.get("TRUST_COLUMN_MAPS")
                        or pathlib.Path(__file__).resolve().parents[3] / "config" / "column_maps.json")
    fields = {f: tuple(a) for f, a in defaults.items()}
    try:
        doc = loads_tolerant(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        doc = {}
    except json.JSONDecodeError as e:
        raise ValueError(f"config/column_maps.json could not be read ({e}). Fix the file and upload again.") from None
    configured = next((v for k, v in doc.items() if not k.startswith("_") and norm(k) == norm(feed)), None) or {}
    by_norm = {norm(f): f for f in fields}
    for field, names in configured.items():
        if field.startswith("_"):
            continue
        names = [names] if isinstance(names, str) else [str(n) for n in (names or [])]
        f = by_norm.get(norm(field))
        if f is not None:
            # The owner's names come first; the built-in ones stay as a fall-back.
            fields[f] = tuple(dict.fromkeys([*names, *fields[f]]))
    return fields


def map_columns(headers, fields, notes):
    """Find the file's header for each field TRUST needs.

    fields: {field: (aliases...)}. Returns {field: header or None}. Fuzzy matches, ties and
    missing fields are added to notes in plain words.
    """
    out = {}
    for field, aliases in fields.items():
        name, how = match_name(field, headers, aliases)
        out[field] = name
        if how == "fuzzy":
            notes.append(f"used column '{name}' for '{field}'")
        elif how == "tie":
            notes.append(f"two columns are equally close to '{field}'; neither used")
        elif how == "missing":
            notes.append(f"no column found for '{field}'. If the file calls it something else, add that name "
                         f"under this feed in config/column_maps.json and upload again")
    return out


def parse_when(value, tz="America/New_York"):
    """Read a date or date-time in whatever common format the file uses. Returns an aware datetime or None.

    Handles MM/DD/YYYY HH:MM:SS AM/PM, M/D/YYYY, YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS(.fraction, any
    number of digits)(Z or +hh:mm), D Mon YYYY and similar. A value with no timezone is read as
    New York time (TCC assumption L-TCC-04) until the owner confirms each field's timezone.
    """
    import datetime as dt
    from zoneinfo import ZoneInfo

    s = str(value or "").strip()
    if not s:
        return None
    s = re.sub(r"Z$", "+00:00", s)
    # Fractions of a second in any length (".1", ".123", ".1234567", or a bare "."), in any format:
    # take them off before reading the rest, then put them back as microseconds.
    frac = 0
    m = re.search(r"(\d{2}:\d{2}:\d{2})\.(\d*)", s)
    if m:
        frac = int((m.group(2) + "000000")[:6])
        s = s[:m.start()] + m.group(1) + s[m.end():]
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        d = None
        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
                    "%m/%d/%Y", "%m/%d/%y", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y",
                    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%d-%b-%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                d = dt.datetime.strptime(s.replace(",", ""), fmt)
                break
            except ValueError:
                continue
        if d is None:
            return None
    d = d.replace(microsecond=frac) if frac else d
    if not 1990 <= d.year <= 2100:      # placeholder values (year 0001 or 9999) are not dates; later steps would overflow
        return None
    return d if d.tzinfo else d.replace(tzinfo=ZoneInfo(tz))


def upload_time(uploaded_at=None, tz="America/New_York"):
    """The as-of time for a file that is dated by its upload: the given upload time (a datetime or
    any date text parse_when reads), or now in New York. Shared so every feed does it the same way."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    if isinstance(uploaded_at, dt.datetime):
        return uploaded_at if uploaded_at.tzinfo else uploaded_at.replace(tzinfo=ZoneInfo(tz))
    return parse_when(uploaded_at, tz) or dt.datetime.now(ZoneInfo(tz))


def add_days(when, days):
    """A date-time plus a number of days (for rules like 'blank ETA -> due 30 days after Created')."""
    import datetime as dt

    return when + dt.timedelta(days=days) if when is not None else None


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def emails_in(text):
    """Every email address in a cell, in order, lower-cased: 'A <a@x.com>; b@x.com' -> ['a@x.com', 'b@x.com']."""
    return [e.lower() for e in EMAIL_RE.findall(str(text or ""))]


def leading_code(value):
    """'40 FAIL backed out' or '40' or '040' -> '40'; '00 PASS' -> '00'; no number -> None."""
    m = re.match(r"\s*(\d+)", str(value or ""))
    return m.group(1).zfill(2)[-2:] if m else None


def as_bool(v):
    """true/false in any form: True, 'true', 'TRUE', 1, 'yes'. Unknown -> None."""
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "t", "yes", "y", "1"):
        return True
    if s in ("false", "f", "no", "n", "0"):
        return False
    return None


def keep_columns(raw_bytes, feed, fields, header_rows=1):
    """Cut a delimited or Excel file down to the columns TRUST uses, before it is kept (owner, 2 Nov 2026).
    What is kept is always a CSV with one header row, so an Excel file is stored as CSV.

    fields: the reader's FIELDS. Columns are found the same way mapping finds them (column map,
    case-insensitive, fuzzy). Every row is kept; only unused columns are dropped. Returns
    (csv_bytes or None, info): None when no column TRUST uses was found, so nothing is kept.
    info lists the columns kept, the columns dropped and the fields not found.
    """
    import csv
    import io

    cmap = column_map(feed, fields)
    headers, rows = read_table(raw_bytes, header_rows, cmap)
    col = map_columns(headers, cmap, [])
    keep = list(dict.fromkeys(h for h in col.values() if h))
    info = {"columns_kept": keep, "columns_dropped": [h for h in headers if h and h not in keep],
            "fields_not_found": [f for f, h in col.items() if not h], "rows": len(rows)}
    if not keep:
        return None, info
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(keep)
    for r in rows:
        w.writerow([r.get(h, "") for h in keep])
    return buf.getvalue().encode("utf-8"), info
