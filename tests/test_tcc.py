"""TCC reader: 33-column export, any date format, codes in any case, no other file needed."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust.intake import tcc  # noqa: E402

RAW = (pathlib.Path(__file__).parent / "fixtures" / "tcc_export.csv").read_bytes()


def by_id():
    return {x["ticket_id"]: x for x in tcc.read(RAW)["rows"]}


def test_loads_and_sets_aside_bad_and_duplicate_ids():
    r = tcc.read(RAW)
    assert r["summary"]["tickets"] == 6 and r["summary"]["set_aside"] == 2
    assert {s["reason"] for s in r["set_aside"]} == {"Ticket ID blank or not a number", "same Ticket ID twice; first kept"}
    assert r["no_data_metrics"] == []


def test_dates_in_several_formats_and_months():
    x = by_id()
    assert x["1001"]["deploy_month"] == "2026-10"         # 7-digit fraction
    assert x["1004"]["deploy_month"] == "2026-09"         # 'YYYY-MM-DD HH:MM:SS'
    # Owner, 2 Nov: counted in the month the ticket was created (28 Sep), not deployed (1 Oct)
    assert x["1001"]["month"] == "2026-09" and x["1001"]["month_from"] == "Created date"
    assert x["1005"]["month"] is None                       # not deployed
    # TE-02 (owner, 2 Nov): a release counts in the month its 7-day window ends (last deployment + 7 days)
    assert x["1004"]["te02_month"] == "2026-09"             # deployed 15 Sep -> window ends 22 Sep
    assert x["1001"]["te02_month"] == "2026-10"             # deployed 1 Oct -> window ends 8 Oct
    assert x["1005"]["te02_month"] is None


def test_blank_created_date_falls_back_to_last_deployment():
    lines = RAW.decode().splitlines()
    lines = [",".join(c if i != 6 else "" for i, c in enumerate(l.split(","))) if l.startswith("1006,") else l
             for l in lines]                               # blank column 7, Created date
    raw = "\n".join(lines).encode()
    r = tcc.read(raw)
    x = {t["ticket_id"]: t for t in r["rows"]}
    assert x["1006"]["month"] == "2026-10" and x["1006"]["month_from"] == "last deployment"
    assert any("no Created date" in n and "1006" in n for n in r["notes"])
    assert x["1005"]["deployed"] is False                 # blank = not deployed


def test_flags_for_te01_and_te02():
    x = by_id()
    assert x["1001"]["approved_before_deploy"] is True
    assert x["1002"]["approved_before_deploy"] is False and x["1002"]["revert"] is True   # approved after deploying
    assert x["1003"]["approved_before_deploy"] is True    # Standard counts as approved
    assert x["1004"]["client_impact"] and x["1004"]["revert"]   # '90 FAIL backout…' read as 90
    assert x["1006"]["outcome_unknown"] and not x["1006"]["approved_before_deploy"]   # REJECTED
    assert x["1002"]["status"] == "Completed" and x["1002"]["category"] == "Planned"   # any case


def test_email_lower_cased_and_bad_date_noted():
    r = tcc.read(RAW)
    assert by_id()["1001"]["author_email"] == "alex.moreno@example.com"
    assert any("'Planned start' that isn't a date" in n and "1006" in n for n in r["notes"])


def test_missing_column_means_no_data_not_refusal():
    raw = RAW.replace(b"Overall outcome,", b"Something else,", 1)
    r = tcc.read(raw)
    assert r["no_data_metrics"] == ["TE-02"] and r["summary"]["tickets"] == 6
    assert any("TE-02 will show No data" in n for n in r["notes"])


def test_confirmed_names_in_any_capitals_read_the_same():
    """Owner, 3 Nov 2026: the confirmed column names (RPD ID, RPD Link, Actual Last Deployment, ...) and
    every value are matched whatever their capitals; known values come out in one standard spelling."""
    import csv
    import io
    names = {"Ticket ID": "RPD ID", "Ticket Link": "RPD Link", "last deployment": "Actual Last Deployment",
             "Planned start": "Planned Start", "Planned end": "Planned End",
             "confirmed risk rating": "Confirmed Risk Rating", "overall change approval": "Overall Change Approval",
             "peer review recorded at (UTC)": "Peer Review Recorded At (UTC)",
             "Approval recorded at (UTC)": "Approval Recorded At (UTC)",
             "Outcome recorded at (UTC)": "Outcome Recorded At (UTC)"}
    raw = RAW.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(raw)))
    header = [names.get(h, h) for h in rows[0]]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([h.upper() for h in header])                     # names in capitals
    for r in rows[1:]:
        w.writerow([v.lower() if not v.startswith("http") else v for v in r])   # values in small letters
    before, after = tcc.read(raw.encode()), tcc.read(out.getvalue().encode())
    assert after["summary"] == before["summary"]
    assert not any("No data" in n for n in after["notes"])
    first = after["rows"][0]
    assert (first["status"], first["category"], first["risk_score"], first["resolved"]) == \
        ("Completed", "Planned", "LOW risk", "Yes")
    assert first["pre_deploy_compliant"] == "Yes" and first["fully_compliant"] == "Yes"
