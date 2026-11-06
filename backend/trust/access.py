"""Who someone is, and what their role lets them see and do (owner, 3 Nov 2026).

The company's access add-on in front of TRUST signs people in. It passes TRUST, on every request:
  - the person's SAM_ACCOUNT, in the header named by `user_header` in config/access.json;
  - their AD groups, in the header named by `groups_header` (optional).
The add-on must remove those headers if a browser tries to send its own.

Roles:
  - CTO and leadership, Tech Risk, Head of Tech Risk, Auditor: from AD groups (config/access.json).
  - Family lead: the family's owners in the product family owners file, plus anyone in the family's
    AD groups (`family_lead_groups`, for delegates).
  - Family member: people placed with the family through HR (the same rule that places their work).
  Family roles come from the newest mapped month, so they follow HR and the owners file.

Until `user_header` is set, TRUST runs open, as before: anyone past the add-on can do everything
and types their name. The page says so in a banner.
"""
import json
import os
import pathlib

from . import storage
from .intake.common import loads_tolerant

GROUP_ROLES = ("cto_leadership", "tech_risk", "head_of_tech_risk", "auditor")
ROLE_NAMES = {"cto_leadership": "CTO and leadership", "tech_risk": "Tech Risk", "head_of_tech_risk": "Head of Tech Risk",
              "auditor": "Auditor", "family_lead": "Family lead", "family_member": "Family member"}


