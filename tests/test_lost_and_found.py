"""Lost and Found (owner, 9 Nov 2026): unplaced items listed with why, claimed by a family lead or Tech Risk,
approved by Tech Risk; an approved claim places the item from the next Update and carries over to later months;
it never overrides a source file; Tech Risk can release it."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_web import H, client, ready, up  # noqa: E402,F401
from trust import linking, lost  # noqa: E402


def feeds_with_one_lost_change():
    return {"tcc": {"rows": [
        dict(ticket_id="T1", deployed=True, family_id="payments", author_email="a@x"),
        dict(ticket_id="T2", deployed=True, family_id=linking.UNATTRIBUTED, author_email="contractor@x", author="Con Tractor"),
        dict(ticket_id="T3", deployed=False, family_id=linking.UNATTRIBUTED, author_email="z@x")]},
        "hr": {"people": [{"email": "a@x"}]}}


def test_only_unplaced_items_that_would_count_are_listed():
    its = lost.items({"feeds": feeds_with_one_lost_change()})
    assert [(i["feed"], i["item"]) for i in its] == [("tcc", "T2")]          # T3 isn't deployed, so it counts nowhere
    assert "isn't in the HR file" in its[0]["why"] and "Con Tractor" in its[0]["names"]


def test_an_approved_claim_places_the_item_but_never_overrides_a_file():
    feeds = feeds_with_one_lost_change()
    claims = [dict(id=1, feed="tcc", item="T2", family_id="cards", status="approved"),
              dict(id=2, feed="tcc", item="T1", family_id="cards", status="approved"),      # T1 is placed by HR
              dict(id=3, feed="tcc", item="T3", family_id="cards", status="draft")]
    used, note = lost.apply_claims(feeds, claims)
    rows = {r["ticket_id"]: r["family_id"] for r in feeds["tcc"]["rows"]}
    assert rows == {"T1": "payments", "T2": "cards", "T3": linking.UNATTRIBUTED} and used == [1]
    assert note.startswith("For information: Lost and Found: 1 item")
    assert lost.items({"feeds": feeds}) == []


def test_released_or_waiting_claims_do_nothing():
    for status in ("draft", "returned", "withdrawn", "released"):
        feeds = feeds_with_one_lost_change()
        assert lost.apply_claims(feeds, [dict(id=1, feed="tcc", item="T2", family_id="cards", status=status)]) == ([], None)


def test_claim_approve_update_and_release_through_the_site(client):
    ready(client)
    got = client.get("/api/lost/2026-09").json
    assert got["ok"] and got["mapped"] and "payments" in got["families"]
    item = {"feed": "tcc", "item": "LOST-1", "label": "Change LOST-1"}
    post = lambda path, **b: client.post(path, json={"by": "Pat", **b}, headers=H)
    assert "Say why" in post("/api/claims", month="2026-09", family="payments", **item).json["error"]
    assert "Choose the product family" in post("/api/claims", month="2026-09", family="nope", why="x", **item).json["error"]
    c = post("/api/claims", month="2026-09", family="payments", why="Our contractor", **item).json["claim"]
    assert c["status"] == "draft"
    assert "already has a claim" in post("/api/claims", month="2026-09", family="cards", why="ours", **item).json["error"]
    assert "Say why" in post(f"/api/claims/{c['id']}/decide", decision="returned").json["error"]
    ok = post(f"/api/claims/{c['id']}/decide", decision="approved").json["claim"]
    assert ok["status"] == "approved" and ok["decided_by"] == "Pat"
    assert "can't be approved" in post(f"/api/claims/{c['id']}/decide", decision="approved").json["error"]
    rel = post(f"/api/claims/{c['id']}/decide", decision="released", reason="HR fixed").json["claim"]
    assert rel["status"] == "released"
    # a released item can be claimed again
    assert post("/api/claims", month="2026-09", family="cards", why="ours now", **item).json["ok"]
    acts = [e for e in client.get("/api/month/2026-09").json.get("activity", []) if e.get("action") == "claim"]
    assert acts == [] or len(acts) >= 3
