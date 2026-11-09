"""The website's change endpoints: upload a file, then update (map, score, publish) a month."""
import io
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import web  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
H = {"X-TRUST": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    return web.app.test_client()


def up(client, feed, name, month="2026-09", by="Tester", headers=H):
    data = {"feed": feed, "month": month, "by": by, "file": (io.BytesIO((FIX / name).read_bytes()), name)}
    return client.post("/api/upload", data=data, headers=headers, content_type="multipart/form-data")


def test_upload_update_then_the_page_shows_it(client):
    r = up(client, "tcc", "tcc_export.csv")
    assert r.status_code == 200 and r.json["ok"] and "kept" in r.json["note"]
    assert up(client, "tcc", "tcc_export.csv").json["note"].startswith("already received")
    up(client, "hr", "hr_firmwide.csv")
    up(client, "hr_mapping", "family_owners.csv")
    st = client.get("/api/month/2026-09").json
    assert st["feeds"]["tcc"]["uploaded_by"] == "Tester" and st["feeds"]["tcc"]["uploads"] == 1
    r = client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H)
    assert r.status_code == 200 and "tcc" in r.json["received"]
    d = client.get("/data.json").json
    assert d["live"] is True and "2026-09" in d["periods"]


def test_changes_without_the_header_are_refused(client):
    assert up(client, "tcc", "tcc_export.csv", headers={}).status_code == 403
    assert client.post("/api/update", json={"month": "2026-09", "by": "T"}).status_code == 403


def test_plain_reasons_for_what_cant_be_done(client):
    assert "Type your name" in up(client, "tcc", "tcc_export.csv", by="  ").json["error"]
    assert "feed TRUST knows" in up(client, "nope", "tcc_export.csv").json["error"]
    assert "2026-10" in up(client, "tcc", "tcc_export.csv", month="Oct").json["error"]
    r = client.post("/api/upload", data={"feed": "tcc", "month": "2026-09", "by": "T"}, headers=H)
    assert "Choose a file" in r.json["error"]
    r = client.post("/api/update", json={"month": "2026-09", "by": "T"}, headers=H)
    assert r.status_code == 400 and "Nothing has been uploaded" in r.json["error"]


def ready(client, month="2026-09"):
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("tcc", "tcc_export.csv")):
        up(client, feed, name, month)
    assert client.post("/api/update", json={"month": month, "by": "Tester"}, headers=H).status_code == 200


def ack_all(client, month="2026-09"):
    keys = [w["key"] for w in client.get(f"/api/month/{month}").json["warnings"] if not w["ack"]]
    return client.post("/api/acknowledge", json={"month": month, "keys": keys, "by": "Rita", "reason": "read"}, headers=H)


def test_lock_needs_every_warning_acknowledged(client):
    ready(client)
    ws = client.get("/api/month/2026-09").json["warnings"]
    assert ws and all(w["ack"] is None for w in ws) and {"feed", "note", "key"} <= set(ws[0])
    r = client.post("/api/lock", json={"month": "2026-09", "by": "T"}, headers=H)
    assert r.status_code == 400 and "haven't been acknowledged" in r.json["error"]
    first = client.post("/api/acknowledge", json={"month": "2026-09", "keys": [ws[0]["key"]], "by": "Rita"}, headers=H)
    assert first.json["acknowledged"] == 1
    assert client.get("/api/month/2026-09").json["warnings"][0]["ack"]["by"] == "Rita"
    assert "Reload" in client.post("/api/acknowledge", json={"month": "2026-09", "keys": ["nope"], "by": "R"},
                                   headers=H).json["error"]
    assert ack_all(client).json["acknowledged"] == len(ws) - 1
    r = client.post("/api/lock", json={"month": "2026-09", "by": "T"}, headers=H)
    assert r.status_code == 200 and r.json["status"]["seal"]["warnings_acknowledged"] == len(ws)


