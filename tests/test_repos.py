"""The GitHub repo file (owner, 3 Nov 2026): 5 hygiene checks, partial score, owner from committers via HR.

The rows here are made up for the tests (synthetic data stays in tests).
"""
import csv
import io
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import mapping, store  # noqa: E402
from trust.intake import repos  # noqa: E402

COLS = list(repos.FIELDS)
GOOD = dict(Archived="False", Fork="False", Empty="False", DefaultBranch="main", PushedAt="2026-10-20T10:00:00Z",
            LastDefaultBranchCommit="2026-10-20T10:00:00Z", ProtectionSource="branch protection",
            BranchProtected="True", RequiredApprovals="1", LastPushApprovalRequired="True",
            ForcePushAllowed="False", DeletionsAllowed="False", AdminEnforced="True", BypassAllowed="False",
            StaleReviewsDismissed="True", CodeOwnerReviewRequired="False", StatusChecksRequired="True",
            CodeOwnersFile="True", LastHumanCommitterEmail="amoreno@example.com", LastHumanCommitterLogin="amoreno",
            LastHumanCommitDate="2026-10-20T10:00:00Z", TopCommitterEmail="amoreno@example.com",
            TopCommitterLogin="amoreno", TopCommitterShare="1.0", HumanCommitsSampled="5")


def row(name, **kw):
    return {"Repo": name, "Url": f"https://ghe.example/{name}", **GOOD, **kw}


def csv_bytes(rows):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=COLS)
    w.writeheader()
    w.writerows(rows)
    return out.getvalue().encode()


ROWS = [
    row("all-good"),                                                         # 5/5
    row("no-protection", BranchProtected="False", RequiredApprovals="0", ProtectionSource="none",
        LastPushApprovalRequired="False", ForcePushAllowed="True", DeletionsAllowed="True",
        AdminEnforced="False"),                                              # 0/5
    row("no-independent", LastPushApprovalRequired="False"),                 # 4/5
    row("admins-bypass", AdminEnforced="False", ForcePushAllowed="True"),    # 3/5
    row("archived", Archived="True"),
    row("old", PushedAt="2026-01-01T00:00:00Z", LastDefaultBranchCommit="2026-01-01T00:00:00Z"),
    row("someone-else", TopCommitterEmail="nobody@example.com", TopCommitterLogin="nobody"),
    row("by-login", TopCommitterEmail="old.address@example.com", TopCommitterLogin="SLEE"),
]


def test_checks_and_scores():
    r = repos.read(csv_bytes(ROWS))
    by = {x["repo"]: x for x in r["rows"]}
    assert by["all-good"]["passed"] == 5 and by["all-good"]["score"] == 100.0
    assert by["no-protection"]["passed"] == 0                         # 2-5 are settings of the protection
    assert by["no-independent"]["passed"] == 4 and by["no-independent"]["score"] == 80.0
    assert by["admins-bypass"]["checks"] == {"protected": True, "review": True, "independent": True,
                                             "history": False, "no_bypass": False}
    assert by["all-good"]["info"] == {"codeowners": True, "status_checks": True, "stale_dismissed": True}
    assert r["summary"]["unprotected"] == 1


def test_blank_settings_count_as_not_set_and_are_listed():
    r = repos.read(csv_bytes([row("blank", AdminEnforced="")]))
    assert r["rows"][0]["checks"]["no_bypass"] is False
    assert any("no value in AdminEnforced" in n for n in r["notes"])


def test_placement_and_family_figures():
    r = repos.read(csv_bytes(ROWS))
    people = [{"sam_account": "amoreno", "email": "amoreno@example.com"},
              {"sam_account": "slee", "email": "slee@example.com"}]
    fams = {"amoreno": "payments", "slee": "cards"}
    out = repos.place_and_score(r["rows"], "2026-10", people, fams, {"repo_match_by": "email_then_login"})
    by = {x["repo"]: x for x in r["rows"]}
    assert by["by-login"]["family_id"] == "cards" and by["by-login"]["owner_matched_by"] == "login = SAM_ACCOUNT"
    assert by["all-good"]["owner_matched_by"] == "email"
    assert by["someone-else"]["family_id"] == "UNATTRIBUTED" and by["someone-else"]["active"]
    assert (by["archived"]["inactive_reason"], by["old"]["inactive_reason"]) == ("archived", "no activity")
    pay = out["families"]["payments"]
    # all-good 5 + no-protection 0 + no-independent 4 + admins-bypass 3 = 12 of 20
    assert (pay["repos"], pay["checks_passed"], pay["checks_possible"], pay["score"]) == (4, 12, 20, 60.0)
    assert pay["unprotected"] == ["no-protection"] and pay["fails"]["independent"] == 2
    assert out["families"]["cards"]["score"] == 100.0
    assert out["unmatched_active"] == 1
    assert any("Not yet mapped: someone-else" in n for n in out["notes"])


