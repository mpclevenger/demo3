"""Checkmarx repos tied to GitHub repos by name, so SE-01 / SE-02 reach families (owner, 4 Nov 2026)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import measure  # noqa: E402
from trust.intake import repos  # noqa: E402

GH = [{"repo": "payments-eng/ledger-api", "family_id": "payments"},
      {"repo": "cards-eng/card_service", "family_id": "cards"},
      {"repo": "payments-eng/common", "family_id": "payments"},
      {"repo": "cards-eng/common", "family_id": "cards"},
      {"repo": "misc/orphan", "family_id": "UNATTRIBUTED"}]


def cx(key, ok=True):
    return {"key": key, "compliant": ok, "overdue_ech": 0, "comment": ""}


def test_matching_order_and_families():
    rows = [cx("payments-eng/ledger-api"),            # same full name
            cx("leading/ledger-api", False),          # leading/reponame -> same repo name
            cx("https://ghe.example.com/cards-eng/card_service.git"),   # web address and .git tidied
            cx("team/card-service"),                  # close spelling ('-' vs '_')
            cx("cards-eng/common"),                   # same name in two orgs, settled by the full name
            cx("other/common"),                       # same name in two orgs, can't tell: not guessed
            cx("misc/orphan"),                        # matched, but its owner has no family
            cx("nothing/like-it")]
    out = repos.match_checkmarx(rows, GH)
    by = {r["key"]: r for r in rows}
    assert by["payments-eng/ledger-api"]["matched_by"] == "exact" and by["payments-eng/ledger-api"]["family_id"] == "payments"
    assert by["leading/ledger-api"]["matched_by"] == "repo name" and by["leading/ledger-api"]["gh_repo"] == "payments-eng/ledger-api"
    assert by["https://ghe.example.com/cards-eng/card_service.git"]["matched_by"] == "exact"
    assert by["team/card-service"]["matched_by"] == "close spelling" and by["team/card-service"]["family_id"] == "cards"
    assert by["cards-eng/common"]["family_id"] == "cards"
    assert by["other/common"]["family_id"] == "UNATTRIBUTED" and out["shared"] == ["other/common"]
    assert by["misc/orphan"]["family_id"] == "UNATTRIBUTED" and out["not_placed"] == ["misc/orphan"]
    assert out["unmatched"] == ["nothing/like-it"]
    assert out["notes"][0] == "6 of 8 Checkmarx repos matched to a GitHub repo (4 same name, 1 same repo name, 1 close spelling)"
    assert any("team/card-service -> cards-eng/card_service" in n for n in out["notes"])


def test_strict_setting_turns_off_close_spellings():
    rows = [cx("team/card-servce")]                     # a missing letter
    repos.match_checkmarx(rows, GH, 1.0)
    assert rows[0]["family_id"] == "UNATTRIBUTED"
    repos.match_checkmarx(rows, GH)                     # 0.9 (default) accepts it
    assert rows[0]["family_id"] == "cards" and rows[0]["match_score"] >= 0.9
    assert repos.checkmarx_match_min({"checkmarx_match_min": 2}) == 0.9


def test_close_spellings_never_pair_different_repos_that_share_a_stem():
    gh = [{"repo": "org/payments-api", "family_id": "payments"}, {"repo": "org/service", "family_id": "cards"},
          {"repo": "org/ledger-app", "family_id": "payments"}]
    rows = [cx("x/payments-ui"), cx("x/service2"), cx("x/ledger-api")]
    out = repos.match_checkmarx(rows, gh)
    assert [r["family_id"] for r in rows] == ["UNATTRIBUTED"] * 3 and len(out["unmatched"]) == 3


def test_se01_counts_follow_the_match():
    rows = [cx("leading/ledger-api", True), cx("team/card-service", False), cx("nothing/like-it", True)]
    repos.match_checkmarx(rows, GH)
    out = measure.checkmarx("cx_sast", {"cx_sast": {"rows": rows}})
    assert (out["payments"]["numerator"], out["payments"]["denominator"]) == (1, 1)
    assert (out["cards"]["numerator"], out["cards"]["denominator"]) == (0, 1)
    assert out["UNATTRIBUTED"]["denominator"] == 1
    assert out["payments"]["items"][0]["gh_repo"] == "payments-eng/ledger-api"
