"""TR-02 (repo hygiene) and RE-03 (resiliency tests passed) switched on (owner, 4 Nov 2026)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import evidence, measure, score_month  # noqa: E402

OK = {"protected": True, "review": True, "independent": True, "history": True, "no_bypass": True}


def repo(name, fam, passed=5, active=True, **checks):
    c = dict(OK, **checks)
    return {"repo": name, "family_id": fam, "active": active, "passed": passed, "checks": c, "url": None}


def test_tr02_counts_checks_of_active_repos():
    feeds = {"repos": {"rows": [repo("a", "pay"), repo("b", "pay", 3, independent=False, no_bypass=False),
                                repo("c", "pay", 5, active=False), repo("d", "UNATTRIBUTED", 0, protected=False)]}}
    out = measure.tr02(feeds)
    assert (out["pay"]["numerator"], out["pay"]["denominator"]) == (8, 10)        # inactive repo left out
    assert out["UNATTRIBUTED"]["denominator"] == 5
    b = next(i for i in out["pay"]["items"] if i["id"] == "b")
    d = evidence.describe("TR-02", b)
    assert d["result"] == "3 of 5 checks; fails: Independent approval, No one can skip the rules" and d["concern"]
    assert "main branch not protected" in evidence.describe("TR-02", out["UNATTRIBUTED"]["items"][0])["result"]


def test_re03_tier_0_to_2_and_dr_tests_or_tabletops_in_12_months():
    apps = [{"ref": "A1", "application_name": "Gateway", "recovery_tier": 0, "tier_label": "Tier 0", "family_id": "pay"},
            {"ref": "A2", "application_name": "Rates", "recovery_tier": 2, "tier_label": "Tier 2", "family_id": "pay"},
            {"ref": "A3", "application_name": "Old", "recovery_tier": 1, "tier_label": "Tier 1", "family_id": "pay"},
            {"ref": "A4", "application_name": "Batch", "recovery_tier": 3, "tier_label": "Tier 3", "family_id": "pay"},
            {"ref": "A5", "application_name": "Loose", "recovery_tier": 1, "tier_label": "Tier 1", "family_id": None}]
    tests = [{"itdr_ref": "A1", "kind": "DR test", "performed_on": "2026-03-14"},
             {"itdr_ref": "A2", "kind": "Tabletop exercise", "performed_on": "2026-05-20"},
             {"itdr_ref": "A3", "kind": "DR test", "performed_on": "2025-09-30"},     # more than 12 months before
             {"itdr_ref": "A3", "kind": "DR test", "performed_on": None},             # not performed
             {"itdr_ref": "A4", "kind": "DR test", "performed_on": "2026-06-01"}]     # Tier 3: not in scope
    out = measure.re03({"itdr": {"rows": apps}, "dr_tests": {"rows": tests}}, "2026-10")
    assert (out["pay"]["numerator"], out["pay"]["denominator"]) == (2, 3)
    assert out["UNATTRIBUTED"]["denominator"] == 1
    items = {i["id"]: i for i in out["pay"]["items"]}
    assert items["Rates"]["test_kind"] == "Tabletop exercise" and not items["Old"]["passed"]
    assert evidence.describe("RE-03", items["Gateway"])["date"] == "2026-03-14"


def test_re03_needs_both_files_and_switch_controls_scoring():
    mapped = {"month": "2026-10", "feeds": {"dr_tests": {"status": "mapped", "rows": []}}}
    assert "RE-03" not in measure.measure(mapped)["received"]               # ITDR file missing
    mapped["feeds"]["itdr"] = {"status": "mapped", "rows": []}
    assert "RE-03" in measure.measure(mapped)["received"]
    cfg = score_month.thresholds_config()
    assert set(cfg["switched_on"]) == {"TR-01", "TR-02", "RE-01", "RE-03"}
    assert {cfg["metrics"][m]["basis"] for m in ("TR-02", "RE-01", "RE-03")} == {"Prevailing median"}


def test_re01_tier_0_and_1_dr_tests_only():
    """Owner, 4 Nov 2026: RE-01 = Tier 0/1 apps with a completed DR test (Comments date) in 12 months; no tabletops."""
    apps = [{"ref": "A1", "application_name": "Gateway", "recovery_tier": 0, "tier_label": "Tier 0", "family_id": "pay"},
            {"ref": "A2", "application_name": "Rates", "recovery_tier": 1, "tier_label": "Tier 1", "family_id": "pay"},
            {"ref": "A3", "application_name": "Batch", "recovery_tier": 2, "tier_label": "Tier 2", "family_id": "pay"}]
    tests = [{"itdr_ref": "A1", "kind": "DR test", "performed_on": "2026-03-14"},
             {"itdr_ref": "A2", "kind": "Tabletop exercise", "performed_on": "2026-05-20"},   # tabletop: not counted
             {"itdr_ref": "A3", "kind": "DR test", "performed_on": "2026-06-01"}]             # Tier 2: not in RE-01
    feeds = {"itdr": {"rows": apps}, "dr_tests": {"rows": tests}}
    r1, r3 = measure.re01(feeds, "2026-10")["pay"], measure.re03(feeds, "2026-10")["pay"]
    assert (r1["numerator"], r1["denominator"]) == (1, 2)
    assert (r3["numerator"], r3["denominator"]) == (3, 3)
    rates = next(i for i in r1["items"] if i["id"] == "Rates")
    assert evidence.describe("RE-01", rates)["result"] == "No DR test in the last 12 months (Tier 1)"
