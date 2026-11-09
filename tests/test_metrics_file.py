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
    assert te01["limitations_table"] and te01["status"] == "Measured" and not te01.get("not_measured")
    un03 = tpl["dictionary"]["metrics"]["UN-03"]
    assert un03["not_measured"] and "UN-03" in measure.COMING_SOON
