from dataclasses import replace
from decimal import Decimal as D

import pytest

from trust_demo.models import (
    Entry, Family, Letter, Metric, Period, Store, Team, TeamObservation, ToleranceThreshold,
)
from trust_demo.scoring import (
    active_thresholds, classify, compute_all, compute_period, declining_letters, is_sharp_drop,
)

LETTERS = ["TR", "RE", "UN", "SE", "TE"]


def mk_metric(mid, letter, hib=False, **kw):
    base = dict(id=mid, letter=letter, name=mid, provider="Cyber", source_system="X", unit="%",
                scale=D(100), higher_is_better=hib, scored=True, zero_rule="NA", min_pop=5,
                numerator_label="n", denominator_label="d", definition="")
    base.update(kw)
    return Metric(**base)


def mk_th(mid, green, red, version=1, eff="2026-01", to=None):
    return ToleranceThreshold(mid, version, D(green), D(red), eff, to, "Tech Risk", "2026-01-01",
                              "REF", "r", "Policy")


def obs(pid, mgr, mid, num, den, **kw):
    return TeamObservation(pid, mgr, mid, D(num), D(den), "S1", **kw)


def mk_store(metrics=None, thresholds=None, observations=(), periods=("2026-01",),
             families=None, teams=None, entries=(), dnr=(), unattr=None):
    families = families or [Family("F1", "Fam One", "product", True, True, ("Lead A",)),
                            Family("F2", "Fam Two", "product", True, True, ("Lead B",)),
                            Family("F3", "Fam Three", "platform", False, False, ("Lead C",))]
    teams = teams or [Team(f"M{i}", f.id, f"Mgr {i} org") for i, f in enumerate(families, 1)]
    metrics = metrics if metrics is not None else [mk_metric(f"{L}-01", L) for L in LETTERS]
    thresholds = thresholds if thresholds is not None else [mk_th(m.id, 5, 15) for m in metrics]
    return Store(families=families, teams=teams,
                 letters=[Letter(L, L, "?", "Cyber") for L in LETTERS], metrics=metrics,
                 thresholds=thresholds,
                 periods=[Period(p, p, "Locked", None) for p in periods],
                 observations=list(observations), submissions=[], connectors=[],
                 entries=list(entries), unattributed_pct=dict(unattr or {}), dnr=set(dnr))


def all_green_obs(pid, mgrs=("M1", "M2", "M3"), metrics=None, num=0, den=100):
    ids = metrics or [f"{L}-01" for L in LETTERS]
    return [obs(pid, m, mid, num, den) for m in mgrs for mid in ids]


# ---------- classify ----------

LOW = mk_metric("SE-01", "SE")
HIGH = mk_metric("TE-01", "TE", hib=True)
TH_LOW = mk_th("SE-01", 5, 15)
TH_HIGH = mk_th("TE-01", 80, 60)


@pytest.mark.parametrize("v,expected", [
    ("5.0", "Green"), ("5.04", "Green"), ("5.05", "Amber"), ("15.0", "Amber"),
    ("15.04", "Amber"), ("15.05", "Red"), ("0", "Green"), ("40", "Red")])
def test_classify_lower_is_better(v, expected):
    assert classify(LOW, D(v), TH_LOW) == expected


@pytest.mark.parametrize("v,expected", [
    ("80.0", "Green"), ("79.95", "Green"), ("79.94", "Amber"), ("60.0", "Amber"),
    ("59.95", "Amber"), ("59.94", "Red"), ("100", "Green")])
def test_classify_higher_is_better(v, expected):
    assert classify(HIGH, D(v), TH_HIGH) == expected


# ---------- thresholds ----------

def test_threshold_versioning():
    ths = [mk_th("SE-01", 5, 15, 1, "2026-01", "2026-03"), mk_th("SE-01", 2, 10, 2, "2026-03")]
    s = mk_store(thresholds=ths)
    assert active_thresholds(s, "2026-02")["SE-01"].version == 1
    assert active_thresholds(s, "2026-03")["SE-01"].version == 2
    assert active_thresholds(s, "2025-12") == {}


def test_threshold_version_applies_only_from_effective_period():
    m = [mk_metric("SE-01", "SE")]
    ths = [mk_th("SE-01", 5, 15, 1), mk_th("SE-01", 2, 10, 2, "2026-02")]
    o = [obs(p, "M1", "SE-01", 12, 100) for p in ("2026-01", "2026-02")]
    s = mk_store(metrics=m, thresholds=ths, observations=o, periods=("2026-01", "2026-02"))
    scs = compute_all(s)
    jan, feb = (scs[p].families["F1"].metrics["SE-01"] for p in ("2026-01", "2026-02"))
    assert (jan.status, jan.threshold_version) == ("Amber", 1)
    assert (feb.status, feb.threshold_version) == ("Red", 2)
    assert scs["2026-01"].thresholds_used == {"SE-01": 1}
    assert scs["2026-02"].thresholds_used == {"SE-01": 2}


