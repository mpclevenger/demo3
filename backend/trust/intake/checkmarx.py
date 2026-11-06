"""Read one Checkmarx SAST or SCA file on its own (doc 16).

Upload of this feed never needs any other file. The result is one row per repo with
pass/fail and whatever counts the comment gives, plus plain notes for anything set aside.
Placing repos with families happens later, at scoring.
"""
import re

from .common import as_bool, column_map, get_field, loads_tolerant, parse_when, upload_time

# Built-in JSON field names; the owner's names in config/column_maps.yaml (cx_sast / cx_sca) come first.
FIELDS = {"importer": ("importer",), "data": ("data", "results", "repos"), "key": ("key", "repo", "repository"),
          "measurements": ("measurements", "measurement", "results"), "name": ("name",),
          "value": ("value", "compliant", "passed"), "comment": ("comment", "message", "detail"),
          # Not in today's files; requested from Cyber (doc 16 section 5). Read the same way as every other date.
          "report_as_of": ("report_as_of", "as_of", "report_date")}

# The three known comment sentences, matched loosely: any case, extra spaces, "exeed" or "exceed",
# backticks optional, numbers optional (the samples carry '#' placeholders).
NUM = r"(\d+|#)"
P_NONE = re.compile(r"^\s*compliant\W+no\s+(sast|sca)\s+findings?\s+detected", re.I)
P_ALL = re.compile(r"^\s*compliant\W+all\s+" + NUM + r"\s+(sast|sca)\s+findings?\s+are\s+within", re.I)
P_FAIL = re.compile(r"^\s*non\W*compliant\W+`?\s*" + NUM + r"\s*/\s*" + NUM + r"\s*`?\s+(sast|sca)\s+findings?\s+ex+c?e+e?d", re.I)
P_VIOL = re.compile(r"violations?\s*:\s*(.*)$", re.I)
P_ONE = re.compile(r"(\d+|#)\s+([a-z]+)", re.I)

# Severities counted for the Tier 0/1 Red rule (D-85).
ECH = {"EMERGENCY", "CRITICAL", "HIGH"}


def _num(s):
    """'12' -> 12; '#' or anything unreadable -> None."""
    return int(s) if s and s.isdigit() else None


def read_comment(comment):
    """Turn a comment sentence into (compliant, open, overdue, by_severity) or None if unreadable."""
    c = (comment or "").strip()
    if P_NONE.search(c):
        return True, 0, 0, {}
    m = P_ALL.search(c)
    if m:
        return True, _num(m.group(1)), 0, {}
    m = P_FAIL.search(c)
    if m:
        by_sev = {}
        v = P_VIOL.search(c)
        if v:
            # The violations list is comma-separated ("2 CRITICAL, 8 MEDIUM"); semicolons accepted too.
            for part in re.split(r"[,;]", v.group(1)):
                one = P_ONE.search(part)
                if one:
                    by_sev[one.group(2).upper()] = _num(one.group(1))
        return False, _num(m.group(2)), _num(m.group(1)), by_sev
    return None


