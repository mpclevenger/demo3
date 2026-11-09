"""Watch-list items and the behind-peers flag (owner, 3 Nov 2026). Cases follow docs/reference/old-demo."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import publish, score_month, scoring  # noqa: E402


def res(status, value=None, **kw):
    return dict(status=status, value=value, provisional=False, override=False, behind_peers=False,
                typical=0.0, history=[status], **kw)


def fam(metrics, trust=None, delta=None, blocks=None, blocks_scored=5):
    return dict(trust=trust, delta=delta, metrics=metrics, declining=[], blocks_scored=blocks_scored,
                blocks=blocks or {c: dict(score=None, delta=None) for c in scoring.BLOCKS})


# ---------- prior month = the calendar month before, only if scored ----------

def test_prior_is_the_calendar_month_before():
    assert publish._prev("2026-09", ["2026-08", "2026-09"]) == "2026-08"
    assert publish._prev("2026-01", ["2025-12", "2026-01"]) == "2025-12"
    assert publish._prev("2026-09", ["2026-07", "2026-09"]) is None      # August not scored: no comparison


# ---------- behind peers ----------

TPL = {"metrics": [dict(id="TE-02", higher_is_better=False), dict(id="TE-01", higher_is_better=True),
                   dict(id="UN-01", higher_is_better=False), dict(id="SE-04", higher_is_better=True)],
       "dictionary": {"metrics": {"TE-02": dict(peer_flag_gap=15.0), "TE-01": dict(peer_flag_gap=15.0),
                                  "UN-01": dict(peer_flag_gap=1.0), "SE-04": dict(peer_flag_gap=None)}}}


POLICY = {"TE-02": {"basis": "Policy"}, "TE-01": {"basis": "Policy"}, "UN-01": {"basis": "Policy"},
          "SE-04": {"basis": "Policy"}}


def families_with(mid, values, status="Amber"):
    return {f"f{i}": {mid: res(status, v)} for i, v in enumerate(values)}


def test_typical_is_the_median_and_the_flag_needs_the_gap():
    r = families_with("TE-02", [1.0, 2.0, 3.0, 4.0, 20.0])
    score_month.flag_behind_peers(r, TPL, POLICY, flag_on=True)
    assert [r[f]["TE-02"]["typical"] for f in r] == [3.0] * 5
    assert [r[f]["TE-02"]["behind_peers"] for f in r] == [False, False, False, False, True]   # 20 - 3 >= 15
    assert r["f4"]["TE-02"]["status"] == "Amber"                                              # never changes status


def test_higher_is_better_flags_the_low_side():
    r = families_with("TE-01", [95.0, 94.0, 90.0, 88.0, 70.0])
    score_month.flag_behind_peers(r, TPL, POLICY, flag_on=True)
    assert [r[f]["TE-01"]["behind_peers"] for f in r] == [False, False, False, False, True]   # 90 - 70 >= 15


def test_no_flag_with_fewer_than_five_families_but_typical_still_shown():
    r = families_with("TE-02", [1.0, 2.0, 3.0, 30.0])
    score_month.flag_behind_peers(r, TPL, POLICY, flag_on=True)
    assert not any(r[f]["TE-02"]["behind_peers"] for f in r)
    assert r["f0"]["TE-02"]["typical"] == 2.5


def test_typical_ignores_unscored_and_reused_results():
    r = families_with("TE-02", [1.0, 2.0, 3.0, 4.0, 5.0])
    r["f5"] = {"TE-02": res("Low confidence", 90.0)}
    r["f6"] = {"TE-02": dict(res("Red", 90.0), provisional=True)}
    score_month.flag_behind_peers(r, TPL, POLICY, flag_on=True)
    assert r["f0"]["TE-02"]["typical"] == 3.0
    assert not r["f5"]["TE-02"]["behind_peers"] and not r["f6"]["TE-02"]["behind_peers"]


def test_no_flag_for_plain_counts_or_metrics_without_a_gap():
    r = families_with("UN-01", [0.0, 0.0, 0.0, 1.0, 9.0])
    r2 = families_with("SE-04", [100.0, 100.0, 100.0, 100.0, 10.0])
    score_month.flag_behind_peers(r, TPL, POLICY, flag_on=True)
    score_month.flag_behind_peers(r2, TPL, POLICY)
    assert not any(x["UN-01"]["behind_peers"] for x in r.values())
    assert not any(x["SE-04"]["behind_peers"] for x in r2.values())


# ---------- watch-list items ----------

def kinds(items):
    return [(i["kind"], i["metric_id"]) for i in items]


def test_new_red_and_chronic_red():
    now = fam({"A": dict(res("Red", 9.0), history=["Green", "Red"]),
               "B": dict(res("Red", 9.0), history=["Red", "Red", "Red"]),
               "C": dict(res("Red", 9.0), history=["Amber", "Red", "Red"])})
    before = fam({"A": res("Green"), "B": res("Red"), "C": res("Red")})
    out = publish._watch("f", "Fam", now, before, None)
    assert kinds(out) == [("New red", "A"), ("Chronic red", "B")]   # C: Red two months only, neither
    assert out[0]["text"] == "Fam: A turned Red"


def test_no_new_red_without_the_month_before():
    out = publish._watch("f", "Fam", fam({"A": res("Red", 9.0)}), None, None)
    assert out == []


def test_override_red_comes_first_and_isnt_also_new_red():
    now = fam({"A": dict(res("Red", 9.0), override=True, history=["Green", "Red"])})
    out = publish._watch("f", "Fam", now, fam({"A": res("Green")}), None)
    assert kinds(out) == [("Override red", "A")]


def test_sharp_drop_needs_ten_points_and_two_worse_metrics():
    before = fam({"A": res("Green"), "B": res("Green"), "C": res("Green")})
    one_worse = fam({"A": res("Red"), "B": res("Green"), "C": res("Green")}, trust=80, delta=-10)
    two_worse = fam({"A": res("Amber"), "B": res("Amber"), "C": res("Green")}, trust=80, delta=-10)
    small = fam({"A": res("Amber"), "B": res("Amber"), "C": res("Green")}, trust=91, delta=-9)
    assert "Sharp drop" not in [k for k, _ in kinds(publish._watch("f", "Fam", one_worse, before, None))]
    assert ("Sharp drop", None) in kinds(publish._watch("f", "Fam", two_worse, before, None))
    assert "Sharp drop" not in [k for k, _ in kinds(publish._watch("f", "Fam", small, before, None))]
    assert publish._watch("f", "Fam", two_worse, before, None)[-1]["text"] == "Fam: TRUST fell 10 points"


def test_declining_needs_two_falls_in_a_row():
    L = lambda **d: {c: dict(score=50, delta=d.get(c)) for c in scoring.BLOCKS}
    now = fam({}, blocks=L(ACC=-10, SEC=-5, REL=5))
    before = fam({}, blocks=L(ACC=-17, SEC=0, REL=-5))
    out = publish._watch("f", "Fam", now, before, fam({}))
    assert kinds(out) == [("Declining", None)] and now["declining"] == ["ACC"]
    assert publish._watch("f", "Fam", fam({}, blocks=L(ACC=-10)), before, None) == []   # needs two earlier months


def test_no_trend_flags_for_scores_on_fewer_than_3_blocks():
    """Owner, 4 Nov 2026: a TRUST score resting on 1-2 blocks gets no Sharp drop or Declining."""
    before = fam({"A": res("Green"), "B": res("Green")})
    drop = fam({"A": res("Amber"), "B": res("Amber")}, trust=50, delta=-50, blocks_scored=2)
    assert publish._watch("f", "Fam", drop, before, None) == []
    assert publish._watch("f", "Fam", dict(drop, blocks_scored=3), dict(before, blocks_scored=2), None) == []
    L = lambda **d: {c: dict(score=50, delta=d.get(c)) for c in scoring.BLOCKS}
    now, prior = fam({}, blocks=L(ACC=-10)), fam({}, blocks=L(ACC=-17))
    assert publish._watch("f", "Fam", now, prior, fam({}, blocks_scored=1)) == []
    # A month saved without the count: it is worked out from the blocks
    assert publish._blocks_scored({"blocks": L()}) == len(scoring.BLOCKS)


def test_behind_peers_listed_unless_already_red_on_the_list():
    now = fam({"A": dict(res("Amber", 20.0), behind_peers=True, typical=3.0),
               "B": dict(res("Red", 30.0), behind_peers=True, typical=3.0, history=["Green", "Red"])})
    out = publish._watch("f", "Fam", now, fam({"A": res("Amber"), "B": res("Green")}), None)
    assert kinds(out) == [("New red", "B"), ("Behind peers", "A")]
    assert out[1]["text"] == "Fam: A 20.0 vs typical 3.0"


def test_no_flag_where_the_prevailing_median_sets_the_threshold():
    r = families_with("TE-02", [1.0, 2.0, 3.0, 4.0, 20.0])
    score_month.flag_behind_peers(r, TPL, {"TE-02": {"basis": "Calibrated"}})
    assert not any(x["TE-02"]["behind_peers"] for x in r.values())
    assert r["f0"]["TE-02"]["typical"] == 3.0                                  # typical still shown


def test_the_flag_is_off_by_setting():
    """Owner, 8 Nov 2026: behind_peers_flag is false in config/thresholds.json, so nobody is flagged; typical still shows."""
    r = families_with("TE-01", [95.0, 94.0, 90.0, 88.0, 70.0])
    score_month.flag_behind_peers(r, TPL, POLICY)
    assert not any(r[f]["TE-01"]["behind_peers"] for f in r) and r["f0"]["TE-01"]["typical"] == 90.0
