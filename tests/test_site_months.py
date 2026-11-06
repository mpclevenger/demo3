"""Which months the website lists, and which page it serves (owner, 4 Nov 2026).

- Before anything is published: the real site for the current month, with no data.
- A month with uploads appears in the month list before it is scored ("Not scored yet"), so it can be picked
  and updated from the site.
- The current month is always listed, so its files can be uploaded, even after other months are published.
- The page is always the one deployed now; a copy saved by an earlier publish is never served.
The files here are the made-up test fixtures (synthetic data stays in tests).
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from trust import mapping, publish, score_month, storage, store  # noqa: E402
from trust.intake.common import upload_time  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
NOW = upload_time().strftime("%Y-%m")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    from trust import web
    return web.app.test_client()


def data(client):
    return client.get("/data.json").get_json()


def test_nothing_published_shows_the_current_month(client):
    d = data(client)
    assert d["nothing_published"] is True and list(d["periods"]) == [NOW] and d["families"] == []
    assert d["periods"][NOW]["meta"]["not_scored"] is True


def test_a_month_with_uploads_is_listed_before_it_is_scored(client):
    store.upload("tcc", "2026-10", (FIX / "tcc_export.csv").read_bytes(), "tcc.csv", "Tester")
    d = data(client)
    assert sorted(d["periods"]) == sorted({"2026-10", NOW})
    assert d["periods"]["2026-10"]["meta"]["not_scored"] is True


def test_current_month_stays_after_another_month_is_published(client):
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("tcc", "tcc_export.csv")):
        store.upload(feed, "2026-10", (FIX / name).read_bytes(), name, "Tester")
    mapping.map_month("2026-10")
    score_month.run("2026-10")
    publish.run()
    d = data(client)
    assert "2026-10" in d["periods"] and NOW in d["periods"]                  # October scored, the current month too
    assert not d["periods"]["2026-10"]["meta"].get("not_scored")
    assert d["periods"][NOW]["meta"]["not_scored"] is True
    assert {f["id"] for f in d["families"]} >= {"payments", "cards"}          # families from the scored month
    assert "nothing_published" not in d


def test_the_page_is_always_the_one_deployed_now(client):
    store.upload("tcc", "2026-10", (FIX / "tcc_export.csv").read_bytes(), "tcc.csv", "Tester")
    mapping.map_month("2026-10")
    score_month.run("2026-10")
    publish.run()
    storage.save_published({"index.html": "<html>an old saved page</html>",
                            "data.json": storage.published("data.json"), "evidence.json": "{}"})
    r = client.get("/")
    assert r.status_code == 200 and b"an old saved page" not in r.data and b"<title>TRUST scorecard</title>" in r.data
    embedded = r.data.split(b'id="data">', 1)[1].split(b"</script>", 1)[0]
    assert "2026-10" in json.loads(embedded.decode())["periods"]
