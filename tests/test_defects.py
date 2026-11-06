"""The Jira issues file (feed "defects"; owner, 3 Nov 2026): team = the person who closed the issue.

Also runs tools/jira_export.py against a made-up Jira Data Center answer and feeds its file to the reader.
The rows here are made up for the tests (synthetic data stays in tests).
"""
import csv
import io
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))
from trust import mapping, store  # noqa: E402
from trust.intake import defects  # noqa: E402

COLS = list(defects.FIELDS)


def row(key, **kw):
    base = dict(project="PAY", issue_type="Bug", is_defect="True", priority="High", status="Done",
                status_category="done", resolution="Fixed", created_at="2026-10-01T10:00:00.000-0400",
                first_in_progress_at="2026-10-02T10:00:00.000-0400", resolved_at="2026-10-11T10:00:00.000-0400",
                closed_by="A Moreno", closed_by_email="AMoreno@example.com", closed_by_username="amoreno",
                reopen_count="0", story_points="")
    return {"issue_key": key, **base, **kw}


def csv_bytes(rows, cols=COLS):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue().encode()


OPEN = dict(status="In Progress", status_category="indeterminate", resolution="", resolved_at="", closed_by="",
            closed_by_email="", closed_by_username="")
ROWS = [
    row("PAY-1"),                                                        # 10 days, Payments by email
    row("PAY-2", reopen_count="2", created_at="2026-10-05T10:00:00.000-0400"),     # reopened, 6 days
    row("PAY-3", issue_type="Story", is_defect="False", story_points="5",
        closed_by_email="old@example.com", closed_by_username="SLEE"),   # Cards by username = SAM_ACCOUNT
    row("PAY-4", closed_by_email="nobody@example.com", closed_by_username="nobody"),   # Not yet mapped
    row("PAY-5", created_at="2026-09-01T10:00:00.000-0400", resolved_at="2026-09-20T10:00:00.000-0400"),  # Sept
    row("PAY-6", created_at="2026-10-20T10:00:00.000-0400", **OPEN),     # opened in Oct, still open
    row("PAY-7", created_at="2026-09-10T10:00:00.000-0400", resolved_at="2026-11-02T10:00:00.000-0500"),  # open at end
    row(""),                                                              # set aside: no key
    row("PAY-1"),                                                         # set aside: repeated
]
PEOPLE = [{"sam_account": "amoreno", "email": "amoreno@example.com"}, {"sam_account": "slee", "email": "slee@example.com"}]
FAMS = {"amoreno": "payments", "slee": "cards"}


def test_read_keeps_rows_and_sets_aside():
    r = defects.read(csv_bytes(ROWS))
    assert r["summary"] == {"issues": 7, "defects": 6, "closed": 6, "set_aside": 2}
    assert [a["reason"] for a in r["set_aside"]] == ["no issue_key", "issue 'PAY-1' is on more than one row; first kept"]
    assert r["rows"][0]["closed_by_email"] == "amoreno@example.com"            # read in any capitals


def test_defect_from_issue_type_when_no_flag():
    r = defects.read(csv_bytes([row("X-1", is_defect=""), row("X-2", is_defect="", issue_type="Task")]))
    assert [x["is_defect"] for x in r["rows"]] == [True, False]


def test_closer_places_the_issue_and_figures():
    r = defects.read(csv_bytes(ROWS))
    out = defects.place_and_measure(r["rows"], "2026-10", PEOPLE, FAMS)
    by = {x["issue_key"]: x for x in r["rows"]}
    assert (by["PAY-1"]["family_id"], by["PAY-1"]["closer_matched_by"]) == ("payments", "email")
    assert (by["PAY-3"]["family_id"], by["PAY-3"]["closer_matched_by"]) == ("cards", "username = SAM_ACCOUNT")
    assert by["PAY-4"]["family_id"] == "UNATTRIBUTED"
    assert "family_id" not in by["PAY-5"]                                      # closed in September
    pay = out["families"]["payments"]
    assert (pay["issues_closed"], pay["defects_closed"], pay["defects_reopened"]) == (2, 2, 1)
    assert (pay["median_lead_time_days"], pay["median_cycle_time_days"]) == (8.0, 9.0)
    assert out["families"]["cards"] == {"issues_closed": 1, "defects_closed": 0, "defects_reopened": 0,
                                        "story_points_closed": 5.0, "median_lead_time_days": 10.0,
                                        "median_cycle_time_days": 9.0, "median_defect_resolution_days": None}
    # opened in Oct: PAY-1, 2, 4, 6 (PAY-3 is a story); open at end of Oct: PAY-6 and PAY-7
    assert out["firm"] == {"defects_opened": 4, "defects_open_at_month_end": 2, "issues_closed": 4, "defects_closed": 3}
    assert out["unmatched"] == 1 and any("Not yet mapped: PAY-4" in n for n in out["notes"])


