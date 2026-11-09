"""Made-up provider files for the TEST environment (owner, 4 Nov 2026).

make_world() invents a firm: a CTO, a handful of product families (some product, some platform), the people under
each family's lead, their applications and their GitHub repos. make_month() then writes one month of every provider
file for that world, in the providers' own layouts, so the normal upload, map, score and publish steps can run on
them. Nothing here is real: names, emails (example.test), tickets, incidents and repos are all invented.

Same seed, same site: everything comes from random.Random, never from the clock or the machine. The world is fixed;
each month varies a little (a per-month random stream and a small drift per family) so trends have something to show.

How the made-up results are shaped. Every family gets a "quality" between 0 and 1 for each kind of result (change
approvals, reverts, incidents, overdue actions, scans, repo settings, DR tests). For most families it is high and
close together; one family per result is middling and one is poor. TRUST's tolerance thresholds come from the median
family, so this is what produces some Green, some Amber and some Red. One change in the first family (Payments) in
2026-10 is marked as having client impact, which turns TE-02 Red by rule. The last Tier 0/1-free family is
"Client portal" (or the last product family when there are fewer families), so RE-01 has a family with no result.
"""
import csv
import io
import json
import random
from datetime import date, datetime, timedelta

ORG = "demo-org"
CLIENT_IMPACT = ("Payments", "2026-10")         # (family, month) with one client-impact change
NO_TOP_TIER_FAMILY = "Client portal"            # a family with no Tier 0 or Tier 1 application
FIRST_MONTH = "2026-07"                         # month 0 for the drift

PRODUCT_FAMILIES = ["Payments", "Cards", "Lending", "Treasury", "Client portal", "Markets", "Insurance", "Wealth",
                    "Mortgages"]
PLATFORM_FAMILIES = ["Data platform", "Cloud platform", "Identity", "Observability"]

FIRST = ["Alex", "Blair", "Casey", "Devon", "Elliot", "Finley", "Gray", "Harper", "Indigo", "Jamie", "Kai", "Logan",
         "Morgan", "Noel", "Oakley", "Parker", "Quinn", "Reese", "Sage", "Taylor", "Umber", "Val", "Wren", "Yael",
         "Zion", "Arden", "Briar", "Cory", "Dale", "Emery", "Flynn", "Glen", "Hollis", "Ira", "Jules", "Kerry",
         "Lane", "Marlow", "Nico", "Orion", "Perry", "Remy", "Sky", "Tatum", "Uri", "Vale", "Wynn", "Yuri"]
LAST = ["Abbot", "Barlow", "Cobb", "Dunmore", "Ellery", "Faraday", "Garrow", "Hale", "Ibsen", "Jarrow", "Kestrel",
        "Lowell", "Marsh", "Nettle", "Orme", "Pryce", "Quill", "Rowan", "Sutter", "Thorne", "Ulmer", "Vance",
        "Wick", "Yarrow", "Zeller", "Ashby", "Birch", "Calder", "Dray", "Everly", "Fenwick", "Gable", "Holt",
        "Ives", "Jessop", "Kemp", "Larch", "Mercer", "Norwood", "Oakes", "Pell", "Rook", "Stannard", "Tully",
        "Upton", "Verity", "Wardle", "Yeo", "Ainsley", "Bexley", "Crane", "Dorsey"]
SUBTEAMS = ["Engineering", "Operations", "Quality", "Delivery"]
APP_NOUNS = ["Gateway", "Ledger", "Portal", "Engine", "Hub", "Scheduler", "Router", "Vault", "Reporting",
             "Notifier", "Sync", "Directory", "Broker", "Archive"]
REPO_NOUNS = ["api", "web", "batch", "ledger", "gateway", "worker", "sdk", "events", "config", "reports", "jobs",
              "adapter", "ui", "core", "tools", "infra", "schema", "auth"]
OTHER_DEPTS = ["Finance", "Operations", "People", "Legal", "Sales", "Risk"]

# ---------------------------------------------------------------------------- small helpers


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1])
    return ys[-1]


def _month_parts(month):
    y, m = month.split("-")
    return int(y), int(m)


def _month_start(month):
    y, m = _month_parts(month)
    return date(y, m, 1)


def _next_month_start(month):
    y, m = _month_parts(month)
    return date(y + (m == 12), m % 12 + 1, 1)


def _month_index(month):
    y, m = _month_parts(month)
    y0, m0 = _month_parts(FIRST_MONTH)
    return (y * 12 + m) - (y0 * 12 + m0)


def _slug(text):
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def _csv(headers, rows):
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(headers)
    w.writerows(rows)
    return out.getvalue().encode("utf-8")


