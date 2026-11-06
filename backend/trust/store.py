"""Step 1, UPLOAD: keep each file exactly as received. Nothing is read, mapped or checked here.

Owner decision (2 Nov 2026, replaces part of D-97): TRUST keeps a copy of every uploaded file, so
mapping (step 2) can be re-run at any time without uploading again. The SharePoint link is still
recorded. Copies are kept 24 months like everything else (D-86).

Only what TRUST uses is kept (owner, 2 Nov 2026). Every file with a reader is cut down as it
arrives: the columns (or JSON fields) TRUST uses are kept, the rest are dropped; the hash of the file
as received is still recorded. The HR file is cut down further: only the CTO and everyone reporting up
to them (setting hr_root_sam_account) are kept (doc 13); the rest of the firm is never stored. If the HR
setting is empty or that person isn't in the file, nothing of it is kept. A feed whose layout hasn't
been given yet (no reader) is kept as received until it has one.

Because dropped columns can't be recovered, fixing a column name in config/column_maps.json for a
column that wasn't found needs the file uploaded again (the upload result lists what wasn't found).

Where it is kept: the database add-on when DATABASE_URL is set (tables kept_file and submission),
otherwise the store/ folder (uploads/<YYYY-MM>/<feed>/<sha256><ext> and register.json). See storage.py.
The newest upload for a feed and month is the one mapping uses (D-92: a new file replaces the old;
both are kept).
"""
import hashlib
import json
import pathlib
import re

from . import checks, config, storage
from .intake import (actions, app_inventory, checkmarx, defects, dr_tests, families, hr, itdr, ntcc, owner_groups,
                     postmortems, repos, tcc)
from .intake.common import column_map, keep_columns
from .intake.common import upload_time

FEEDS = ("hr", "hr_mapping", "app_inventory", "app_owner_members", "repos", "tcc", "ntcc", "postmortems", "actions",
         "cx_sast", "cx_sca", "commits", "itdr", "dr_tests", "secrets",
         "cyberark", "sailpoint", "hosting_eol", "defects")


store_dir = storage.store_dir


def _check(feed, month):
    if feed not in FEEDS:
        raise ValueError(f"'{feed}' isn't a feed TRUST knows. Feeds: {', '.join(FEEDS)}")
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month or ""):
        raise ValueError(f"Month must look like 2026-10 (got '{month}').")


def contract_warnings(feed, kept):
    """Data contract check at upload (owner, 4 Nov 2026): once a feed's contract is approved, the provider may not
    change the file on us. A column the contract names that isn't in the file, or a column TRUST now reads that the
    contract doesn't name, is a warning that must be acknowledged before the month is locked. kept = the upload's
    kept-columns record (columns_kept, fields_not_found)."""
    c = storage.approved_contracts().get(feed)
    if not c or not isinstance(c.get("columns"), list):
        return []
    tidy = lambda x: " ".join(str(x).lower().split())
    found = {tidy(x) for x in (kept.get("columns_kept") or [])}
    if not found:
        return []
    contracted = {tidy(x): str(x) for x in c["columns"]}
    missing = [v for k, v in contracted.items() if k not in found]
    extra = sorted({x for x in (kept.get("columns_kept") or []) if tidy(x) not in contracted})
    out = []
    if missing:
        out.append(f"Layout differs from the data contract (version {c['version']}, approved {str(c.get('decided_at') or '')[:10]}): "
                   f"{len(missing)} contracted {'column is' if len(missing) == 1 else 'columns are'} not in this file: "
                   f"{', '.join(missing[:8])}{' and more' if len(missing) > 8 else ''}. Ask the provider whether the file changed.")
    if extra:
        out.append(f"Layout differs from the data contract (version {c['version']}): TRUST read {len(extra)} "
                   f"{'column' if len(extra) == 1 else 'columns'} the contract doesn't name: {', '.join(extra[:8])}"
                   f"{' and more' if len(extra) > 8 else ''}. A new contract version needs the provider's approval.")
    return out