def test_month_with_nothing_closed_says_so():
    r = defects.read(csv_bytes([row("PAY-1")]))
    out = defects.place_and_measure(r["rows"], "2026-08", PEOPLE, FAMS)
    assert any("No issue in the file was closed in 2026-08" in n for n in out["notes"])


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    s = tmp_path / "settings.json"
    s.write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(s))


def test_uploads_on_its_own_and_maps(tmp_store):
    extra = COLS + ["summary", "lead_time_days"]                  # columns TRUST doesn't use are dropped
    e = store.upload("defects", "2026-10", csv_bytes(ROWS, extra), "jira_issues.csv", "Tester")
    assert e["checks"]["rows"] == 7 and e["checks"]["set_aside"] == 2
    m = mapping.map_month("2026-10")["feeds"]["defects"]
    assert m["figures"]["families"].keys() == {"UNATTRIBUTED"}    # no HR: all Not yet mapped
    assert m["figures"]["firm"]["defects_closed"] == 3
    with pytest.raises(ValueError, match="Not uploaded"):
        store.upload("defects", "2026-10", b"Colour,Size\nred,1\n", "wrong.csv", "Tester")


# ---- tools/jira_export.py against a made-up Jira Data Center answer -----------------------------------

def test_export_script_data_center_to_reader(tmp_path, monkeypatch):
    import jira_export as je
    st = lambda i, k, n: {"id": i, "name": n, "statusCategory": {"key": k}}
    statuses = [st("1", "new", "Open"), st("3", "indeterminate", "In Progress"), st("5", "done", "Done")]
    names = {s["id"]: s["name"] for s in statuses}
    who = lambda n: {"displayName": n.title(), "name": n, "emailAddress": f"{n}@example.com"}
    hist = lambda t, a, f, to: {"created": t, "author": who(a), "items": [
        {"field": "status", "from": f, "to": to, "fromString": names[f], "toString": names[to]}]}
    issue = {"key": "PAY-1", "fields": {
        "issuetype": {"name": "Bug"}, "project": {"key": "PAY"}, "summary": "s", "priority": {"name": "High"},
        "status": statuses[2], "resolution": {"name": "Fixed"}, "created": "2026-10-01T10:00:00.000-0400",
        "resolutiondate": "2026-10-11T10:00:00.000-0400", "assignee": who("bob"), "reporter": who("bob"),
        "labels": [], "components": [], "fixVersions": [], "issuelinks": []},
        "changelog": {"total": 4, "histories": [
            hist("2026-10-02T10:00:00.000-0400", "bob", "1", "3"), hist("2026-10-05T10:00:00.000-0400", "bob", "3", "5"),
            hist("2026-10-06T10:00:00.000-0400", "bob", "5", "3"),
            hist("2026-10-11T10:00:00.000-0400", "amoreno", "3", "5")]}}
    calls = []

    class Resp:
        status_code, headers = 200, {}

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

        def raise_for_status(self):
            pass

    def fake_get(self, url, params=None, timeout=None):
        calls.append((url, self.headers.get("Authorization")))
        if url.endswith("/rest/api/2/status"):
            return Resp(statuses)
        if url.endswith("/rest/api/2/search"):
            return Resp({"issues": [issue], "total": 1})
        raise AssertionError(url)

    monkeypatch.setattr(je.requests.Session, "get", fake_get)
    monkeypatch.setenv("JIRA_URL", "https://jira.example")
    monkeypatch.setenv("JIRA_TOKEN", "pat")
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.setattr(sys, "argv", ["jira_export.py", "--jql", "project = PAY", "--out", str(tmp_path)])
    assert je.main() == 0
    assert calls[0][1] == "Bearer pat"                          # Data Center by default, personal access token
    r = defects.read((tmp_path / "jira_issues.csv").read_bytes())
    x = r["rows"][0]
    assert (x["closed_by_username"], x["reopen_count"], x["is_defect"]) == ("amoreno", 1, True)   # the last closer
    out = defects.place_and_measure(r["rows"], "2026-10", PEOPLE, FAMS)
    assert out["families"]["payments"]["defects_reopened"] == 1