def _xlsx(headers, rows):
    """Excel with the header merged over rows 1 and 2, then one row per line (as the ITDR and DR tests files come)."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
        ws.merge_cells(start_row=1, start_column=c, end_row=2, end_column=c)
    for i, r in enumerate(rows):
        for c, v in enumerate(r, start=1):
            ws.cell(row=3 + i, column=c, value=v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _us_datetime(d):
    return d.strftime("%m/%d/%Y %I:%M:%S %p")


def _profile(rng, n):
    """Qualities for n families: most high and close together, one or two middling, one poor (shuffled by the caller)."""
    if n <= 2:
        return [0.85, 0.62][:n]
    mids = 2 if n >= 7 else 1
    out = [rng.uniform(0.74, 0.95) for _ in range(max(n - 1 - mids, 0))] + [rng.uniform(0.58, 0.66) for _ in range(mids)]
    out.append(rng.uniform(0.36, 0.44))
    return out


def _frac_re(q):
    """Share of a family's applications with a passed test: all of them for the high group, about half to three
    quarters for the middling family, none for the poor one."""
    return _interp(q, [0.30, 0.44, 0.58, 0.66, 0.70, 0.95], [0.0, 0.0, 0.5, 0.75, 1.0, 1.0])


def _pass_rate(q):
    """Share of scanned repos that pass: 90 to 100 percent for the high group, about 70 for the middling one, 50 for the poor."""
    return _interp(q, [0.30, 0.44, 0.58, 0.66, 0.74, 0.95], [0.42, 0.50, 0.72, 0.84, 0.96, 1.0])


GROUPS = ("te01", "te02", "un01", "un02", "se01", "se02", "tr02", "re01", "re03")


# ---------------------------------------------------------------------------- the world


class _Namer:
    def __init__(self, rng):
        self.rng, self.names, self.sams, self.emails = rng, set(), set(), set()

    def person(self, **kw):
        for _ in range(500):
            first, last = self.rng.choice(FIRST), self.rng.choice(LAST)
            if f"{first} {last}" in self.names:
                continue
            self.names.add(f"{first} {last}")
            base = (first[0] + last).lower()
            sam = f"{base}{self.rng.randint(1, 9)}"
            while sam in self.sams:
                sam = f"{base}{self.rng.randint(1, 99)}"
            self.sams.add(sam)
            email = f"{first}.{last}@example.test".lower()
            while email in self.emails:
                email = f"{first}.{last}{self.rng.randint(2, 99)}@example.test".lower()
            self.emails.add(email)
            return dict(first=first, last=last, name=f"{first} {last}", sam=sam, email=email, **kw)
        raise ValueError("ran out of made-up names")


def make_world(families=8, seed=7, cto_sam=None):
    """A made-up firm. Returns a dict (JSON-friendly) with at least cto_sam."""
    rng = random.Random(f"{seed}:world")
    families = max(1, min(len(PRODUCT_FAMILIES) + len(PLATFORM_FAMILIES), int(families)))
    cto_sam = (cto_sam or "cto.demo").strip()
    namer = _Namer(rng)

    ceo = namer.person(manager_sam=None, level=1, dept="Office of the CEO", is_manager=True, country="United States of America")
    ceo["sam"] = "ceo.demo"
    cto = namer.person(manager_sam=ceo["sam"], level=2, dept="Technology", is_manager=True, country="United States of America")
    cto["sam"] = cto_sam
    cto["email"] = f"{cto['first']}.{cto['last']}@example.test".lower()

    platform_n = round(families / 3)
    product_n = families - platform_n
    names = PRODUCT_FAMILIES[:product_n] + PLATFORM_FAMILIES[:platform_n]
    bands = ["product"] * product_n + ["platform"] * platform_n

    profiles = {g: _profile(rng, families) for g in GROUPS}
    if families >= 6:           # TE-01 share of changes through TCC: most families high, three lower (spread for the median)
        profiles["te01"] = ([rng.uniform(0.84, 0.95) for _ in range(families - 3)]
                            + [rng.uniform(0.66, 0.70), rng.uniform(0.54, 0.58), rng.uniform(0.38, 0.42)])
    for g in GROUPS:
        rng.shuffle(profiles[g])
    no_top = NO_TOP_TIER_FAMILY if NO_TOP_TIER_FAMILY in names else names[min(product_n, len(names)) - 1]
    # The family with no Tier 0/1 app has no DR result, so it must not hold the poor or middling quality; and a family
    # that is poor at DR tests is poor at resiliency testing generally (RE-03 counts DR tests too).
    i = names.index(no_top)
    best = max(range(families), key=lambda k: profiles["re01"][k])
    profiles["re01"][i], profiles["re01"][best] = profiles["re01"][best], profiles["re01"][i]
    profiles["re03"] = list(profiles["re01"])

    fams, used_apps, used_repos, ref = [], set(), set(), 100
    for i, (name, band) in enumerate(zip(names, bands)):
        token = name.split()[0]
        lead = namer.person(manager_sam=cto["sam"], level=3, dept=name, is_manager=True,
                            country=rng.choice(["United States of America"] * 3 + ["United Kingdom"]))
        size = rng.randint(6, 15)                                   # people under the lead, managers included
        n_mgr = 1 if size < 9 else 2
        subteams = [f"{token} {s}" for s in SUBTEAMS[:n_mgr + 1]]
        managers = [namer.person(manager_sam=lead["sam"], level=4, dept=subteams[k], is_manager=True,
                                 country=lead["country"]) for k in range(n_mgr)]
        staff = []
        for k in range(size - n_mgr):
            mgr = managers[k % n_mgr]
            staff.append(namer.person(manager_sam=mgr["sam"], level=5, dept=mgr["dept"], is_manager=False,
                                      country=lead["country"]))
        for p in staff:
            p["contingent"] = rng.random() < 0.08
        if len(staff) > 5:                                          # a few joiners, so headcount moves a little
            for p in rng.sample(staff, rng.randint(1, 2)):
                p["from"] = rng.choice(["2026-08", "2026-09", "2026-10"])

        # applications
        tiers = ["Tier 0", "Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5", "TBC"]
        weights = [12, 23, 22, 17, 10, 6, 10]
        apps = []
        n_apps = rng.randint(2, 6)
        nouns = rng.sample(APP_NOUNS, n_apps)
        for k in range(n_apps):
            if name == no_top:
                tier = "Tier 2" if k == 0 else rng.choice(["Tier 2", "Tier 3", "Tier 4", "Tier 5", "TBC"])
            elif k == 0:
                tier = rng.choice(["Tier 0", "Tier 1"])
            elif k == 1 and rng.random() < 0.6:
                tier = "Tier 1"
            else:
                tier = rng.choices(tiers, weights)[0]
            app_name = f"{token} {nouns[k]}"
            while app_name in used_apps:
                app_name += " 2"
            used_apps.add(app_name)
            ref += 1
            apps.append(dict(ref=ref, name=app_name, tier=tier, area=name,
                             lead=rng.choice([lead] + managers)["name"],
                             test_date=(date(2025, 11, 1) + timedelta(days=rng.randint(0, 235))).isoformat(),
                             old_test_date=(date(2024, 10, 1) + timedelta(days=rng.randint(0, 200))).isoformat(),
                             test_type=rng.choice(["Open", "Closed", "Closed"]),
                             ttx_date=(date(2025, 11, 1) + timedelta(days=rng.randint(0, 235))).isoformat()))

        # repos
        n_repos = rng.randint(3, 12)
        people = managers + [p for p in staff if not p.get("from")]       # repo owners are in the firm all year
        rnouns = rng.sample(REPO_NOUNS, min(n_repos, len(REPO_NOUNS)))
        rnouns += [f"svc{k}" for k in range(n_repos - len(rnouns))]
        total = 5 * n_repos
        strata = [(k + 0.5) / total for k in range(total)]
        rng.shuffle(strata)
        sca_strata = [(k + 0.5) / n_repos for k in range(n_repos)]
        sast_strata = [(k + 0.5) / n_repos for k in range(n_repos)]
        rng.shuffle(sca_strata)
        rng.shuffle(sast_strata)
        repos = []
        for k in range(n_repos):
            full = f"{ORG}/{_slug(name)}-{rnouns[k]}"
            used_repos.add(full)
            repos.append(dict(name=full, owner=rng.choice(people)["sam"], u=strata[k * 5:(k + 1) * 5],
                              sast_u=sast_strata[k], sca_u=sca_strata[k], special=None,
                              codeowners=rng.random() < 0.7, status_checks=rng.random() < 0.8,
                              stale=rng.random() < 0.5))
        fams.append(dict(
            id=_slug(name), name=name, band=band, token=token, lead=lead, managers=managers, staff=staff,
            subteams=subteams, apps=apps, repos=repos,
            q={g: profiles[g][i] for g in GROUPS},
            slope={g: rng.uniform(-0.012, 0.015) for g in GROUPS},
            tcc_n=rng.randint(20, 60), open_actions=rng.randint(4, 10),
            legacy=[dict(id=f"INC-L{i + 1}{k + 1}", end=(date(2026, 3, 10) + timedelta(days=rng.randint(0, 45))).isoformat(),
                         defcon=rng.choice([3, 4])) for k in range(2)]))

    # a few repos that are archived, forks, bot-only or dormant (never one of a family's first three)
    spare = [(f, r) for f in fams for r in f["repos"][3:]]
    rng.shuffle(spare)
    for kind, count in (("archived", 2), ("fork", 2), ("bot", 2), ("dormant", max(1, len(spare) // 12))):
        for _ in range(min(count, len(spare))):
            spare.pop()[1]["special"] = kind

    # people outside the CTO's line: the firm-wide HR file holds them, TRUST must cut them out
    outside = []
    heads = []
    for dept in OTHER_DEPTS[:4]:
        h = namer.person(manager_sam=ceo["sam"], level=2, dept=dept, is_manager=True, country="United States of America")
        h["exec"] = dept
        heads.append(h)
        outside.append(h)
    while len(outside) < 34:
        h = rng.choice(heads)
        p = namer.person(manager_sam=h["sam"], level=3, dept=h["dept"], is_manager=False, country=rng.choice(
            ["United States of America", "United Kingdom"]))
        p["exec"] = h["dept"]
        outside.append(p)

    return dict(seed=seed, cto_sam=cto_sam, ceo=ceo, cto=cto, families=fams, outside=outside, no_top_family=no_top)


# ---------------------------------------------------------------------------- per-month qualities


def _q(world, fam, group, month, rng):
    """The family's quality for one kind of result in one month: base + drift + a little noise."""
    return _clamp(fam["q"][group] + fam["slope"][group] * _month_index(month) + rng.uniform(-0.012, 0.012), 0.3, 0.97)