def config():
    path = pathlib.Path(os.environ.get("TRUST_ACCESS")
                        or pathlib.Path(__file__).resolve().parents[2] / "config" / "access.json")
    try:
        doc = loads_tolerant(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        doc = {}
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def enforced(cfg=None):
    return bool((cfg if cfg is not None else config()).get("user_header"))


def _norm_user(v):
    """'DOMAIN\\jsmith' or 'jsmith@corp' -> 'jsmith'."""
    v = (v or "").strip()
    v = v.split("\\")[-1].split("@")[0]
    return v.lower()


def _norm_group(g):
    """'CN=TRUST-TechRisk,OU=Groups,DC=corp' -> 'trust-techrisk'; plain names stay as they are."""
    g = (g or "").strip()
    if g.upper().startswith("CN="):
        g = g[3:].split(",")[0]
    return g.lower()


# ---- family roles, from the newest mapped month (cached until that month is mapped again) ----

_cache = {"key": None, "people": {}, "owners": {}}


def _families_index():
    months = storage.months("mapped")
    if not months:
        return {}, {}
    m = months[-1]
    run = storage.run_info("mapped", m) or {}
    key = (str(storage.store_dir()), storage.using_database(), m, run.get("at"))
    if _cache["key"] != key:
        mapped = storage.load_month("mapped", m) or {}
        feeds = mapped.get("feeds", {})
        people = {(p.get("sam_account") or "").lower(): p for p in (feeds.get("hr", {}).get("people") or [])}
        owners = {}
        for f in feeds.get("hr_mapping", {}).get("families") or []:
            for e in f.get("owner_emails") or []:
                owners.setdefault(e.lower(), set()).add(f["family_id"])
        _cache.update(key=key, people=people, owners=owners)
    return _cache["people"], _cache["owners"]


def person(headers, cfg=None):
    """The person behind a request: {sam, name, roles, lead_of, member_of, open}. None if not signed in."""
    cfg = cfg if cfg is not None else config()
    if not enforced(cfg):
        return {"sam": None, "name": None, "roles": set(GROUP_ROLES), "lead_of": set(), "member_of": set(),
                "open": True}
    sam = _norm_user(headers.get(cfg["user_header"]))
    if not sam:
        return None
    sep = cfg.get("groups_separator") or ","
    raw = headers.get(cfg.get("groups_header") or "", "") if cfg.get("groups_header") else ""
    # a DN contains commas, so with the comma separator split on ',CN=' boundaries too
    parts = raw.replace(";CN=", "\nCN=").replace(",CN=", "\nCN=").split("\n") if "CN=" in raw.upper() else raw.split(sep)
    groups = {_norm_group(g) for g in parts if g.strip()}
    roles = {r for r in GROUP_ROLES if groups & {_norm_group(g) for g in (cfg.get("groups", {}).get(r) or [])}}
    people, owners = _families_index()
    p = people.get(sam) or {}
    lead_of = set(owners.get((p.get("email") or "").lower(), set()))
    for fid, gs in (cfg.get("family_lead_groups") or {}).items():
        if groups & {_norm_group(g) for g in gs or []}:
            lead_of.add(fid)
    member_of = {p["family_id"]} if p.get("family_id") and p["family_id"] != "UNATTRIBUTED" else set()
    member_of -= lead_of
    return {"sam": sam, "name": p.get("worker") or sam, "roles": roles, "lead_of": lead_of, "member_of": member_of,
            "open": False}


def has_access(pr):
    return bool(pr and (pr["roles"] or pr["lead_of"] or pr["member_of"]))


def sees_all(pr):
    """CTO and leadership, Tech Risk, Head of Tech Risk and auditors see every family."""
    return bool(pr["roles"])


def families_seen(pr, all_ids):
    return set(all_ids) if sees_all(pr) else (pr["lead_of"] | pr["member_of"])


def is_tech_risk(pr):
    return bool(pr["roles"] & {"tech_risk", "head_of_tech_risk"})


def can(pr, action, family=None):
    """The roles page's table (docs/wiki/roles-and-permissions.md), one action at a time."""
    r = pr["roles"]
    tr = is_tech_risk(pr)
    if action in ("run_month", "propose"):            # upload, update, acknowledge, lock, reopen; dictionary proposals
        return tr
    if action == "decide":                            # approve, return or decline a proposal
        return "head_of_tech_risk" in r
    if action == "console_read":                      # Data sources, This month, Validation checks, activity, proposals list
        return tr or "auditor" in r
    if action == "download":
        return tr or family in pr["lead_of"]
    if action == "comment":                           # a new explanation, data query or action on a family page
        return tr or family in pr["lead_of"] or family in pr["member_of"]
    if action == "reply":                             # reply to a query or action; leads reply but don't close
        return tr or family in pr["lead_of"]
    if action == "close":
        return tr
    return False


def page_role(pr):
    """The page's own role choice for this person (the page knows cto, tr and fl:<family>)."""
    if is_tech_risk(pr) or "auditor" in pr["roles"]:
        return "tr"
    if "cto_leadership" in pr["roles"]:
        return "cto"
    fams = sorted(pr["lead_of"]) or sorted(pr["member_of"])
    return "fl:" + fams[0] if fams else "cto"


def me(pr):
    """What the page is told about the person."""
    roles = sorted(pr["roles"]) + (["family_lead"] if pr["lead_of"] else []) + (["family_member"] if pr["member_of"] else [])
    return {"sam": pr["sam"], "name": pr["name"], "roles": roles, "role_names": [ROLE_NAMES[r] for r in roles],
            "lead_of": sorted(pr["lead_of"]), "member_of": sorted(pr["member_of"]), "page_role": page_role(pr),
            "read_only": not is_tech_risk(pr) and "auditor" in pr["roles"],
            "can": {"run_month": can(pr, "run_month"), "propose": can(pr, "propose"), "decide": can(pr, "decide"),
                    "console": can(pr, "console_read")}}


# ---- what each person is sent ----

KEEP_OTHER = ("status", "points", "override", "behind_peers", "history", "delta", "provisional")


def filter_data(d, pr):
    """The published data, cut down for family roles: other families keep their scores and colours (the CTO
    view and Firm position are for everyone), but not their numbers, reasons or comments."""
    if sees_all(pr):
        return d
    mine = pr["lead_of"] | pr["member_of"]
    out = json.loads(json.dumps(d))
    for p in (out.get("periods") or {}).values():
        for fid, fr in (p.get("families") or {}).items():
            if fid in mine:
                continue
            fr["metrics"] = {mid: {k: v for k, v in (r or {}).items() if k in KEEP_OTHER}
                             for mid, r in (fr.get("metrics") or {}).items()}
        p["submissions"] = []              # file details are for Tech Risk and auditors
    out["entries"] = [e for e in out.get("entries") or [] if e.get("family_id") in mine]
    return out


def filter_evidence(ev, pr):
    """Item detail (with people's names): only the families a person may see."""
    if sees_all(pr):
        return ev
    mine = pr["lead_of"] | pr["member_of"]
    return {pid: {fid: x for fid, x in (fams or {}).items() if fid in mine} for pid, fams in (ev or {}).items()}
