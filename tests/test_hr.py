"""HR reader: firm-wide file, only the CTO's reporting line kept, no other file needed."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust.intake import hr  # noqa: E402

RAW = (pathlib.Path(__file__).parent / "fixtures" / "hr_firmwide.csv").read_bytes()


def kept(root="dcto"):
    return {p["sam_account"]: p for p in hr.read(RAW, root)["people"]}


def test_only_the_cto_line_is_kept():
    assert set(kept()) == {"dcto", "amoreno", "slee", "pkim"}   # CEO, Finance and the broken link are left out


def test_same_name_resolved_by_level_and_org():
    assert kept()["pkim"]["manager_sam"] == "slee"              # not slee2 in Finance


def test_root_is_case_insensitive_and_has_no_manager():
    p = kept("DcTo")
    assert "dcto" in p and p["dcto"]["manager_sam"] is None


def test_notes_explain_what_was_left_out():
    r = hr.read(RAW, "dcto")
    text = " ".join(r["notes"])
    assert "used column 'Workers Manger' for 'Workers Manager'" in text   # a misspelt header is matched and shown
    assert "differs from the name" not in text                  # leaders named in their own team are fine
    assert "jray" in text                                       # broken manager link listed
    assert "slee: work email blank or not an email" in text
    assert {s.get("sam") for s in r["set_aside"]} == {"dup1"}   # duplicate SAM_ACCOUNT set aside
    assert r["summary"]["kept"] == 4 and r["summary"]["rows_in_file"] == 10


def test_no_setting_or_unknown_cto_loads_nobody_but_does_not_refuse():
    assert hr.read(RAW, "")["people"] == []
    r = hr.read(RAW, "nobody")
    assert r["people"] == [] and "not in this file" in r["notes"][-1]


def test_left_out_columns_are_not_returned():
    p = kept()["amoreno"]
    assert "Location Address - Country" not in p and "Department" not in p   # minimisation


def test_column_name_can_be_changed_in_the_settings_file(tmp_path, monkeypatch):
    """A column TRUST can't guess ('Login ID' for SAM_ACCOUNT) works once added to config/column_maps.json."""
    renamed = RAW.replace(b"SAM ACCOUNT", b"Login ID", 1)
    assert hr.read(renamed, "dcto")["people"] == []            # not guessable: nobody can be keyed
    maps = tmp_path / "column_maps.json"
    maps.write_text('{"HR": {"sam_account": ["Login ID"],},}')  # any case; trailing commas fine
    monkeypatch.setenv("TRUST_COLUMN_MAPS", str(maps))
    assert {p["sam_account"] for p in hr.read(renamed, "dcto")["people"]} == {"dcto", "amoreno", "slee", "pkim"}


def test_headers_in_any_case():
    """ALL CAPS and all lower case headers read the same as the original."""
    head, rest = RAW.split(b"\n", 1)
    for h in (head.upper(), head.lower()):
        assert len(hr.read(h + b"\n" + rest, "dcto")["people"]) == 4


def test_sam_column_is_the_one_ending_in_sam_acct(tmp_path, monkeypatch):
    """Owner, 3 Nov 2026: the HR column whose name ends in SAM_Acct is the SAM_ACCOUNT, even next to an Employee ID."""
    from trust import store
    from trust.intake.common import match_name
    head, rest = RAW.decode().split("\n", 1)
    raw = (head.replace("SAM ACCOUNT", "Worker_SAM_Acct") + ",Employee ID\n"
           + "\n".join(line + ",E123" for line in rest.splitlines() if line) + "\n").encode()
    assert {p["sam_account"] for p in hr.read(raw, "dcto")["people"]} == set(kept())
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    e = store.upload("hr", "2026-10", raw, "hr.csv", "Tester")         # kept at upload, not dropped
    assert e["checks"]["rows"] == len(kept())
    assert match_name("SAM_ACCOUNT", ["A_SAM_Acct", "B_SAM_Acct"], ("*SAM_Acct",)) == (None, "tie")
