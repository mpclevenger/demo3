"""Export the repo file for TRUST (feed "repos": TR-01 active repos, TR-02 hygiene; owner, 3 Nov 2026).

Run it monthly against GitHub Enterprise Server and upload repos.csv on the Data sources page.
It uses github_client.py next to it (set GITHUB_HOST and GITHUB_TOKEN); nothing here is part of the website.

One row per repo in the org. TRUST, not this script, decides what passes: the script only reports the
settings as GitHub has them, so the rules can change without running the export again.

Columns:
  Repo, Url, Archived, Fork, Empty, DefaultBranch, PushedAt, LastDefaultBranchCommit,
  ProtectionSource, BranchProtected, RequiredApprovals, LastPushApprovalRequired, ForcePushAllowed,
  DeletionsAllowed, AdminEnforced, BypassAllowed, StaleReviewsDismissed, CodeOwnerReviewRequired,
  StatusChecksRequired, CodeOwnersFile,
  LastHumanCommitterEmail, LastHumanCommitterLogin, LastHumanCommitDate,
  TopCommitterEmail, TopCommitterLogin, TopCommitterShare, HumanCommitsSampled

Protection can come from classic branch protection, from rulesets, or both. A setting counts as on
when either one turns it on for the default branch; BypassAllowed is true when either lets someone
skip the rules. Rulesets apply to admins unless they are listed as bypass actors.
"""
import csv
import json
import os
import re
import sys
from collections import Counter

from github_client import graphql      # graphql(query, variables) -> the "data" part

# Which orgs to export. The server itself (e.g. company.github.com) is the GITHUB_HOST setting, not here.
# ORG = ""                      every org the token's account belongs to (Repo is then "org/repo")
# ORG = "payments-eng"          just that one org (Repo is the repo name)
# ORG = ["payments-eng", "x"]   those orgs (Repo is "org/repo")
ORG = ""
INCLUDE_RULESETS = True    # set False if this GHES version rejects `rulesets` (older than 3.10)
PAGE_SIZE = 25             # lower it if the query times out

# Bots and service accounts are never owners (TRUST also has its own list; this keeps the export clean).
BOT = re.compile(r"\[bot\]$|^(dependabot|renovate|github-actions|svc[-_]|jenkins)", re.I)

RULESETS = """
        rulesets(first: 20, includeParents: true) {
          nodes {
            enforcement
            bypassActors(first: 1) { totalCount }
            conditions { refName { include exclude } }
            rules(first: 50) {
              nodes {
                type
                parameters {
                  ... on PullRequestParameters {
                    requiredApprovingReviewCount requireCodeOwnerReview
                    requireLastPushApproval dismissStaleReviewsOnPush
                  }
                }
              }
            }
          }
        }"""

QUERY = """
query($org: String!, $cursor: String) {
  rateLimit { cost remaining resetAt }
  organization(login: $org) {
    repositories(first: %d, after: $cursor, orderBy: {field: NAME, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        url
        isArchived
        isFork
        isEmpty
        pushedAt
        defaultBranchRef {
          name
          target {
            ... on Commit {
              committedDate
              history(first: 20) {
                nodes { committedDate author { name email user { login } } }
              }
            }
          }
          branchProtectionRule {
            requiresApprovingReviews
            requiredApprovingReviewCount
            requireLastPushApproval
            dismissesStaleReviews
            requiresCodeOwnerReviews
            requiresStatusChecks
            isAdminEnforced
            allowsForcePushes
            allowsDeletions
            bypassPullRequestAllowances(first: 1) { totalCount }
            bypassForcePushAllowances(first: 1) { totalCount }
          }
        }
        codeownersRoot:   object(expression: "HEAD:CODEOWNERS")         { ... on Blob { byteSize } }
        codeownersGithub: object(expression: "HEAD:.github/CODEOWNERS") { ... on Blob { byteSize } }
        codeownersDocs:   object(expression: "HEAD:docs/CODEOWNERS")    { ... on Blob { byteSize } }
        %s
      }
    }
  }
}
""" % (PAGE_SIZE, RULESETS if INCLUDE_RULESETS else "")


def rulesets_for(repo, branch):
    """What the active rulesets that cover the default branch turn on, combined. None if none cover it."""
    found = None
    for rs in ((repo.get("rulesets") or {}).get("nodes") or []):
        if rs.get("enforcement") != "ACTIVE":
            continue
        ref = (rs.get("conditions") or {}).get("refName") or {}
        include, exclude = set(ref.get("include") or []), set(ref.get("exclude") or [])
        mine = {"~DEFAULT_BRANCH", "~ALL", f"refs/heads/{branch}"}
        if exclude & mine or not include & mine:
            continue
        f = found or {"approvals": 0, "last_push": False, "stale": False, "code_owner": False,
                      "status_checks": False, "no_force_push": False, "no_deletion": False, "bypass": False}
        f["bypass"] |= ((rs.get("bypassActors") or {}).get("totalCount") or 0) > 0
        for rule in ((rs.get("rules") or {}).get("nodes") or []):
            t, p = rule.get("type"), rule.get("parameters") or {}
            if t == "PULL_REQUEST":
                f["approvals"] = max(f["approvals"], p.get("requiredApprovingReviewCount") or 0)
                f["last_push"] |= bool(p.get("requireLastPushApproval"))
                f["stale"] |= bool(p.get("dismissStaleReviewsOnPush"))
                f["code_owner"] |= bool(p.get("requireCodeOwnerReview"))
            elif t == "REQUIRED_STATUS_CHECKS":
                f["status_checks"] = True
            elif t == "NON_FAST_FORWARD":
                f["no_force_push"] = True
            elif t == "DELETION":
                f["no_deletion"] = True
        found = f
    return found


