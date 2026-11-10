"""config/metrics.json, the one place a metric is defined (owner, 8 Nov 2026). These checks catch a typo after an edit."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import config, measure, score_month, store  # noqa: E402

STATUSES = {"Measured", "In progress", "Planned", "Coming soon"}
BLOCKS = {b["code"] for b in score_month.template()["blocks"]}


def test_every_metric_has_the_basics():
    for mid, x in config.metrics().items():
        assert x.get("name") and x.get("block") in BLOCKS, f"{mid}: needs a name and a known block"
        assert x.get("status") in STATUSES, f"{mid}: status must be one of {sorted(STATUSES)}"
        assert isinstance(x.get("card"), dict), f"{mid}: needs a card"
        for r in x.get("known_limits") or []:
            assert set(r) <= {"limit", "mitigation", "status"} and r.get("limit"), f"{mid}: a known limit needs 'limit'"


def test_measured_metrics_say_how_they_are_counted():
    for mid, x in config.metrics().items():
        c = x.get("counting") or {}
        if mid in measure.NEEDS:
            assert x["status"] == "Measured", f"{mid} is counted, so its status is Measured"
            assert all(f in store.FEEDS for f in c["files"]), f"{mid}: unknown file in counting.files"
            assert c.get("item_type") and c.get("items_name"), f"{mid}: counting needs item_type and items_name"
        for link in c.get("code") or []:
            assert (score_month.ROOT / "backend" / "trust" / link["file"]).exists(), f"{mid}: no such file {link['file']}"


def test_the_page_gets_every_metric_and_card():
    tpl = score_month.template()
    ids = list(config.metrics())
    assert [m["id"] for m in tpl["metrics"]] == ids and list(tpl["dictionary"]["metrics"]) == ids
    te01 = tpl["dictionary"]["metrics"]["TE-01"]
    assert te01["status"] == "Measured" and not te01.get("not_measured") and "limitations_table" in te01
    un03 = tpl["dictionary"]["metrics"]["UN-03"]
    assert un03["not_measured"] and "UN-03" in measure.COMING_SOON


def test_every_linked_risk_has_its_file():
    """card.risks names risk files in config/risks/ (owner, 9 Nov 2026)."""
    have = config.risks()
    for mid, x in config.metrics().items():
        for rid in x["card"].get("risks") or []:
            assert rid in have, f"{mid}: no risk file config/risks/{rid}.yaml"


def test_a_linked_risk_shows_its_name_and_description():
    card = score_month.dictionary_card({"card": {"risks": ["external-data-breach-tool-use", "not-there"]}}, config.risks())
    ok, gone = card["risks_detail"]
    assert ok["name"] == "External data breach based on tool use" and ok["domain"] == "Cyber"
    assert ok["category"] == "Unauthorized access" and ok["description"].startswith("Someone outside the firm")
    assert gone == {"id": "not-there", "missing": True}


def test_every_data_source_has_an_owner_entry():
    """config/data_sources.json (owner, 9 Nov 2026): one section per feed, with an owner (blank until named)."""
    from trust import store
    ds = config.data_sources()
    assert set(ds) == set(store.FEEDS), f"missing or unknown sources: {set(store.FEEDS) ^ set(ds)}"
    assert all("owner" in x for x in ds.values())


def test_a_domain_risk_file_holds_several_risks(tmp_path, monkeypatch):
    """Owner, 9 Nov 2026: risk files are named by domain (air.cyber.yaml) and hold several risks, linked by ID."""
    from trust import config
    (tmp_path / "air.cyber.yaml").write_text("air.cyber.01:\n  domain: Cyber\n  name: Breach\n"
                                             "'02':\n  domain: Cyber\n  name: Misuse\n")
    (tmp_path / "air.data.yaml").write_text("- id: air.data.07\n  name: Leak\n- name: Loss\n")
    (tmp_path / "old-one.yaml").write_text("domain: Change\nname: Single\n")
    monkeypatch.setenv("TRUST_RISKS", str(tmp_path))
    got = config.risks()
    assert {k: v["name"] for k, v in got.items()} == {"air.cyber.01": "Breach", "air.cyber.02": "Misuse",
                                                     "air.data.07": "Leak", "air.data.02": "Loss", "old-one": "Single"}