def _present(p, month):
    return p.get("from") is None or p["from"] <= month


def _people(fam, month, with_lead=False):
    ppl = [p for p in fam["managers"] + fam["staff"] if _present(p, month)]
    return ([fam["lead"]] + ppl) if with_lead else ppl


# ---------------------------------------------------------------------------- HR


def _hr(world, month):
    cto, ceo = world["cto"], world["ceo"]
    line = [(cto, "Technology")]
    for f in world["families"]:
        line.append((f["lead"], f["name"]))
        line.extend((p, p["dept"]) for p in _people(f, month))
    everyone = [(ceo, "Office of the CEO")] + line + [(p, p["dept"]) for p in world["outside"]]
    name_of = {p["sam"]: p["name"] for p, _ in everyone}
    reports = {}
    for p, _ in everyone:
        if p["manager_sam"]:
            reports[p["manager_sam"]] = reports.get(p["manager_sam"], 0) + 1
    cto_exec = f"Technology ({cto['name']})"
    headers = ["Worker", "Email - Work", "Workers Manager", "Supervisory Organization", "Top Level Supervisory",
               "Executive Level Supervisory", "Department", "Worker Type", "Position Worker Type",
               "Location Address - Country", "Is Manager", "Number of Direct Reports", "VP or Higher",
               "Management reporting level from top", "Worker SAM_Acct"]
    rows = []
    for p, dept in everyone:
        mgr = name_of.get(p["manager_sam"], "")
        in_line = p is cto or (p["sam"] in {x["sam"] for x, _ in line})
        if p is ceo:
            sup = top = exe = f"Office of the CEO ({p['name']})"
        elif not in_line:
            sup = f"{p['dept']} ({mgr})" if p["level"] > 2 else f"{p['dept']} ({p['name']})"
            top = exe = f"{p['exec']} ({next(h['name'] for h in world['outside'] if h['dept'] == p['exec'] and h['level'] == 2)})"
        else:
            if p is cto:
                sup = top = f"Technology ({p['name']})"
            elif p["level"] == 3:
                sup, top = f"{dept} ({p['name']})", f"Technology ({cto['name']})"
            elif p["is_manager"]:
                sup, top = f"{dept} ({p['name']})", f"Technology ({cto['name']})"
            else:
                sup, top = f"{dept} ({mgr})", f"Technology ({cto['name']})"
            exe = cto_exec                                          # the rule: starts with 'Technology'
        contingent = p.get("contingent")
        rows.append([p["name"], p["email"], mgr, sup, top, exe, dept,
                     "Contingent" if contingent else "Employee", "Agency contractor" if contingent else "Regular",
                     p.get("country", "United States of America"), "Yes" if p["is_manager"] else "No",
                     reports.get(p["sam"], 0), "Yes" if p["level"] <= 2 else "No", p["level"], p["sam"]])
    return "hr_firmwide.csv", _csv(headers, rows)


