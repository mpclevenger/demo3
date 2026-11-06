"""Calibrate: set tolerance thresholds once from pooled scored months, then freeze them."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import __main__ as cli, calibrate, score_month, storage  # noqa: E402

TPL = {"metrics": [{"id": "TE-02", "higher_is_better": False}, {"id": "UN-01", "higher_is_better": False},
                   {"id": "TE-01", "higher_is_better": True}]}


def cfg():
    return {"amber_band_min_points": 5, "amber_band_spread_multiple": 1.5, "metrics": {
        "TE-01": {"basis": "Policy", "green": 80.0, "red": 60.0},
        "TE-02": {"basis": "Prevailing median"},
        "UN-01": {"basis": "Prevailing median", "amber_band_min": 1, "_note": "keep me"}}}


def scored(month, te02, un01=None):
    """A small scored month: te02 / un01 are lists of (status, value), one per family."""
    fams = {}
    for i, (st, v) in enumerate(te02):
        fams[f"f{i}"] = {"metrics": {"TE-02": {"status": st, "value": v}}}
    for i, (st, v) in enumerate(un01 or []):
        fams.setdefault(f"f{i}", {"metrics": {}})["metrics"]["UN-01"] = {"status": st, "value": v}
    storage.save_month("scored", month, {"period": {"families": fams}})


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    return tmp_path


def row(rows, mid):
    return next(r for r in rows if r["metric"] == mid)


def test_pooled_result_matches_thresholds_for(tmp_store):
    scored("2026-07", [("Green", 2.0), ("Amber", 6.0), ("Red", 10.0)])
    scored("2026-08", [("Green", 4.0), ("Green", 8.0), ("Red", 20.0)])
    r = row(calibrate.calibrate(["2026-07", "2026-08"], cfg(), TPL), "TE-02")
    want = score_month.thresholds_for("TE-02", [2.0, 6.0, 10.0, 4.0, 8.0, 20.0], False, cfg())
    assert r["ok"] and r["values_used"] == 6
    assert (r["green"], r["red"], r["band"]) == (want["green"], want["red"], want["band"])


def test_count_only_metric_uses_incidents(tmp_store):
    scored("2026-07", [], [("Green", 0.0), ("Green", 1.0), ("Amber", 2.0), ("Red", 3.0), ("Red", 4.0)])
    r = row(calibrate.calibrate(["2026-07"], cfg(), TPL), "UN-01")
    want = score_month.thresholds_for("UN-01", [0.0, 1.0, 2.0, 3.0, 4.0], False, cfg(), unit_word="incidents")
    assert r["ok"] and (r["green"], r["red"], r["band"]) == (want["green"], want["red"], want["band"])


def test_fewer_than_five_values_is_not_ok(tmp_store):
    scored("2026-07", [("Green", 2.0), ("Green", 3.0), ("Red", 9.0), ("Amber", 5.0)])
    r = row(calibrate.calibrate(["2026-07"], cfg(), TPL), "TE-02")
    assert not r["ok"] and r["values_used"] == 4 and "at least 5" in r["why"] and r["green"] is None
    assert not any(x["metric"] == "TE-01" for x in calibrate.calibrate(["2026-07"], cfg(), TPL))   # policy metric: not listed


def test_unscored_month_is_refused(tmp_store):
    scored("2026-07", [("Green", 1.0)] * 5)
    with pytest.raises(ValueError, match="2026-08 hasn't been scored"):
        calibrate.calibrate(["2026-07", "2026-08"], cfg(), TPL)


def test_only_scored_statuses_are_used(tmp_store):
    others = [("Low confidence", 50.0), ("N/A", 60.0), ("DNR", None), ("Coming soon", None)]
    scored("2026-07", [("Green", 1.0), ("Green", 2.0), ("Amber", 3.0), ("Red", 4.0)] + others)
    r = row(calibrate.calibrate(["2026-07"], cfg(), TPL), "TE-02")
    assert r["values_used"] == 4 and not r["ok"]


def test_write_keeps_notes_and_other_metrics(tmp_store):
    scored("2026-07", [("Green", 2.0), ("Green", 4.0), ("Amber", 6.0), ("Red", 8.0), ("Red", 10.0)])
    rows = calibrate.calibrate(["2026-07"], cfg(), TPL)       # UN-01 has no values: not ok, left alone
    path = tmp_store / "t.json"
    doc = {"_how_to": ["note"], "caps": {"a": 1}, "metrics": {**cfg()["metrics"], "TE-02": {"basis": "Prevailing median", "_note": "n"}}}
    path.write_text(json.dumps(doc))
    calibrate.write(rows, ["2026-07", "2026-10"], "Pat", path)
    text = path.read_text()
    assert text.endswith("}\n")
    out = json.loads(text)
    assert out["_how_to"] == ["note"] and out["caps"] == {"a": 1}
    assert out["metrics"]["TE-01"] == doc["metrics"]["TE-01"]
    assert out["metrics"]["UN-01"] == doc["metrics"]["UN-01"]
    t = out["metrics"]["TE-02"]
    assert t["basis"] == "Policy" and t["_note"] == "n" and t["review"] == "quarterly" and t["set_by"] == "Pat"
    assert t["set_from"] == "prevailing median of 5 family results, July 2026–October 2026"
    assert t["set_on"] and (t["green"], t["red"]) == (row(rows, "TE-02")["green"], row(rows, "TE-02")["red"])


def test_scoring_uses_frozen_values_and_says_where_from(tmp_store):
    c = cfg()
    c["metrics"]["TE-02"].update({"basis": "Policy", "green": 6.0, "red": 11.0, "set_from": "prevailing median of 20 family results, July 2026–October 2026", "set_on": "2026-11-03"})
    t = score_month.thresholds_for("TE-02", [1.0, 2.0, 3.0], False, c)      # month's own values are ignored
    assert (t["green"], t["red"], t["basis"]) == (6.0, 11.0, "Policy")
    assert t["reason"].startswith("Set from the prevailing median of 20 family results")
    assert "(set 3 Nov 2026); reviewed quarterly" in t["reason"] and t["set_on"] == "2026-11-03"
    c["metrics"]["TE-02"].pop("set_from")
    assert score_month.thresholds_for("TE-02", [1.0], False, c)["reason"] == "Initial tolerance thresholds for go-live"


def test_command_line_table_and_write(tmp_store, monkeypatch, capsys):
    scored("2026-07", [("Green", 2.0), ("Green", 4.0), ("Amber", 6.0), ("Red", 8.0), ("Red", 10.0)])
    p = tmp_store / "th.json"
    p.write_text(json.dumps({"metrics": {"TE-02": {"basis": "Prevailing median"}}, "amber_band_min_points": 5,
                             "amber_band_spread_multiple": 1.5}))
    monkeypatch.setenv("TRUST_THRESHOLDS", str(p))
    monkeypatch.setattr(score_month, "template", lambda: TPL)
    assert cli.main(["calibrate", "2026-07"]) == 0
    out = capsys.readouterr().out
    assert "TE-02" in out and "Nothing was changed" in out and json.loads(p.read_text())["metrics"]["TE-02"]["basis"] == "Prevailing median"
    assert cli.main(["calibrate", "2026-07", "--write"]) == 1          # --by is needed
    assert cli.main(["calibrate", "2026-07", "--write", "--by", "Pat"]) == 0
    assert "deploy" in capsys.readouterr().out.lower()
    assert json.loads(p.read_text())["metrics"]["TE-02"]["basis"] == "Policy"


def test_quarterly_review_resets_a_fixed_metric_from_new_months(tmp_store):
    c = cfg()
    c["metrics"]["TE-02"].update({"basis": "Policy", "green": 99.0, "red": 99.9, "set_from": "prevailing median of 5 family results, July 2026", "set_on": "2026-08-01"})
    scored("2026-10", [("Green", 2.0), ("Green", 4.0), ("Amber", 6.0), ("Red", 8.0), ("Red", 10.0)])
    r = row(calibrate.calibrate(["2026-10"], c, TPL), "TE-02")          # listed again, worked out as a median
    want = score_month.thresholds_for("TE-02", [2.0, 4.0, 6.0, 8.0, 10.0], False, cfg())
    assert r["ok"] and (r["green"], r["red"]) == (want["green"], want["red"])
    assert all(x["metric"] != "TE-01" for x in calibrate.calibrate(["2026-10"], c, TPL))   # a real policy is never touched
