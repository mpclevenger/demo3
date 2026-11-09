"""Step 4, PUBLISH: put every scored month into one data.json and a ready-to-open page.

Reads store/scored/*.json, adds what needs more than one month (prior value, change arrows,
history, New red / Chronic red on the watch list, trend) only where the earlier month is scored,
and writes:

    store/published/data.json     the data the front end reads
    store/published/index.html    the front end with that data built in (serve the folder, open it)
    store/published/evidence.json item detail for "What's driving it" (empty for now)

The front end's own definitions (building blocks, metrics, dictionary, method page) are kept as they are.
Nothing synthetic is carried over: the prototype's families, entries and connectors are replaced.
"""
import copy
import json
import os
import re

from . import codelinks, config, evidence, measure, score_month, scoring, storage, store


def _prev(month, months):
    """The calendar month before, if it is scored; else None. Every month stands alone (DEVELOPER_GUIDE.md rule 1):
    change arrows and trends compare with the month just before, never a month further back."""
    y, mo = int(month[:4]), int(month[5:7])
    pm = f"{y - 1}-12" if mo == 1 else f"{y}-{mo - 1:02d}"
    return pm if pm in months else None


# Watch-list order (owner, 1 Nov 2026: the CTO page shows the top 10 in this order); the page groups them.
TREND_MIN_BLOCKS = 3      # Sharp drop and Declining only for TRUST scores resting on at least this many blocks


def _blocks(f):
    """A family-month's block scores."""
    return f.get("blocks") or {}


def _blocks_scored(f):
    """How many blocks a family-month's TRUST rests on (older months without the count: worked out)."""
    n = f.get("blocks_scored")
    if n is not None:
        return n
    return sum(1 for B in _blocks(f).values() if B.get("score") is not None)


WATCH_ORDER = ["Override red", "New red", "Chronic red", "Sharp drop", "Declining", "Behind peers"]
RANK = {"Green": 0, "Amber": 1, "Red": 2}


def _watch(fid, name, fr, pf, ppf):
    """Watch-list items for one family-month. pf / ppf: the same family one and two months before (or None).

    Rules from 02_metric_dictionary and the old demo's reference (docs/reference/old-demo):
      Override red  a metric made Red by an automatic Red rule
      New red       Red now, not Red the month before
      Chronic red   Red this month and the two months before
      Sharp drop    TRUST down 10 points or more, with at least 2 metrics worse than the month before
      Declining     a block's score fell this month and the month before
      (Sharp drop and Declining are skipped when this month's or the month before's TRUST rests on fewer than
       3 blocks, so a file arriving or not doesn't look like a fall; owner, 4 Nov 2026.)
      Behind peers  worse than the typical family by the metric's gap (set when scoring)
    None of them changes a status or a score."""
    out = []
    add = lambda kind, mid, text: out.append(dict(kind=kind, family_id=fid, metric_id=mid, text=f"{name}: {text}"))
    for mid, r in fr["metrics"].items():
        pr = pf["metrics"].get(mid) if pf else None
        if r["status"] == "Red" and r.get("override"):
            add("Override red", mid, f"{mid} is Red by an automatic Red rule")
        elif r["status"] == "Red" and pr:
            streak = 0
            for s in reversed(r["history"]):
                if s != "Red":
                    break
                streak += 1
            if streak >= 3:
                add("Chronic red", mid, f"{mid} Red this month and the two months before")
            elif pr["status"] != "Red":
                add("New red", mid, f"{mid} turned Red")
    enough = lambda *fs: all(_blocks_scored(f) >= TREND_MIN_BLOCKS for f in fs if f)
    if enough(fr, pf) and pf and fr.get("delta") is not None and fr["delta"] <= -10:
        worse = sum(1 for mid, r in fr["metrics"].items()
                    if mid in pf["metrics"] and r["status"] in RANK and pf["metrics"][mid]["status"] in RANK
                    and RANK[r["status"]] > RANK[pf["metrics"][mid]["status"]])
        if worse >= 2:
            add("Sharp drop", None, f"TRUST fell {-fr['delta']} points")
    if enough(fr, pf, ppf) and pf and ppf:
        fr["declining"] = [c for c in _blocks(fr)
                           if (_blocks(fr).get(c, {}).get("delta") or 0) < 0
                           and (_blocks(pf).get(c, {}).get("delta") or 0) < 0]
        if fr["declining"]:
            add("Declining", None, f"{', '.join(fr['declining'])} fell two months in a row")
    listed = {i["metric_id"] for i in out}          # a metric already on the list as Red isn't listed twice
    for mid, r in fr["metrics"].items():
        if r.get("behind_peers") and mid not in listed:
            add("Behind peers", mid, f"{mid} {r['value']} vs typical {r['typical']}")
    return out


