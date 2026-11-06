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


def test_owner_of_two_families_is_not_guessed():
    rows = F["rows"] + [{"family_id": "wealth", "family": "Wealth", "band": "product", "owner_emails": ["alex.moreno@example.com"]}]
    p = linking.families_from_owners(PEOPLE, rows)
    assert "amoreno" not in p["family_of_sam"] and "slee" not in p["family_of_sam"]
    assert p["family_of_sam"]["pkim"] == "cards"                  # their own nearer owner still works
    assert any("amoreno owns more than one family" in n for n in p["notes"])
