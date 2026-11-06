"""Checkmarx reader: works on the owner's samples as pasted, with no other file loaded."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust.intake import checkmarx  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"


def load(name, kind):
    return checkmarx.read((FIX / name).read_bytes(), kind)


def test_sast_sample_loads_with_trailing_commas():
    r = load("final_checkmarx_sast_report.json", "SAST")
    assert r["summary"] == dict(repos=3, passing=2, failing=1, set_aside=0)
    fail = next(x for x in r["rows"] if x["key"] == "reponame2/anothername2")
    assert fail["overdue_by_severity"] == {"CRITICAL": 2, "MEDIUM": 8}   # comma-separated violations
    assert fail["overdue_ech"] == 2
    assert fail["note"] == "value disagrees with the comment; the comment decides"


def test_sca_sample_loads_on_its_own():
    r = load("final_checkmarx_sca_report 1.json", "SCA")
    assert r["summary"]["repos"] == 3 and r["summary"]["failing"] == 1


def test_case_and_spelling_variants():
    assert checkmarx.read_comment("non-compliant 3/9 sca findings EXCEED their aging thresholds. Violations: 1 high; 2 low")[0] is False
    assert checkmarx.read_comment("compliant.  no sast findings detected")[:2] == (True, 0)


def test_unreadable_file_is_the_only_refusal():
    try:
        checkmarx.read(b"not json at all", "SCA")
    except ValueError as e:
        assert "can't be read" in str(e)
    else:
        raise AssertionError("expected a refusal")


def test_json_field_names_in_any_case():
    raw = (FIX / "final_checkmarx_sast_report.json").read_bytes()
    for k in (b'"key"', b'"measurements"', b'"comment"', b'"value"', b'"data"'):
        raw = raw.replace(k, k.upper())
    assert checkmarx.read(raw, "SAST")["summary"]["repos"] == 3


def test_as_of_is_the_upload_date():
    raw = (FIX / "final_checkmarx_sast_report.json").read_bytes()
    r = checkmarx.read(raw, "SAST", uploaded_at="11/03/2026 09:15:00 AM")
    assert r["as_of"] == "2026-11-03T09:15:00-05:00" and r["as_of_source"] == "upload date"
    assert checkmarx.read(raw, "SAST")["as_of"]            # no upload time given: now


def test_report_date_in_file_wins_when_given():
    raw = (FIX / "final_checkmarx_sast_report.json").read_bytes().replace(
        b'"importer"', b'"report_as_of": "10/31/2026 11:59:00.123 PM",\n"importer"', 1)
    r = checkmarx.read(raw, "SAST", uploaded_at="2026-11-03T09:15:00")
    assert r["as_of"] == "2026-10-31T23:59:00.123000-04:00" and r["as_of_source"] == "report date in the file"


def test_unreadable_report_date_falls_back_to_upload_date():
    raw = (FIX / "final_checkmarx_sast_report.json").read_bytes().replace(
        b'"importer"', b'"report_as_of": "end of month",\n"importer"', 1)
    r = checkmarx.read(raw, "SAST", uploaded_at="2026-11-03T09:15:00")
    assert r["as_of"] == "2026-11-03T09:15:00-05:00" and r["as_of_source"] == "upload date"
    assert any("isn't a date; the upload date is used" in n for n in r["notes"])
