"""Where TRUST keeps things: the database add-on when DATABASE_URL is set, otherwise the store/ folder.

On the platform the app's own disk is wiped on every restart and isn't shared between the website and
one-off commands, so everything kept (the cut-down files, the upload register, the mapped and scored
months and the published page) goes in Postgres. Locally and in tests, with no DATABASE_URL, it goes
in the folder named by TRUST_STORE_DIR (default ./store), exactly as before.

Everything else in TRUST goes through these few functions, so it doesn't care which one is in use.
"""
import hashlib
import json
import os
import pathlib
import subprocess


def database_url():
    """The add-on's connection string (DATABASE_URL), or TRUST_DATABASE_URL for local use."""
    return os.environ.get("DATABASE_URL") or os.environ.get("TRUST_DATABASE_URL") or None


def using_database():
    return database_url() is not None


def store_dir():
    return pathlib.Path(os.environ.get("TRUST_STORE_DIR", "store"))


def connect():
    import psycopg                      # only needed when the database is in use
    return psycopg.connect(database_url(), autocommit=True)


# ---- the upload register (one list per feed and month, newest last) and the kept files ----

def register(month, feed):
    if using_database():
        with connect() as c:
            rows = c.execute("SELECT entry FROM submission WHERE month = %s AND feed = %s ORDER BY id",
                             (month, feed)).fetchall()
        return [r[0] for r in rows]
    path = store_dir() / "uploads" / month / feed / "register.json"
    return json.loads(path.read_text()) if path.exists() else []


# Feeds whose rows are also kept as a table (owner, 3 Nov 2026), with the columns written for each row.
ROW_TABLES = {
    "itdr": ("itdr_application", ("ref", "application_name", "business_product_area", "recovery_tier", "tier_label")),
    "dr_tests": ("dr_test", ("application_name", "recovery_tier", "tier_label", "business_area", "itdr_lead",
                             "test_type", "kind", "environment", "test_date", "status", "performed_on",
                             "comments", "comment_date", "ttx_in_comment")),
}


def add_upload(month, feed, entry, file_bytes, table_rows=None):
    """Keep the cut-down file (if anything was kept) and add its entry to the register.

    table_rows: for a feed in ROW_TABLES, its rows, kept in that table in the same step. Without the
    database they go next to the file as <sha256>.rows.json.
    """
    if using_database():
        from psycopg.types.json import Jsonb
        with connect() as c, c.transaction():
            if file_bytes:
                c.execute("INSERT INTO kept_file (sha256, content) VALUES (%s, %s) ON CONFLICT (sha256) DO NOTHING",
                          (entry["sha256"], file_bytes))
            sid = c.execute("INSERT INTO submission (month, feed, entry) VALUES (%s, %s, %s) RETURNING id",
                            (month, feed, Jsonb(entry))).fetchone()[0]
            if table_rows:
                table, cols = ROW_TABLES[feed]
                with c.cursor() as cur:
                    cur.executemany(
                        f"INSERT INTO {table} (submission_id, month, {', '.join(cols)}) "
                        f"VALUES (%s, %s, {', '.join(['%s'] * len(cols))})",
                        [(sid, month, *[r[k] for k in cols]) for r in table_rows])
        return
    folder = store_dir() / "uploads" / month / feed
    folder.mkdir(parents=True, exist_ok=True)
    if file_bytes:
        (folder / entry["file"]).write_bytes(file_bytes)
    if table_rows:
        (folder / f"{entry['sha256']}.rows.json").write_text(json.dumps(table_rows, indent=1))
    reg = register(month, feed)
    reg.append(entry)
    (folder / "register.json").write_text(json.dumps(reg, indent=2))


def table_rows(month, feed):
    """The rows of a ROW_TABLES feed for a month, from its newest upload, in file order. [] if none."""
    table, cols = ROW_TABLES[feed]
    if using_database():
        with connect() as c:
            rows = c.execute(
                f"SELECT {', '.join(cols)} FROM {table} WHERE submission_id = (SELECT max(id) FROM submission "
                "WHERE month = %s AND feed = %s) ORDER BY id", (month, feed)).fetchall()
        out = [dict(zip(cols, r)) for r in rows]
        for r in out:
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
        return out
    reg = register(month, feed)
    if not reg or not reg[-1].get("sha256"):
        return []
    path = store_dir() / "uploads" / month / feed / f"{reg[-1]['sha256']}.rows.json"
    return json.loads(path.read_text()) if path.exists() else []