def _hr_mapping(world):
    doc = [{"product_line": f["name"], "owner_email": f["lead"]["email"], "band": f["band"]} for f in world["families"]]
    return "product_line_owners.json", json.dumps(doc, indent=1).encode("utf-8")


# ---------------------------------------------------------------------------- TCC and Non-TCC

TCC_HEADERS = ["RPD ID", "RPD Link", "Title", "Status", "Change Category", "Risk Score", "Created date (UTC)", "Author",
               "Author email", "Assignees", "Department", "L4 director", "Planned Start", "Planned End",
               "Actual Last Deployment", "Implementer", "Peer reviewer", "Peer review outcome", "Confirmed Risk Rating",
               "Overall Change Approval", "SBU Engineering Head Approver", "Stakeholder Approvers",
               "Go/No-Go Meeting", "Go/No-Go Outcome", "Install Window", "Overall outcome", "Resolved",
               "Pre-Deploy Compliant", "Fully Compliant", "Fields Missing", "Peer Review Recorded At (UTC)",
               "Approval Recorded At (UTC)", "Outcome Recorded At (UTC)"]
TITLES = ["Release {} service", "Config change for {}", "Patch {} runtime", "Scale {} workers", "Rotate {} certificates",
          "Roll out {} feature flag", "Upgrade {} library"]


def _tcc(world, month):
    rng = random.Random(f"{world['seed']}:{month}:tcc")
    y, m = _month_parts(month)
    base_id = int(f"{y}{m:02d}") * 1000
    rows, k = [], 0
    for fam in world["families"]:
        people = _people(fam, month)
        q1, q2 = _q(world, fam, "te01", month, rng), _q(world, fam, "te02", month, rng)
        n = max(18, fam["tcc_n"] + rng.randint(-4, 4))
        p_ok = _interp(q1, [0.30, 0.40, 0.50, 0.62, 0.70, 0.80, 0.95], [0.42, 0.48, 0.53, 0.56, 0.70, 0.84, 1.0])
        approved = [True] * round(p_ok * n) + [False] * (n - round(p_ok * n))
        rng.shuffle(approved)
        rate = max(0.0, 0.15 * (0.95 - q2) / 0.6)
        reverted = set(rng.sample(range(n), round(rate * n)))
        client_row = rng.randrange(n) if (fam["name"], month) == CLIENT_IMPACT else None
        if client_row is not None:
            reverted.add(client_row)
        for j in range(n):
            k += 1
            author, impl, rev = rng.choice(people), rng.choice(people), rng.choice(people)
            day = rng.randint(1, 20)
            created = datetime(y, m, day, rng.randint(8, 10), rng.randint(0, 59))
            deployed = datetime(y, m, day + rng.randint(0, 1), rng.randint(13, 17), rng.randint(0, 59))
            ok = approved[j]
            if ok:
                category = rng.choice(["Planned", "Planned", "Standard", "Emergency"])
                approval, approval_at = "Approved", created + timedelta(hours=rng.randint(1, 3))
            else:
                category = rng.choice(["Planned", "Emergency"])
                if rng.random() < 0.5:
                    approval, approval_at = "", None
                else:
                    approval, approval_at = "Approved", deployed + timedelta(hours=rng.randint(1, 3))
            if j in reverted:
                outcome = "90 FAIL backout initiated by client" if j == client_row else rng.choice(["40", "50", "60"])
            else:
                outcome = rng.choice(["10", "10", "00"])
            status = "Client" if j == client_row else rng.choice(["Completed", "Completed", "Resolved", "Monitoring"])
            tid = base_id + k
            rows.append([
                tid, f"https://tcc.example.test/{tid}", rng.choice(TITLES).format(fam["token"]), status, category,
                rng.choice(["Standard Change", "LOW risk", "LOW risk", "MEDIUM risk", "HIGH risk"]),
                _us_datetime(created), author["name"], author["email"].title() if rng.random() < 0.2 else author["email"],
                f"{impl['name']}; {rev['name']}", author["dept"], fam["lead"]["name"],
                _us_datetime(created + timedelta(hours=4)), _us_datetime(created + timedelta(hours=6)),
                deployed.strftime("%Y-%m-%dT%H:%M:%S.0000000"), impl["name"], rev["name"], "10", "",
                approval, "", "", "", "", "", outcome, "Yes", "Yes" if ok else "No", "Yes" if ok else "No", "",
                _us_datetime(created + timedelta(hours=2)), _us_datetime(approval_at) if approval_at else "",
                _us_datetime(deployed + timedelta(days=1))])
    return "tcc_export.csv", _csv(TCC_HEADERS, rows)