def read(raw_bytes, kind, uploaded_at=None):
    """Read a Checkmarx file. kind is 'SAST' or 'SCA' and comes from the feed it was uploaded to.

    The as-of date (owner, 2 Nov 2026): the report date inside the file if Cyber gives one and it reads
    as a date; otherwise the upload date (uploaded_at, or now in New York if not given).

    Returns dict(rows=[...], set_aside=[...], notes=[...]). Raises ValueError only when the file
    cannot be read as JSON at all (the one allowed refusal).
    """
    notes, set_aside, rows, seen = [], [], [], set()
    names = column_map("cx_" + kind.lower(), FIELDS)
    f = lambda obj, field: get_field(obj, field, aliases=names[field][1:] if names[field][0] == field else names[field], notes=notes)
    try:
        doc = loads_tolerant(raw_bytes.decode("utf-8-sig", errors="replace"))
    except Exception as e:  # the only refusal: not readable at all
        raise ValueError(f"This file can't be read as JSON ({e}).") from None

    importer = f(doc, "importer")
    if importer is not None and str(importer).strip().lower() != "checkmarx":
        notes.append(f"importer is '{importer}', not 'checkmarx'; read anyway")
    entries = f(doc, "data")
    if not isinstance(entries, list):
        notes.append("no list of repos found in the file; nothing to load")
        entries = []

    for i, e in enumerate(entries, start=1):
        key = f(e, "key")
        if not key or not str(key).strip():
            set_aside.append(dict(entry=i, reason="no repo key"))
            continue
        key = str(key).strip()
        if key.lower() in seen:
            set_aside.append(dict(entry=i, key=key, reason="same repo listed twice; first kept"))
            continue
        seen.add(key.lower())

        ms = f(e, "measurements")
        ms = ms if isinstance(ms, list) else ([ms] if isinstance(ms, dict) else [])
        # Prefer the measurement that mentions this feed's type; otherwise the first one.
        pick = next((m for m in ms if kind.lower() in (str(f(m, "name")) + str(f(m, "comment"))).lower()), ms[0] if ms else {})
        comment = f(pick, "comment")
        value = as_bool(f(pick, "value"))

        parsed = read_comment(comment)
        row = dict(key=key, compliant=None, open=None, overdue=None, overdue_by_severity={}, overdue_ech=None, comment=comment, note=None)
        if parsed:
            compliant, opn, ovd, by_sev = parsed
            row.update(compliant=compliant, open=opn, overdue=ovd, overdue_by_severity=by_sev)
            row["overdue_ech"] = sum(n or 0 for s, n in by_sev.items() if s in ECH) if by_sev else (0 if compliant else None)
            if value is not None and value != compliant:
                row["note"] = "value disagrees with the comment; the comment decides"
            if ovd is not None and by_sev and all(n is not None for n in by_sev.values()) and sum(by_sev.values()) != ovd:
                row["note"] = "overdue count and violations don't add up; still counted as failing"
        elif value is not None:
            row.update(compliant=value, note="comment not recognised; pass/fail taken from value")
        else:
            set_aside.append(dict(entry=i, key=key, reason="neither comment nor value could be read"))
            continue
        rows.append(row)

    # As-of = the upload date. Any date the caller passes goes through the same reader as every feed.
    as_of = upload_time(uploaded_at)
    raw_report = f(doc, "report_as_of")
    report_date = parse_when(raw_report)            # same date reader as every feed
    if report_date is not None:
        as_of, source = report_date, "report date in the file"
    else:
        source = "upload date"
        if raw_report:
            notes.append(f"report date '{raw_report}' in the file isn't a date; the upload date is used")
    return dict(kind=kind, rows=rows, set_aside=set_aside, notes=notes,
                as_of=as_of.isoformat(), as_of_source=source,
                report_date=report_date.isoformat() if report_date else None,
                summary=dict(repos=len(rows), passing=sum(1 for r in rows if r["compliant"]),
                             failing=sum(1 for r in rows if r["compliant"] is False), set_aside=len(set_aside)))


def keep_fields(raw_bytes, kind):
    """Cut a Checkmarx JSON file down to the fields TRUST uses, before it is kept (owner, 2 Nov 2026):
    the importer, the report date (if any), and per repo its key and each measurement's name, value
    and comment. Returns (json_bytes or None, info); None if the file can't be read as JSON (then the
    file as received is kept, so mapping can say why)."""
    import json

    names = column_map("cx_" + kind.lower(), FIELDS)
    f = lambda obj, field: get_field(obj, field, aliases=names[field][1:] if names[field][0] == field else names[field])
    try:
        doc = loads_tolerant(raw_bytes.decode("utf-8-sig", errors="replace"))
    except Exception:
        return None, {"note": "not readable as JSON; kept as received so mapping can report it"}
    out = {}
    for field in ("importer", "report_as_of"):
        v = f(doc, field) if isinstance(doc, dict) else None
        if v is not None:
            out[field] = v
    entries = f(doc, "data") if isinstance(doc, dict) else None
    kept = []
    for e in entries if isinstance(entries, list) else []:
        if not isinstance(e, dict):
            continue
        ms = f(e, "measurements")
        ms = ms if isinstance(ms, list) else ([ms] if isinstance(ms, dict) else [])
        kept.append({"key": f(e, "key"),
                     "measurements": [{k: f(m, k) for k in ("name", "value", "comment")} for m in ms if isinstance(m, dict)]})
    out["data"] = kept
    return json.dumps(out, indent=1).encode("utf-8"), {"repos": len(kept), "has_repo_list": isinstance(entries, list),
                                                       "fields_kept": ["importer", "report_as_of", "key", "name", "value", "comment"]}