def protection(repo, ref):
    bpr = ref.get("branchProtectionRule")
    rs = rulesets_for(repo, ref.get("name") or "") if INCLUDE_RULESETS else None
    if not bpr and not rs:
        return {"ProtectionSource": "none", "BranchProtected": False, "RequiredApprovals": 0,
                "LastPushApprovalRequired": False, "ForcePushAllowed": True, "DeletionsAllowed": True,
                "AdminEnforced": False, "BypassAllowed": False, "StaleReviewsDismissed": False,
                "CodeOwnerReviewRequired": False, "StatusChecksRequired": False}
    b = bpr or {}
    r = rs or {}
    count = lambda x: ((b.get(x) or {}).get("totalCount") or 0)
    return {
        "ProtectionSource": " + ".join(s for s, on in (("branch protection", bpr), ("ruleset", rs)) if on),
        "BranchProtected": True,
        "RequiredApprovals": max((b.get("requiredApprovingReviewCount") or 0) if b.get("requiresApprovingReviews") else 0,
                                 r.get("approvals", 0)),
        "LastPushApprovalRequired": bool(b.get("requireLastPushApproval")) or r.get("last_push", False),
        "ForcePushAllowed": (bool(b.get("allowsForcePushes")) if bpr else True) and not r.get("no_force_push", False),
        "DeletionsAllowed": (bool(b.get("allowsDeletions")) if bpr else True) and not r.get("no_deletion", False),
        "AdminEnforced": bool(b.get("isAdminEnforced")) if bpr else True,
        "BypassAllowed": count("bypassPullRequestAllowances") > 0 or count("bypassForcePushAllowances") > 0
                         or r.get("bypass", False),
        "StaleReviewsDismissed": bool(b.get("dismissesStaleReviews")) or r.get("stale", False),
        "CodeOwnerReviewRequired": bool(b.get("requiresCodeOwnerReviews")) or r.get("code_owner", False),
        "StatusChecksRequired": bool(b.get("requiresStatusChecks")) or r.get("status_checks", False),
    }


def committers(ref):
    """The last human committer and the most frequent one in the last 20 default-branch commits."""
    nodes = (((ref.get("target") or {}).get("history") or {}).get("nodes")) or []
    humans = []
    for c in nodes:
        a = c.get("author") or {}
        login = ((a.get("user") or {}).get("login") or "").strip().lower()
        email = (a.get("email") or "").strip().lower()
        name = a.get("name") or ""
        if (login or email) and not any(BOT.search(x) for x in (login, email, name) if x):
            humans.append((email, login, c.get("committedDate") or ""))
    if not humans:
        return {"LastHumanCommitterEmail": "", "LastHumanCommitterLogin": "", "LastHumanCommitDate": "",
                "TopCommitterEmail": "", "TopCommitterLogin": "", "TopCommitterShare": "", "HumanCommitsSampled": 0}
    counts = Counter((e, l) for e, l, _ in humans)
    most = max(counts.values())
    top = next((e, l) for e, l, _ in humans if counts[(e, l)] == most)      # a tie goes to the most recent
    return {"LastHumanCommitterEmail": humans[0][0], "LastHumanCommitterLogin": humans[0][1],
            "LastHumanCommitDate": humans[0][2], "TopCommitterEmail": top[0], "TopCommitterLogin": top[1],
            "TopCommitterShare": round(most / len(humans), 2), "HumanCommitsSampled": len(humans)}


ORGS_QUERY = """
query($cursor: String) {
  viewer { organizations(first: 100, after: $cursor) { pageInfo { hasNextPage endCursor } nodes { login } } }
}"""


def orgs():
    """The orgs to export: ORG as set, or every org the token's account belongs to."""
    if isinstance(ORG, (list, tuple)):
        return [o for o in ORG if o]
    if ORG:
        return [ORG]
    found, cursor = [], None
    while True:
        page = graphql(ORGS_QUERY, {"cursor": cursor})["viewer"]["organizations"]
        found += [o["login"] for o in page["nodes"]]
        if not page["pageInfo"]["hasNextPage"]:
            return found
        cursor = page["pageInfo"]["endCursor"]


