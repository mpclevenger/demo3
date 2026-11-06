#!/usr/bin/env python3
"""
Jira extract for defect and performance reporting -> CSV (TRUST feed "defects"; owner, 3 Nov 2026).

Run it monthly and upload jira_issues.csv on the Data sources page (feed "defects").
The other two files are for your own analysis; TRUST does not read them.

Writes three files to --out (default ./jira_out):
  jira_issues.csv          one row per issue (the item-level evidence)
  jira_transitions.csv     every status change (who, when, from, to)
  jira_monthly_summary.csv counts and times per month x owning team

Ownership: the team is worked out from the person who CLOSED the issue
(the author of the last change into a "Done"-category status), not the
assignee. If --team-map is given (CSV: user,team) the closer is looked up
there by email, username or accountId; otherwise the closer's name is used
and TRUST can place it later through HR (email -> manager -> family).

Made for Jira Data Center (owner, 3 Nov 2026); add --cloud for Jira Cloud. Only needs `requests`.

Auth (environment variables, never put tokens on the command line):
  JIRA_URL        e.g. https://yourco.atlassian.net or https://jira.yourco.com
  JIRA_TOKEN      Data Center: personal access token (PAT)  |  Cloud: API token
  JIRA_EMAIL      Cloud only: your Atlassian email
                  (JIRA_API_TOKEN also accepted)

Examples:
  python jira_export.py --jql 'project in (PAY, TRD) AND updated >= "2026-07-01"'
  python jira_export.py --jql 'project = PAY' --team-map teams.csv \
      --story-points-field customfield_10016 --severity-field customfield_10100
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("America/New_York")  # month-end cut-off used by TRUST


# --------------------------------------------------------------------------- API

class Jira:
    def __init__(self, url: str, email: str | None, token: str, cloud: bool):
        self.url = url.rstrip("/")
        self.cloud = cloud
        self.api = "/rest/api/3" if cloud else "/rest/api/2"
        self.s = requests.Session()
        self.s.headers["Accept"] = "application/json"
        if cloud:
            self.s.auth = (email, token)
        else:
            self.s.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str, **params):
        for attempt in range(6):
            r = self.s.get(self.url + path, params=params, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:  # rate limit / blip
                time.sleep(int(r.headers.get("Retry-After", 2 ** attempt)))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()

    def status_categories(self) -> dict[str, str]:
        """status id -> category key ('new', 'indeterminate', 'done')."""
        return {s["id"]: s["statusCategory"]["key"] for s in self.get(f"{self.api}/status")}

    def search(self, jql: str, fields: list[str]):
        """Yield issues with changelog. Handles both paging styles."""
        f = ",".join(fields)
        if self.cloud:  # /search/jql uses nextPageToken (old /search is retired)
            token = None
            while True:
                p = {"jql": jql, "fields": f, "expand": "changelog", "maxResults": 100}
                if token:
                    p["nextPageToken"] = token
                data = self.get(f"{self.api}/search/jql", **p)
                yield from data.get("issues", [])
                token = data.get("nextPageToken")
                if not token:
                    return
        else:
            start = 0
            while True:
                data = self.get(f"{self.api}/search", jql=jql, fields=f,
                                expand="changelog", startAt=start, maxResults=100)
                issues = data.get("issues", [])
                yield from issues
                start += len(issues)
                if not issues or start >= data.get("total", 0):
                    return

    def full_changelog(self, issue: dict) -> list[dict]:
        """Search results can cut the changelog short; fetch the rest if so."""
        cl = issue.get("changelog") or {}
        histories = cl.get("histories", [])
        if cl.get("total", len(histories)) <= len(histories):
            return histories
        out, start = [], 0
        while True:
            data = self.get(f"{self.api}/issue/{issue['key']}/changelog",
                            startAt=start, maxResults=100)
            vals = data.get("values", [])
            out.extend(vals)
            start += len(vals)
            if not vals or data.get("isLast", start >= data.get("total", 0)):
                return out


# ----------------------------------------------------------------------- helpers

def ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z")


def days(a: datetime | None, b: datetime | None) -> float | None:
    return round((b - a).total_seconds() / 86400, 2) if a and b else None


def person(u: dict | None) -> dict:
    u = u or {}
    return {
        "name": u.get("displayName", ""),
        "email": (u.get("emailAddress") or "").lower(),  # Cloud may hide this
        "username": u.get("name", ""),                    # Server/DC login
        "account_id": u.get("accountId", ""),             # Cloud id
    }


def month_of(d: datetime | None) -> str:
    return d.astimezone(TZ).strftime("%Y-%m") if d else ""


def load_team_map(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {r["user"].strip().lower(): r["team"].strip() for r in csv.DictReader(f)}


def team_for(p: dict, team_map: dict[str, str]) -> str:
    for k in (p["email"], p["username"], p["account_id"]):
        if k and k.lower() in team_map:
            return team_map[k.lower()]
    if team_map:
        return "UNATTRIBUTED"
    return p["name"] or "UNATTRIBUTED"


def field_text(v) -> str:
    """Flatten Jira custom-field shapes (option, list, number) to text."""
    if v is None:
        return ""
    if isinstance(v, dict):
        return str(v.get("value") or v.get("name") or v.get("displayName") or "")
    if isinstance(v, list):
        return ";".join(field_text(x) for x in v)
    return str(v)


# ------------------------------------------------------------------- per issue

def analyse(issue: dict, histories: list[dict], cats: dict[str, str]) -> tuple[dict, list[dict]]:
    """Return (issue fields worked out from history, transition rows)."""
    transitions = []
    for h in sorted(histories, key=lambda h: h["created"]):
        for it in h.get("items", []):
            if it.get("field") == "status":
                transitions.append({
                    "at": ts(h["created"]),
                    "author": person(h.get("author")),
                    "from": it.get("fromString", ""), "to": it.get("toString", ""),
                    "from_cat": cats.get(str(it.get("from")), ""),
                    "to_cat": cats.get(str(it.get("to")), ""),
                })

    first_start = next((t["at"] for t in transitions if t["to_cat"] == "indeterminate"), None)
    closes = [t for t in transitions if t["to_cat"] == "done" and t["from_cat"] != "done"]
    reopens = sum(1 for t in transitions if t["from_cat"] == "done" and t["to_cat"] != "done")
    last_close = closes[-1] if closes else None

    rows = [{
        "issue_key": issue["key"], "changed_at": t["at"].isoformat(),
        "changed_by": t["author"]["name"], "changed_by_email": t["author"]["email"],
        "changed_by_username": t["author"]["username"],
        "from_status": t["from"], "to_status": t["to"],
        "from_category": t["from_cat"], "to_category": t["to_cat"],
    } for t in transitions]
    return {"first_start": first_start, "last_close": last_close, "reopens": reopens}, rows


# ------------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jql", required=True, help="Which issues to pull (all types; defects are flagged)")
    ap.add_argument("--out", default="jira_out")
    ap.add_argument("--cloud", action="store_true", help="Jira Cloud (default: Data Center)")
    ap.add_argument("--defect-types", default="Bug,Defect", help="Issue types counted as defects")
    ap.add_argument("--team-map", help="CSV with columns user,team (user = email, username or accountId)")
    ap.add_argument("--story-points-field", default="", help="e.g. customfield_10016")
    ap.add_argument("--severity-field", default="", help="Custom field holding defect severity, if any")
    ap.add_argument("--env-field", default="", help="Custom field for 'found in' environment, if any")
    a = ap.parse_args()

    url = os.environ.get("JIRA_URL")
    token = os.environ.get("JIRA_TOKEN") or os.environ.get("JIRA_API_TOKEN")
    email = os.environ.get("JIRA_EMAIL")
    if not url or not token or (a.cloud and not email):
        sys.exit("Set JIRA_URL and JIRA_TOKEN (and JIRA_EMAIL for Cloud).")

    jira = Jira(url, email, token, cloud=a.cloud)
    cats = jira.status_categories()
    team_map = load_team_map(a.team_map)
    defect_types = {t.strip().lower() for t in a.defect_types.split(",")}
    extra = [f for f in (a.story_points_field, a.severity_field, a.env_field) if f]
    fields = ["issuetype", "project", "summary", "status", "priority", "resolution",
              "created", "resolutiondate", "assignee", "reporter", "labels",
              "components", "fixVersions", "issuelinks", *extra]

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    run_at = datetime.now(TZ)
    issues, transitions = [], []

    for n, it in enumerate(jira.search(a.jql, fields), 1):
        f = it["fields"]
        hist = jira.full_changelog(it)
        calc, trows = analyse(it, hist, cats)
        transitions += trows

        created, resolved = ts(f.get("created")), ts(f.get("resolutiondate"))
        status_cat = f["status"]["statusCategory"]["key"]
        closer = calc["last_close"]["author"] if calc["last_close"] and status_cat == "done" else person(None)
        closed_at = calc["last_close"]["at"] if calc["last_close"] and status_cat == "done" else None
        done_at = resolved or closed_at
        itype = f["issuetype"]["name"]

        issues.append({
            "issue_key": it["key"], "project": f["project"]["key"], "issue_type": itype,
            "is_defect": itype.lower() in defect_types,
            "summary": f.get("summary", ""),
            "priority": (f.get("priority") or {}).get("name", ""),
            "severity": field_text(f.get(a.severity_field)) if a.severity_field else "",
            "found_in_env": field_text(f.get(a.env_field)) if a.env_field else "",
            "status": f["status"]["name"], "status_category": status_cat,
            "resolution": (f.get("resolution") or {}).get("name", ""),
            "created_at": created.isoformat() if created else "",
            "first_in_progress_at": calc["first_start"].isoformat() if calc["first_start"] else "",
            "resolved_at": done_at.isoformat() if done_at else "",
            "created_month": month_of(created), "resolved_month": month_of(done_at),
            "closed_by": closer["name"], "closed_by_email": closer["email"],
            "closed_by_username": closer["username"], "closed_by_account_id": closer["account_id"],
            "owning_team": team_for(closer, team_map) if done_at else "",
            "assignee": person(f.get("assignee"))["name"],
            "reporter": person(f.get("reporter"))["name"],
            "labels": ";".join(f.get("labels") or []),
            "components": ";".join(c["name"] for c in f.get("components") or []),
            "fix_versions": ";".join(v["name"] for v in f.get("fixVersions") or []),
            "linked_issues": len(f.get("issuelinks") or []),
            "story_points": field_text(f.get(a.story_points_field)) if a.story_points_field else "",
            "reopen_count": calc["reopens"],
            "lead_time_days": days(created, done_at),
            "cycle_time_days": days(calc["first_start"], done_at),
            "age_days_if_open": days(created, run_at) if status_cat != "done" else "",
            "extracted_at": run_at.isoformat(),
        })
        if n % 200 == 0:
            print(f"  {n} issues...", file=sys.stderr)

    write_csv(out / "jira_issues.csv", issues)
    write_csv(out / "jira_transitions.csv", transitions)
    write_csv(out / "jira_monthly_summary.csv", summarise(issues))
    print(f"Done: {len(issues)} issues, {len(transitions)} status changes -> {out}/")
    return 0


def summarise(issues: list[dict]) -> list[dict]:
    """Per resolved month x owning team. Created counts use the month opened."""
    g = defaultdict(list)
    for i in issues:
        if i["resolved_month"]:
            g[(i["resolved_month"], i["owning_team"])].append(i)
    opened = defaultdict(int)
    for i in issues:
        if i["is_defect"]:
            opened[i["created_month"]] += 1

    def med(xs):
        xs = [x for x in xs if x is not None]
        return round(statistics.median(xs), 2) if xs else ""

    def p85(xs):
        xs = sorted(x for x in xs if x is not None)
        return xs[min(len(xs) - 1, int(0.85 * len(xs)))] if xs else ""

    rows = []
    for (m, team), items in sorted(g.items()):
        d = [i for i in items if i["is_defect"]]
        rows.append({
            "month": m, "owning_team": team,
            "issues_closed": len(items),
            "defects_closed": len(d),
            "defects_opened_firmwide_this_month": opened.get(m, 0),
            "defects_reopened_at_least_once": sum(1 for i in d if i["reopen_count"] > 0),
            "story_points_closed": sum(float(i["story_points"] or 0) for i in items),
            "median_lead_time_days": med([i["lead_time_days"] for i in items]),
            "p85_lead_time_days": p85([i["lead_time_days"] for i in items]),
            "median_cycle_time_days": med([i["cycle_time_days"] for i in items]),
            "median_defect_resolution_days": med([i["lead_time_days"] for i in d]),
        })
    return rows


def write_csv(path: Path, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        if not rows:
            f.write("")
            return
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    sys.exit(main())
