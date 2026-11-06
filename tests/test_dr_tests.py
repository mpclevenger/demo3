"""The completed DR tests file (owner, 3 Nov 2026): read on its own, kept as a table, linked to ITDR by name.

The workbooks here are made up for the tests (synthetic data stays in tests).
"""
import io
import pathlib
import sys

import openpyxl
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import mapping, storage, store  # noqa: E402
from trust.intake import dr_tests  # noqa: E402

HEAD = ("Tier", "Name", "Business Area", "ITDR Lead", "Type of Test", "When", "Status", "Comments")
ROWS = [
    ("Tier 0", "Payments Gateway", "Payments", "A. Lead", "Open", "03/14/2026", "Successful",
     "DR Test completed on 14th March 2026"),
    ("Tier 1", " Card  Authoriser ", None, "B. Lead", "Closed", "04/02/2026", None,
     "DR Test Completed on 2nd April 2026"),
    ("Tier 1", "Rates Feed", "Markets", "C. Lead", "TTX", "05/20/2026", "Successful",
     "TTX: Tabletop exercise completed"),
    ("Tier 2", "Unknown App", "Ops", None, "Live failover", "13/45/2026", "Failed", None),
    ("Tier 3", None, "Ops", "D. Lead", "Open", "06/01/2026", "Successful", None),
    ("TBC", "Ledger Sync", "Lending", "E. Lead", "open", None, "successful", "DR test completed on 1st of June 2026"),
]


def workbook(rows=ROWS, header=HEAD):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    s = tmp_path / "settings.json"
    s.write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(s))


@pytest.mark.parametrize("text,want", [
    ("DR Test completed on 14th March 2026", "2026-03-14"),
    ("DR Test Completed on 3rd April 2026", "2026-04-03"),
    ("dr test completed on 1st of June 2026", "2026-06-01"),
    ("DR Test completed on 22nd September, 2026", "2026-09-22"),
    ("TTX: Tabletop exercise completed", None),
    ("", None)])
def test_comment_date(text, want):
    d = dr_tests.comment_date(text)
    assert (d.date().isoformat() if d else None) == want


def test_rows_are_read_and_listed():
    r = dr_tests.read(workbook())
    rows = {x["application_name"]: x for x in r["rows"]}
    assert len(r["rows"]) == 5 and r["set_aside"][0]["reason"] == "no Name"
    pg = rows["Payments Gateway"]
    assert (pg["tier_label"], pg["test_type"], pg["kind"], pg["environment"], pg["status"], pg["performed_on"]) == \
        ("Tier 0", "Open", "DR test", "Production (live)", "Successful", "2026-03-14")
    ca = rows["Card Authoriser"]                                    # Closed, blank Status
    assert (ca["kind"], ca["environment"], ca["status"], ca["performed_on"]) == \
        ("DR test", "Non-production (UAT, test)", "Not performed", None)
    assert ca["business_area"] is None and ca["comment_date"] == "2026-04-02"
    rf = rows["Rates Feed"]                                         # TTX: not a DR test, dated by When
    assert (rf["kind"], rf["environment"], rf["performed_on"], rf["ttx_in_comment"]) == \
        ("Tabletop exercise", None, "2026-05-20", True)
    ls = rows["Ledger Sync"]                                        # DR test dated by its comment, not When
    assert (ls["tier_label"], ls["kind"], ls["status"], ls["test_date"], ls["performed_on"]) == \
        ("TBC", "DR test", "Successful", None, "2026-06-01")
    ua = rows["Unknown App"]
    assert ua["kind"] is None and ua["performed_on"] is None
    notes = " | ".join(r["notes"])
    assert "Type of Test 'Live failover' isn't Open, Closed or TTX (Unknown App); kept as written" in notes
    assert "Status 'Failed' isn't Successful or blank (Unknown App); kept as written, not counted as performed" in notes
    assert "When '13/45/2026' isn't a date" in notes
    assert "1 row has a blank Status (not performed) but a comment saying completed (Card Authoriser)" in notes
    assert "1 row has no Status: not performed" in notes
    s = r["summary"]
    assert (s["dr_tests"], s["dr_tests_performed"], s["tabletop_exercises"], s["tabletop_exercises_performed"],
            s["not_performed"]) == (3, 2, 1, 1, 1)
    assert s["by_type"] == {"Open": 2, "Closed": 1, "TTX": 1, "Live failover": 1}


