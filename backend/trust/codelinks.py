"""Links from each metric's dictionary card to the code that measures and scores it (owner, 5 Nov 2026).

Setting `code_repo_url` in config/settings.json is the repo's web address on GitHub (or GitHub Enterprise
Server), e.g. https://github.example.com/tech-risk/trust. With it set, publish adds `code_links` to the page
data: for every metric, the file, function and real line numbers of the code behind it, and a link of the form
<repo>/blob/<commit>/backend/trust/measure.py#L66-L81 that GitHub opens with those lines highlighted. Line
numbers are read from the source that is running (Python's ast), so they can't go stale; the commit is the
platform's build commit when it is known (TRUST_GIT_SHA or SOURCE_VERSION), else `main` (setting `code_ref`).
Without the setting there are no links and the page shows nothing extra.
"""
import ast
import pathlib

from . import config, storage

ROOT = pathlib.Path(__file__).resolve().parents[2]

# What to link for each metric: (file under backend/trust/, function, what it does in plain words).
# Shared steps (thresholds, statuses, block and TRUST maths) are linked on every card after the metric's own.
METRIC_CODE = {
    "TE-01": [("measure.py", "te01", "Counts approved and deployed changes per family"),
              ("intake/tcc.py", "read", "Reads the TCC export and flags each change")],
    "TE-02": [("measure.py", "te02", "Counts releases and reverts in each 7-day window"),
              ("score_month.py", "score_month", "Automatic Red rule for client impact", 'c.get("client_impact")'),
              ("intake/tcc.py", "read", "Reads the TCC export and flags each change")],
    "UN-01": [("measure.py", "un01", "Counts Critical and SWE incidents that ended in the month"),
              ("linking.py", "link_actions_to_incidents", "Links incidents to families through their actions")],
    "UN-02": [("measure.py", "un02", "Counts postmortem actions open and overdue at month end")],
    "SE-01": [("measure.py", "checkmarx", "Counts scanned repos passing the Checkmarx SAST policy"),
              ("intake/repos.py", "match_checkmarx", "Matches Checkmarx repos to GitHub repos and families")],
    "SE-02": [("measure.py", "checkmarx", "Counts scanned repos passing the Checkmarx SCA policy"),
              ("intake/repos.py", "match_checkmarx", "Matches Checkmarx repos to GitHub repos and families")],
    "TR-01": [("measure.py", "tr01", "Counts active repos linked to a confirmed app"),
              ("intake/app_links.py", "link", "Links the app inventory's service repos to GitHub repos")],
    "TR-02": [("measure.py", "tr02", "Counts hygiene checks passed across active repos"),
              ("intake/repos.py", "read", "Reads the GitHub export and judges the five checks")],
    "RE-01": [("measure.py", "re01", "Tier 0/1 apps with a completed DR test in 12 months"),
              ("measure.py", "_tested", "How a test counts (status, kind, date window)"),
              ("intake/dr_tests.py", "read", "Reads the DR tests file")],
    "RE-03": [("measure.py", "re03", "Tier 0–2 apps with a successful DR test or tabletop in 12 months"),
              ("measure.py", "_tested", "How a test counts (status, kind, date window)"),
              ("intake/dr_tests.py", "read", "Reads the DR tests file")],
}
SHARED = [("score_month.py", "thresholds_for", "Tolerance thresholds: policy or prevailing median"),
          ("score_month.py", "status_of", "Green, Amber or Red from the result and thresholds"),
          ("scoring.py", "block", "Building block score from its metrics, with caps"),
          ("scoring.py", "family", "TRUST from the building blocks")]


def _lines(file, func, marker=None):
    """(first, last) line of a top-level function in backend/trust/<file>, or None if it isn't there.
    With a marker (a piece of code text), the lines from the marker's first line inside that function to the
    end of that statement (5 lines at most), so the link lands on the rule rather than the whole function."""
    path = ROOT / "backend" / "trust" / file
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func:
            if not marker:
                return node.lineno, node.end_lineno
            lines = text.splitlines()
            for n in range(node.lineno, node.end_lineno + 1):
                if marker in lines[n - 1]:
                    return n, min(n + 4, node.end_lineno)
            return node.lineno, node.end_lineno
    return None


def repo_url():
    return (config.settings().get("code_repo_url") or "").strip().rstrip("/")


def ref():
    return storage.git_sha() or (config.settings().get("code_ref") or "main").strip() or "main"


def links():
    """{metric id: [{file, function, what, from, to, url}]} for the page, or {} when no repo address is set."""
    base = repo_url()
    if not base:
        return {}
    r = ref()
    out = {}
    for mid, places in METRIC_CODE.items():
        rows = []
        for file, func, what, *marker in places + SHARED:
            ln = _lines(file, func, marker[0] if marker else None)
            if not ln:
                continue
            rel = f"backend/trust/{file}"
            rows.append({"file": rel, "function": func, "what": what, "from": ln[0], "to": ln[1],
                         "url": f"{base}/blob/{r}/{rel}#L{ln[0]}-L{ln[1]}"})
        out[mid] = rows
    return {"ref": r, "repo": base, "metrics": out}
