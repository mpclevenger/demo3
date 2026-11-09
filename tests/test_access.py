"""Roles on TRUST's side (owner, 3 Nov 2026): the add-on passes the SAM_ACCOUNT and AD groups; TRUST checks
every page, file and change against docs/wiki/roles-and-permissions.md."""
import io
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import storage, web  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
CFG = {"user_header": "X-User", "groups_header": "X-Groups",
       "groups": {"cto_leadership": ["TRUST-Leaders"], "tech_risk": ["TRUST-TR"],
                  "head_of_tech_risk": ["TRUST-HoTR"], "auditor": ["TRUST-Audit"]},
       "family_lead_groups": {"cards": ["TRUST-Cards-Delegates"]}}


def who(sam, groups=""):
    return {"X-User": sam, "X-Groups": groups, "X-TRUST": "1"}


TR, HOTR, AUD, CTO = who("trisk", "TRUST-TR"), who("hotr", "TRUST-HoTR"), who("auditr", "TRUST-Audit"), who("boss", "TRUST-Leaders")
LEAD, MEMBER = who("CORP\\amoreno"), who("slee")          # owner of Payments; placed in Payments through HR


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    acc = tmp_path / "access.json"
    acc.write_text(json.dumps(CFG))
    monkeypatch.setenv("TRUST_ACCESS", str(acc))
    c = web.app.test_client()
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("tcc", "tcc_export.csv"),
                       ("postmortems", "postmortems_export.csv"), ("actions", "actions_export.csv")):
        data = {"feed": feed, "month": "2026-09", "file": (io.BytesIO((FIX / name).read_bytes()), name)}
        assert c.post("/api/upload", data=data, headers=TR, content_type="multipart/form-data").status_code == 200
    assert c.post("/api/update", json={"month": "2026-09"}, headers=TR).status_code == 200
    return c


def test_no_role_no_entry(client):
    assert client.get("/").status_code == 403
    assert client.get("/", headers=who("stranger")).status_code == 403
    assert "access to TRUST" in client.get("/data.json", headers=who("stranger")).get_data(as_text=True)
    assert client.get("/healthz").status_code == 200


def test_tech_risk_runs_the_month_and_is_recorded_by_account(client):
    st = client.get("/api/month/2026-09", headers=TR).json
    assert st["feeds"]["tcc"]["uploaded_by"] == "trisk"          # not a typed name
    assert client.post("/api/lock", json={"month": "2026-09"}, headers=MEMBER).status_code == 403


def test_auditor_reads_and_downloads_but_cannot_change(client):
    assert client.get("/api/month/2026-09", headers=AUD).status_code == 200
    assert client.post("/api/update", json={"month": "2026-09"}, headers=AUD).status_code == 403
    # owner, 9 Nov 2026: whoever is logged in can drill into the data and export it
    assert client.get("/api/items/2026-09/payments.csv", headers=AUD).status_code != 403
    me = client.get("/data.json", headers=AUD).json["access"]["me"]
    assert me["read_only"] and me["page_role"] == "tr"


def test_cto_sees_and_exports_every_family_but_no_console(client):
    d = client.get("/data.json", headers=CTO).json
    assert all("reason" in r for f in d["periods"]["2026-09"]["families"].values() for r in f["metrics"].values())
    assert client.get("/api/month/2026-09", headers=CTO).status_code == 403
    assert client.get("/api/items/2026-09/payments.csv", headers=CTO).status_code != 403        # owner, 9 Nov 2026
    assert d["access"]["me"]["page_role"] == "cto"