def test_email_only_by_default():
    """Owner, 4 Nov 2026: GitHub owners are found in HR by email address only."""
    r = repos.read(csv_bytes(ROWS))
    people = [{"sam_account": "amoreno", "email": "amoreno@example.com"},
              {"sam_account": "slee", "email": "slee@example.com"}]
    out = repos.place_and_score(r["rows"], "2026-10", people, {"amoreno": "payments", "slee": "cards"}, {})
    by = {x["repo"]: x for x in r["rows"]}
    assert by["by-login"]["family_id"] == "UNATTRIBUTED" and by["by-login"]["owner_matched_by"] is None
    assert by["all-good"]["family_id"] == "payments" and out["match_by"] == "email"
    assert any("couldn't match to HR by email address" in n for n in out["notes"])


def test_no_human_committer_note_gives_reasons_and_counts():
    blank = dict(LastHumanCommitterEmail="", LastHumanCommitterLogin="", TopCommitterEmail="", TopCommitterLogin="")
    rows = [row(f"empty{i}", Empty="true", **blank) for i in range(7)] + [row("bots", **blank)]
    note = next(n for n in repos.read(csv_bytes(rows))["notes"] if "no human committer" in n)
    assert note.startswith("8 repos have no human committer")
    assert "7 empty (no commits) (e.g. empty0, empty1, empty2, empty3, empty4, and 2 more)" in note
    assert "1 only bots or service accounts in the last 20 commits (e.g. bots)" in note


def test_owner_rule_setting():
    rows = [row("x", LastHumanCommitterEmail="slee@example.com", LastHumanCommitterLogin="slee",
                TopCommitterEmail="amoreno@example.com", TopCommitterLogin="amoreno")]
    people = [{"sam_account": "amoreno", "email": "amoreno@example.com"},
              {"sam_account": "slee", "email": "slee@example.com"}]
    fams = {"amoreno": "payments", "slee": "cards"}
    last = repos.read(csv_bytes(rows))["rows"]
    repos.place_and_score(last, "2026-10", people, fams, {"repo_owner_rule": "last_commit"})
    most = repos.read(csv_bytes(rows))["rows"]
    repos.place_and_score(most, "2026-10", people, fams, {})          # default (owner, 3 Nov 2026): most commits
    assert (last[0]["family_id"], most[0]["family_id"]) == ("cards", "payments")


def test_bulk_committer_is_flagged():
    rows = [row(f"r{i}") for i in range(3)]
    r = repos.read(csv_bytes(rows))["rows"]
    out = repos.place_and_score(r, "2026-10", [{"sam_account": "amoreno", "email": "amoreno@example.com"}],
                                {"amoreno": "payments"}, {"repo_owner_flag_count": 3})
    assert any("amoreno is the owner of 3 active repos" in n for n in out["notes"])


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    s = tmp_path / "settings.json"
    s.write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(s))


def test_uploads_on_its_own_and_maps(tmp_store):
    e = store.upload("repos", "2026-10", csv_bytes(ROWS), "repos.csv", "Tester")
    assert e["checks"]["rows"] == 8
    m = mapping.map_month("2026-10")["feeds"]["repos"]
    assert m["hygiene"]["families"] == {} and m["hygiene"]["unmatched_active"] == 6   # no HR: all Not yet mapped
    with pytest.raises(ValueError, match="Not uploaded"):
        store.upload("repos", "2026-10", b"Colour,Size\nred,1\n", "wrong.csv", "Tester")