def itdr_applications(month):
    """The current ITDR application list for a month (from its newest upload), sorted by Ref."""
    return sorted(table_rows(month, "itdr"), key=lambda r: r["ref"])


def dr_tests(month):
    """The current list of completed DR tests for a month (from its newest upload), in file order."""
    return table_rows(month, "dr_tests")


def kept_file(month, feed, entry):
    if not entry.get("file"):
        return None
    if using_database():
        with connect() as c:
            row = c.execute("SELECT content FROM kept_file WHERE sha256 = %s", (entry["sha256"],)).fetchone()
        return bytes(row[0]) if row else None
    return (store_dir() / "uploads" / month / feed / entry["file"]).read_bytes()


# ---- mapped and scored months (every run kept; the newest is current) ----

ROOT = pathlib.Path(__file__).resolve().parents[2]


def git_sha():
    """The commit of the running code: TRUST_GIT_SHA, the platform's SOURCE_VERSION, or git itself."""
    sha = os.environ.get("TRUST_GIT_SHA") or os.environ.get("SOURCE_VERSION")
    if sha:
        return sha
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def settings_sha256():
    """One hash over the settings, thresholds and column maps in use, so a run says which version it used."""
    h = hashlib.sha256()
    for env, name in (("TRUST_SETTINGS", "settings.json"), ("TRUST_THRESHOLDS", "thresholds.json"),
                      (None, "column_maps.json")):
        path = pathlib.Path((env and os.environ.get(env)) or ROOT / "config" / name)
        h.update(name.encode() + b"\0" + (path.read_bytes() if path.exists() else b"") + b"\0")
    return h.hexdigest()


def save_month(kind, month, doc, by="command line"):
    """kind is 'mapped' or 'scored'. Adds a run; the newest is the current one."""
    text = json.dumps(doc, indent=2, default=str)
    if using_database():
        with connect() as c:
            c.execute("""INSERT INTO month_result (kind, month, doc, by, git_sha, settings_sha256)
                         VALUES (%s, %s, %s::jsonb, %s, %s, %s)""",
                      (kind, month, text, by, git_sha(), settings_sha256()))
        return
    path = store_dir() / kind / f"{month}.json"         # the folder keeps only the newest run
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    (path.parent / f"{month}.run").write_text(json.dumps(
        {"by": by, "at": _now(), "git_sha": git_sha(), "settings_sha256": settings_sha256()}))


def run_info(kind, month):
    """Who ran the newest mapping or scoring of a month, when, and with which code and settings (or None)."""
    if using_database():
        with connect() as c:
            r = c.execute("""SELECT by, run_at, git_sha, settings_sha256 FROM month_result
                             WHERE kind = %s AND month = %s ORDER BY id DESC LIMIT 1""", (kind, month)).fetchone()
        return {"by": r[0], "at": r[1].isoformat(), "git_sha": r[2], "settings_sha256": r[3]} if r else None
    path = store_dir() / kind / f"{month}.run"
    return json.loads(path.read_text()) if path.exists() else None


def load_month(kind, month):
    """The newest run's document, or None if that month hasn't been mapped/scored."""
    if using_database():
        with connect() as c:
            row = c.execute("SELECT doc FROM month_result WHERE kind = %s AND month = %s ORDER BY id DESC LIMIT 1",
                            (kind, month)).fetchone()
        return row[0] if row else None
    path = store_dir() / kind / f"{month}.json"
    return json.loads(path.read_text()) if path.exists() else None


def months(kind):
    if using_database():
        with connect() as c:
            rows = c.execute("SELECT DISTINCT month FROM month_result WHERE kind = %s ORDER BY month",
                             (kind,)).fetchall()
        return [r[0] for r in rows]
    folder = store_dir() / kind
    return sorted(p.stem for p in folder.glob("*.json")) if folder.exists() else []


