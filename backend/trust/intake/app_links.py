"""Join the app inventory to everything else, at mapping (owner, 6 Nov 2026). Nothing here is scored.

For each active app (app_status "confirmed"):

1. **Family from the org (the inventory is the golden source).** The second part of app_org_hierarchy is
   matched to an HR Supervisory Organization with its "(Manager Name)" part removed: an exact match
   first, else the closest name scoring at least the setting app_org_match_min (every close match is
   listed with its score). That organization's family is the family most of its people are in (a tie
   places nothing and is listed).
2. **Owners.** Each app_owner_email found in HR is a person. One that isn't is probably an AD group: its
   members from the AD owner groups file (feed app_owner_members) are matched to HR by SAM_ACCOUNT, then
   email. Anything left is Not yet mapped.
3. **Fallback family: HR.** Only when step 1 places nothing, the family most of the app's owners are in.
4. **ITDR ("BCP inventory") by name.** app_id doesn't map to ITDR's Ref, so app_name is matched to the
   ITDR Application Name: exact first, else the closest at the setting app_itdr_match_min, listed.
5. **Service repos to GitHub repos**, with the same matching as Checkmarx (setting app_repo_match_min).

The drill-down then shows each repo's and ITDR application's app and its owners (evidence.py).
"""
from collections import Counter
import re

from .common import norm
from .itdr import AREA_MATCH_CLOSE, department_families, name_similarity, tidy

UNATTRIBUTED = "UNATTRIBUTED"
ORG_MATCH_MIN = 0.85
ITDR_MATCH_MIN = 0.9
REPO_MATCH_MIN = 0.9


def _setting(settings, key, default):
    v = (settings or {}).get(key, default)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0.5 <= v <= 1 else default


def sup_org_name(value):
    """'Payments Engineering (Alex Moreno)' -> 'Payments Engineering' (owner, 6 Nov 2026)."""
    return tidy(re.sub(r"\s*\([^()]*\)\s*$", "", str(value or "")))


def label(app):
    return f"{app['app_name']} ({app['app_id']})" if app["app_name"] != app["app_id"] else app["app_id"]


def _show(v, n=8):
    v = list(dict.fromkeys(v))
    return ", ".join(v[:n]) + (f", and {len(v) - n} more" if len(v) > n else "")


def _closest(name, cands, min_score, cache):
    """-> (candidate, score) or (None, reason). cands: {display name: value}. Exact (tidied) wins; else the
    closest at min_score or above; two different values within 0.02 are too close to call."""
    if name in cache:
        return cache[name]
    exact = cands.get("__norm__", {}).get(norm(name))
    if exact is not None:
        cache[name] = (exact, 1.0)
        return cache[name]
    floor = min_score - 0.001
    scored = sorted(((round(name_similarity(name, c, floor), 3), c) for c in cands["__grams__"].shortlist(name)),
                    key=lambda x: -x[0])
    scored = [x for x in scored if x[0] >= min_score]
    if not scored:
        cache[name] = (None, "none close enough")
    else:
        best, c = scored[0]
        rival = next((x for x in scored[1:] if cands[x[1]] != cands[c]), None)
        cache[name] = ((None, f"about as close to '{c}' ({best:.2f}) as to '{rival[1]}' ({rival[0]:.2f})")
                       if rival and best - rival[0] <= AREA_MATCH_CLOSE else (cands[c], best))
    return cache[name]


def _grams(name):
    """Three-letter pieces of each word ('card ledger' -> car, ard, led, edg, dge, ger); short words whole."""
    out = set()
    for w in re.findall(r"[a-z0-9]+", str(name).lower()):
        out.update({w} if len(w) <= 3 else {w[i:i + 3] for i in range(len(w) - 2)})
    return out


class _Grams:
    """The candidate names worth scoring for a name, found without scoring them all (speed only, 6 Nov 2026:
    thousands of apps against thousands of ITDR names took many minutes). Two names close enough to match share
    most of their three-letter pieces whatever the word order; a candidate sharing fewer than a third of the
    name's pieces can't come near the match settings (0.5 to 1) and is skipped."""

    SHORT = 8          # names this short (letters and digits only) have too few pieces: scored against every short name

    def __init__(self, names):
        self.post, self.short = {}, []
        for n in names:
            for g in _grams(n):
                self.post.setdefault(g, []).append(n)
            if len(norm(n)) <= self.SHORT + 4:
                self.short.append(n)

    def shortlist(self, name):
        mine = _grams(name)
        if not mine:
            return []
        hits = Counter(n for g in mine for n in self.post.get(g, ()))
        need = max(1, len(mine) / 3)
        out = [n for n, k in hits.items() if k >= need]
        if len(norm(name)) <= self.SHORT:
            out = list(dict.fromkeys(out + self.short))
        return out