# ---------- metric statuses ----------

def test_reason_texts_and_values():
    m = [mk_metric("SE-01", "SE")]
    o = [obs("2026-01", "M1", "SE-01", 504, 10000), obs("2026-01", "M2", "SE-01", 1505, 10000),
         obs("2026-01", "M3", "SE-01", 10, 100)]
    sc = compute_period(mk_store(metrics=m, observations=o), "2026-01")
    r = {f: sc.families[f].metrics["SE-01"] for f in ("F1", "F2", "F3")}
    assert (r["F1"].value, r["F1"].status, r["F1"].points) == (D("5.0"), "Green", 100)
    assert r["F1"].reason == "Within Green tolerance (≤ 5.0%)"
    assert (r["F2"].value, r["F2"].status, r["F2"].points) == (D("15.1"), "Red", 0)
    assert r["F2"].reason == "Worse than Red limit (> 15.0%)"
    assert r["F3"].status == "Amber" and r["F3"].reason == "Between tolerance and Red limit"


def test_zero_denominator_best_vs_na():
    m = [mk_metric("SE-01", "SE", zero_rule="BEST"), mk_metric("SE-02", "SE")]
    o = [obs("2026-01", "M1", "SE-01", 0, 0), obs("2026-01", "M1", "SE-02", 0, 0),
         obs("2026-01", "M2", "SE-01", 0, 0, coverage_confirmed=False)]
    sc = compute_period(mk_store(metrics=m, observations=o), "2026-01")
    f1 = sc.families["F1"].metrics
    assert (f1["SE-01"].status, f1["SE-01"].value) == ("Green", D("0.0"))
    assert f1["SE-01"].reason == "No open items, coverage confirmed"
    assert f1["SE-02"].status == "N/A"
    assert sc.families["F2"].metrics["SE-01"].status == "N/A"


def test_low_confidence_and_info_only_and_not_tier01():
    m = [mk_metric("SE-01", "SE"), mk_metric("SE-02", "SE", scored=False, higher_is_better=None),
         mk_metric("RE-01", "RE", tier01_only=True)]
    o = [obs("2026-01", "M1", "SE-01", 0, 4), obs("2026-01", "M1", "SE-02", 1, 10),
         obs("2026-01", "M3", "RE-01", 0, 100)]
    sc = compute_period(mk_store(metrics=m, observations=o), "2026-01")
    f1 = sc.families["F1"].metrics
    assert f1["SE-01"].status == "Low confidence" and f1["SE-01"].points is None
    assert f1["SE-02"].status == "Info only" and f1["SE-02"].value == D("10.0")
    assert sc.families["F3"].metrics["RE-01"].status == "Not Tier 0/1"
    assert sc.families["F3"].letters["RE"].status == "Not Tier 0/1"
    # Low confidence is applicable but unscored -> SE coverage 0% -> Insufficient data
    assert sc.families["F1"].letters["SE"].status == "Insufficient data"


def test_aggregation_excludes_unattributed_from_families_but_in_firm_totals():
    m = [mk_metric("SE-01", "SE")]
    o = [obs("2026-01", "M1", "SE-01", 1, 100), obs("2026-01", "M4", "SE-01", 2, 100),
         obs("2026-01", "UNATTRIBUTED", "SE-01", 50, 100)]
    teams = [Team("M1", "F1", "a"), Team("M4", "F1", "b"), Team("M2", "F2", "c"), Team("M3", "F3", "d")]
    sc = compute_period(mk_store(metrics=m, observations=o, teams=teams), "2026-01")
    assert sc.families["F1"].metrics["SE-01"].value == D("1.5")
    assert "UNATTRIBUTED" not in sc.families
    assert sc.firm_totals["SE-01"] == D("17.7")


def test_rolling_three_months():
    m = [mk_metric("UN-01", "UN", rolling_months=3)]
    ps = ("2026-01", "2026-02", "2026-03", "2026-04")
    nums = (30, 0, 0, 0)
    o = [obs(p, "M1", "UN-01", n, 100) for p, n in zip(ps, nums)]
    scs = compute_all(mk_store(metrics=m, observations=o, periods=ps))
    vals = [scs[p].families["F1"].metrics["UN-01"].value for p in ps]
    assert vals == [D("30.0"), D("15.0"), D("10.0"), D("0.0")]
    assert scs["2026-03"].families["F1"].metrics["UN-01"].denominator == D(300)


# ---------- overrides & caps ----------