def upload_months():
    """Every month that has at least one stored upload (refused files are never stored), oldest first."""
    if using_database():
        with connect() as c:
            return [r[0] for r in c.execute("SELECT DISTINCT month FROM submission ORDER BY month").fetchall()]
    folder = store_dir() / "uploads"
    return sorted(p.name for p in folder.iterdir() if p.is_dir() and any(p.iterdir())) if folder.exists() else []


# ---- month status (open or locked) ----

def _jsonl(name):
    return store_dir() / name


def month_status(month):
    """{status, locked_by, locked_at, seal}. A month never locked is open."""
    blank = {"status": "open", "locked_by": None, "locked_at": None, "seal": None}
    if using_database():
        with connect() as c:
            row = c.execute("SELECT status, locked_by, locked_at, seal FROM month WHERE month = %s",
                            (month,)).fetchone()
        if not row:
            return blank
        return {"status": row[0], "locked_by": row[1], "locked_at": row[2].isoformat() if row[2] else None,
                "seal": row[3]}
    path = store_dir() / "months.json"
    return {**blank, **(json.loads(path.read_text()).get(month, {}) if path.exists() else {})}


def set_month_status(month, status, locked_by=None, locked_at=None, seal=None):
    if using_database():
        from psycopg.types.json import Jsonb
        with connect() as c:
            c.execute("""INSERT INTO month (month, status, locked_by, locked_at, seal) VALUES (%s, %s, %s, %s, %s)
                         ON CONFLICT (month) DO UPDATE SET status = EXCLUDED.status, locked_by = EXCLUDED.locked_by,
                             locked_at = EXCLUDED.locked_at, seal = EXCLUDED.seal, updated_at = now()""",
                      (month, status, locked_by, locked_at, Jsonb(seal) if seal is not None else None))
        return
    path = store_dir() / "months.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    allm = json.loads(path.read_text()) if path.exists() else {}
    allm[month] = {"status": status, "locked_by": locked_by, "locked_at": locked_at, "seal": seal}
    path.write_text(json.dumps(allm, indent=2))


def ensure_open(month):
    """Refuse a change to a locked month, in plain words."""
    st = month_status(month)
    if st["status"] == "locked":
        raise ValueError(f"{month} is locked (by {st['locked_by']}), so it can't be changed. "
                         "Reopen it on the Tech Risk console first, with a reason.")


# ---- the event log (one line per action, never edited) ----

def log(action, by, month=None, note="", detail=None):
    if using_database():
        from psycopg.types.json import Jsonb
        with connect() as c:
            c.execute("INSERT INTO event_log (month, action, by, note, detail) VALUES (%s, %s, %s, %s, %s)",
                      (month, action, by, note, Jsonb(detail) if detail is not None else None))
        return
    path = _jsonl("events.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"at": _now(), "month": month, "action": action, "by": by, "note": note,
                            "detail": detail}, default=str) + "\n")


def events(month=None, limit=200):
    """Newest first."""
    if using_database():
        with connect() as c:
            rows = c.execute("""SELECT at, month, action, by, note, detail FROM event_log
                                WHERE %s::text IS NULL OR month = %s OR month IS NULL
                                ORDER BY id DESC LIMIT %s""", (month, month, limit)).fetchall()
        return [{"at": r[0].isoformat(), "month": r[1], "action": r[2], "by": r[3], "note": r[4], "detail": r[5]}
                for r in rows]
    path = _jsonl("events.jsonl")
    rows = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    rows = [r for r in rows if month is None or r["month"] in (month, None)]
    return rows[::-1][:limit]


# ---- comments (never edited; a reply is a new row) ----

COMMENT_FIELDS = ("month", "family", "metric", "block", "kind", "text", "by", "reply_to", "status", "after_lock")


