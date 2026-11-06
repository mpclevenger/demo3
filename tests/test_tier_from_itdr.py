"""Family tier from the ITDR application file, and the Not Tier 0/1 rule on Resilient (owner, 4 Nov 2026)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import score_month  # noqa: E402
from trust.intake import dr_tests  # noqa: E402


def app(ref, fam, tier, name=None):
    return {"ref": ref, "application_name": name or ref, "family_id": fam, "recovery_tier": tier,
            "tier_label": "TBC" if tier is None else f"Tier {tier}"}


def mapped(apps, tests=()):
    fams = [{"family_id": f, "family": f.title(), "owner_emails": [], "band": "product"}
            for f in ("pay", "cards", "data", "web", "ops", "risk")]
    return {"month": "2026-10", "notes": [], "feeds": {
        "hr_mapping": {"status": "mapped", "families": fams},
        "itdr": {"status": "mapped", "rows": apps},
        "dr_tests": {"status": "mapped", "rows": list(tests)}}}


APPS = [app("A1", "pay", 0), app("A2", "pay", 3), app("B1", "cards", 1),
        app("C1", "data", 2),                                   # Tier 2 only: not Tier 0/1
        app("D1", "web", None),                                 # TBC only: not Tier 0/1
        app("E1", "ops", 1), app("F1", "risk", 0), app("X1", None, 0)]   # X1 not placed: no family


def test_family_tier_counts_come_from_the_itdr_file():
    fams = {f["id"]: f for f in score_month.score_month(mapped(APPS))["families"]}
    assert (fams["pay"]["tier01"], fams["pay"]["tier01_apps"], fams["pay"]["apps_total"]) == (True, 1, 2)
    assert (fams["data"]["tier01"], fams["data"]["tier01_apps"], fams["data"]["apps_total"]) == (False, 0, 1)
    assert fams["web"]["tier01"] is False


def test_tier_not_known_without_the_itdr_file():
    m = mapped(APPS)
    del m["feeds"]["itdr"]
    fams = score_month.score_month(m)["families"]
    assert all(f["tier01"] is None and f["apps_total"] is None for f in fams)


def test_not_tier01_families_are_not_scored_on_resilient_and_left_out_of_the_median():
    tests = [{"itdr_ref": r, "kind": "DR test", "performed_on": "2026-03-14"} for r in ("A1", "B1", "C1", "E1")]
    out = score_month.score_month(mapped(APPS, tests))
    fam = out["period"]["families"]
    data = fam["data"]
    for mid in ("RE-01", "RE-02", "RE-03"):
        assert data["metrics"][mid]["status"] == "Not Tier 0/1"
    assert data["blocks"]["RES"]["status"] == "Not Tier 0/1" and data["blocks"]["RES"]["score"] is None
    # RE-03's median comes from the 4 Tier 0/1 families only (data's tested Tier 2 app is left out), and a median
    # needs 5 families (min_families_for_threshold), so it isn't set this month. With data counted it would be.
    assert fam["pay"]["metrics"]["RE-03"]["status"] == "N/A"
    assert "RE-03" not in out["period"]["thresholds"]


def test_tier_difference_warning_says_the_itdr_file_wins():
    tests = [{"application_name": "A1", "tier_label": "Tier 2"}]
    notes = dr_tests.match_applications(tests, [app("A1", "pay", 0)])["notes"]
    assert len(notes) == 1 and "uses the ITDR application file's tier" in notes[0] and "Tier 2 here" in notes[0]
