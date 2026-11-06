"""Set up or update the database tables from migrations/*.sql, in number order.

Applied migrations are append-only: each file's SHA-256 is recorded, and if an applied file has been
edited, nothing runs and the message names it. To change anything, add a new numbered file.
Runs on every deploy (the release line in the Procfile) and is safe to repeat.
"""
import hashlib
import pathlib

from . import storage

FOLDER = pathlib.Path(__file__).resolve().parents[2] / "migrations"


def run():
    if not storage.using_database():
        raise ValueError("no database: DATABASE_URL isn't set, so there is nothing to set up "
                         "(without it TRUST keeps everything in the store/ folder)")
    files = sorted(FOLDER.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    done = []
    with storage.connect() as c:
        enc = c.execute("SHOW server_encoding").fetchone()[0]
        enc = enc.decode() if isinstance(enc, bytes) else enc
        if enc.upper() not in ("UTF8", "UTF-8"):             # names and wording use characters beyond ASCII
            raise ValueError(f"the database uses the {enc} character set; TRUST needs UTF8. "
                             "Ask for the database to be created with UTF8.")
        c.execute("""CREATE TABLE IF NOT EXISTS schema_migration (
                         name text PRIMARY KEY, sha256 text NOT NULL,
                         applied_at timestamptz NOT NULL DEFAULT now())""")
        c.execute("COMMENT ON TABLE schema_migration IS 'Which migration files have run, with the hash of each.'")
        c.execute("SELECT pg_advisory_lock(7_301_2026)")          # two deploys at once can't both migrate
        try:
            applied = dict(c.execute("SELECT name, sha256 FROM schema_migration").fetchall())
            if not applied:
                # Tables already there but never built by this step (for example, SQL run by hand): stop plainly
                # rather than fail half-way on "already exists".
                there = [r[0] for r in c.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
                    "AND tablename = ANY(%s)", (["kept_file", "submission", "month_result"],)).fetchall()]
                if there:
                    raise ValueError(f"TRUST's tables are already in this database ({', '.join(sorted(there))}) but this "
                                     "step has no record of building them, so it would fail half-way. Start from an "
                                     "empty database, or ask for the tables to be removed, then deploy again.")
            shas = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
            changed = [n for n, s in applied.items() if n in shas and shas[n] != s]
            if changed:                                            # check them all before running anything
                raise ValueError(f"{', '.join(changed)} changed after it ran. Put it back as it was and "
                                 "add a new numbered file for the change.")
            for f in files:
                sha = shas[f.name]
                if f.name in applied:
                    continue
                with c.transaction():
                    c.execute(f.read_text(encoding="utf-8"))
                    c.execute("INSERT INTO schema_migration (name, sha256) VALUES (%s, %s)", (f.name, sha))
                done.append(f.name)
        finally:
            c.execute("SELECT pg_advisory_unlock(7_301_2026)")
    return done
