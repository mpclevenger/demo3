"""The database add-on: the same steps, with everything kept in Postgres instead of the store/ folder.

Starts its own throwaway Postgres (PG_BIN, default /usr/lib/postgresql/16/bin) on a local socket and
removes it afterwards. Skipped if the Postgres programs aren't installed.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import mapping, migrate, publish, score_month, storage, store  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
PG_BIN = pathlib.Path(os.environ.get("PG_BIN", "/usr/lib/postgresql/16/bin"))
pytestmark = pytest.mark.skipif(not (PG_BIN / "initdb").exists(), reason="Postgres programs not installed")


@pytest.fixture(scope="module")
def database():
    base = pathlib.Path(tempfile.mkdtemp(prefix="trust-pg-"))     # directly under /tmp, so postgres can reach it
    data, sock = base / "data", base / "sock"
    sock.mkdir()
    as_user = []
    if os.geteuid() == 0:                       # initdb won't run as root: use the postgres account
        shutil.chown(base, "postgres")
        shutil.chown(sock, "postgres")
        as_user = ["runuser", "-u", "postgres", "--"]
    run = lambda *a: subprocess.run([*as_user, *a], check=True, capture_output=True)
    run(str(PG_BIN / "initdb"), "-D", str(data), "-U", "trust", "--auth=trust", "-E", "UTF8")
    run(str(PG_BIN / "pg_ctl"), "-D", str(data), "-w", "-l", str(base / "log"),
        "-o", f"-k {sock} -c listen_addresses='' -p 8711", "start")
    try:
        yield f"postgresql://trust@/postgres?host={sock}&port=8711"
    finally:
        run(str(PG_BIN / "pg_ctl"), "-D", str(data), "-w", "-m", "immediate", "stop")
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def db(database, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))      # must stay empty
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    migrate.run()
    with storage.connect() as c:
        c.execute("TRUNCATE dr_test, itdr_application, kept_file, submission, month_result, published_file, month, event_log, comment, warning_ack, proposal_decision, proposal RESTART IDENTITY")
    yield tmp_path


def test_migrate_is_safe_to_repeat(db):
    assert migrate.run() == []


def test_an_edited_migration_stops_everything(db, monkeypatch, tmp_path):
    folder = tmp_path / "migrations"
    folder.mkdir()
    for f in migrate.FOLDER.glob("*.sql"):
        (folder / f.name).write_text(f.read_text() + "\n-- edited")
    monkeypatch.setattr(migrate, "FOLDER", folder)
    with pytest.raises(ValueError, match="changed after it ran"):
        migrate.run()


def test_upload_map_score_publish_all_in_the_database(db):
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("tcc", "tcc_export.csv"),
                       ("cx_sast", "final_checkmarx_sast_report.json")):
        e = store.upload(feed, "2026-09", (FIX / name).read_bytes(), name, "Tester")
        assert e["file"]
    again = store.upload("tcc", "2026-09", (FIX / "tcc_export.csv").read_bytes(), "tcc_export.csv", "Tester")
    assert again["note"].startswith("already received")
    mapping.map_month("2026-09")
    p = score_month.run("2026-09")["period"]
    assert p["families"]["payments"]["metrics"]["TE-01"]["status"] == "Green"
    assert publish.run() == "database"
    assert storage.months("scored") == ["2026-09"]
    assert '"env_label"' in storage.published("data.json")
    assert storage.published("index.html").startswith("<!")
    assert not (db / "store").exists()                         # nothing went to the app's disk
    # Only the columns TRUST uses were stored (the TCC Title column was dropped at upload)
    tcc_kept = storage.kept_file("2026-09", "tcc", storage.register("2026-09", "tcc")[-1])
    header = tcc_kept.decode().splitlines()[0].split(",")
    assert "Title" not in header and "Ticket ID" in header


def test_itdr_applications_are_a_table(db):
    from test_itdr import workbook
    wb = workbook()
    store.upload("itdr", "2026-10", wb, "itdr.xlsx", "Tester")
    assert store.upload("itdr", "2026-10", wb, "itdr.xlsx", "Tester")["note"].startswith("already received")
    apps = storage.itdr_applications("2026-10")
    assert len(apps) == 8 and apps[1]["application_name"] == "Card Authoriser" and apps[0]["recovery_tier"] == 0
    with storage.connect() as c:
        assert c.execute("SELECT count(*) FROM itdr_application").fetchone()[0] == 8
    assert not (db / "store").exists()


def test_dr_tests_are_a_table(db):
    from test_dr_tests import workbook
    store.upload("dr_tests", "2026-10", workbook(), "dr.xlsx", "Tester")
    t = storage.dr_tests("2026-10")
    assert len(t) == 5 and t[0]["test_date"] == "2026-03-14" and t[0]["performed_on"] == "2026-03-14"
    assert t[1]["status"] == "Not performed" and t[2]["kind"] == "Tabletop exercise" and t[2]["ttx_in_comment"] is True


def test_website(db):
    from trust import web
    client = web.app.test_client()
    r = client.get("/")
    assert r.status_code == 200 and b"<title>TRUST scorecard</title>" in r.data and b'"nothing_published": true' in r.data   # the real site, empty (owner, 4 Nov 2026)
    d = client.get("/data.json")
    assert d.status_code == 200 and d.get_json()["nothing_published"] is True and d.get_json()["families"] == []
    store.upload("cx_sca", "2026-10", (FIX / "final_checkmarx_sca_report 1.json").read_bytes(), "sca.json", "T")
    mapping.map_month("2026-10")
    score_month.run("2026-10")
    publish.run()
    r = client.get("/")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    assert client.get("/data.json").json["env_label"]
    ev = client.get("/evidence.json").json
    assert ev["2026-10"]["UNATTRIBUTED"]["SE-02"]["n_items"] == 3     # repos wait for the repo list
    assert client.get("/healthz").data == b"ok"
    assert client.get("/../config/settings.json").status_code == 404
    assert client.get("/store").status_code == 404


def test_lock_comments_events_and_run_history_in_the_database(db):
    from trust import lock
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("tcc", "tcc_export.csv")):
        store.upload(feed, "2026-09", (FIX / name).read_bytes(), name, "Tester")
    for _ in range(2):                                          # two runs: both kept, the newest is current
        mapping.map_month("2026-09", "Tester")
        score_month.run("2026-09", "Tester")
    publish.run("Tester")
    with storage.connect() as c:
        runs = c.execute("SELECT kind, count(*), min(by), bool_and(settings_sha256 IS NOT NULL) FROM month_result "
                         "GROUP BY kind ORDER BY kind").fetchall()
    assert runs == [("mapped", 2, "Tester", True), ("scored", 2, "Tester", True)]
    storage.add_comment({"month": "2026-09", "family": "payments", "metric": "TE-02", "block": None,
                         "kind": "query", "text": "Real revert?", "by": "Lead", "reply_to": None,
                         "status": "open", "after_lock": False})
    with pytest.raises(ValueError, match="acknowledged"):
        lock.lock("2026-09", "Head of TR")
    assert lock.acknowledge("2026-09", [w["key"] for w in lock.warnings("2026-09")], "Rita") > 0
    st = lock.lock("2026-09", "Head of TR")
    assert st["status"] == "locked" and st["seal"]["comments"] == 1
    with pytest.raises(ValueError, match="is locked"):
        store.upload("ntcc", "2026-09", (FIX / "ntcc_export.csv").read_bytes(), "ntcc.csv", "T")
    with pytest.raises(ValueError, match="is locked"):
        mapping.map_month("2026-09")
    import json
    assert json.loads(storage.published("data.json"))["periods"]["2026-09"]["meta"]["status"] == "Locked"
    lock.reopen("2026-09", "Head of TR", "Corrected file")
    acts = [e["action"] for e in storage.events("2026-09")]
    assert acts[:2] == ["publish", "reopen"] and acts.count("upload") == 3 and "lock" in acts
    assert storage.month_status("2026-09")["status"] == "open"


def test_proposals_in_the_database(db):
    p = storage.add_proposal({"kind": "retire", "metric": "TE-01", "title": "Retire it",
                              "detail": {"reason": "r", "effective": "2026-12"}, "by": "Rita"})
    storage.add_proposal({"kind": "new_metric", "metric": None, "title": "New", "detail": {"name": "n", "why": "w"},
                          "by": "Rita"})
    assert [x["title"] for x in storage.proposals()] == ["New", "Retire it"] and storage.proposals()[0]["status"] == "open"
    storage.add_decision({"proposal_id": p["id"], "decision": "returned", "reason": "more", "by": "Head"})
    got = storage.proposal(p["id"])
    assert got["status"] == "returned" and got["decisions"][0]["reason"] == "more" and got["detail"]["effective"] == "2026-12"
    storage.log("download", "Rita", "2026-09", "items for payments", {"rows": 3})
    assert storage.events("2026-09")[0]["action"] == "download"


def test_update_button_and_retention_on_the_database(db):
    """Found in review, 5 Nov 2026: the background update's log lines were refused by the event_log
    check on the database (migration 0010 admits them). Retention prunes old runs and removes expired months."""
    import datetime
    from trust import jobs, retention
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("tcc", "tcc_export.csv")):
        for month in ("2026-08", "2026-09"):
            store.upload(feed, month, (FIX / name).read_bytes(), name, "Tester")
    wait = jobs.WAIT
    jobs.WAIT = True
    try:
        job = jobs.start_update("2026-09", "Tester")
        assert jobs.status("2026-09", job)["state"] == "finished", jobs.status("2026-09", job)
        jobs.start_update("2026-09", "Tester")                      # a second run, so there is an old one
        jobs.start_update("2026-08", "Tester")
    finally:
        jobs.WAIT = wait
    assert "update finished" in {e["action"] for e in storage.events("2026-09", 50)}
    with storage.connect() as c:
        assert c.execute("SELECT count(*) FROM month_result WHERE month = '2026-09'").fetchone()[0] == 4
        c.execute("UPDATE month_result SET run_at = now() - interval '40 days' WHERE month = '2026-09' "
                  "AND id NOT IN (SELECT max(id) FROM month_result GROUP BY kind, month)")
    assert len(storage.old_runs(30)) == 2
    p = retention.run(write=True, today=datetime.date(2026, 10, 1), keep_months=2, out=lambda *_: None)
    assert [m["month"] for m in p["months"]] == ["2026-08"]
    with storage.connect() as c:
        assert c.execute("SELECT count(*) FROM month_result WHERE month = '2026-09'").fetchone()[0] == 2
        assert c.execute("SELECT count(*) FROM submission WHERE month = '2026-08'").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM kept_file k WHERE NOT EXISTS (SELECT 1 FROM submission s "
                         "WHERE s.entry->>'sha256' = k.sha256)").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM event_log WHERE action = 'retention'").fetchone()[0] == 1
    assert storage.months("scored") == ["2026-09"]


def test_update_lock_lives_with_the_process(db):
    """From review, 5 Nov 2026: a second worker can't start the same month while the lock is held, and a
    'started' line left by a restart counts as stopped at once (its lock went with the process)."""
    from trust import jobs
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("tcc", "tcc_export.csv")):
        store.upload(feed, "2026-09", (FIX / name).read_bytes(), name, "Tester")
    other = storage.connect()                                          # "another web worker" holds the lock
    assert other.execute("SELECT pg_try_advisory_lock(hashtext(%s))", ("trust-update:2026-09",)).fetchone()[0]
    with pytest.raises(ValueError, match="already being updated"):
        jobs.start_update("2026-09", "Tester")
    storage.log("update started", "Tester", "2026-09", "", {"job": "dangling"})   # as a restart would leave it
    assert jobs.status("2026-09", "dangling")["state"] == "running"               # the lock is still held
    other.close()                                                                  # the process died
    assert jobs.status("2026-09", "dangling")["state"] == "stopped"
    assert jobs.running("2026-09") is None
    wait = jobs.WAIT
    jobs.WAIT = True
    try:
        job = jobs.start_update("2026-09", "Tester")                               # free again at once
    finally:
        jobs.WAIT = wait
    assert jobs.status("2026-09", job)["state"] == "finished"
