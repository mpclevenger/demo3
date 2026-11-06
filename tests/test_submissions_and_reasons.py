"""Each input file is its own submission (feed id, own notes, own not-yet-mapped share); plain reasons for the Amber band."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from test_web import client, up, H  # noqa: E402,F401
from trust import score_month  # noqa: E402


def month_data(client):
    for feed, name in (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("tcc", "tcc_export.csv"),
                       ("postmortems", "postmortems_export.csv"), ("actions", "actions_export.csv")):
        up(client, feed, name)
    assert client.post("/api/update", json={"month": "2026-09", "by": "T"}, headers=H).status_code == 200
    return client.get("/data.json").json["periods"]["2026-09"]


def test_each_file_is_its_own_submission_with_its_own_notes_and_share(client):
    p = month_data(client)
    subs = {s["feed"]: s for s in p["submissions"]}
    assert subs["postmortems"]["id"] == "2026-09-postmortems" and subs["actions"]["id"] == "2026-09-actions"
    assert subs["postmortems"]["provider"] == subs["actions"]["provider"] == "Ops"
    pm = " ".join(w["detail"] for w in subs["postmortems"]["warnings"])
    ac = " ".join(w["detail"] for w in subs["actions"]["warnings"])
    assert "INC-D" in pm and "could not be placed" in pm and "could not be placed" not in ac     # the postmortem file's own note
    assert "Weird new" in ac and "Weird new" not in pm
    for s in p["submissions"]:                       # numbered within each file, from 1
        assert [w["rule"] for w in s["warnings"]] == [f"Mapping note {i}" for i in range(1, len(s["warnings"]) + 1)]
    assert subs["postmortems"]["metrics"] == ["UN-01"] and subs["actions"]["metrics"] == ["UN-02"]
    # not-yet-mapped share per file, from the same counts as the provider share
    assert subs["actions"]["unattributed_pct"] is not None and subs["postmortems"]["unattributed_pct"] is not None
    assert subs["hr"]["unattributed_pct"] is None            # no metric reads the HR file
    assert subs["tcc"]["unattributed_pct"] == p["unattributed_pct"]["Change"]


def test_firm_result_without_a_threshold_says_why(client):
    p = month_data(client)
    f = p["firm"]["UN-02"]
    assert f["status"] == "N/A" and "No tolerance threshold" in f["reason"]


def test_amber_band_reasons_are_plain():
    t = dict(green=2.0, red=4.0, band=2.0, basis="Calibrated", unit_word="points")
    assert score_month.status_of(1.0, t, False, "%")[1] == "At or below the prevailing median (Green tolerance: at most 2.0%)"
    assert score_month.status_of(3.0, t, False, "%")[1] == (
        "Above the prevailing median, within the Amber band of 2 points (Red limit: more than 4.0%)")
    assert score_month.status_of(5.0, t, False, "%")[1] == (
        "More than the Amber band of 2 points above the prevailing median (Red limit: more than 4.0%)")
    c = dict(green=0.5, red=2.0, band=1.5, basis="Calibrated", unit_word="incidents")
    assert score_month.status_of(0, c, False, "count")[1] == (
        "At or below the prevailing median (Green tolerance: at most 0.5 incidents)")
    assert score_month.status_of(1, c, False, "count")[1] == (
        "Above the prevailing median, within the Amber band of 1.5 incidents (Red limit: more than 2 incidents)")
    assert score_month.status_of(3, c, False, "count")[1] == (
        "More than the Amber band of 1.5 incidents above the prevailing median (Red limit: more than 2 incidents)")
    one = dict(green=1.0, red=2.0, band=1.0, basis="Calibrated", unit_word="incidents")
    assert "Amber band of 1 incident " in score_month.status_of(2, one, False, "count")[1]