def test_override_red_and_letter_cap_49_and_trust_cap_79():
    m = [mk_metric("SE-01", "SE", override_rule="critical_secret"), mk_metric("SE-02", "SE"),
         mk_metric("SE-03", "SE"), mk_metric("SE-04", "SE"),
         mk_metric("RE-01", "RE", override_rule="t01_internet_eol")]
    m += [mk_metric(f"{L}-01", L) for L in ("TR", "UN", "TE")]
    o = all_green_obs("2026-01", mgrs=("M1",), metrics=[x.id for x in m])
    o = [replace(x, critical_overdue=1) if x.metric_id == "SE-01" else x for x in o]
    sc = compute_period(mk_store(metrics=m, observations=o), "2026-01")
    fr = sc.families["F1"]
    se1 = fr.metrics["SE-01"]
    assert (se1.status, se1.override, se1.reason) == ("Red", True, "Red: overdue critical secret")
    se = fr.letters["SE"]
    assert (se.score, se.status, se.capped, se.red_count) == (49, "Red", True, 1)  # 75 -> 49
    # letters: 100,100,100,49,100 -> 89.8 -> capped at 79
    assert (fr.trust, fr.capped, fr.status) == (79, True, "Amber")


def test_eol_override_reason():
    m = [mk_metric("RE-01", "RE", override_rule="t01_internet_eol")]
    o = [obs("2026-01", "M1", "RE-01", 0, 100, t01_internet_eol=2)]
    mr = compute_period(mk_store(metrics=m, observations=o), "2026-01").families["F1"].metrics["RE-01"]
    assert mr.status == "Red" and mr.reason == "Red: EOL on Tier 0/1 internet-facing app"


def test_letter_rounding_and_trust_from_unrounded_means():
    m = [mk_metric(f"TR-0{i}", "TR") for i in (1, 2, 3)] + \
        [mk_metric(f"{L}-01", L) for L in ("RE", "UN", "SE")]
    o = [obs("2026-01", "M1", "TR-01", 0, 100), obs("2026-01", "M1", "TR-02", 0, 100),
         obs("2026-01", "M1", "TR-03", 10, 100)] + \
        [obs("2026-01", "M1", f"{L}-01", 10, 100) for L in ("RE", "UN", "SE")]
    fr = compute_period(mk_store(metrics=m, observations=o), "2026-01").families["F1"]
    assert fr.letters["TR"].score == 83  # 83.33
    assert fr.letters["TE"].status == "N/A"
    # (83.333 + 50*3)/4 = 58.33 -> 58
    assert fr.trust == 58 and fr.status == "Amber"


def test_trust_insufficient_with_fewer_than_three_letters():
    m = [mk_metric("TR-01", "TR"), mk_metric("RE-01", "RE")]
    o = all_green_obs("2026-01", metrics=["TR-01", "RE-01"])
    sc = compute_period(mk_store(metrics=m, observations=o), "2026-01")
    assert sc.families["F1"].trust is None and sc.families["F1"].status == "Insufficient data"
    assert sc.firm_trust is None


# ---------- DNR carry forward ----------

def test_dnr_carry_forward_one_month_then_dnr():
    ps = ("2026-01", "2026-02", "2026-03")
    o = all_green_obs("2026-01")
    s = mk_store(observations=o, periods=ps, dnr={("2026-02", "Cyber"), ("2026-03", "Cyber")})
    scs = compute_all(s)
    feb = scs["2026-02"].families["F1"]
    mr = feb.metrics["SE-01"]
    assert (mr.status, mr.provisional, mr.carried_from, mr.points) == ("Green", True, "2026-01", 100)
    assert mr.value == D("0.0")
    assert mr.reason == "Carried forward from 2026-01 — Cyber did not submit (provisional)"
    assert feb.letters["SE"].provisional and feb.trust == 100
    mar = scs["2026-03"].families["F1"].metrics["SE-01"]
    assert mar.status == "DNR" and mar.points is None and not mar.provisional
    assert scs["2026-03"].families["F1"].letters["SE"].status == "Insufficient data"


def test_dnr_with_no_prior_is_dnr():
    sc = compute_period(mk_store(dnr={("2026-01", "Cyber")}), "2026-01")
    assert sc.families["F1"].metrics["SE-01"].status == "DNR"


# ---------- peers ----------

