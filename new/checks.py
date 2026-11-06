"""Data quality checks at upload (owner, 3 Nov 2026: "make sure we aren't getting junk").

Every file is read with its feed's reader the moment it arrives, after it has been cut down to the
columns TRUST uses. Two outcomes:

- **Refused, not stored** (the attempt is still in the event log): the file can't be read at all; it
  doesn't look like this feed's file (most of the fields TRUST needs aren't in it); every row in it is
  unusable; or, for HR, nobody in it is in the CTO's line. Each reason is said in plain words.
- **Stored, with warnings**: anything else worth a look (a column matched by a close spelling, dates that
  aren't dates, rows set aside, a file with no rows this month). The same warnings come back when the
  month is mapped, and each must be acknowledged before the month can be locked.

This narrows the 2 Nov 2026 rule "a file is never refused for what's in it": a real file with small
problems still loads; only files TRUST can do nothing with are turned away.
"""

NAMES = {"hr": "HR", "hr_mapping": "product family owners", "tcc": "TCC changes", "ntcc": "Non-TCC changes",
         "actions": "postmortem action items", "postmortems": "postmortems", "cx_sast": "Checkmarx SAST",
         "cx_sca": "Checkmarx SCA", "itdr": "ITDR applications",
         "dr_tests": "DR tests", "repos": "GitHub repos",
         "defects": "Jira issues", "app_inventory": "app inventory", "app_owner_members": "AD owner groups"}


def _fields_needed(feed):
    from . import store
    from .intake import checkmarx, hr
    return (store.TABLE_FIELDS.get(feed) or (hr.FIELDS if feed == "hr" else
            checkmarx.FIELDS if feed in ("cx_sast", "cx_sca") else {}))


def check_upload(feed, kept_bytes, entry, kept_info):
    """-> dict(refused=[reasons], warnings=[...], rows=n, set_aside=n). kept_bytes is what would be stored."""
    from . import config, mapping
    name = NAMES.get(feed, feed)
    out = {"refused": [], "warnings": [], "rows": 0, "set_aside": 0}
    reader = mapping.READERS.get(feed)
    if reader is None:
        out["warnings"].append("No checks yet: this file's layout hasn't been given, so it is kept as received.")
        return out
    if not kept_bytes:
        if feed == "hr":
            root = entry.get("hr_root_sam_account")
            out["refused"].append(
                "Nobody in this file is in the CTO's line, so there is nothing to keep."
                + (f" The CTO's SAM_ACCOUNT is set to '{root}': check it is right and in this file." if root else
                   " The CTO's SAM_ACCOUNT (hr_root_sam_account) isn't set in config/settings.json yet."))
        else:
            missing = (kept_info or {}).get("fields_not_found") or []
            out["refused"].append(f"None of the columns TRUST uses for {name} were found"
                                  + (f" (looked for: {', '.join(missing[:6])})" if missing else "")
                                  + ". Check this is the right file; if the provider renamed the columns, add the new "
                                    "names in config/column_maps.json and upload it again.")
        return out
    if feed in ("cx_sast", "cx_sca") and "not readable as JSON" in str((kept_info or {}).get("note", "")):
        out["refused"].append(f"It can't be read as a {name} report: it isn't valid JSON.")
        return out
    try:
        r = reader(kept_bytes, entry, config.settings())
    except ValueError as err:
        out["refused"].append(f"It can't be read as a {name} file: {err}")
        return out
    rows, aside, notes = r.get("rows") or r.get("people") or [], r.get("set_aside") or [], r.get("notes") or []
    if "members" in r:                        # AD owner groups: kept compact, counted in its summary (6 Nov 2026)
        rows = range((r.get("summary") or {}).get("rows", 0))
    out["rows"], out["set_aside"] = len(rows), len(aside)
    needed = _fields_needed(feed)
    missing = (kept_info or {}).get("fields_not_found") or []
    if not rows and aside:
        why = "; ".join(str(a.get("reason", a)) if isinstance(a, dict) else str(a) for a in aside[:3])
        out["refused"].append(f"None of its {len(aside)} rows could be used ({why}). Check this is the right file.")
    elif not rows and needed and len(missing) * 2 >= len(needed):
        out["refused"].append(f"It doesn't look like a {name} file: {len(missing)} of the {len(needed)} columns TRUST "
                              f"needs aren't in it ({', '.join(missing[:6])}). Check this is the right file; if the "
                              "provider renamed the columns, add the new names in config/column_maps.json.")
    elif not rows and feed in ("cx_sast", "cx_sca") and ((kept_info or {}).get("has_repo_list") is False
                                                        or any("no list of repos" in n for n in notes)):
        out["refused"].append(f"It doesn't look like a {name} report: there is no list of repos in it.")
    if out["refused"]:
        return out
    if not rows:
        out["warnings"].append("The file has no rows: TRUST will treat this month as having nothing to count for it.")
    if aside:
        out["warnings"].append(f"{len(aside)} of {len(aside) + len(rows)} rows were set aside (each with its reason in "
                               "the mapping result).")
    out["warnings"].extend(notes)
    return out