def test_lock_seals_the_month_and_refuses_changes_until_reopened(client):
    ready(client)
    ack_all(client)
    r = client.post("/api/lock", json={"month": "2026-09", "by": "Head of TR"}, headers=H)
    assert r.status_code == 200 and r.json["status"]["status"] == "locked"
    seal = r.json["status"]["seal"]
    assert {f["feed"] for f in seal["files"]} == {"hr", "hr_mapping", "tcc"} and len(seal["scored_sha256"]) == 64
    meta = client.get("/data.json").json["periods"]["2026-09"]["meta"]
    assert meta["status"] == "Locked" and meta["locked_by"] == "Head of TR"
    assert "is locked" in up(client, "ntcc", "ntcc_export.csv").json["error"]
    assert "is locked" in client.post("/api/update", json={"month": "2026-09", "by": "T"}, headers=H).json["error"]
    assert "already locked" in client.post("/api/lock", json={"month": "2026-09", "by": "T"}, headers=H).json["error"]
    # a comment while locked is kept, marked received after lock
    c = client.post("/api/comments", json={"month": "2026-09", "family": "payments", "kind": "explanation",
                                           "text": "Late note", "by": "Lead"}, headers=H).json["comment"]
    assert c["after_lock"] is True
    # reopening needs a reason, then changes work again
    assert "Say why" in client.post("/api/reopen", json={"month": "2026-09", "by": "T"}, headers=H).json["error"]
    r = client.post("/api/reopen", json={"month": "2026-09", "by": "T", "reason": "Corrected TCC file"}, headers=H)
    assert r.json["status"]["status"] == "open"
    assert up(client, "ntcc", "ntcc_export.csv").status_code == 200
    acts = [e["action"] for e in client.get("/api/month/2026-09").json["events"]]
    assert acts[:3] == ["upload", "publish", "reopen"] and "lock" in acts and "comment" in acts


def test_lock_refuses_when_the_scorecard_is_behind_the_files(client):
    ready(client)
    up(client, "ntcc", "ntcc_export.csv")
    r = client.post("/api/lock", json={"month": "2026-09", "by": "T"}, headers=H)
    assert r.status_code == 400 and "Update the scorecard first" in r.json["error"]
    r = client.post("/api/lock", json={"month": "2026-08", "by": "T"}, headers=H)
    assert "hasn't been scored" in r.json["error"]


def test_comments_threads_and_checks(client):
    ready(client)
    post = lambda **kw: client.post("/api/comments", json={"month": "2026-09", "by": "Lead", **kw}, headers=H)
    q = post(family="payments", metric="TE-02", kind="query", text="Is the revert real?").json["comment"]
    assert q["status"] == "open" and q["after_lock"] is False
    a = post(family="payments", reply_to=q["id"], text="Yes, see CHG-1", status="closed").json["comment"]
    assert a["kind"] == "query" and a["metric"] == "TE-02" and a["status"] == "closed"
    e = post(family="payments", block="REL", kind="explanation", text="Two releases only").json["comment"]
    assert e["status"] is None
    assert "isn't on the scorecard" in post(family="nope", kind="explanation", text="x").json["error"]
    assert "isn't on the scorecard" in post(family="payments", metric="XX-99", kind="explanation", text="x").json["error"]
    assert "Write something" in post(family="payments", kind="explanation", text="  ").json["error"]
    assert "Choose explanation" in post(family="payments", kind="note", text="x").json["error"]
    assert [c["id"] for c in client.get("/api/comments/2026-09").json["comments"]] == [q["id"], a["id"], e["id"]]


def test_drill_down_and_csv_download(client):
    ready(client)
    for feed, name in (("actions", "actions_export.csv"), ("postmortems", "postmortems_export.csv"),
                       ("ntcc", "ntcc_export.csv")):                        # TE-01 needs both change files
        up(client, feed, name)
    client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H)
    ev = client.get("/evidence.json").json["2026-09"]
    te01 = ev["payments"]["TE-01"]
    assert te01["n_items"] == 3 and sum(t["den"] for t in te01["by_team"]) == 3            # 2 TCC + 1 Non-TCC
    it = te01["items"][0]
    assert it["item_type"] == "change" and it["tag"].startswith(("Through TCC", "Outside TCC")) and it["team_key"]
    assert all(t["team_key"] and t["team_name"] for f in ev.values() for e in f.values() for t in e["by_team"])
    un02 = next(e for f in ev.values() for m, e in f.items() if m == "UN-02")
    assert all(i["item_type"] == "action" for i in un02["items"])
    r = client.get("/api/items/2026-09/payments.csv")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    text = r.data.decode("utf-8-sig")
    assert "Metric,Metric name,Item,What it shows,Needs attention,Person,Team" in text and "TE-01" in text
    assert client.get("/api/items/2026-09/nope.csv").status_code == 404