def test_dates_and_type_problems_are_listed():
    r = dr_tests.read(workbook([
        ("Tier 0", "A", "x", "L", "Open", "03/15/2026", "Successful", "Restored fine"),
        ("Tier 0", "B", "x", "L", "TTX", None, "Successful", "TTX: Tabletop exercise completed"),
        ("Tier 0", "C", "x", "L", "Closed", "03/15/2026", "Successful", "TTX: Tabletop exercise completed"),
        ("Tier 0", "D", "x", "L", None, "03/15/2026", "Successful", None)]))
    notes = " | ".join(r["notes"])
    assert "2 successful DR tests have no completed date in the comment, so when it was performed isn't known (A, C)" in notes
    assert "1 successful tabletop exercise has no date in When (B)" in notes
    assert "Type of Test and comment disagree for 1 row: C (Closed, comment: 'TTX: Tabletop exercise completed')" in notes
    assert "1 row has no Type of Test (D); counted as neither" in notes


def test_uploads_alone_then_links_to_itdr_by_name():
    from test_itdr import workbook as itdr_workbook
    e = store.upload("dr_tests", "2026-10", workbook(), "DR tests.xlsx", "Tester")
    assert e["checks"]["rows"] == 5
    assert [t["application_name"] for t in storage.dr_tests("2026-10")][:2] == ["Payments Gateway", "Card Authoriser"]
    r = mapping.map_month("2026-10")
    assert "linked_to_applications" not in r["feeds"]["dr_tests"]      # alone: nothing to link to, still maps
    store.upload("itdr", "2026-10", itdr_workbook(), "ITDR apps.xlsx", "Tester")
    store.upload("hr_mapping", "2026-10", b"Product Family,Owner Email(s),Band\nPayments,a@x.com,product\nCards,b@x.com,product\n",
                 "owners.csv", "Tester")
    m = mapping.map_month("2026-10")
    link = m["feeds"]["dr_tests"]["linked_to_applications"]
    assert m["feeds"]["itdr"]["families"] == {"placed": 3, "not_placed": 5, "exact": 3, "fuzzy": 0,
                                              "by_family_name": 3, "by_department": 0}          # Refs 1 and 9 Payments, Ref 2 Cards
    apps = {a["ref"]: a for a in m["feeds"]["itdr"]["rows"]}
    assert apps[1]["family_id"] == "payments" and apps[2]["family_id"] == "cards" and apps[4]["family_id"] is None
    assert any("isn't close enough to a family name or an HR department: 'Lending' (Ref 4)" in n for n in m["feeds"]["itdr"]["notes"])
    tests = {t["application_name"]: t for t in m["feeds"]["dr_tests"]["rows"]}
    assert tests["Payments Gateway"]["family_id"] is None        # name on Refs 1 and 9: can't tell which, not guessed
    assert tests["Card Authoriser"]["family_id"] == "cards"
    assert link["matched"] == 4 and link["not_matched"] == ["Unknown App"]
    assert link["tier_differs"] == ["Rates Feed (Tier 1 here, TBC in the ITDR application file)",
                                    "Ledger Sync (TBC here, Tier 2 in the ITDR application file)"]


def test_junk_is_refused():
    with pytest.raises(ValueError, match="Not uploaded"):
        store.upload("dr_tests", "2026-10", b"Colour,Size\nred,1\n", "wrong.csv", "Tester")