def _index(names_to_values):
    d = dict(names_to_values)
    d["__norm__"] = {}
    for k, v in names_to_values.items():
        d["__norm__"].setdefault(norm(k), v)
    d["__grams__"] = _Grams(names_to_values)
    return d


def link(apps, people, ad_rows=None, itdr_rows=None, gh_rows=None, cx_feeds=(), settings=None):
    """Place and link the active apps. Sets on each active app: family_id, family_how, org_match, owners,
    owners_not_mapped, itdr (ref, name, tier), repos. Annotates gh rows, cx rows and itdr rows with 'apps'
    (labels) and 'app_owners' (names). Returns dict(summary, by_family, notes)."""
    notes = []
    live = [a for a in apps if a.get("active")]
    people = people or []
    by_email = {p["email"]: p for p in people if p.get("email")}
    by_sam = {p["sam_account"]: p for p in people if p.get("sam_account")}

    # 1. Org -> HR Supervisory Organization (without "(Manager Name)") -> the family most of its people are in.
    org_min = _setting(settings, "app_org_match_min", ORG_MATCH_MIN)
    orgs = department_families([{"department": sup_org_name(p.get("sup_org")), "family_id": p.get("family_id")}
                                for p in people])
    org_index = _index({name: name for name in orgs})
    cache, fuzzy, unknown, tied, too_close = {}, [], [], [], []

    # 2. Owners: HR person, else AD group members found in HR.
    members = {}
    for x in ad_rows or []:
        members.setdefault(x["owner_email"], []).append(x)
    no_ad = ad_rows is None
    owner_cache = {}

    def resolve(email):
        if email in owner_cache:
            return owner_cache[email]
        if email in by_email:
            p = by_email[email]
            res = ([dict(sam=p["sam_account"], name=p.get("worker"), email=email, via="HR")], None)
        elif no_ad:
            res = ([], "not in HR; AD owner groups file not loaded")
        elif email not in members:
            res = ([], "not in HR or the AD owner groups file")
        else:
            found, kinds = [], {m["owner_kind"] for m in members[email]}
            for m in members[email]:
                if not m.get("included") or not m.get("member_sam"):
                    continue
                p = by_sam.get(m["member_sam"]) or by_email.get(m.get("member_email") or "")
                if p:
                    found.append(dict(sam=p["sam_account"], name=p.get("worker"), email=p.get("email"),
                                      via=f"AD group {m.get('group_sam') or email}"))
            why = ("not found in AD" if "not found" in kinds else
                   "no member of the AD group is in HR (the CTO's line)" if not found else None)
            res = (found, why)
        owner_cache[email] = res
        return res

    owner_not_mapped = {}
    for a in live:
        owners, missing = [], []
        for e in a["owner_emails"]:
            got, why = resolve(e)
            owners += got
            if not got:
                missing.append(e)
                owner_not_mapped.setdefault(why, []).append(e)
        seen, a["owners"] = set(), []
        for o in owners:
            if o["sam"] not in seen:
                seen.add(o["sam"])
                a["owners"].append(o)
        a["owners_not_mapped"] = missing

        # Family: org first (golden source), owners' HR family only when the org places nothing.
        a["family_id"], a["family_how"], a["org_match"] = None, None, None
        grp = a.get("org_group")
        if grp and people:
            org, score = _closest(grp, org_index, org_min, cache)
            if org is None:
                (too_close if score.startswith("about") else unknown).append(f"'{grp}'" + (f": {score}" if score.startswith("about") else ""))
            else:
                fid, why = orgs[org]
                a["org_match"] = {"matched": org, "score": score}
                if score < 1:
                    fuzzy.append(f"'{grp}' → '{org}' ({score:.2f})")
                if fid:
                    a["family_id"], a["family_how"] = fid, "org"
                else:
                    tied.append(why)
        if a["family_id"] is None:
            fams = Counter((by_sam.get(o["sam"]) or {}).get("family_id") for o in a["owners"])
            fams.pop(None, None)
            fams.pop(UNATTRIBUTED, None)
            top = fams.most_common(2)
            if top and (len(top) == 1 or top[0][1] > top[1][1]):
                a["family_id"], a["family_how"] = top[0][0], "owners (HR)"
    for a in apps:
        if not a.get("active"):
            a.update(family_id=None, family_how=None, owners=[], owners_not_mapped=[])

    # 4. ITDR by name.
    itdr_notes = []
    itdr_min = _setting(settings, "app_itdr_match_min", ITDR_MATCH_MIN)
    itdr_links = {}
    if itdr_rows is not None:
        by_name = {}
        for r in itdr_rows:
            by_name.setdefault(r["application_name"], []).append(r)
        idx, icache, ifuzzy, inone, iamb = _index({n: n for n in by_name}), {}, [], [], []
        for a in live:
            name, score = _closest(a["app_name"], idx, itdr_min, icache)
            a["itdr"] = None
            if name is None:
                inone.append(label(a))
                continue
            if len(by_name[name]) > 1:
                iamb.append(f"{label(a)} → '{name}' (Refs {', '.join(str(r['ref']) for r in by_name[name])})")
                continue
            r = by_name[name][0]
            a["itdr"] = {"ref": r["ref"], "name": r["application_name"], "tier": r.get("tier_label"), "score": score}
            itdr_links.setdefault(r["ref"], []).append(a)
            if score < 1:
                ifuzzy.append(f"{label(a)} → '{name}' ({score:.2f})")
        for r in itdr_rows:
            linked = itdr_links.get(r["ref"], [])
            r["apps"] = [label(a) for a in linked]
            r["app_owners"] = sorted({o["name"] or o["sam"] for a in linked for o in a["owners"]})
        if (settings or {}).get("itdr_family_from_inventory", True) is not False:
            itdr_notes += _place_itdr(itdr_rows, itdr_links)
        n = len(live)
        notes.append(f"{n - len(inone) - len(iamb)} of {n} active {'app' if n == 1 else 'apps'} linked to an ITDR "
                     f"application by name")
        if ifuzzy:
            notes.append(f"App names linked to ITDR by a close spelling (setting app_itdr_match_min {itdr_min}), "
                         f"check these: {_show(ifuzzy)}")
        if iamb:
            notes.append(f"{len(iamb)} {'app matches' if len(iamb) == 1 else 'apps match'} an ITDR name used on more than "
                         f"one Ref, so not linked (never guessed): {_show(iamb)}")
        if inone:
            notes.append(f"{len(inone)} active {'app has' if len(inone) == 1 else 'apps have'} no ITDR application with "
                         f"the same or a close name: {_show(inone)}")
    else:
        for a in live:
            a["itdr"] = None
        notes.append("For information: ITDR application file not loaded this month: apps aren't linked to ITDR yet.")

    # 5. Service repos -> GitHub repos (same matching as Checkmarx).
    for a in live:
        a["repos"] = []
    if gh_rows is not None:
        from .repos import match_checkmarx
        keys = {}
        for a in live:
            for s in a["services"]:
                if s.get("service_repo"):
                    keys.setdefault(s["service_repo"], []).append(a)
        rows = [{"key": k} for k in keys]
        m = match_checkmarx(rows, gh_rows, _setting(settings, "app_repo_match_min", REPO_MATCH_MIN),
                            what="app inventory", setting="app_repo_match_min")
        notes += [x for x in m["notes"] if "couldn't place with a family" not in x]
        apps_of_repo = {}
        for r in rows:
            if r.get("gh_repo"):
                for a in keys[r["key"]]:
                    if r["gh_repo"] not in a["repos"]:
                        a["repos"].append(r["gh_repo"])
                    apps_of_repo.setdefault(r["gh_repo"], {})[a["app_id"]] = a
        for g in gh_rows:
            linked = list(apps_of_repo.get(g["repo"], {}).values())
            g["apps"] = [label(a) for a in linked]
            g["app_owners"] = sorted({o["name"] or o["sam"] for a in linked for o in a["owners"]})
        for rows_cx in cx_feeds:
            for x in rows_cx or []:
                linked = list(apps_of_repo.get(x.get("gh_repo"), {}).values())
                x["apps"] = [label(a) for a in linked]
                x["app_owners"] = sorted({o["name"] or o["sam"] for a in linked for o in a["owners"]})
    else:
        notes.append("For information: GitHub repo file not loaded this month: service repos aren't linked to repos yet.")

    # Notes on placing.
    if not people:
        notes.append("HR not loaded (or no people kept): every app is Not yet mapped.")
    if fuzzy:
        notes.append(f"{len(set(fuzzy))} {'org was' if len(set(fuzzy)) == 1 else 'orgs were'} matched to an HR "
                     f"Supervisory Organization by a close spelling (setting app_org_match_min {org_min}), check these: "
                     f"{_show(fuzzy)}")
    if too_close:
        notes.append(f"Too close to call, no family from the org: {_show(too_close)}")
    if tied:
        notes.append(f"No family from the org because its people are split evenly: {_show(tied)}")
    if unknown:
        notes.append(f"{len(set(unknown))} {'org isn' if len(set(unknown)) == 1 else 'orgs aren'}'t close enough to an "
                     f"HR Supervisory Organization: {_show(unknown)}")
    for why, emails in owner_not_mapped.items():
        notes.append(f"{len(set(emails))} owner {'email' if len(set(emails)) == 1 else 'emails'} not mapped ({why}): "
                     f"{_show(emails)}")
    by_how = Counter(a["family_how"] for a in live)
    placed = len(live) - by_how.get(None, 0)
    if by_how.get("owners (HR)"):
        notes.append(f"For information: {by_how['owners (HR)']} {'app was' if by_how['owners (HR)'] == 1 else 'apps were'} "
                     "placed by its owners' HR family because the org placed nothing")
    unplaced = [label(a) for a in live if not a["family_id"]]
    if unplaced and people:
        notes.append(f"{len(unplaced)} active {'app is' if len(unplaced) == 1 else 'apps are'} Not yet mapped to a "
                     f"family: {_show(unplaced)}")
    by_family = Counter(a["family_id"] or UNATTRIBUTED for a in live)
    summary = dict(active_apps=len(live), placed=placed, by_org=by_how.get("org", 0),
                   by_owners=by_how.get("owners (HR)", 0), not_placed=len(live) - placed,
                   with_owner_in_hr=sum(1 for a in live if a["owners"]),
                   linked_to_itdr=sum(1 for a in live if a.get("itdr")),
                   with_github_repo=sum(1 for a in live if a["repos"]))
    return dict(summary=summary, by_family=dict(by_family), notes=notes, itdr_notes=itdr_notes)


