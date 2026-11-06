"""Postmortems and action items: each uploads on its own; scoring links assignee -> action -> incident(s)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import linking  # noqa: E402
from trust.intake import actions, postmortems  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
A = actions.read((FIX / "actions_export.csv").read_bytes())
P = postmortems.read((FIX / "postmortems_export.csv").read_bytes())
HR_EMAIL = {"alex.moreno@example.com": "payments", "sam.lee@example.com": "payments", "pat.kim@example.com": "cards"}
HR_SAM = {"pkim": "cards"}


def act(ref):
    return next(x for x in A["rows"] if x["item_ref"] == ref)


def test_actions_load_on_their_own():
    assert A["summary"]["actions"] == 7 and A["summary"]["set_aside"] == 1          # duplicate A-1 set aside
    assert act("JIRA:A-1")["status"] == "Tracking" and act("JIRA:A-1")["open"]       # Monitoring counts as open
    assert act("JIRA:A-2")["status"] == "Done" and not act("JIRA:A-2")["open"]
    assert act("JIRA:A-1")["due"].startswith("2026-10-01") and act("JIRA:A-1")["due_from_blank_eta"]   # 9/1 + 30 days
    assert act("JIRA:A-1")["url"] == "https://jira.example.com/A-1"                  # =HYPERLINK parsed
    assert act("JIRA:P-7")["url"] is None and act("JIRA:P-7")["status"] == "Open"    # plain value; new status = Open
    text = " ".join(A["notes"])
    assert "Weird new" in text and "JIRA:P-7 (ETA)" in text and "no assignee email" in text


def test_first_assignee_email_places_the_action():
    x = act("GITHUB:org/r/issues/5")
    assert x["assignee_email"] == "pat.kim@example.com"                             # name + email, any case
    assert x["all_assignee_emails"] == ["pat.kim@example.com", "sam.lee@example.com"]


def test_postmortems_load_on_their_own():
    assert P["summary"] == dict(postmortems=5, incidents=4, set_aside=1, in_scope_incidents=3, defcon0_incidents=1)
    d = {(x["incident_id"], x["postmortem_id"]): x for x in P["rows"]}
    assert d[("INC-D", "104")]["defcon_type"] == "critical"                          # 'critial' typo fixed
    assert d[("INC-C", "103")]["in_scope"] and d[("INC-C", "103")]["defcon"] is None  # Not Available is in scope
    assert any("not a date" in n for n in P["notes"])


def test_link_with_everything_loaded():
    L = linking.link_actions_to_incidents(A["rows"], P["rows"], HR_EMAIL, HR_SAM)
    inc = L["incidents"]
    assert inc["INC-A"]["families"] == ["cards", "payments"] and inc["INC-A"]["placed_by"] == "action assignees"
    assert inc["INC-C"]["families"] == ["cards"] and inc["INC-C"]["placed_by"] == "user_stakeholders"
    assert inc["INC-D"]["families"] == ["UNATTRIBUTED"]                              # assignee not in HR
    scope = {a["item_ref"]: a["scope_reason"] for a in L["actions"]}
    assert scope["RPD:123"] == "incident is DEFCON 0"
    assert scope["JIRA:X-9"] == "incident not in the postmortem file"
    assert scope["JIRA:A-1"] == "in scope"


def test_link_with_only_the_action_file():
    L = linking.link_actions_to_incidents(A["rows"])
    assert all(a["family_id"] == "UNATTRIBUTED" and a["in_scope"] for a in L["actions"])
    assert any("postmortem file not loaded" in n for n in L["notes"]) and any("HR not loaded" in n for n in L["notes"])