def test_behind_peers_flag_and_typical():
    m = [mk_metric("SE-01", "SE", peer_flag_gap=D(3))]
    fams = [Family(f"F{i}", f"Fam {i}", "product", True, True, ()) for i in range(1, 5)]
    o = [obs("2026-01", f"M{i}", "SE-01", n, 100) for i, n in ((1, 2), (2, 4), (3, 6), (4, 8))]
    sc = compute_period(mk_store(metrics=m, observations=o, families=fams), "2026-01")
    rs = {f: sc.families[f].metrics["SE-01"] for f in sc.families}
    assert all(r.typical == D("5.0") for r in rs.values())
    assert [rs[f].behind_peers for f in ("F1", "F2", "F3", "F4")] == [False, False, False, True]
    assert rs["F4"].status == "Amber"  # flag does not change status
    assert any(w.kind == "Behind peers" and w.family_id == "F4" for w in sc.watch_list)


# ---------- trends ----------

def _two_period(jan_nums, feb_nums):
    ps = ("2026-01", "2026-02")
    o = [obs("2026-01", "M1", f"{L}-01", n, 100) for L, n in zip(LETTERS, jan_nums)]
    o += [obs("2026-02", "M1", f"{L}-01", n, 100) for L, n in zip(LETTERS, feb_nums)]
    return compute_all(mk_store(observations=o, periods=ps))


def test_sharp_drop_requires_two_worse_metrics():
    scs = _two_period([0] * 5, [10, 0, 0, 0, 0])  # 100 -> 90, one worse
    fr, pfr = scs["2026-02"].families["F1"], scs["2026-01"].families["F1"]
    assert fr.delta == -10 and not is_sharp_drop(fr, pfr)
    scs = _two_period([0] * 5, [10, 10, 0, 0, 0])  # 100 -> 80, two worse
    fr, pfr = scs["2026-02"].families["F1"], scs["2026-01"].families["F1"]
    assert fr.delta == -20 and is_sharp_drop(fr, pfr)
    assert any(w.kind == "Sharp drop" for w in scs["2026-02"].watch_list)
    assert scs["2026-02"].firm_trust_delta == -20


def test_new_red_chronic_and_most_improved_and_declining():
    ps = ("2026-01", "2026-02", "2026-03")
    o = []
    for p in ps:
        o.append(obs(p, "M1", "SE-01", 20, 100))  # chronic red
        o.append(obs(p, "M1", "TR-01", {"2026-01": 0, "2026-02": 10, "2026-03": 20}[p], 100))
        o.append(obs(p, "M2", "SE-01", {"2026-01": 20, "2026-02": 10, "2026-03": 0}[p], 100))
        o += [obs(p, m, f"{L}-01", 0, 100) for m in ("M1", "M2") for L in ("RE", "UN", "TE")]
    o.append(obs("2026-01", "M2", "TR-01", 0, 100))
    o += [obs(p, "M2", "TR-01", 0, 100) for p in ps[1:]]
    scs = compute_all(mk_store(observations=o, periods=ps))
    wl = scs["2026-03"].watch_list
    kinds = {(w.kind, w.family_id, w.metric_id) for w in wl}
    assert ("Chronic red", "F1", "SE-01") in kinds
    assert ("New red", "F1", "TR-01") in kinds
    assert ("New red", "F1", "SE-01") not in kinds
    assert scs["2026-03"].most_improved[0] == "F2"
    assert declining_letters(scs["2026-03"], "F1") == ["TR"]


# ---------- watch list ----------

def test_watch_list_order_cap_and_data_quality():
    entries = [Entry(f"E{i}", "2026-01", "F1", None, "Action", f"fix {i}", "Lead A", "Open",
                     due="2026-01-15") for i in range(6)]
    entries.append(Entry("E9", "2026-01", "F1", None, "Action", "done", "Lead A", "Done",
                         due="2026-01-02"))
    entries.append(Entry("E10", "2026-01", "F1", None, "Action", "later", "Lead A", "Open",
                         due="2026-02-15"))
    m = [mk_metric("SE-01", "SE", override_rule="critical_secret"), mk_metric("TR-01", "TR")]
    o = [obs("2026-01", "M1", "SE-01", 0, 100, critical_overdue=1), obs("2026-01", "M1", "TR-01", 0, 100)]
    s = mk_store(metrics=m, observations=o, entries=entries,
                 unattr={("2026-01", "Ops"): D("7.2")}, dnr={("2026-01", "Arch")})
    wl = compute_period(s, "2026-01").watch_list
    assert len(wl) == 9
    assert wl[0].kind == "Override red"
    assert [w.kind for w in wl[1:7]] == ["Overdue action"] * 6
    assert [w.kind for w in wl[-2:]] == ["Data quality", "Data quality"]
    assert [w.priority for w in wl] == sorted(w.priority for w in wl)
    # add more actions -> capped at 10, lowest priority items dropped
    s.entries += [replace(entries[0], id=f"X{i}") for i in range(5)]
    wl = compute_period(s, "2026-01").watch_list
    assert len(wl) == 10 and wl[0].kind == "Override red"
    assert all(w.kind != "Data quality" for w in wl)