def add_comment(c_):
    """c_ has COMMENT_FIELDS. Returns the stored comment with its id and time."""
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO comment (month, family, metric, block, kind, text, by, reply_to, status,
                                   after_lock) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, at""",
                            tuple(c_[k] for k in COMMENT_FIELDS)).fetchone()
        return {**c_, "id": row[0], "at": row[1].isoformat()}
    path = _jsonl("comments.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(path.read_text().splitlines()) if path.exists() else 0
    out = {**c_, "id": n + 1, "at": _now()}
    with path.open("a") as f:
        f.write(json.dumps(out) + "\n")
    return out


def comments(month):
    """Every comment for a month, oldest first."""
    if using_database():
        with connect() as c:
            rows = c.execute(f"""SELECT id, at, {", ".join(COMMENT_FIELDS)} FROM comment WHERE month = %s ORDER BY id""",
                             (month,)).fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), **dict(zip(COMMENT_FIELDS, r[2:]))} for r in rows]
    path = _jsonl("comments.jsonl")
    rows = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    return [r for r in rows if r["month"] == month]


def comment(cid):
    if using_database():
        with connect() as c:
            r = c.execute(f"SELECT id, at, {', '.join(COMMENT_FIELDS)} FROM comment WHERE id = %s", (cid,)).fetchone()
        return {"id": r[0], "at": r[1].isoformat(), **dict(zip(COMMENT_FIELDS, r[2:]))} if r else None
    path = _jsonl("comments.jsonl")
    rows = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    return next((r for r in rows if r["id"] == cid), None)


# ---- warning acknowledgements (never edited) ----

def add_ack(month, feed, note_key, note, by, reason=""):
    if using_database():
        with connect() as c:
            c.execute("INSERT INTO warning_ack (month, feed, note_key, note, by, reason) VALUES (%s, %s, %s, %s, %s, %s)",
                      (month, feed, note_key, note, by, reason))
        return
    path = _jsonl("acks.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"month": month, "feed": feed, "note_key": note_key, "note": note, "by": by,
                            "at": _now(), "reason": reason}) + "\n")


def acks(month):
    """{note_key: the first acknowledgement} for a month."""
    if using_database():
        with connect() as c:
            rows = c.execute("SELECT note_key, by, at, reason FROM warning_ack WHERE month = %s ORDER BY id",
                             (month,)).fetchall()
        rows = [{"note_key": r[0], "by": r[1], "at": r[2].isoformat(), "reason": r[3]} for r in rows]
    else:
        path = _jsonl("acks.jsonl")
        rows = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
        rows = [r for r in rows if r["month"] == month]
    out = {}
    for r in rows:
        out.setdefault(r["note_key"], {k: r[k] for k in ("by", "at", "reason")})
    return out


# ---- dictionary proposals and decisions (never edited; a decision is a new row) ----

def _with_status(p, decs):
    return {**p, "decisions": decs, "status": decs[-1]["decision"] if decs else "open"}


def add_proposal(p):
    """p has kind, metric, title, detail, by. Returns the stored proposal with its id and time."""
    if using_database():
        from psycopg.types.json import Jsonb
        with connect() as c:
            row = c.execute("""INSERT INTO proposal (kind, metric, title, detail, by) VALUES (%s, %s, %s, %s, %s)
                               RETURNING id, at""",
                            (p["kind"], p["metric"], p["title"], Jsonb(p["detail"]), p["by"])).fetchone()
        return {**p, "id": row[0], "at": row[1].isoformat()}
    path = _jsonl("proposals.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(path.read_text().splitlines()) if path.exists() else 0
    out = {**p, "id": n + 1, "at": _now()}
    with path.open("a") as f:
        f.write(json.dumps(out) + "\n")
    return out


def add_decision(d):
    """d has proposal_id, decision, reason, by. Returns the stored decision with its id and time."""
    if using_database():
        with connect() as c:
            row = c.execute("""INSERT INTO proposal_decision (proposal_id, decision, reason, by)
                               VALUES (%s, %s, %s, %s) RETURNING id, at""",
                            (d["proposal_id"], d["decision"], d["reason"], d["by"])).fetchone()
        return {**d, "id": row[0], "at": row[1].isoformat()}
    path = _jsonl("decisions.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(path.read_text().splitlines()) if path.exists() else 0
    out = {**d, "id": n + 1, "at": _now()}
    with path.open("a") as f:
        f.write(json.dumps(out) + "\n")
    return out


def _all_proposals():
    """(proposals oldest first, decisions oldest first)."""
    if using_database():
        with connect() as c:
            ps = c.execute("SELECT id, at, kind, metric, title, detail, by FROM proposal ORDER BY id").fetchall()
            ds = c.execute("SELECT id, at, proposal_id, decision, reason, by FROM proposal_decision ORDER BY id").fetchall()
        return ([{"id": r[0], "at": r[1].isoformat(), "kind": r[2], "metric": r[3], "title": r[4], "detail": r[5],
                  "by": r[6]} for r in ps],
                [{"id": r[0], "at": r[1].isoformat(), "proposal_id": r[2], "decision": r[3], "reason": r[4],
                  "by": r[5]} for r in ds])
    read = lambda name: ([json.loads(x) for x in _jsonl(name).read_text().splitlines()]
                         if _jsonl(name).exists() else [])
    return read("proposals.jsonl"), read("decisions.jsonl")


def proposals():
    """Every proposal, newest first, each with its status and its decisions (oldest first)."""
    ps, ds = _all_proposals()
    return [_with_status(p, [d for d in ds if d["proposal_id"] == p["id"]]) for p in reversed(ps)]


def proposal(pid):
    return next((p for p in proposals() if p["id"] == pid), None)


# ---- data contracts (owner, 4 Nov 2026): a request is never edited; the decision is filled in once ----

CONTRACT_FIELDS = ("feed", "version", "provider", "contact", "what", "cadence", "columns", "metrics", "note", "by")


def add_contract(c_):
    """c_ has CONTRACT_FIELDS. Returns the stored request (status draft) with its id and time."""
    if using_database():
        from psycopg.types.json import Jsonb
        with connect() as c:
            row = c.execute("""INSERT INTO data_contract (feed, version, provider, contact, what, cadence, columns,
                                   metrics, note, by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, at""",
                            (c_["feed"], c_["version"], c_["provider"], c_["contact"], c_["what"], c_["cadence"],
                             Jsonb(c_["columns"]), Jsonb(c_["metrics"]), c_["note"], c_["by"])).fetchone()
        return {**c_, "id": row[0], "at": row[1].isoformat(), "status": "draft", "decided_by": None,
                "decided_at": None, "reason": ""}
    rows = _contract_rows()
    out = {**c_, "id": len(rows) + 1, "at": _now(), "status": "draft", "decided_by": None, "decided_at": None,
           "reason": ""}
    _write_contract_rows(rows + [out])
    return out


def decide_contract(cid, status, by, reason=""):
    """Fill in the decision on a draft: approved, returned or withdrawn. Returns the contract, or None."""
    if using_database():
        with connect() as c:
            row = c.execute("""UPDATE data_contract SET status = %s, decided_by = %s, decided_at = now(), reason = %s
                               WHERE id = %s AND status = 'draft' RETURNING id""", (status, by, reason, cid)).fetchone()
        return contract(cid) if row else None
    rows = _contract_rows()
    for r in rows:
        if r["id"] == cid and r["status"] == "draft":
            r.update(status=status, decided_by=by, decided_at=_now(), reason=reason)
            _write_contract_rows(rows)
            return r
    return None


def _contract_rows():
    if using_database():
        with connect() as c:
            rs = c.execute(f"""SELECT id, at, {", ".join(CONTRACT_FIELDS)}, status, decided_by, decided_at, reason
                               FROM data_contract ORDER BY id""").fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), **dict(zip(CONTRACT_FIELDS, r[2:2 + len(CONTRACT_FIELDS)])),
                 "status": r[-4], "decided_by": r[-3], "decided_at": r[-2].isoformat() if r[-2] else None,
                 "reason": r[-1]} for r in rs]
    path = _jsonl("contracts.jsonl")
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def _write_contract_rows(rows):
    path = _jsonl("contracts.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def contracts():
    """Every data contract request, oldest first."""
    return _contract_rows()


def contract(cid):
    return next((c for c in _contract_rows() if c["id"] == cid), None)


def approved_contracts():
    """The current (highest approved version) contract per feed: {feed: contract}."""
    out = {}
    for c in _contract_rows():
        if c["status"] == "approved" and (c["feed"] not in out or c["version"] > out[c["feed"]]["version"]):
            out[c["feed"]] = c
    return out


# ---- Lost and Found claims (owner, 9 Nov 2026): a claim is never edited; its decision changes once or twice ----

CLAIM_FIELDS = ("feed", "item", "label", "family_id", "month", "why", "by")
# which status a decision may move a claim from
CLAIM_MOVES = {"approved": ("draft",), "returned": ("draft",), "withdrawn": ("draft",), "released": ("approved",)}


def add_claim(c_):
    if using_database():
        with connect() as c:
            row = c.execute(f"""INSERT INTO claim ({", ".join(CLAIM_FIELDS)}) VALUES ({", ".join(["%s"] * len(CLAIM_FIELDS))})
                                RETURNING id, at""", tuple(c_[k] for k in CLAIM_FIELDS)).fetchone()
        return {**c_, "id": row[0], "at": row[1].isoformat(), "status": "draft", "decided_by": None,
                "decided_at": None, "reason": ""}
    rows = _claim_rows()
    out = {**c_, "id": len(rows) + 1, "at": _now(), "status": "draft", "decided_by": None, "decided_at": None, "reason": ""}
    _write_claim_rows(rows + [out])
    return out


def decide_claim(cid, status, by, reason=""):
    """approved / returned / withdrawn (from draft) or released (from approved). Returns the claim, or None."""
    allowed = CLAIM_MOVES[status]
    if using_database():
        with connect() as c:
            row = c.execute("""UPDATE claim SET status = %s, decided_by = %s, decided_at = now(), reason = %s
                               WHERE id = %s AND status = ANY(%s) RETURNING id""",
                            (status, by, reason, cid, list(allowed))).fetchone()
        return claim(cid) if row else None
    rows = _claim_rows()
    for r in rows:
        if r["id"] == cid and r["status"] in allowed:
            r.update(status=status, decided_by=by, decided_at=_now(), reason=reason)
            _write_claim_rows(rows)
            return r
    return None


def _claim_rows():
    if using_database():
        with connect() as c:
            rs = c.execute(f"""SELECT id, at, {", ".join(CLAIM_FIELDS)}, status, decided_by, decided_at, reason
                               FROM claim ORDER BY id""").fetchall()
        return [{"id": r[0], "at": r[1].isoformat(), **dict(zip(CLAIM_FIELDS, r[2:2 + len(CLAIM_FIELDS)])),
                 "status": r[-4], "decided_by": r[-3], "decided_at": r[-2].isoformat() if r[-2] else None,
                 "reason": r[-1]} for r in rs]
    path = _jsonl("claims.jsonl")
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def _write_claim_rows(rows):
    path = _jsonl("claims.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def claims():
    """Every claim, oldest first."""
    return _claim_rows()


def claim(cid):
    return next((c for c in _claim_rows() if c["id"] == cid), None)


def doc_sha256(doc):
    """A fingerprint of a JSON document that doesn't depend on key order or spacing."""
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---- the published page (index.html, data.json, evidence.json) ----

PUBLISHED = ("index.html", "data.json", "evidence.json")


def save_published(files):
    """files: {name: text}. Returns where they went (a folder, or 'database')."""
    if using_database():
        with connect() as c, c.transaction():
            for name, body in files.items():
                c.execute("""INSERT INTO published_file (name, body) VALUES (%s, %s)
                             ON CONFLICT (name) DO UPDATE SET body = EXCLUDED.body, updated_at = now()""",
                          (name, body))
        return "database"
    out = store_dir() / "published"
    out.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (out / name).write_text(body, encoding="utf-8")
    return out


def published(name):
    """The published file's text, or None if nothing has been published."""
    if name not in PUBLISHED:
        return None
    if using_database():
        with connect() as c:
            row = c.execute("SELECT body FROM published_file WHERE name = %s", (name,)).fetchone()
        return row[0] if row else None
    path = store_dir() / "published" / name
    return path.read_text(encoding="utf-8") if path.exists() else None


# ---- retention (D-86): remove a month's data, and old runs that aren't the newest ----

MONTH_TABLES = ("itdr_application", "dr_test", "warning_ack", "comment", "submission", "event_log", "month")


def month_footprint(month):
    """What the store holds for a month: {table_or_kind: count}. Used by the retention dry run."""
    out = {}
    if using_database():
        with connect() as c:
            for t in MONTH_TABLES:
                out["month_status" if t == "month" else t] = c.execute(
                    f"SELECT count(*) FROM {t} WHERE month = %s", (month,)).fetchone()[0]
            out["month_result"] = c.execute("SELECT count(*) FROM month_result WHERE month = %s",
                                            (month,)).fetchone()[0]
            out["kept_bytes"] = c.execute(
                """SELECT coalesce(sum(length(k.content)), 0) FROM kept_file k
                   WHERE k.sha256 IN (SELECT entry->>'sha256' FROM submission WHERE month = %s)
                     AND k.sha256 NOT IN (SELECT entry->>'sha256' FROM submission WHERE month <> %s)""",
                (month, month)).fetchone()[0]
        return out
    up = store_dir() / "uploads" / month
    out["submission"] = sum(len(register(month, f.name)) for f in up.iterdir() if f.is_dir()) if up.exists() else 0
    out["kept_bytes"] = sum(p.stat().st_size for p in up.rglob("*") if p.is_file() and p.name != "register.json") if up.exists() else 0
    out["month_result"] = sum(1 for k in ("mapped", "scored") if (store_dir() / k / f"{month}.json").exists())
    for name, key in (("events.jsonl", "event_log"), ("comments.jsonl", "comment"), ("acks.jsonl", "warning_ack")):
        p = _jsonl(name)
        out[key] = sum(1 for x in p.read_text().splitlines() if json.loads(x).get("month") == month) if p.exists() else 0
    out["month_status"] = 1 if (_jsonl("months.json").exists() and month in json.loads(_jsonl("months.json").read_text())) else 0
    return out


def remove_month(month):
    """Delete everything kept for one month (files, register, rows, results, comments, acknowledgements,
    activity and the lock record). A kept file is removed only when no other month uses it. All or nothing."""
    if using_database():
        with connect() as c, c.transaction():
            for t in MONTH_TABLES:
                c.execute(f"DELETE FROM {t} WHERE month = %s", (month,))
            c.execute("DELETE FROM month_result WHERE month = %s", (month,))
            c.execute("DELETE FROM kept_file WHERE sha256 NOT IN (SELECT entry->>'sha256' FROM submission "
                      "WHERE entry ? 'sha256')")
        return
    import shutil
    shutil.rmtree(store_dir() / "uploads" / month, ignore_errors=True)
    for k in ("mapped", "scored"):
        for ext in ("json", "run"):
            (store_dir() / k / f"{month}.{ext}").unlink(missing_ok=True)
    for name in ("events.jsonl", "comments.jsonl", "acks.jsonl"):
        p = _jsonl(name)
        if p.exists():
            keep = [x for x in p.read_text().splitlines() if json.loads(x).get("month") != month]
            p.write_text("".join(x + "\n" for x in keep))
    p = _jsonl("months.json")
    if p.exists():
        d = json.loads(p.read_text())
        if month in d:
            del d[month]
            p.write_text(json.dumps(d, indent=2))


def old_runs(grace_days):
    """Mapping and scoring runs that are not the newest of their month and are older than grace_days:
    [(kind, month, run_at)]. Without the database the folder only ever holds the newest run, so []."""
    if not using_database():
        return []
    with connect() as c:
        rows = c.execute(
            """SELECT r.kind, r.month, r.run_at FROM month_result r
               WHERE r.id < (SELECT max(id) FROM month_result n WHERE n.kind = r.kind AND n.month = r.month)
                 AND r.run_at < now() - make_interval(days => %s) ORDER BY r.month, r.kind, r.id""",
            (int(grace_days),)).fetchall()
    return [(k, m, t.isoformat()) for k, m, t in rows]


def remove_old_runs(grace_days):
    """Delete the runs old_runs() lists. Returns how many went."""
    if not using_database():
        return 0
    with connect() as c:
        return c.execute(
            """DELETE FROM month_result r
               WHERE r.id < (SELECT max(id) FROM month_result n WHERE n.kind = r.kind AND n.month = r.month)
                 AND r.run_at < now() - make_interval(days => %s)""", (int(grace_days),)).rowcount