def pause_until(reset_at):
    """Wait until GitHub's rate limit resets (resetAt, e.g. 2026-11-04T15:00:00Z) so the next page doesn't fail."""
    from datetime import datetime, timezone
    import time
    try:
        reset = datetime.fromisoformat(str(reset_at).replace("Z", "+00:00"))
        wait = max(int((reset - datetime.now(timezone.utc)).total_seconds()), 0) + 5
    except ValueError:
        wait = 60
    wait = min(wait, 3900)
    print(f"Nearly out of GitHub's hourly allowance: waiting {wait // 60} min {wait % 60} s for it to reset, "
          "then carrying on (leave this window open)", file=sys.stderr)
    time.sleep(wait)


def plan():
    """The orgs to export, each with the prefix its repo names get."""
    names = orgs()
    if not names:
        sys.exit("No orgs found: set ORG, or check the token's account belongs to at least one org.")
    one = len(names) == 1 and not isinstance(ORG, (list, tuple)) and bool(ORG)
    return [(org, "" if one else f"{org}/") for org in names]


def rows():
    """Every repo row, all orgs (no saving as it goes; the command line uses export())."""
    for org, prefix in plan():
        yield from org_rows(org, prefix)


def org_rows(org, prefix=""):
    for page_rows, _ in org_pages(org, prefix):
        yield from page_rows


def repo_row(r, prefix):
    ref = r.get("defaultBranchRef") or {}
    return {
        "Repo": prefix + r["name"], "Url": r["url"], "Archived": r["isArchived"], "Fork": r["isFork"],
        "Empty": r["isEmpty"], "DefaultBranch": ref.get("name") or "", "PushedAt": r.get("pushedAt") or "",
        "LastDefaultBranchCommit": ((ref.get("target") or {}).get("committedDate") or ""),
        **protection(r, ref),
        "CodeOwnersFile": any(r.get(k) for k in ("codeownersRoot", "codeownersGithub", "codeownersDocs")),
        **committers(ref),
    }


def org_pages(org, prefix="", cursor=None):
    """One org's repos a page at a time: yields (rows, cursor for the next page or None at the end)."""
    while True:
        data = graphql(QUERY, {"org": org, "cursor": cursor})
        page = data["organization"]["repositories"]
        rl = data.get("rateLimit") or {}
        nxt = page["pageInfo"]["endCursor"] if page["pageInfo"]["hasNextPage"] else None
        yield [repo_row(r, prefix) for r in page["nodes"]], nxt
        print(f"{org}: page done (cost {rl.get('cost')}, remaining {rl.get('remaining')})", file=sys.stderr)
        if not nxt:
            return
        cursor = nxt
        if rl.get("remaining") is not None and rl.get("cost") is not None and rl["remaining"] < 2 * rl["cost"]:
            pause_until(rl.get("resetAt"))      # not enough allowance left for the next page: wait for the reset


# ---- saving as it goes, so a stopped run carries on where it left off ----

OUT = "repos.csv"
PROGRESS = "repos.progress.json"     # exists only while a run is unfinished


def _save_progress(state):
    tmp = PROGRESS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, PROGRESS)


def export(fresh=False):
    state = None
    if not fresh and os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            state = json.load(f)
        if state.get("org_setting") != repr(ORG) or not os.path.exists(OUT):
            sys.exit(f"The unfinished run in {PROGRESS} was for a different ORG setting, or {OUT} is missing. "
                     "To start over, run again with --fresh.")
        print(f"Carrying on from where the last run stopped ({state['org']}). "
              "To start over instead: --fresh", file=sys.stderr)
    if state is None:
        targets = plan()
        state = {"org_setting": repr(ORG), "orgs": targets, "done": [], "org": targets[0][0], "cursor": None}
        if os.path.exists(OUT):
            os.remove(OUT)
        _save_progress(state)
    print(f"exporting {len(state['orgs'])} org(s): {', '.join(o for o, _ in state['orgs'])}", file=sys.stderr)

    seen, header = set(), None
    if os.path.exists(OUT) and os.path.getsize(OUT):
        with open(OUT, newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            header = rd.fieldnames
            seen = {r["Repo"] for r in rd}
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header) if header else None
        for org, prefix in state["orgs"]:
            if org in state["done"]:
                continue
            cursor = state["cursor"] if org == state["org"] else None
            for page_rows, nxt in org_pages(org, prefix, cursor):
                new = [r for r in page_rows if r["Repo"] not in seen]   # a page fetched twice isn't written twice
                if new and w is None:
                    w = csv.DictWriter(f, fieldnames=list(new[0]))
                    w.writeheader()
                if new:
                    w.writerows(new)
                f.flush()
                os.fsync(f.fileno())
                seen.update(r["Repo"] for r in new)
                state.update(org=org, cursor=nxt)
                if nxt is None:
                    state["done"].append(org)
                _save_progress(state)
    os.remove(PROGRESS)
    if not seen:
        sys.exit("No repos returned: check ORG and the token's access.")
    print(f"{len(seen)} repos written to {OUT}")


if __name__ == "__main__":
    export(fresh="--fresh" in sys.argv[1:])