def _ntcc(world, month):
    rng = random.Random(f"{world['seed']}:{month}:ntcc")
    y, m = _month_parts(month)
    headers = ["RPD ID", "RPD Link", "Title", "Status", "RPD Category", "Created Date (UTC)", "Last updated (UTC)",
               "Author", "Author Email", "Assignees", "Department", "L4 director"]
    rows = []
    # TE-01 (owner, 8 Nov 2026): a family's share of changes through TCC follows its "te01" quality, so its
    # Non-TCC changes are about tcc_n x (1 - q) / q.
    picks = []
    for fam in world["families"]:
        q = max(0.3, _q(world, fam, "te01", month, rng))
        picks += [fam] * round(fam["tcc_n"] * (1 - q) / q)
    for k, fam in enumerate(picks):
        a = rng.choice(_people(fam, month))
        created = datetime(y, m, rng.randint(1, 20), 10, 0)
        rows.append([f"{int(f'9{y}{m:02d}') * 1000 + k + 1}", f"https://rpd.example.test/{k + 1}",   # 9-prefix: never a TCC id
                     rng.choice(["Hotfix", "Tweak", "Patch"]), rng.choice(["Completed", "Resolved", "Monitoring"]),
                     rng.choice(["Hotfix", "Change"]), _us_datetime(created), _us_datetime(created + timedelta(days=2)),
                     a["name"], a["email"], "", a["dept"], fam["lead"]["name"]])
    return "ntcc_export.csv", _csv(headers, rows)


# ---------------------------------------------------------------------------- postmortems and actions


def _incidents_and_actions(world, month):
    rng = random.Random(f"{world['seed']}:{month}:ops")
    y, m = _month_parts(month)
    start, end = _month_start(month), _next_month_start(month)
    incidents, actions = [], []                                   # incidents: dicts; actions: dicts
    pm_id, act_no = [1000 * (y % 100) + 10 * m], [0]

    def incident(fam, iid, ended, defcon, title=None):
        pm_id[0] += 1
        inc = dict(id=iid, fam=fam, end=ended, defcon=defcon, pm=pm_id[0],
                   title=title or f"Incident in {fam['name']}")
        incidents.append(inc)
        return inc

    def action(fam, inc, created, eta, status, assignee):
        act_no[0] += 1
        key = f"{fam['token'][:4].upper()}-{y % 100}{m:02d}{act_no[0]:03d}"
        actions.append(dict(key=key, fam=fam, inc=inc, created=created, eta=eta, status=status, who=assignee))

    for fam in world["families"]:
        people = _people(fam, month)
        n_new = round(max(0.0, 6 * (0.95 - _q(world, fam, "un01", month, rng)) / 0.6))
        mine = []
        for L in fam["legacy"]:
            if date.fromisoformat(L["end"]) < start:
                mine.append(incident(fam, L["id"], date.fromisoformat(L["end"]), L["defcon"], f"Earlier incident in {fam['name']}"))
        legacy = list(mine)
        for k in range(n_new):
            mine.append(incident(fam, f"INC-{y % 100}{m:02d}-{fam['token'][:3].upper()}{k + 1}",
                                 date(y, m, rng.randint(2, 18)), rng.choice([1, 2, 3, 3, 4, 4, 5])))
        for inc in mine:                                           # one finished action so every incident is placed
            action(fam, inc, inc["end"] + timedelta(days=2), inc["end"] + timedelta(days=30), "Completed", rng.choice(people))
        q = _q(world, fam, "un02", month, rng)
        n_open = max(3, fam["open_actions"] + rng.randint(-1, 1))
        n_over = round(_interp(q, [0.30, 0.44, 0.58, 0.66, 0.74, 0.95], [0.9, 0.75, 0.4, 0.28, 0.15, 0.0]) * n_open)
        for j in range(n_open):
            overdue = j < n_over
            pool = legacy if (overdue and legacy) else mine
            inc = pool[j % len(pool)]
            created = inc["end"] + timedelta(days=rng.randint(1, 9))
            if overdue:
                lo = created + timedelta(days=14)
                eta = lo + timedelta(days=rng.randint(0, max(0, (end - timedelta(days=1) - lo).days)))
            else:
                eta = end + timedelta(days=rng.randint(5, 60))
            action(fam, inc, created, eta, rng.choice(["To Do", "In Progress", "In Progress", "Queued", "Monitoring"]),
                   rng.choice(people))

    # incidents with no rating (DEFCON Not Available) and one DEFCON 0, so the scope rules have something to read
    for k, fam in enumerate(rng.sample(world["families"], min(3, len(world["families"])))):
        inc = incident(fam, f"INC-{y % 100}{m:02d}-NA{k + 1}", date(y, m, rng.randint(3, 16)),
                       "Not Available" if k < 2 else 0)
        action(fam, inc, inc["end"] + timedelta(days=1), end + timedelta(days=20), "To Do", rng.choice(_people(fam, month)))
    return incidents, actions