def _mark_locked(p, st):
    """The front end reads 'Locked' with who and when. The seal goes in without the frozen page copy
    (its fingerprint shown_sha256 stays), so data.json doesn't carry the month twice."""
    p["meta"].update(status="Locked", locked_by=st["locked_by"], locked_at=st["locked_at"][:10],
                     prepared_by=st["locked_by"], current_bd=None)
    p["seal"] = {k: v for k, v in (st["seal"] or {}).items() if k != "shown"}


def shown_period(month):
    """The month's page data as it would be published now (with change arrows, prior values, history and
    watch list worked out from its neighbours), for the lock to freeze."""
    return build()["periods"][month]


def build(empty_months=()):
    """Assemble data.json from every scored month. Returns the dict.

    empty_months (YYYY-MM): months to show although they aren't scored, each with no results, saying
    "Not scored yet" (owner, 4 Nov 2026: the real site shows from the start, and a month with uploads can be
    picked before it is scored). Nothing is saved: these months exist only in what is returned."""
    tpl = score_month.template()
    real = storage.months("scored")
    extra = sorted(set(empty_months or ()) - set(real))
    if not real and not extra:
        raise ValueError("no month has been scored yet: run  python manage.py score YYYY-MM")
    scored = {m: storage.load_month("scored", m) for m in real}
    for m in extra:
        scored[m] = score_month.score_month({"month": m, "feeds": {}, "notes": []})
        scored[m]["period"].setdefault("meta", {})["not_scored"] = True    # shown, but nothing scored yet
    months = sorted(scored)

    # The family list is the newest scored month's (owners file); older months keep their own results.
    families = scored[real[-1]]["families"] if real else []
    names = {f["id"]: f["name"] for m in months for f in scored[m]["families"]}
    periods = {}
    for m in months:
        p = scored[m]["period"]
        pm = _prev(m, months)
        prev = periods.get(pm) if pm else None
        st = storage.month_status(m)
        if st["status"] == "locked" and (st["seal"] or {}).get("shown"):
            # A locked month is frozen as it was shown at the lock (owner, 5 Nov 2026): its change arrows,
            # prior values, history and watch list don't move when a neighbouring month is scored again.
            p = copy.deepcopy(st["seal"]["shown"])
            _mark_locked(p, st)
            periods[m] = p
            continue
        p["watch_list"] = []
        for fid, fr in p["families"].items():
            pf = prev["families"].get(fid) if prev else None
            if pf and fr["trust"] is not None and pf["trust"] is not None:
                fr["delta"] = fr["trust"] - pf["trust"]
            for c, B in _blocks(fr).items():
                pb = _blocks(pf).get(c) if pf else None
                if pb and B["score"] is not None and pb["score"] is not None:
                    B["delta"] = B["score"] - pb["score"]
            for mid, r in fr["metrics"].items():
                pr = pf["metrics"].get(mid) if pf else None
                if pr:
                    r["prior_value"], r["prior_status"] = pr["value"], pr["status"]
                    r["history"] = (pr.get("history") or [])[-2:] + [r["status"]]
                else:
                    r["history"] = [r["status"]]
            ppm = _prev(pm, months) if pm else None
            ppf = periods[ppm]["families"].get(fid) if ppm and ppm in periods else None
            p["watch_list"] += _watch(fid, names.get(fid, fid), fr, pf, ppf)
        p["watch_list"].sort(key=lambda w: WATCH_ORDER.index(w["kind"]))
        if prev:
            for mid, x in p["firm"].items():
                px = prev["firm"].get(mid, {})
                x["prior_value"], x["prior_status"] = px.get("value"), px.get("status")
            if p["firm_trust"] is not None and prev["firm_trust"] is not None:
                p["firm_trust_delta"] = p["firm_trust"] - prev["firm_trust"]
        if st["status"] == "locked":
            _mark_locked(p, st)
        periods[m] = p

    data = dict(tpl)
    data["metrics"] = _metric_list(tpl, periods)
    data.update(
        # The firm tolerance threshold is a setting; with no value set, the page leaves out the line and the sentence.
        firm_tolerance=_firm_tolerance(),
        min_families_for_threshold=score_month.min_families(score_month.thresholds_config()),   # shown in the dictionary
        behind_peers_flag=bool(score_month.thresholds_config().get("behind_peers_flag", True)),
        automatic_red_rules=bool(score_month.thresholds_config().get("automatic_red_rules", True)),   # owner, 9 Nov 2026
        data_sources=config.data_sources(),                         # who owns each data source (owner, 9 Nov 2026)   # owner, 8 Nov 2026: Flags section shown only when on
        caps=scoring.caps_from(score_month.thresholds_config().get("caps")),   # the current caps; each month keeps its own
        code_links=codelinks.links(),      # links from each metric card to its code (owner, 5 Nov 2026); {} without code_repo_url
        env_label=env_label(), test_env=is_test_env(), live=True, feeds=list(store.FEEDS), families=families, periods=periods, entries=[], connectors=[], 
        trend=dict(months=months, sample_before=None,
                   firm=[periods[m]["firm_trust"] for m in months],
                   families={f["id"]: [periods[m]["families"].get(f["id"], {}).get("trust") for m in months]
                             for f in families},
                   incomplete_months=[m for m in months if periods[m]["firm_incomplete"]]))
    return data


