"""Dictionary proposals and decisions, and the log of item downloads."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_web import H, client, ready, up  # noqa: E402,F401  (the same file-store set-up as the web tests)


@pytest.fixture
def pub(client):
    ready(client)                                   # publishes data, so the metric ids exist
    return client


def propose(c, **kw):
    body = {"by": "Rita", "kind": "change", "metric": "TE-01", "title": "Clearer wording",
            "detail": {"field": "definition", "wording": "New words", "reason": "Easier to read"}, **kw}
    return c.post("/api/proposals", json=body, headers=H)


def decide(c, pid, **kw):
    return c.post(f"/api/proposals/{pid}/decide", json={"by": "Head", **kw}, headers=H)


def test_create_each_kind(pub):
    a = propose(pub).json["proposal"]
    assert a["status"] == "open" and a["decisions"] == [] and a["id"] and a["at"]
    b = propose(pub, kind="retire", metric="TE-02", title="Stop",
                detail={"reason": "Not useful", "effective": "2026-12"}).json["proposal"]
    c = propose(pub, kind="new_metric", metric=None, title="Pager load",
                detail={"name": "Pager load", "why": "Shows strain", "extra": 1}).json["proposal"]
    assert (a["kind"], b["kind"], c["kind"]) == ("change", "retire", "new_metric") and c["metric"] is None
    acts = [e["action"] for e in pub.get("/api/month/2026-09").json["events"]]
    assert acts.count("proposal") == 3
    ev = [e for e in pub.get("/api/month/2026-09").json["events"] if e["action"] == "proposal"][-1]
    assert ev["note"] == "change proposed: Clearer wording" and ev["detail"]["proposal_id"] == a["id"]


def test_refusals(pub):
    err = lambda r: (r.status_code, r.json["error"])
    assert "Choose change" in err(propose(pub, kind="other"))[1]
    assert "isn't on the scorecard" in err(propose(pub, metric="XX-99"))[1]
    assert "isn't on the scorecard" in err(propose(pub, metric=None))[1]
    assert "leave the metric empty" in err(propose(pub, kind="new_metric", metric="TE-01",
                                                   detail={"name": "n", "why": "w"}))[1]
    assert "title" in err(propose(pub, title="  "))[1]
    assert "200" in err(propose(pub, title="x" * 201))[1]
    assert "details are missing" in err(propose(pub, detail="text"))[1]
    assert "'wording'" in err(propose(pub, detail={"field": "f", "reason": "r"}))[1]
    assert "'name'" in err(propose(pub, kind="new_metric", metric=None, detail={"name": " ", "why": "w"}))[1]
    assert "20,000" in err(propose(pub, detail={"field": "f", "wording": "w", "reason": "x" * 20001}))[1]
    bad = propose(pub, kind="retire", detail={"reason": "r", "effective": "2026-13"})
    assert "2026-10" in err(bad)[1]
    assert "Type your name" in err(propose(pub, by=" "))[1]
    assert pub.get("/api/proposals").json["proposals"] == []


def test_list_newest_first_and_decisions(pub):
    first = propose(pub, title="First").json["proposal"]
    second = propose(pub, title="Second").json["proposal"]
    got = pub.get("/api/proposals").json
    assert got["ok"] and [p["title"] for p in got["proposals"]] == ["Second", "First"]
    assert {p["status"] for p in got["proposals"]} == {"open"}
    r = decide(pub, first["id"], decision="approved")
    p = r.json["proposal"]
    assert r.json["ok"] and p["status"] == "approved" and p["decisions"][0]["by"] == "Head"
    assert pub.get("/api/proposals").json["proposals"][1]["status"] == "approved"
    assert [p["status"] for p in pub.get("/api/proposals").json["proposals"]] == ["open", "approved"]
    assert "decision" in [e["action"] for e in pub.get("/api/month/2026-09").json["events"]]
    assert second["id"] != first["id"]


def test_deciding_rules(pub):
    pid = propose(pub).json["proposal"]["id"]
    assert "Choose approved" in decide(pub, pid, decision="maybe").json["error"]
    assert "Say why" in decide(pub, pid, decision="returned", reason=" ").json["error"]
    assert "Say why" in decide(pub, pid, decision="declined").json["error"]
    assert "2,000" in decide(pub, pid, decision="declined", reason="x" * 2001).json["error"]
    assert "no such proposal" in decide(pub, 99, decision="approved").json["error"]
    assert decide(pub, pid, decision="returned", reason="Add an example").json["proposal"]["status"] == "returned"
    r = decide(pub, pid, decision="approved")
    assert r.status_code == 400 and r.json["error"] == "This proposal was already returned."
    assert len(pub.get("/api/proposals").json["proposals"][0]["decisions"]) == 1


def test_withdraw(pub):
    pid = propose(pub).json["proposal"]["id"]
    p = decide(pub, pid, decision="withdrawn").json["proposal"]
    assert p["status"] == "withdrawn" and p["decisions"][0]["reason"] == ""
    assert "already withdrawn" in decide(pub, pid, decision="declined", reason="no").json["error"]


def test_header_required(pub):
    assert pub.post("/api/proposals", json={"by": "R"}).status_code == 403
    assert pub.post("/api/proposals/1/decide", json={"by": "R", "decision": "approved"}).status_code == 403


def test_download_is_logged_with_the_name(pub):
    r = pub.get("/api/items/2026-09/payments.csv?by=Rita%20Jones")
    assert r.status_code == 200
    r = pub.get("/api/items/2026-09/payments.csv")
    ev = [e for e in pub.get("/api/month/2026-09").json["events"] if e["action"] == "download"]
    assert [e["by"] for e in ev] == ["name not given", "Rita Jones"]
    assert ev[1]["note"] == "items for payments" and ev[1]["month"] == "2026-09"
    assert ev[1]["detail"]["family"] == "payments" and isinstance(ev[1]["detail"]["rows"], int)
    pub.get("/api/items/2026-09/nope.csv?by=X")
    assert len([e for e in pub.get("/api/month/2026-09").json["events"] if e["action"] == "download"]) == 2