def _place_itdr(itdr_rows, itdr_links):
    """Owner, 6 Nov 2026: an ITDR application linked to an inventory app takes the app's family (the inventory is the
    golden source); one not linked keeps its Business Product Area's family. Its DR tests and the family's Tier 0/1
    status follow. Apps in different families: nothing changes and it is listed. Setting itdr_family_from_inventory
    false switches this off."""
    placed, moved, split = 0, [], []
    for r in itdr_rows:
        fams = {a["family_id"] for a in itdr_links.get(r["ref"], []) if a.get("family_id")}
        if len(fams) > 1:
            split.append(f"{r['application_name']} (Ref {r['ref']})")
        if len(fams) != 1:
            continue
        fid = fams.pop()
        placed += 1
        if r.get("family_id") != fid:
            moved.append(f"{r['application_name']} (Ref {r['ref']}): {r.get('family_id') or 'not placed'} → {fid}")
        a = itdr_links[r["ref"]][0]
        r["family_id"] = fid
        r["family_match"] = {"how": "app inventory", "matched": label(a), "score": (a.get("itdr") or {}).get("score")}
    notes = [f"For information: {placed} ITDR {'application takes' if placed == 1 else 'applications take'} the family of "
             "the app inventory app it is linked to; the others keep their Business Product Area's family"] if placed else []
    if moved:
        notes.append(f"{len(moved)} ITDR {'application' if len(moved) == 1 else 'applications'} changed family because the "
                     f"app inventory places {'it' if len(moved) == 1 else 'them'} differently from the Business Product Area "
                     f"(their DR tests follow): {_show(moved)}")
    if split:
        notes.append(f"{len(split)} ITDR {'application is' if len(split) == 1 else 'applications are'} linked to inventory "
                     f"apps in different families, so {'it keeps' if len(split) == 1 else 'they keep'} the Business Product "
                     f"Area's family: {_show(split)}")
    return notes