def is_test_env():
    """The TEST environment is the same code with the config var TRUST_ENV=test (owner, 4 Nov 2026). Only it may hold
    seed data; the page says so on every screen."""
    return (os.environ.get("TRUST_ENV") or "").strip().lower() == "test"


def env_label():
    return "TEST · synthetic data" if is_test_env() else "Live data"


def _firm_tolerance():
    v = score_month.thresholds_config().get("firm_tolerance")
    return {"value": v} if isinstance(v, (int, float)) else None


def page_html(data):
    """The front end with this data built in."""
    safe = json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")   # keep the JSON from closing the script tag
    html = (score_month.ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    return re.sub(r'(<script type="application/json" id="data">).*?(</script>)',
                  lambda m: m.group(1) + safe + m.group(2), html, count=1, flags=re.S)


def _metric_list(tpl, periods):
    """The page's metric list from the definitions; a metric with no source yet is marked coming soon."""
    metrics = []
    for x in tpl["metrics"]:
        if x["id"] in measure.COMING_SOON:
            x = dict(x, coming_soon=True)
        metrics.append(x)
    return metrics


def with_current_definitions(data):
    """The metrics and their dictionary cards as deployed now (config/metrics.json), not the copy saved at the
    last update (owner, 8 Nov 2026: a changed definition shows as soon as it is deployed). Scores and every
    month's results are left exactly as published; only Update changes those."""
    tpl = score_month.template()
    data = dict(data)
    data["metrics"] = _metric_list(tpl, data.get("periods") or {})
    data["dictionary"] = dict(data.get("dictionary") or {}, metrics=tpl["dictionary"]["metrics"])
    data["behind_peers_flag"] = bool(score_month.thresholds_config().get("behind_peers_flag", True))
    data["automatic_red_rules"] = bool(score_month.thresholds_config().get("automatic_red_rules", True))
    data["data_sources"] = config.data_sources()
    data["code_links"] = codelinks.links()
    return data


def site_data(published, current_month):
    """What the website shows: the published data, plus any month with uploads that isn't scored yet; before
    anything is published, the real site for the current month with no data. Built only when needed."""
    shown = set((published or {}).get("periods") or {})
    # Months with uploads, and always the current month, so its files can be uploaded (owner, 4 Nov 2026).
    missing = sorted({m for m in storage.upload_months() + [current_month] if m not in shown})
    if published and not missing:
        return with_current_definitions(published)
    data = build(empty_months=missing)
    if not published:
        data["nothing_published"] = True
    return data


def run(by="command line"):
    data = build()
    text = json.dumps(data, ensure_ascii=False)
    html = page_html(data)
    # Item detail ("What's driving it") isn't built from live data yet; an empty file makes the page
    # say "No item detail for this metric this month" instead of failing to load it.
    # The items behind each family's numbers, for the drill-down (owner, 3 Nov 2026).
    ev = {m: evidence.page_evidence(storage.load_month("scored", m), m) for m in data["periods"]}
    out = storage.save_published({"index.html": html, "data.json": text,
                                  "evidence.json": json.dumps(ev, ensure_ascii=False)})
    storage.log("publish", by, None, f"{len(data['periods'])} {'month' if len(data['periods']) == 1 else 'months'} on the scorecard")
    return out
