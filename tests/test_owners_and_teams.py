"""product_line_owners.json and level-3 teams (owner, 3 Nov 2026).

- The owners file can be JSON: [{"product_line": ..., "owner_email": ...}]; a product line can have several leads;
  band is optional. It uploads on its own and is kept as the CSV's three columns.
- Setting team_grouping: product_family (default) uses the owners file; l3 makes a team of each level-3 person in HR
  with everyone under them, and lists everyone else as Not yet mapped.
The people and emails here are made up for the tests (synthetic data stays in tests).
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from trust import linking, mapping, store  # noqa: E402
from trust.intake import families  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
OWNERS = json.dumps([
    {"product_line": "Payments", "owner_email": "alex.moreno@example.com"},
    {"product_line": "Payments", "owner_email": "dup.one@example.com"},           # a second lead: same line again
    {"product_line": "Cards", "owner_email": ["pat.kim@example.com"], "band": "product"},
    {"product_line": "Cloud platform", "owner_email": "dana.cto@example.com, nobody.here@example.com", "band": "Platform"},
    {"product_line": "", "owner_email": "x@example.com"},                         # no name: set aside
]).encode()


def test_json_owners_file_reads_like_the_csv():
    r = families.read(OWNERS)
    rows = {x["family_id"]: x for x in r["rows"]}
    assert rows["payments"]["owner_emails"] == ["alex.moreno@example.com", "dup.one@example.com"]   # two leads combined
    assert rows["cards"]["owner_emails"] == ["pat.kim@example.com"]                                  # a list works
    assert rows["cloud-platform"]["owner_emails"] == ["dana.cto@example.com", "nobody.here@example.com"]
    assert rows["cloud-platform"]["band"] == "platform" and rows["payments"]["band"] == "product"
    assert not any("band" in n or "more than one line" in n for n in r["notes"])   # both normal now: nothing to acknowledge
    assert [a["reason"] for a in r["set_aside"]] == ["no Product Family"]
    assert families.read(b'{"product_lines": [{"product_line": "Cards", "owner_email": "pat.kim@example.com"}]}')["rows"]
    with pytest.raises(ValueError):
        families.to_csv(b"[not json")


PEOPLE = [   # cexec (1) > dcto (2) > amoreno (3) > slee (4) > pkim (5); dcto > dup1 (3); cexec > fhead (2) > slee2 (3) > ann (4)
    dict(sam_account="cexec", worker="Chris Exec", email="chris.exec@example.com", manager_sam=None, reporting_level=1),
    dict(sam_account="dcto", worker="Dana Cto", email="dana.cto@example.com", manager_sam="cexec", reporting_level=2),
    dict(sam_account="amoreno", worker="Alex Moreno", email="alex.moreno@example.com", manager_sam="dcto", reporting_level=3),
    dict(sam_account="slee", worker="Sam Lee", email=None, manager_sam="amoreno", reporting_level=4),
    dict(sam_account="pkim", worker="Pat Kim", email="pat.kim@example.com", manager_sam="slee", reporting_level=5),
    dict(sam_account="dup1", worker="Dup One", email="dup.one@example.com", manager_sam="dcto", reporting_level=3),
    dict(sam_account="fhead", worker="Fran Head", email="fran.head@example.com", manager_sam="cexec", reporting_level=2),
    dict(sam_account="slee2", worker="Sam Lee", email="sam.lee2@example.com", manager_sam="fhead", reporting_level=3),
    dict(sam_account="ann", worker="Ann Bo", email="ann.bo@example.com", manager_sam="slee2", reporting_level=4),
]


def test_level_3_teams_roll_up_everyone_under_them():
    p = linking.families_from_level(PEOPLE, 3)
    f = p["family_of_sam"]
    assert f["amoreno"] == f["slee"] == f["pkim"] == "alex-moreno"            # the lead and everyone under them
    assert f["dup1"] == "dup-one"
    assert f["slee2"] == f["ann"] != f["slee"]                                # two leads both called Sam Lee stay apart
    assert "cexec" not in f and "dcto" not in f and "fhead" not in f          # above level 3: Not yet mapped
    assert any("3 people aren't under a level-3 lead (Not yet mapped): cexec, dcto, fhead" in n for n in p["notes"])
    teams = {t["family_id"]: t for t in p["families"]}
    assert teams["alex-moreno"]["owner_emails"] == ["alex.moreno@example.com"] and teams["alex-moreno"]["people"] == 3
    assert {t["family"] for t in p["families"]} >= {"Alex Moreno", "Dup One"}


def test_grouping_setting_defaults_to_product_family():
    assert linking.grouping({}) == "product_family" and linking.grouping({"team_grouping": "L3"}) == "l3"
    assert linking.grouping({"team_grouping": "teams"}) == "product_family"    # anything else: the default
    assert linking.l3_level({}) == 3 and linking.l3_level({"l3_level": 4}) == 4 and linking.l3_level({"l3_level": "x"}) == 3


@pytest.fixture
def store_with(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))

    def setup(**settings):
        (tmp_path / "s.json").write_text(json.dumps({"hr_root_sam_account": "dcto", **settings}))
        monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    return setup


def test_json_upload_is_kept_and_places_people(store_with):
    store_with()
    store.upload("hr", "2026-10", (FIX / "hr_firmwide.csv").read_bytes(), "hr.csv", "Tester")
    e = store.upload("hr_mapping", "2026-10", OWNERS, "product_line_owners.json", "Tester")
    assert e["file"].endswith(".csv") and e["checks"]["rows"] == 3                 # kept as the CSV's three columns
    m = mapping.map_month("2026-10")
    assert m["team_grouping"] == "product_family"
    people = {p["sam_account"]: p["family_id"] for p in m["feeds"]["hr"]["people"]}
    assert people["amoreno"] == "payments" and people["dcto"] == "cloud-platform"


def test_l3_setting_reports_on_level_3_teams(store_with):
    store_with(team_grouping="l3")
    store.upload("hr", "2026-10", (FIX / "hr_firmwide.csv").read_bytes(), "hr.csv", "Tester")
    store.upload("hr_mapping", "2026-10", OWNERS, "product_line_owners.json", "Tester")   # loaded, but not used
    m = mapping.map_month("2026-10")
    assert m["team_grouping"] == "l3"
    assert any("each level-3 person in HR" in n for n in m["notes"])
    teams = {t["family"] for t in m["feeds"]["hr_mapping"]["families"]}
    assert "Alex Moreno" in teams and "Payments" not in teams
    people = {p["sam_account"]: p["family_id"] for p in m["feeds"]["hr"]["people"]}
    assert people["amoreno"] == people["slee"] == people["pkim"] == "alex-moreno"
    assert people["dcto"] == "UNATTRIBUTED"                                        # the CTO is above level 3


def test_l3_works_with_no_owners_file(store_with):
    store_with(team_grouping="l3")
    store.upload("hr", "2026-10", (FIX / "hr_firmwide.csv").read_bytes(), "hr.csv", "Tester")
    m = mapping.map_month("2026-10")
    assert {t["family"] for t in m["feeds"]["hr_mapping"]["families"]} >= {"Alex Moreno"}
    assert not any("owners file not loaded" in n for n in m["notes"])
