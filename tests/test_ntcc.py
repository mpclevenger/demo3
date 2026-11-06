"""Non-TCC reader: 12 columns, loads alone, working rules marked; counted once if also in TCC."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import mapping, store  # noqa: E402
from trust.intake import ntcc  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
R = ntcc.read((FIX / "ntcc_export.csv").read_bytes())
X = {x["rpd_id"]: x for x in R["rows"]}


def test_loads_and_sets_aside():
    assert R["summary"]["changes"] == 4 and R["summary"]["set_aside"] == 2
    assert R["summary"]["deployed"] == 3                          # Completed, MONITORING, Resolved (any case)


def test_working_rules_are_applied_and_labelled():
    # created 28 Sep, last updated 2 Oct -> September, by Created Date (Q-NTCC-01, owner 2 Nov)
    assert X["5001"]["deployed"] and X["5001"]["month"] == "2026-09" and X["5001"]["approved"] is False
    assert X["5001"]["month_from"] == "Created Date"
    assert not X["5002"]["deployed"] and X["5002"]["month"] is None   # queued = not deployed (Q-NTCC-02)
    assert X["5003"]["last_updated"].startswith("2026-10-20T09:15:00.123")   # shared date reader
    assert X["5003"]["month"] == "2026-10"
    assert any("Q-NTCC-01" in n and "Q-NTCC-02" in n for n in R["notes"])
    assert X["5003"]["author_email"] is None and any("5003" in n for n in R["notes"])


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))


def test_change_in_both_files_is_counted_once_as_tcc(tmp_store):
    for feed, name in (("ntcc", "ntcc_export.csv"), ("tcc", "tcc_export.csv"), ("hr", "hr_firmwide.csv"),
                       ("hr_mapping", "family_owners.csv")):
        store.upload(feed, "2026-10", (FIX / name).read_bytes(), name, "Tester")
    r = mapping.map_month("2026-10")
    n = {x["rpd_id"]: x for x in r["feeds"]["ntcc"]["rows"]}
    assert n["1001"]["also_in_tcc"] and not n["5001"]["also_in_tcc"]
    assert any("counted once, as TCC: 1001" in s for s in r["feeds"]["ntcc"]["notes"])
    assert n["5001"]["family_id"] == "payments"                   # Author Email -> HR -> nearest owner
    t = {x["ticket_id"]: x for x in r["feeds"]["tcc"]["rows"]}
    assert t["1003"]["family_id"] == "cards"                      # TCC Author -> Pat Kim -> Cards


def test_blank_created_date_falls_back_to_last_updated():
    csv = (FIX / "ntcc_export.csv").read_bytes().replace(b"10/05/2026,10/20/2026", b",10/20/2026")
    X = {x["rpd_id"]: x for x in ntcc.read(csv)["rows"]}
    assert X["5003"]["month"] == "2026-10" and X["5003"]["month_from"] == "Last updated"
