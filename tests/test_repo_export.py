"""tools/github_repo_export.py against a made-up GitHub answer, then straight into TRUST's reader."""
import csv
import importlib
import io
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))
from trust.intake import repos  # noqa: E402


def commit(login, email, when="2026-10-20T10:00:00Z", name="x"):
    return {"committedDate": when, "author": {"name": name, "email": email, "user": {"login": login} if login else None}}


NODES = [
    {"name": "classic", "url": "u1", "isArchived": False, "isFork": False, "isEmpty": False,
     "pushedAt": "2026-10-21T00:00:00Z",
     "defaultBranchRef": {"name": "main", "target": {"committedDate": "2026-10-20T10:00:00Z", "history": {"nodes": [
         commit("dependabot[bot]", "bot@x"), commit("SLee", "slee@example.com"), commit("amoreno", "amoreno@example.com"),
         commit("amoreno", "amoreno@example.com")]}},
         "branchProtectionRule": {"requiresApprovingReviews": True, "requiredApprovingReviewCount": 2,
                                  "requireLastPushApproval": True, "dismissesStaleReviews": False,
                                  "requiresCodeOwnerReviews": False, "requiresStatusChecks": True,
                                  "isAdminEnforced": True, "allowsForcePushes": False, "allowsDeletions": False,
                                  "bypassPullRequestAllowances": {"totalCount": 0},
                                  "bypassForcePushAllowances": {"totalCount": 0}}},
     "codeownersRoot": None, "codeownersGithub": {"byteSize": 10}, "codeownersDocs": None,
     "rulesets": {"nodes": []}},
    {"name": "ruleset-only", "url": "u2", "isArchived": False, "isFork": False, "isEmpty": False,
     "pushedAt": "2026-10-21T00:00:00Z",
     "defaultBranchRef": {"name": "main", "target": {"committedDate": "2026-10-20T10:00:00Z",
                                                     "history": {"nodes": [commit("amoreno", "amoreno@example.com")]}},
                          "branchProtectionRule": None},
     "codeownersRoot": None, "codeownersGithub": None, "codeownersDocs": None,
     "rulesets": {"nodes": [{"enforcement": "ACTIVE", "bypassActors": {"totalCount": 1},
                             "conditions": {"refName": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
                             "rules": {"nodes": [{"type": "PULL_REQUEST", "parameters": {
                                 "requiredApprovingReviewCount": 1, "requireCodeOwnerReview": False,
                                 "requireLastPushApproval": False, "dismissStaleReviewsOnPush": True}},
                                 {"type": "NON_FAST_FORWARD", "parameters": None},
                                 {"type": "DELETION", "parameters": None}]}}]}},
    {"name": "bare", "url": "u3", "isArchived": True, "isFork": False, "isEmpty": True, "pushedAt": None,
     "defaultBranchRef": None, "codeownersRoot": None, "codeownersGithub": None, "codeownersDocs": None,
     "rulesets": {"nodes": []}},
]


def _fake_graphql(q, v):
    if "viewer" in q:
        return {"viewer": {"organizations": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                                             "nodes": [{"login": "alpha"}, {"login": "beta"}]}}}
    return {"rateLimit": {"cost": 1, "remaining": 9},
            "organization": {"repositories": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": NODES}}}


def test_blank_org_exports_every_org(monkeypatch):
    fake = types.ModuleType("github_client")
    fake.graphql = _fake_graphql
    monkeypatch.setitem(sys.modules, "github_client", fake)
    exp = importlib.import_module("github_repo_export")
    monkeypatch.setattr(exp, "ORG", "")
    names = [r["Repo"] for r in exp.rows()]
    assert names == [f"{o}/{n['name']}" for o in ("alpha", "beta") for n in NODES]   # same repo name in two orgs kept apart


def test_export_then_read(monkeypatch, tmp_path):
    fake = types.ModuleType("github_client")
    fake.graphql = _fake_graphql
    monkeypatch.setitem(sys.modules, "github_client", fake)
    exp = importlib.import_module("github_repo_export")
    monkeypatch.setattr(exp, "ORG", "one-org")                 # one org named: Repo is the plain repo name
    out = list(exp.rows())
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)
    assert list(out[0]) == list(repos.FIELDS)                  # the export's columns are what TRUST reads
    r = repos.read(buf.getvalue().encode())
    by = {x["repo"]: x for x in r["rows"]}
    assert by["classic"]["passed"] == 5 and by["classic"]["info"]["codeowners"] is True
    assert by["classic"]["last_committer"]["login"] == "slee"   # the bot is skipped
    assert by["classic"]["top_committer"]["login"] == "amoreno"
    rs = by["ruleset-only"]
    assert rs["protection_source"] == "ruleset"
    assert rs["checks"] == {"protected": True, "review": True, "independent": False, "history": True,
                            "no_bypass": False}                # bypass actor, and no last-push approval
    assert by["bare"]["passed"] == 0 and by["bare"]["archived"]


def test_saves_as_it_goes_and_carries_on(monkeypatch, tmp_path):
    """A run that stops part-way keeps what it wrote; the next run carries on from that page, with no repeats."""
    import copy
    pages = {("alpha", None): (NODES[:2], "c1"), ("alpha", "c1"): (NODES[2:], None),
             ("beta", None): (NODES[:1], "c2"), ("beta", "c2"): (NODES[1:], None)}
    calls, stop_at = [], {"n": 3}

    def fake(q, v):
        if "viewer" in q:
            return {"viewer": {"organizations": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                                                 "nodes": [{"login": "alpha"}, {"login": "beta"}]}}}
        calls.append((v["org"], v["cursor"]))
        if len(calls) == stop_at["n"]:
            raise SystemExit("GitHub went away")
        nodes, nxt = pages[(v["org"], v["cursor"])]
        return {"rateLimit": {"cost": 1, "remaining": 999},
                "organization": {"repositories": {"pageInfo": {"hasNextPage": nxt is not None, "endCursor": nxt},
                                                  "nodes": copy.deepcopy(nodes)}}}

    fake_mod = types.ModuleType("github_client")
    fake_mod.graphql = fake
    monkeypatch.setitem(sys.modules, "github_client", fake_mod)
    exp = importlib.import_module("github_repo_export")
    monkeypatch.setattr(exp, "graphql", fake)                 # the module may already be loaded with another fake
    monkeypatch.setattr(exp, "ORG", "")
    monkeypatch.chdir(tmp_path)
    try:
        exp.export()
    except SystemExit:
        pass
    assert (tmp_path / "repos.progress.json").exists()
    kept = list(csv.DictReader(open(tmp_path / "repos.csv", encoding="utf-8")))
    assert [r["Repo"] for r in kept] == ["alpha/classic", "alpha/ruleset-only", "alpha/bare"]   # alpha finished
    stop_at["n"] = 0
    calls.clear()
    exp.export()
    assert calls == [("beta", None), ("beta", "c2")]           # alpha not fetched again
    out = [r["Repo"] for r in csv.DictReader(open(tmp_path / "repos.csv", encoding="utf-8"))]
    assert out == [f"{o}/{n['name']}" for o in ("alpha", "beta") for n in NODES]
    assert not (tmp_path / "repos.progress.json").exists()
    r = repos.read(open(tmp_path / "repos.csv", "rb").read())
    assert len(r["rows"]) == 6