def test_each_metric_has_its_data_table_and_downloads(client):
    """Owner, 9 Nov 2026: drill into the data on the page (a table per metric, its own key details, items that
    need attention first), download one table as a CSV, and download everything as Excel, one tab per metric."""
    import io
    from openpyxl import load_workbook
    ready(client)
    for feed, name in (("actions", "actions_export.csv"), ("postmortems", "postmortems_export.csv"),
                       ("ntcc", "ntcc_export.csv")):
        up(client, feed, name)
    client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H)
    ev = client.get("/evidence.json").json["2026-09"]
    t = ev["payments"]["TE-01"]["table"]
    assert t["columns"] == ["Change", "Route", "Created", "Deployed"] and t["types"][2] == "date"
    assert len(t["rows"]) == 3 and all(len(r["cells"]) == 4 for r in t["rows"])
    r0 = t["rows"][0]                                                         # owner, 9 Nov 2026: the minimum
    assert r0["who"] and r0["who"][0]["name"] and r0["who"][0]["sam"] and r0["who"][0]["email"]
    assert set(r0["who"][0]) >= {"l4", "l4_email", "l3", "l3_email"} and r0["as_of"] and r0["detail"]
    att = [r["attention"] for r in t["rows"]]
    assert att == sorted(att, reverse=True)                                   # needs attention first
    assert [r["cells"][1] for r in t["rows"] if r["attention"]] == ["Outside TCC (Non-TCC)"]
    r = client.get("/api/items/2026-09/payments/TE-01.csv")
    assert r.status_code == 200 and "trust-TE-01-payments-2026-09.csv" in r.headers["Content-Disposition"]
    lines = r.data.decode("utf-8-sig").splitlines()
    assert lines[1] == ("Needs attention,Change,Route,Created,Deployed,Detail,Name,ID (SAM account),Email,L4 manager,"
                        "L4 manager email,L3 manager,L3 manager email,Team,Product family,As of (file uploaded),Link")
    assert len(lines) == 5 and ",Payments," in lines[2]
    team = t["rows"][0]["team_key"]
    some = client.get(f"/api/items/2026-09/payments/TE-01.csv?team={team}").data.decode("utf-8-sig").splitlines()
    assert 2 < len(some) <= len(lines)
    assert client.get("/api/items/2026-09/payments/XX-99.csv").status_code == 404
    x = client.get("/api/items/2026-09/payments.xlsx")
    assert x.status_code == 200 and "spreadsheetml" in x.headers["Content-Type"]
    wb = load_workbook(io.BytesIO(x.data))
    assert wb.sheetnames[0] == "About" and "TE-01" in wb.sheetnames and "UN-02" in wb.sheetnames
    assert [c.value for c in wb["TE-01"][2]][:3] == ["Needs attention", "Change", "Route"]
    assert client.get("/api/items/2026-09/nope.xlsx").status_code == 404


def test_every_measured_metric_lists_columns_that_its_items_carry():
    """counting.columns in config/metrics.json name fields the measure step really puts on each item."""
    from trust import config, evidence
    for mid, m in config.metrics().items():
        cols = (m.get("counting") or {}).get("columns")
        if m.get("status") != "Measured":
            continue
        assert cols, f"{mid} has no counting.columns"
        for c in cols:
            assert c.get("label") and c.get("field"), (mid, c)
            assert c.get("as") in (None, "yes_no", "date", "list", "map", "of"), (mid, c)
        assert evidence.table(mid, [])["columns"] == [c["label"] for c in cols]


def test_csv_cells_that_excel_would_run_are_quoted():
    from trust import evidence
    rows = [{"metric": "TE-01", "metric_name": "x", "item": "=HYPERLINK(\"http://bad\")", "result": "-1", "needs_attention": True,
             "person": "@me", "team": "+t", "date_label": "", "date": "", "incident": "", "detail": "", "link": ""}]
    text = evidence.to_csv(rows, "2026-09", "Payments")
    assert "'=HYPERLINK" in text and ",'-1," in text and "'@me" in text and "'+t" in text and ",Yes," in text


def test_the_site_shows_the_deployed_definitions_not_the_saved_copy(client):
    """Owner, 8 Nov 2026: a definition changed in config/metrics.json shows once deployed, before any Update.
    Scores stay as published until the month is updated."""
    import json
    from trust import storage
    ready(client)
    saved = json.loads(storage.published("data.json"))
    old = saved["periods"]["2026-09"]["families"]["payments"]["metrics"]["TE-01"]
    saved["dictionary"]["metrics"]["TE-01"] = {"definition": "an old write-up"}          # as saved by an earlier version
    saved["metrics"] = [dict(m, name="Old name") if m["id"] == "TE-01" else m for m in saved["metrics"]]
    storage.save_published({"data.json": json.dumps(saved), "index.html": "", "evidence.json": "{}"})
    d = client.get("/data.json").json
    card = d["dictionary"]["metrics"]["TE-01"]
    assert "through TCC" in card["definition"] and card["wording"]["counts"]["verb_one"] == "went through TCC"
    assert next(m for m in d["metrics"] if m["id"] == "TE-01")["name"] == "Change ticket adoption"
    assert d["periods"]["2026-09"]["families"]["payments"]["metrics"]["TE-01"] == old     # results untouched
    assert "through TCC" in client.get("/").get_data(as_text=True)