def upload(feed, month, file_bytes, filename, uploaded_by, sharepoint_link=None, uploaded_at=None):
    """Keep one file for a feed and month. Returns the register entry.

    Only refuses an empty file, an unknown feed or a badly written month. The file's contents are
    not looked at: a file that later turns out to be unreadable is reported by mapping, not here.
    """
    _check(feed, month)
    storage.ensure_open(month)
    if not file_bytes:
        raise ValueError("This file is empty.")
    original_sha = hashlib.sha256(file_bytes).hexdigest()     # of the file as received (matches SharePoint)
    register = storage.register(month, feed)

    extra, root = {}, None
    if feed == "hr":
        root = (config.settings().get("hr_root_sam_account") or "").strip().lower()
    maps = _column_map_hash(feed)
    # Only the newest upload counts as "already received": uploading an older version again makes it current
    # (from review, 5 Nov 2026).
    same = [e for e in register[-1:] if e.get("original_sha256", e["sha256"]) == original_sha and e.get("column_map") == maps
            and (feed != "hr" or (e.get("hr_root_sam_account") == root and e.get("file")))]
    if same:
        return {**same[-1], "note": "already received: the same file was uploaded before; nothing changed"}

    ext = pathlib.Path(filename or "").suffix.lower()[:10]
    if feed == "hr":
        kept_bytes, result = hr.minimise(file_bytes, root)
        s = result["summary"]
        extra = {"hr_root_sam_account": root, "notes": result["notes"],
                 "kept": {"rows_in_file": s["rows_in_file"], "people_kept": s["kept"], "left_out": s["left_out"],
                          "set_aside": s["set_aside"]}}
        file_bytes, ext = kept_bytes, ".csv"
    elif feed in TABLE_FIELDS:
        try:
            if feed == "hr_mapping" and families.is_json(file_bytes):   # product_line_owners.json (owner, 3 Nov 2026)
                file_bytes = families.to_csv(file_bytes)
            kept_bytes, info = keep_columns(file_bytes, feed, TABLE_FIELDS[feed], HEADER_ROWS.get(feed, 1))
        except ValueError as err:           # not readable as a table: keep it as received, mapping says why
            kept_bytes, info = file_bytes, {"note": str(err)}
        extra = {"kept": info}
        if kept_bytes is not None and kept_bytes is not file_bytes:
            ext = ".csv"
        file_bytes = kept_bytes
    elif feed in ("cx_sast", "cx_sca"):
        kept_bytes, info = checkmarx.keep_fields(file_bytes, "SAST" if feed == "cx_sast" else "SCA")
        extra = {"kept": info}
        if kept_bytes is not None:
            file_bytes, ext = kept_bytes, ".json"
    extra["column_map"] = maps
    sha = hashlib.sha256(file_bytes).hexdigest() if file_bytes else None
    entry = {
        "feed": feed, "month": month, "sha256": sha, "original_sha256": original_sha,
        "file": f"{sha}{ext}" if file_bytes else None, "original_name": filename,
        "size_bytes": len(file_bytes) if file_bytes else 0, "uploaded_by": uploaded_by,
        "uploaded_at": upload_time(uploaded_at).isoformat(), "sharepoint_link": sharepoint_link,
        "replaces": register[-1].get("original_sha256", register[-1]["sha256"]) if register else None, **extra,
    }
    # Data quality checks before anything is stored (owner, 3 Nov 2026): junk is refused, the rest kept with warnings.
    res = checks.check_upload(feed, file_bytes, entry, extra.get("kept") or {})
    if res["refused"]:
        storage.log("upload", uploaded_by, month, f"{feed}: {filename} refused", {
            "feed": feed, "file": filename, "original_sha256": original_sha, "refused": res["refused"]})
        raise ValueError("Not uploaded. " + " ".join(res["refused"]))
    res["warnings"].extend(contract_warnings(feed, extra.get("kept") or {}))
    entry["checks"] = {"rows": res["rows"], "set_aside": res["set_aside"], "warnings": res["warnings"]}
    # Files kept as tables too (owner, 3 Nov 2026): the ITDR applications and the DR tests.
    table_rows = ({"itdr": itdr, "dr_tests": dr_tests}[feed].read(file_bytes)["rows"]
                  if feed in storage.ROW_TABLES and file_bytes else None)
    storage.add_upload(month, feed, entry, file_bytes, table_rows=table_rows)
    if feed == "hr" and not file_bytes:
        note = ("received, but nothing kept: set the CTO's SAM_ACCOUNT (hr_root_sam_account) in config/settings.json "
                "and upload the file again" if not root else
                f"received, but nothing kept: SAM_ACCOUNT '{root}' is not in this file")
    elif feed == "hr":
        k = entry["kept"]
        note = (f"kept {k['people_kept']} people in the CTO's line (of {k['rows_in_file']} rows) and only the "
                f"columns TRUST uses; the rest of the file was not stored")
    elif not file_bytes:
        note = ("received, but nothing kept: none of the columns TRUST uses were found. Add the file's column "
                "names to config/column_maps.json and upload it again")
    elif entry.get("kept", {}).get("columns_dropped") is not None:
        k = entry["kept"]
        note = (f"kept {len(k['columns_kept'])} columns TRUST uses ({len(k['columns_dropped'])} others not stored)"
                + (f"; not found: {', '.join(k['fields_not_found'])}" if k["fields_not_found"] else ""))
    else:
        note = "replaces the earlier file for this feed and month" if entry["replaces"] else "received"
    storage.log("upload", uploaded_by, month, f"{feed}: {filename}", {
        "feed": feed, "file": filename, "original_sha256": original_sha, "kept_sha256": sha, "note": note})
    return {**entry, "note": note}


# Delimited files and the reader fields that decide which columns are kept.
TABLE_FIELDS = {"tcc": tcc.FIELDS, "ntcc": ntcc.FIELDS, "actions": actions.FIELDS,
                "postmortems": postmortems.FIELDS, "hr_mapping": families.FIELDS, "itdr": itdr.FIELDS,
                "dr_tests": dr_tests.FIELDS, "repos": repos.FIELDS,
                "defects": defects.FIELDS, "app_inventory": app_inventory.FIELDS,
                "app_owner_members": owner_groups.FIELDS}
# Files whose header spans more than one row (ITDR: merged over rows 1 and 2, owner 3 Nov 2026).
HEADER_ROWS = {"itdr": itdr.HEADER_ROWS, "dr_tests": dr_tests.HEADER_ROWS}


def _column_map_hash(feed):
    """A fingerprint of the column names in use for a feed: a changed map lets the same file be re-uploaded."""
    fields = (TABLE_FIELDS.get(feed) or (hr.FIELDS if feed == "hr" else
              checkmarx.FIELDS if feed in ("cx_sast", "cx_sca") else None))
    if fields is None:
        return None
    return hashlib.sha256(json.dumps(column_map(feed, fields), sort_keys=True).encode()).hexdigest()[:16]


def latest(month):
    """The upload each feed's mapping uses for a month: {feed: (entry, bytes)}. Feeds with no upload are absent."""
    out = {}
    for feed in FEEDS:
        register = storage.register(month, feed)
        if register:
            e = register[-1]
            out[feed] = (e, storage.kept_file(month, feed, e))
    return out