def test_family_lead_gets_their_family_only(client):
    d = client.get("/data.json", headers=LEAD).json
    fams = d["periods"]["2026-09"]["families"]
    assert "reason" in fams["payments"]["metrics"]["TE-01"]                    # own family in full
    assert set(fams["cards"]["metrics"]["TE-01"]) <= {"status", "points", "override", "behind_peers", "history", "delta", "provisional"}
    assert d["periods"]["2026-09"]["submissions"] == []
    assert d["access"]["me"]["lead_of"] == ["payments"] and d["access"]["me"]["page_role"] == "fl:payments"
    ev = client.get("/evidence.json", headers=LEAD).json
    assert set(ev["2026-09"]) <= {"payments"}
    assert storage.events(None, 5)[0]["action"] == "view"
    assert client.get("/api/items/2026-09/payments.csv", headers=LEAD).status_code == 200
    assert client.get("/api/items/2026-09/cards.csv", headers=LEAD).status_code == 403
    ok = client.post("/api/comments", json={"month": "2026-09", "family": "payments", "kind": "explanation", "text": "Why"}, headers=LEAD)
    assert ok.status_code == 200 and ok.json["comment"]["by"] == "Alex Moreno (amoreno)"
    no = client.post("/api/comments", json={"month": "2026-09", "family": "cards", "kind": "explanation", "text": "x"}, headers=LEAD)
    assert no.status_code == 403
    # the page itself carries the cut-down data and who they are
    html = client.get("/", headers=LEAD).get_data(as_text=True)
    assert '"page_role": "fl:payments"' in html


def test_family_member_comments_and_downloads_own_family_but_cannot_reply(client):
    q = client.post("/api/comments", json={"month": "2026-09", "family": "payments", "kind": "query", "text": "Is this right?"}, headers=TR).json["comment"]
    assert client.post("/api/comments", json={"month": "2026-09", "family": "payments", "kind": "explanation", "text": "Context"}, headers=MEMBER).status_code == 200
    assert client.get("/api/items/2026-09/payments.csv", headers=MEMBER).status_code != 403     # own family (owner, 9 Nov 2026)
    assert client.get("/api/items/2026-09/cards.csv", headers=MEMBER).status_code == 403          # not another family's
    assert client.post("/api/comments", json={"month": "2026-09", "family": "payments", "reply_to": q["id"], "text": "Yes"}, headers=MEMBER).status_code == 403
    # the lead replies but can't close; Tech Risk can
    assert client.post("/api/comments", json={"month": "2026-09", "family": "payments", "reply_to": q["id"], "text": "Yes", "status": "closed"}, headers=LEAD).status_code == 403
    assert client.post("/api/comments", json={"month": "2026-09", "family": "payments", "reply_to": q["id"], "text": "Yes"}, headers=LEAD).status_code == 200
    seen = client.get("/api/comments/2026-09", headers=MEMBER).json["comments"]
    assert {c["family"] for c in seen} == {"payments"}


def test_proposals_tech_risk_proposes_head_of_tech_risk_decides(client):
    body = {"kind": "change", "metric": "TE-01", "title": "TE-01 wording", "detail": {"field": "Population", "wording": "w", "reason": "r"}}
    assert client.post("/api/proposals", json=body, headers=LEAD).status_code == 403
    pid = client.post("/api/proposals", json=body, headers=TR).json["proposal"]["id"]
    assert client.post(f"/api/proposals/{pid}/decide", json={"decision": "approved"}, headers=TR).status_code == 403
    r = client.post(f"/api/proposals/{pid}/decide", json={"decision": "approved"}, headers=HOTR)
    assert r.status_code == 200 and r.json["proposal"]["decisions"][0]["by"] == "hotr"
    assert client.get("/api/proposals", headers=AUD).status_code == 200
    assert client.get("/api/proposals", headers=CTO).status_code == 403


def test_groups_as_distinguished_names_and_delegates(client):
    dn = who("someone", "CN=TRUST-Audit,OU=Groups,DC=corp,DC=example,CN=Other,OU=Groups,DC=corp")
    assert client.get("/data.json", headers=dn).json["access"]["me"]["roles"] == ["auditor"]
    dele = who("helper", "trust-cards-delegates")                                # any capitals
    assert client.get("/data.json", headers=dele).json["access"]["me"]["lead_of"] == ["cards"]
    assert client.get("/api/items/2026-09/cards.csv", headers=dele).status_code in (200, 404)
