"""The ITDR application file (owner, 3 Nov 2026): Excel, header merged over rows 1 and 2, kept as a table.

The workbooks here are made up for the tests (synthetic data stays in tests).
"""
import io
import pathlib
import sys

import openpyxl
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import mapping, storage, store  # noqa: E402
from trust.intake import itdr  # noqa: E402
from trust.intake.common import read_table  # noqa: E402

ROWS = [
    (1, "Payments Gateway", "Payments", "Tier 0"),
    (2, "  Card\nAuthoriser  ", "Cards", "Tier 1"),
    (3, "Statement Builder", None, "Tier 3"),
    (4.0, "Ledger Sync", "Lending", "tier2"),
    (5, "Rates Feed", "Markets", "TBC"),
    (6, "Old Reporting", "Markets", None),
    (7, "Mystery App", "Ops", "Gold"),
    (None, "No Ref App", "Ops", "Tier 1"),
    ("A9", "Bad Ref App", "Ops", "Tier 1"),
    (3, "Statement Builder copy", "Cards", "Tier 4"),
    (8, None, "Ops", "Tier 5"),
    (9, "Payments Gateway", "Payments", "Tier 5"),
]


def workbook(rows=ROWS, merged=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    for c, h in enumerate(("Ref", "Application Name", "Business Product Area", "Recovery Tier"), start=1):
        ws.cell(row=1, column=c, value=h)
        if merged:
            ws.merge_cells(start_row=1, start_column=c, end_row=2, end_column=c)
    start = 3 if merged else 2
    for i, r in enumerate(rows):
        for c, v in enumerate(r, start=1):
            ws.cell(row=start + i, column=c, value=v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    s = tmp_path / "settings.json"
    s.write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(s))


def test_merged_header_is_one_header_row():
    headers, rows = read_table(workbook(), header_rows=2)
    assert headers == ["Ref", "Application Name", "Business Product Area", "Recovery Tier"]
    assert rows[0]["Ref"] == "1" and rows[0]["Recovery Tier"] == "Tier 0"
    assert rows[3]["Ref"] == "4"                                   # 4.0 from Excel reads as 4


def test_a_file_with_one_header_row_still_reads():
    headers, rows = read_table(workbook(merged=False), header_rows=2)
    assert headers[0] == "Ref" and rows[0]["Application Name"] == "Payments Gateway"
    csv = b"Ref,Application Name,Business Product Area,Recovery Tier\n,,,\n1,App,Area,Tier 0\n"
    assert read_table(csv, header_rows=2)[1][0]["Ref"] == "1"


def test_two_word_header_rows_are_joined():
    csv = b"Recovery,Application\nTier,Name\n1,x\n"
    assert read_table(csv, header_rows=2)[0] == ["Recovery Tier", "Application Name"]


def test_tiers_names_refs_and_blanks():
    r = itdr.read(workbook())
    by = {x["ref"]: x for x in r["rows"]}
    assert sorted(by) == [1, 2, 3, 4, 5, 6, 7, 9]
    assert by[2]["application_name"] == "Card Authoriser"           # spaces, line break, nbsp tidied
    assert (by[1]["recovery_tier"], by[1]["tier_label"]) == (0, "Tier 0")
    assert (by[4]["recovery_tier"], by[4]["tier_label"]) == (2, "Tier 2")
    assert (by[5]["recovery_tier"], by[5]["tier_label"]) == (None, "TBC")
    assert by[6]["tier_label"] == "Not given" and by[7]["tier_label"] == "Not given"
    assert by[3]["business_product_area"] is None and by[3]["application_name"] == "Statement Builder"
    reasons = [a["reason"] for a in r["set_aside"]]
    assert "no Ref" in reasons and "Ref 'A9' is not a number" in reasons and "no Application Name" in reasons
    assert any(x.startswith("Ref 3 repeated") for x in reasons)
    s = r["summary"]
    assert s["applications"] == 8 and s["tier_0_1"] == 2 and s["no_business_product_area"] == 1
    assert s["by_tier"] == {"Tier 0": 1, "Tier 1": 1, "Tier 2": 1, "Tier 3": 1, "Tier 4": 0, "Tier 5": 1,
                            "TBC": 1, "Not given": 2}
    notes = " | ".join(r["notes"])
    assert "Recovery Tier 'Gold' isn't Tier 0 to Tier 5 or TBC (Ref 7)" in notes
    assert "1 application has no Recovery Tier" in notes
    assert "1 application name was tidied" in notes
    assert "same application name is on Refs 1, 9" in notes


@pytest.mark.parametrize("raw,want", [("Tier 0", 0), ("tier 5", 5), ("T1", 1), ("3", 3), ("Tier-2", 2),
                                      ("TBC", None), ("Tier 6", None), ("", None)])
def test_tier_of(raw, want):
    assert itdr.tier_of(raw)[0] == want


def test_upload_keeps_the_table_and_maps():
    e = store.upload("itdr", "2026-10", workbook(), "ITDR apps.xlsx", "Tester")
    assert e["file"].endswith(".csv")                              # stored cut down, as CSV
    assert e["checks"]["rows"] == 8 and e["checks"]["set_aside"] == 4
    apps = storage.itdr_applications("2026-10")
    assert [a["ref"] for a in apps] == [1, 2, 3, 4, 5, 6, 7, 9]
    assert apps[0] == {"ref": 1, "application_name": "Payments Gateway", "business_product_area": "Payments",
                       "recovery_tier": 0, "tier_label": "Tier 0"}
    r = mapping.map_month("2026-10")
    assert r["feeds"]["itdr"]["summary"]["tier_0_1"] == 2
    # A new file for the month replaces the list; the earlier one is still kept.
    store.upload("itdr", "2026-10", workbook(ROWS[:2]), "ITDR apps v2.xlsx", "Tester")
    assert [a["ref"] for a in storage.itdr_applications("2026-10")] == [1, 2]
    assert len(storage.register("2026-10", "itdr")) == 2
    assert storage.itdr_applications("2026-09") == []


def test_junk_is_refused():
    with pytest.raises(ValueError, match="Not uploaded"):
        store.upload("itdr", "2026-10", b"PK\x03\x04 not really a workbook", "x.xlsx", "Tester")
    with pytest.raises(ValueError, match="Not uploaded"):
        store.upload("itdr", "2026-10", b"Colour,Size\nred,1\n", "wrong.csv", "Tester")


def fams():
    return [{"family_id": "payments", "family": "Payments"}, {"family_id": "cards", "family": "Cards"},
            {"family_id": "lending", "family": "Lending"}]


def people():
    return ([{"department": "Retail Banking Technology", "family_id": "cards"}] * 3
            + [{"department": "Retail Banking Technology", "family_id": "lending"}]
            + [{"department": "Retail Banking Technology", "family_id": "UNATTRIBUTED"}] * 9
            + [{"department": "Shared Services", "family_id": "cards"},
               {"department": "Shared Services", "family_id": "payments"}]
            + [{"department": "Lending Platform A", "family_id": "lending"}]
            + [{"department": "Lending Platform B", "family_id": "cards"}])


def test_family_from_family_name_or_department_exact_then_close():
    """Owner, 3 Nov 2026: Business Product Area is a family name or an HR Department, not always spelled the
    same; a department's family is the one most of its people are in; close calls and ties are listed."""
    apps = [{"ref": 1, "business_product_area": "payments"},                  # exact family name
            {"ref": 2, "business_product_area": "Retail Banking Technology"},  # exact department -> cards (3 v 1)
            {"ref": 3, "business_product_area": "Retail Bankng Tech."},         # close spelling of the department
            {"ref": 4, "business_product_area": "Shared Services"},            # department split 1-1
            {"ref": 5, "business_product_area": "Nowhere"},
            {"ref": 6, "business_product_area": None},
            {"ref": 7, "business_product_area": "Lending Platform"}]            # as close to two departments, different families
    r = itdr.match_families(apps, fams(), people(), 0.85)
    got = {a["ref"]: (a["family_id"], (a["family_match"] or {}).get("how")) for a in apps}
    assert got[1] == ("payments", "exact family name")
    assert got[2] == ("cards", "exact department")
    assert got[3][0] == "cards" and got[3][1] == "fuzzy department"
    assert apps[2]["family_match"]["matched"] == "Retail Banking Technology" and 0.85 <= apps[2]["family_match"]["score"] < 1
    assert got[4][0] is None and got[5] == (None, None) and got[6] == (None, None) and got[7][0] is None
    assert (r["placed"], r["exact"], r["fuzzy"], r["by_family_name"], r["by_department"]) == (3, 2, 1, 1, 2)
    notes = " | ".join(r["notes"])
    assert "matched by a close spelling (confidence at least 0.85); please check: 'Retail Bankng Tech.' → department 'Retail Banking Technology'" in notes
    assert "'Shared Services' matches department 'Shared Services' has as many people in cards, payments; no family chosen (Ref 4)" in notes
    assert "'Lending Platform' is about as close to department" in notes and "(Ref 7)" in notes
    assert "isn't close enough to a family name or an HR department: 'Nowhere' (Ref 5)" in notes
    assert "1 application has no Business Product Area" in notes


def test_confidence_setting():
    apps = [{"ref": 3, "business_product_area": "Retail Bankng Tech."}]
    assert itdr.match_families(apps, fams(), people(), 1.0)["placed"] == 0            # exact only
    assert itdr.match_families(apps, fams(), people(), 0.85)["placed"] == 1
    assert itdr.area_match_min({}) == 0.85 and itdr.area_match_min({"area_match_min": 0.9}) == 0.9
    assert itdr.area_match_min({"area_match_min": 0.2}) == 0.85 and itdr.area_match_min({"area_match_min": "x"}) == 0.85


def test_name_similarity_allows_short_and_misspelt_words_but_not_extra_ones():
    assert itdr.name_similarity("Retail Bankng Tech.", "Retail Banking Technology") >= 0.9
    assert itdr.name_similarity("Payments Tech", "Payment Technology") >= 0.85
    assert itdr.name_similarity("Payments", "Payments Operations") < 0.85
    assert itdr.name_similarity("Markets Tech", "Retail Banking Technology") < 0.5