def _postmortems(world, month):
    incidents, actions = _incidents_and_actions(world, month)
    headers = ["incident_id", "incident_title", "SBU", "Status", "start_datetime", "end_datetime", "Incident type",
               "Incident Defcon", "incident_defcon_type", "critical_or_swe_escalated", "postmortem_conducted",
               "user_stakeholders", "postmoretm_id", "postmortem_is_primary", "action_items_total"]
    n_actions = {}
    for a in actions:
        n_actions[a["inc"]["id"]] = n_actions.get(a["inc"]["id"], 0) + 1
    rows = []
    for inc in incidents:
        d = inc["defcon"]
        dtype = ("Cannot determine defcon type" if d == "Not Available" else "false alarm" if d == 0
                 else "SWE" if d in (1, 2) else "critical")
        e = datetime(inc["end"].year, inc["end"].month, inc["end"].day, 15, 30)
        rows.append([inc["id"], inc["title"], inc["fam"]["name"], "Closed", (e - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     e.strftime("%Y-%m-%dT%H:%M:%SZ"), "Critical/SWE", d, dtype, "True", "True",
                     inc["fam"]["lead"]["sam"], inc["pm"], "true", n_actions.get(inc["id"], 0)])
    return "postmortems_export.csv", _csv(headers, rows), incidents, actions


def _actions(world, month, actions):
    headers = ["Type", "ActionItemLink", "ActionItemTitle", "Severity", "Created", "ETA", "DaysLeftOrPastETA", "Assignees",
               "ActionCategory", "Status", "OriginalRpds", "SBU", "PostmortemLink", "PostmortemTitle", "incident_id",
               "incident_title"]
    end = _next_month_start(month)
    rows = []
    for a in actions:
        link = f'=HYPERLINK("https://jira.example.test/browse/{a["key"]}","JIRA:{a["key"]}")'
        left = (a["eta"] - end).days
        rows.append(["JIRA", link, f"Follow-up for {a['inc']['id']}", ["High", "Medium", "Low"][a["inc"]["pm"] % 3],
                     f"{a['created'].month}/{a['created'].day}/{a['created'].year}",
                     f"{a['eta'].month}/{a['eta'].day}/{a['eta'].year}", left, a["who"]["email"],
                     ["Prevent", "Detect", "Mitigate"][a["inc"]["pm"] % 3], a["status"], "", a["fam"]["name"],
                     f"https://pm.example.test/{a['inc']['pm']}", f"Postmortem {a['inc']['id']}", a["inc"]["id"],
                     a["inc"]["title"]])
    return "actions_export.csv", _csv(headers, rows)


# ---------------------------------------------------------------------------- repos and Checkmarx

REPO_HEADERS = ["Repo", "Url", "Archived", "Fork", "Empty", "DefaultBranch", "PushedAt", "LastDefaultBranchCommit",
                "ProtectionSource", "BranchProtected", "RequiredApprovals", "LastPushApprovalRequired",
                "ForcePushAllowed", "DeletionsAllowed", "AdminEnforced", "BypassAllowed", "StaleReviewsDismissed",
                "CodeOwnerReviewRequired", "StatusChecksRequired", "CodeOwnersFile", "LastHumanCommitterEmail",
                "LastHumanCommitterLogin", "LastHumanCommitDate", "TopCommitterEmail", "TopCommitterLogin",
                "TopCommitterShare", "HumanCommitsSampled"]


def _repos(world, month):
    rng = random.Random(f"{world['seed']}:{month}:repos")
    end = _next_month_start(month)
    people = {p["sam"]: p for f in world["families"] for p in [f["lead"]] + f["managers"] + f["staff"]}
    rows = []
    for fam in world["families"]:
        q = _q(world, fam, "tr02", month, rng)
        d = _interp(q, [0.30, 0.44, 0.58, 0.66, 0.74, 0.95], [0.45, 0.58, 0.86, 0.92, 0.97, 1.0])   # chance each of a repo's 5 checks passes
        for r in fam["repos"]:
            owner = people[r["owner"]]
            special = r["special"]
            pushed = end - timedelta(days=rng.randint(1, 55))
            if special in ("dormant", "bot", "archived", "fork"):
                pushed = date(2026, 1, 5) + timedelta(days=rng.randint(0, 25))
            if special == "bot":
                commit_email, login = "", "ci-bot[bot]"
            else:
                commit_email, login = owner["email"], owner["sam"]
            u = r["u"]
            prot = u[0] < min(1.0, d + 0.1)
            review = u[1] < d
            indep = u[2] < d
            history = u[3] < d
            nobypass = u[4] < d
            rows.append([
                r["name"], f"https://github.example.test/{r['name']}", str(special == "archived"), str(special == "fork"),
                "False", "main", f"{pushed.isoformat()}T10:00:00Z", f"{pushed.isoformat()}T10:00:00Z",
                "branch protection" if prot else "none", str(prot), (2 if u[1] < d / 2 else 1) if (prot and review) else 0,
                str(prot and indep), "False" if (prot and history) else "True",
                "False" if (prot and history) else str(rng.random() < 0.5),
                str(prot and nobypass), "False" if (prot and nobypass) else "True",
                str(r["stale"]), "False", str(r["status_checks"]), str(r["codeowners"]), commit_email, login,
                "" if special == "bot" else f"{pushed.isoformat()}T09:00:00Z", commit_email, login,
                "" if special == "bot" else f"{0.45 + (u[0] * 0.5):.2f}", "0" if special == "bot" else "20"])
    return "repos.csv", _csv(REPO_HEADERS, rows)


def _checkmarx(world, month, kind):
    rng = random.Random(f"{world['seed']}:{month}:{kind}")
    group, key_u = ("se01", "sast_u") if kind == "SAST" else ("se02", "sca_u")
    entries = []
    for fam in world["families"]:
        q = _q(world, fam, group, month, rng)
        pass_rate = _pass_rate(q)
        for r in fam["repos"]:
            if r["special"] in ("archived", "fork", "bot"):
                continue
            if r[key_u] < pass_rate:
                comment = rng.choice([f"Compliant. No {kind} findings detected.",
                                      f"COMPLIANT All {rng.randint(1, 12)} {kind} findings are within acceptable aging thresholds for their security levels."])
                ok = True
            else:
                opn = rng.randint(3, 15)
                over = rng.randint(1, min(opn, 5))
                med = rng.randint(0, over)
                high = over - med if rng.random() < 0.8 else 0
                low = over - med - high
                parts = [f"{n} {s}" for n, s in ((high, "HIGH"), (med, "MEDIUM"), (low, "LOW")) if n]
                comment = f"NON-COMPLIANT `{over}/{opn}` {kind} findings exeed their aging thresholds. Violations: {', '.join(parts)}."
                ok = False
            entries.append({"key": r["name"], "measurements": [
                {"name": f"checkmarx-{kind.lower()}-policy-compliant", "value": ok, "comment": comment}]})
    doc = {"importer": "checkmarx", "data": entries}
    return f"final_checkmarx_{kind.lower()}_report.json", json.dumps(doc, indent=1).encode("utf-8")


# ---------------------------------------------------------------------------- ITDR and DR tests


def _itdr(world):
    rows = [[a["ref"], a["name"], a["area"], a["tier"]] for f in world["families"] for a in f["apps"]]
    return "itdr_applications.xlsx", _xlsx(["Ref", "Application Name", "Business Product Area", "Recovery Tier"], rows)


def _dr_tests(world, month):
    """Which apps have a successful DR test (Tier 0/1: RE-01) or a DR test or tabletop (Tier 0-2: RE-03) this month."""
    rng = random.Random(f"{world['seed']}:{month}:dr")
    start = _month_start(month)
    rows = []

    def ordinal(n):
        return "%d%s" % (n, "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))

    def dr_row(a, f, when, ok):
        if ok:
            comment = f"DR Test completed on {ordinal(when.day)} {when.strftime('%B %Y')}"
            return [a["tier"], a["name"], f["name"], a["lead"], a["test_type"], "", "Successful", comment]
        return [a["tier"], a["name"], f["name"], a["lead"], a["test_type"], "", "", ""]

    def ttx_row(a, f, when):
        return [a["tier"], a["name"], f["name"], a["lead"], "TTX", when.strftime("%m/%d/%Y"), "Successful",
                "TTX: Tabletop exercise completed"]

    for f in world["families"]:
        top = [a for a in f["apps"] if a["tier"] in ("Tier 0", "Tier 1")]
        mid = [a for a in f["apps"] if a["tier"] == "Tier 2"]
        k01 = round(_frac_re(_q(world, f, "re01", month, rng)) * len(top))
        k03 = round(_frac_re(_q(world, f, "re03", month, rng)) * (len(top) + len(mid)))
        dr_done = top[:k01]
        order = mid + top[k01:]                                       # next in line for a passed test of any kind
        extra = order[:max(0, k03 - len(dr_done))]
        for a in f["apps"]:
            if a["tier"] not in ("Tier 0", "Tier 1", "Tier 2"):
                continue
            when = min(date.fromisoformat(a["test_date"]), start - timedelta(days=10))
            if a in dr_done:
                rows.append(dr_row(a, f, when, True))
            elif a in extra:
                if a["tier"] == "Tier 2" and rng.random() < 0.5:
                    rows.append(dr_row(a, f, when, True))
                else:
                    rows.append(ttx_row(a, f, min(date.fromisoformat(a["ttx_date"]), start - timedelta(days=10))))
                    if a["tier"] in ("Tier 0", "Tier 1"):
                        rows.append(dr_row(a, f, date.fromisoformat(a["old_test_date"]), True))   # old DR test: out of the window
            else:
                rows.append(dr_row(a, f, None, False) if rng.random() < 0.5
                            else dr_row(a, f, date.fromisoformat(a["old_test_date"]), True))
    headers = ["Tier", "Name", "Business Area", "ITDR Lead", "Type of Test", "When", "Status", "Comments"]
    return "dr_tests.xlsx", _xlsx(headers, rows)


# ---------------------------------------------------------------------------- Jira


def _defects(world, month):
    rng = random.Random(f"{world['seed']}:{month}:jira")
    y, m = _month_parts(month)
    headers = ["issue_key", "project", "issue_type", "is_defect", "priority", "severity", "found_in_env", "status",
               "status_category", "resolution", "created_at", "first_in_progress_at", "resolved_at", "closed_by",
               "closed_by_email", "closed_by_username", "reopen_count", "story_points"]
    rows = []
    for k in range(15):
        fam = rng.choice(world["families"])
        who = rng.choice(_people(fam, month))
        itype = rng.choice(["Bug", "Bug", "Story", "Task"])
        created = datetime(y, m, rng.randint(1, 10), 9, 0)
        started = created + timedelta(days=1)
        resolved = started + timedelta(days=rng.randint(1, 12))
        proj = fam["token"][:3].upper()
        rows.append([f"{proj}-{y % 100}{m:02d}{k + 1:02d}", proj, itype, str(itype == "Bug"),
                     rng.choice(["High", "Medium", "Low"]), rng.choice(["Major", "Minor", ""]),
                     rng.choice(["Production", "UAT", ""]), "Done", "done", "Done", created.isoformat() + "Z",
                     started.isoformat() + "Z", resolved.isoformat() + "Z", who["name"], who["email"], who["sam"],
                     rng.choice([0, 0, 0, 1]), rng.choice([1, 2, 3, 5, 8]) if itype != "Bug" else ""])
    return "jira_issues.csv", _csv(headers, rows)


# ---------------------------------------------------------------------------- app inventory and AD owner groups

APP_INV_HEADERS = ["app_id", "app_name", "app_status", "app_department", "app_sbu", "app_org_hierarchy", "app_owner_raw",
                   "app_owner_type", "app_owner_email", "bcp_tier", "bcp_tier_source", "itdr_match", "service_id",
                   "service_name", "service_owner_email", "service_repo", "unmapped_reasons"]
AD_HEADERS = ["owner_email", "owner_kind", "group_sam", "member_sam", "member_email", "member_name", "member_enabled",
              "included", "reason"]


def _owner_dl(fam):
    return f"dl-{_slug(fam['name'])}-apps@example.test"


def _app_inventory(world):
    """One row per application service (owner, 6 Nov 2026). Each ITDR application is in it (once spelt a little
    differently), most owned by the family's distribution list; one app's org isn't in HR, so its owner's family is
    used; one owner list isn't in AD; a couple of apps aren't 'Confirmed'. Its own random stream: other files don't move."""
    rng = random.Random(f"{world['seed']}:apps")
    rows, n = [], 0
    for fi, fam in enumerate(world["families"]):
        live = [r for r in fam["repos"] if not r["special"]]
        for k, a in enumerate(fam["apps"]):
            n += 1
            app_id = f"APP-{1000 + n}"
            name = a["name"] if not (fi == 0 and k == 0) else a["name"][:-1]          # a close spelling of the ITDR name
            org = rng.choice(fam["subteams"][:len(fam["managers"])])
            if fi == 1 and k == 0:
                org = "Shared Services Tooling"                                       # not an HR org: owner's family used
            if fi == 2 and k == 0:
                owner, kind = "dl-retired-team@example.test", "Distribution list"     # not in AD: Not yet mapped
            elif k == 1:
                owner, kind = fam["lead"]["email"], "Person"
            else:
                owner, kind = _owner_dl(fam), "Distribution list"
            status = "Retired" if (fi == 3 and k == len(fam["apps"]) - 1) else "Confirmed"
            for s in range(rng.randint(1, 3)):
                repo = rng.choice(live)["name"] if live else ""
                if repo and rng.random() < 0.3:
                    repo = repo.split("/", 1)[1]                                      # written without the org
                rows.append([app_id, name, status, fam["name"], "Technology", f"Technology > {org} > {name}", owner,
                             kind, owner, a["tier"].replace("Tier ", ""), "BCP register", "", f"{app_id}-S{s + 1}",
                             f"{name} service {s + 1}", rng.choice([fam["lead"]] + fam["managers"])["email"], repo, ""])
    return "app_inventory.csv", _csv(APP_INV_HEADERS, rows)


def _app_owner_members(world):
    """What tools/expand_owner_groups.ps1 writes for the inventory's owner emails."""
    rng = random.Random(f"{world['seed']}:ad")
    rows = []
    for fam in world["families"]:
        dl, group = _owner_dl(fam), f"DL-{fam['token'].upper()}-APPS"
        for p in rng.sample(fam["managers"] + fam["staff"], min(3, len(fam["managers"] + fam["staff"]))):
            rows.append([dl, "group", group, p["sam"], p["email"], p["name"], "True", "Yes", ""])
        rows.append([dl, "group", group, f"old.{fam['token'].lower()}", "", "Old Account", "False", "No", "disabled account"])
        lead = fam["lead"]
        rows.append([lead["email"], "person", "", lead["sam"], lead["email"], lead["name"], "True", "Yes", ""])
    rows.append(["dl-retired-team@example.test", "not found", "", "", "", "", "", "No", "not found in AD"])
    return "app_owner_members.csv", _csv(AD_HEADERS, rows)


# ---------------------------------------------------------------------------- the month


def make_month(world, month):
    """One month of every provider file: {feed: (filename, bytes)}."""
    pm_name, pm_bytes, _incidents, actions = _postmortems(world, month)
    return {
        "hr": _hr(world, month),
        "hr_mapping": _hr_mapping(world),
        "tcc": _tcc(world, month),
        "ntcc": _ntcc(world, month),
        "postmortems": (pm_name, pm_bytes),
        "actions": _actions(world, month, actions),
        "cx_sast": _checkmarx(world, month, "SAST"),
        "cx_sca": _checkmarx(world, month, "SCA"),
        "repos": _repos(world, month),
        "itdr": _itdr(world),
        "dr_tests": _dr_tests(world, month),
        "defects": _defects(world, month),
        "app_inventory": _app_inventory(world),
        "app_owner_members": _app_owner_members(world),
    }


# ---------------------------------------------------------------------------------------------------------------
# Standalone use (owner, 5 Nov 2026): the app itself holds no fake data and no seeding step. Run this on a laptop
# to write the made-up provider files, then upload them to the TEST site (tools/upload_test_data.py, or by hand
# on Data sources). Never upload them to production.
#
#   python tools/make_test_data.py --out demo-files                       # August to October 2026, 8 families
#   python tools/make_test_data.py --out demo-files --months 2026-07 2026-08 2026-09 2026-10 --families 10
#
# Writes demo-files/<month>/<file> for every feed, plus demo-files/manifest.json (which file is which feed) and
# demo-files/README.txt with the CTO's made-up SAM_ACCOUNT (cto.demo): the TEST app needs the config var
# TRUST_HR_ROOT_SAM_ACCOUNT=cto.demo so the HR file places people in families.
# ---------------------------------------------------------------------------------------------------------------

def write_files(out_dir, months, families=8, seed=7, cto_sam=None):
    """Write every provider file for the months into out_dir/<month>/. Returns the manifest dict."""
    import pathlib
    out = pathlib.Path(out_dir)
    world = make_world(families=max(3, min(13, int(families))), seed=seed, cto_sam=cto_sam)
    manifest = {"cto_sam": world["cto_sam"], "families": families, "seed": seed, "months": {}}
    for month in months:
        folder = out / month
        folder.mkdir(parents=True, exist_ok=True)
        files = make_month(world, month)
        manifest["months"][month] = {}
        for feed, (name, data) in files.items():
            (folder / name).write_bytes(data)
            manifest["months"][month][feed] = name
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (out / "README.txt").write_text(
        "Made-up provider files for the TRUST TEST site. Nothing here is real.\n"
        f"Months: {', '.join(months)}. Families: {families}. Random seed: {seed}.\n"
        f"The made-up CTO's SAM_ACCOUNT is {world['cto_sam']}: set the TEST app's config var "
        f"TRUST_HR_ROOT_SAM_ACCOUNT={world['cto_sam']} before uploading, or nobody is placed in a family.\n"
        "Upload: python tools/upload_test_data.py --site https://<test app> --folder <this folder>\n"
        "Never upload these to production.\n")
    return manifest


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Write made-up TRUST provider files for the TEST site.")
    p.add_argument("--out", default="demo-files", help="folder to write into (default demo-files)")
    p.add_argument("--months", nargs="+", default=["2026-08", "2026-09", "2026-10"], help="months, oldest first")
    p.add_argument("--families", type=int, default=8, help="how many product families to make up (3 to 13)")
    p.add_argument("--seed", type=int, default=7, help="random seed: the same seed makes the same files")
    p.add_argument("--cto-sam", default=None, help="the made-up CTO's SAM_ACCOUNT (default cto.demo)")
    a = p.parse_args(argv)
    m = write_files(a.out, a.months, a.families, a.seed, a.cto_sam)
    n = sum(len(v) for v in m["months"].values())
    print(f"Wrote {n} files for {len(m['months'])} months into {a.out}/ (CTO: {m['cto_sam']}). See {a.out}/README.txt.")


if __name__ == "__main__":
    main()
