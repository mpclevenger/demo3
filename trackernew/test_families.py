"""Product family owners file: loads on its own; people are placed under their nearest owner in HR."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import linking  # noqa: E402
from trust.intake import families, hr  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
F = families.read((FIX / "family_owners.csv").read_bytes())
PEOPLE = hr.read((FIX / "hr_firmwide.csv").read_bytes(), "dcto")["people"]


def test_file_loads_alone_with_comma_separated_owners_and_band():
    rows = {r["family_id"]: r for r in F["rows"]}
    assert rows["payments"]["owner_emails"] == ["alex.moreno@example.com", "nobody.here@example.com"]
    assert rows["cloud-platform"]["band"] == "platform"           # 'PLATFORM', any case
    assert rows["payments"]["band"] == "product"
    assert rows["lending"]["band"] == "product" and not any("band" in n for n in F["notes"])   # band optional, no note (owner, 3 Nov 2026)
    assert any("'Lending' has no owner email" in n for n in F["notes"])


def test_nearest_owner_above_wins():
    # HR chain: dcto (Cloud platform owner) > amoreno (Payments owner) > slee > pkim (Cards owner)
    p = linking.families_from_owners(PEOPLE, F["rows"])
    assert p["family_of_sam"] == {"dcto": "cloud-platform", "amoreno": "payments", "slee": "payments", "pkim": "cards"}
    assert p["family_of_email"]["pat.kim@example.com"] == "cards"
    assert any("nobody.here@example.com isn't in the HR file" in n for n in p["notes"])


def test_lead_of_two_families_counts_for_both():
    """Owner, 6 Nov 2026: a lead of several families rolls up to each of them (same numbers in each)."""
    rows = F["rows"] + [{"family_id": "wealth", "family": "Wealth", "band": "product", "owner_emails": ["alex.moreno@example.com"]}]
    p = linking.families_from_owners(PEOPLE, rows)
    g = linking.SHARED + "payments+wealth"
    assert p["family_of_sam"]["amoreno"] == g and p["family_of_sam"]["slee"] == g
    assert p["shared"] == {g: ["payments", "wealth"]}
    assert p["family_of_sam"]["pkim"] == "cards"                  # their own nearer owner still works
    people = {x["family_id"]: x["people"] for x in p["families"]}
    assert people["payments"] == people["wealth"] == 2
    assert any(n.startswith("For information: amoreno leads 2 families (Payments, Wealth)") for n in p["notes"])


def test_shared_group_counts_once_for_the_firm_and_fully_for_each_family():
    from trust import score_month
    g = linking.SHARED + "payments+wealth"
    counts = {"TE-01": {g: {"numerator": 3, "denominator": 4, "items": [{"id": "c1"}]},
                        "payments": {"numerator": 1, "denominator": 1, "items": [{"id": "c2"}]}},
              "UN-01": {g: {"numerator": 1, "items": [{"id": "INC-1"}]},
                        "payments": {"numerator": 1, "items": [{"id": "INC-1"}]}, "_firm": {"numerator": 1}}}
    f = score_month.expand_shared(counts, {g: ["payments", "wealth"]})
    assert (f["TE-01"]["payments"]["numerator"], f["TE-01"]["payments"]["denominator"]) == (4, 5)
    assert (f["TE-01"]["wealth"]["numerator"], f["TE-01"]["wealth"]["denominator"]) == (3, 4)
    assert g not in f["TE-01"] and len(f["TE-01"]["payments"]["items"]) == 2
    assert f["UN-01"]["payments"]["numerator"] == 1 and f["UN-01"]["wealth"]["numerator"] == 1   # one incident, once each
    assert counts["TE-01"][g]["numerator"] == 3                   # the firm's counts are untouched
