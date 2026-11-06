"""Data contracts (owner, 4 Nov 2026): requested from the Data dictionary, approved by Tech Risk (formal = approved);
then TRUST may only use the file for the contracted metrics, and a changed layout is flagged at upload."""
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


def up(client, feed, name, month="2026-09"):
    data = {"feed": feed, "month": month, "by": "Tester", "file": (io.BytesIO((FIX / name).read_bytes()), name)}
    return client.post("/api/upload", data=data, headers=H, content_type="multipart/form-data")


def ask(client, **kw):
    body = {"by": "Pat (Change)", "feed": "tcc", "provider": "Change", "what": "The monthly TCC export",
            "columns": "RPD ID, Status, Created date (UTC), Actual Last Deployment, Overall Change Approval, Overall outcome",
            "metrics": ["TE-01", "TE-02"]}
    body.update(kw)
    return client.post("/api/contracts", json=body, headers=H)


def decide(client, cid, decision, by="Tech Risk", reason=""):
    return client.post(f"/api/contracts/{cid}/decide", json={"by": by, "decision": decision, "reason": reason}, headers=H)


def test_request_then_approve_is_formal(client):
    r = ask(client)
    assert r.status_code == 200 and r.json["contract"]["status"] == "draft" and r.json["contract"]["version"] == 1
    cid = r.json["contract"]["id"]
    assert "already waiting" in ask(client).json["error"]                  # one open request per file
    assert "Say why" in decide(client, cid, "returned").json["error"]
    c = decide(client, cid, "approved").json["contract"]
    assert c["status"] == "approved" and c["decided_by"] == "Tech Risk" and c["decided_at"]
    assert "already approved" in decide(client, cid, "returned", reason="x").json["error"]
    # a new version is version 2, and the list shows both
    v2 = ask(client, metrics=["TE-01", "TE-02", "TE-03"]).json["contract"]
    assert v2["version"] == 2 and v2["status"] == "draft"
    assert [c["version"] for c in client.get("/api/contracts").json["contracts"]] == [1, 2]
    # the person who asked may withdraw their own request
    assert decide(client, v2["id"], "withdrawn", by="Pat (Change)").json["contract"]["status"] == "withdrawn"


def test_request_checks(client):
    assert "which file" in ask(client, feed="nope").json["error"]
    assert "Not a metric" in ask(client, metrics=["ZZ-99"]).json["error"]
    assert "columns" in ask(client, columns="").json["error"]
    assert "at least one" in ask(client, metrics=[]).json["error"]


def test_contracted_metrics_only_and_layout_check(client):
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv")):
        up(client, feed, name)
    cols = up(client, "tcc", "tcc_export.csv", month="2026-08").json["kept"]["columns_kept"]   # the file's own names
    cid = ask(client, metrics=["TE-01"], columns=cols).json["contract"]["id"]                  # TE-02 not in the contract
    decide(client, cid, "approved")
    r = up(client, "tcc", "tcc_export.csv")
    assert r.status_code == 200
    assert not [w for w in r.json["checks"]["warnings"] if "data contract" in w]              # same layout: no warning
    assert client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H).status_code == 200
    d = client.get("/data.json").json
    te2 = d["periods"]["2026-09"]["families"]["payments"]["metrics"]["TE-02"]
    assert te2["status"] == "DNR" and "data contract" in te2["reason"] and "TE-02" in te2["reason"]
    assert d["periods"]["2026-09"]["families"]["payments"]["metrics"]["TE-01"]["status"] == "Green"
    # version 2 with a column the file doesn't have: the next upload is flagged (acknowledged before the lock)
    v2 = ask(client, metrics=["TE-01", "TE-02"], columns=cols[:-2] + ["Made Up Column"]).json["contract"]
    decide(client, v2["id"], "approved")
    r = up(client, "tcc", "tcc_export.csv", month="2026-10")
    w = [w for w in r.json["checks"]["warnings"] if "data contract" in w]
    assert len(w) == 2 and "Made Up Column" in w[0] and "version 2" in w[0]
    assert "doesn't name" in w[1]                                           # columns TRUST reads beyond the contract
