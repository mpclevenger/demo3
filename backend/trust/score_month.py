"""Step 3b, SCORE: turn a mapped month into results, statuses, building-block and TRUST scores.

    measured counts (measure.py)  ->  value per family  ->  tolerance thresholds (config/thresholds.json)
    ->  Green / Amber / Red  ->  blocks and TRUST (scoring.py)  ->  store/scored/<month>.json

Each month stands alone: nothing here needs another month. A metric whose file hasn't arrived is
'No data' (DNR) and left out of its block. Rows not placed with a family count in the firm totals
and in 'Not yet mapped', never in a family.
"""
import json
import os
import pathlib
import re
import statistics
from datetime import datetime, timedelta
from decimal import Decimal as D, ROUND_HALF_UP

from . import config, measure, scoring, storage, store
from .intake.common import loads_tolerant
from .linking import UNATTRIBUTED

ROOT = pathlib.Path(__file__).resolve().parents[2]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
FEED_PROVIDER = {"tcc": "Change", "ntcc": "Change", "actions": "Ops", "postmortems": "Ops",
                 "cx_sast": "Cyber", "cx_sca": "Cyber", "hr": "HR", "hr_mapping": "Tech Risk"}


def r1(x):
    """One decimal place, half up (D-04)."""
    return float(D(str(x)).quantize(D("0.1"), rounding=ROUND_HALF_UP))


def label(month):
    y, m = month.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def template():
    """The front end's built-in data (building blocks, method page) plus every metric and its dictionary card,
    which come from config/metrics.json (owner, 8 Nov 2026: one place to edit a metric)."""
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    tpl = json.loads(m.group(1))
    defs = config.metrics()
    parts = ("card", "known_limits", "wording", "counting", "status_note")
    tpl["metrics"] = [dict(id=mid, **{k: v for k, v in x.items() if k not in parts and not k.startswith("_")})
                      for mid, x in defs.items()]
    tpl.setdefault("dictionary", {})["metrics"] = {mid: dictionary_card(x) for mid, x in defs.items()}
    return tpl


def dictionary_card(x):
    """One metric's dictionary card as the page reads it: the card, its known limits and its wording."""
    c = {k: v for k, v in (x.get("card") or {}).items() if not k.startswith("_")}
    c.setdefault("override_rule", x.get("override_rule"))
    c["status"] = x.get("status") or "Measured"
    if c["status"] != "Measured":              # In progress, Planned, Coming soon: counts in no score, shows No data
        c["not_measured"] = True
    c.setdefault("thresholds", [])
    c.setdefault("proposed_fields", None)
    limits = x.get("known_limits") or []
    c["limitations"] = [r.get("limit", "") for r in limits]
    c["countermeasures"] = [r.get("mitigation", "") for r in limits]
    c["limitations_table"] = [dict(limitation=r.get("limit", ""), mitigation=r.get("mitigation", ""),
                                   status=r.get("status") or "No mitigation yet") for r in limits]
    if x.get("wording"):
        c["wording"] = x["wording"]
    return c


def thresholds_config():
    path = pathlib.Path(os.environ.get("TRUST_THRESHOLDS") or ROOT / "config" / "thresholds.json")
    doc = loads_tolerant(path.read_text(encoding="utf-8"))
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def _day(iso):
    """'2026-11-03' -> '3 Nov 2026' for the reasons people read."""
    try:
        d = datetime.strptime(str(iso), "%Y-%m-%d")
        return f"{d.day} {d.strftime('%b %Y')}"
    except (TypeError, ValueError):
        return str(iso or "")


def min_families(cfg):
    """Fewest family results needed to set a tolerance threshold from the median (setting; 5 unless set)."""
    v = cfg.get("min_families_for_threshold", 5)
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else 5


def no_threshold_reason(n, cfg):
    need = min_families(cfg)
    if n < need:
        return (f"No tolerance threshold yet: {plural(n, 'family has', 'families have')} a result and "
                f"{need} are needed. Not scored this month")
    return "No tolerance threshold for this metric yet: not scored"


def thresholds_for(mid, values, hib, cfg, unit_word="points"):
    """Green tolerance and Red limit for one metric this month. values: family results that count.

    Owner, 3 Nov 2026: a prevailing-median threshold is calculated from the month's own data; there are no
    static starting values. Owner, 4 Nov 2026: it needs at least `min_families_for_threshold` family results
    (a setting, 5); with fewer there is no threshold and the metric isn't scored that month."""
    mc = cfg["metrics"].get(mid, {})
    if mc.get("basis") == "Policy":
        set_from = mc.get("set_from")
        reason = (f"Set from the {set_from} (set {_day(mc.get('set_on'))}); reviewed quarterly" if set_from
                  else "Initial tolerance thresholds for go-live")
        return dict(green=mc["green"], red=mc["red"], basis="Policy", provisional=False, reason=reason,
                    set_from=set_from, set_on=mc.get("set_on"))
    if not values or len(values) < min_families(cfg):
        return None
    med = r1(statistics.median(values))
    spread = 0.0
    if len(values) >= 4:
        q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
        spread = q3 - q1
    band = r1(max(mc.get("amber_band_min", cfg["amber_band_min_points"]), cfg["amber_band_spread_multiple"] * spread))
    red = r1(med - band) if hib else r1(med + band)
    if unit_word == "points":                     # a percentage: a limit can't go below 0% or above 100%
        red = min(100.0, max(0.0, red))
    return dict(green=med, red=red, band=band, basis="Calibrated", provisional=True, unit_word=unit_word,
                reason=f"Prevailing median of {plural(len(values), 'family', 'families')} ({{month}}); "
                       f"Amber band {band:g} {unit_word}; provisional")


def _amt(x):
    """A number for a reason: no '.0' on whole numbers (0.5 stays 0.5)."""
    return f"{x:g}" if abs(x - round(x)) > 1e-9 else f"{int(round(x))}"


def _qty(x, word):
    """'1 incident', '1.5 incidents', '1 point': the unit word follows the number."""
    return f"{_amt(x)} {word[:-1] if x == 1 and word.endswith('s') else word}"


def status_of(v, t, hib, unit):
    """Green / Amber / Red against the thresholds, with the plain reason shown on the page."""
    u = "%" if unit == "%" else ""
    g, r = t["green"], t["red"]
    if t["basis"] == "Policy":
        if (v >= g) if hib else (v <= g):
            return "Green", f"Within Green tolerance ({'≥' if hib else '≤'} {g:.1f}{u})"
        if (v >= r) if hib else (v <= r):
            return "Amber", "Between tolerance and Red limit"
        return "Red", f"Past the Red limit ({'<' if hib else '>'} {r:.1f}{u})"
    word = "median"
    band, bw = t.get("band", 5), t.get("unit_word", "points")
    # a percentage metric shows its limits as 12.5%; a count metric shows them in its unit ("2 incidents")
    show = (lambda x: f"{x:.1f}{u}") if u else (lambda x: _qty(x, bw))
    amber = _qty(band, bw)
    if (v >= g) if hib else (v <= g):
        return "Green", (f"At or {'above' if hib else 'below'} the prevailing {word} "
                         f"(Green tolerance: {'at least' if hib else 'at most'} {show(g)})")
    if (v >= r) if hib else (v <= r):
        return "Amber", (f"{'Below' if hib else 'Above'} the prevailing {word}, within the Amber band of {amber} "
                         f"(Red limit: {'less' if hib else 'more'} than {show(r)})")
    return "Red", (f"More than the Amber band of {amber} {'below' if hib else 'above'} the prevailing {word} "
                   f"(Red limit: {'less' if hib else 'more'} than {show(r)})")


PEER_MIN_FAMILIES = 5   # the behind-peers flag needs at least 5 families with a scored result (02_metric_dictionary §1.3)


def flag_behind_peers(results, tpl, thresholds=None, flag_on=None):
    """Typical value and the behind-peers flag, per metric, across families (owner, 3 Nov 2026).

    Typical = the median of the families' scored results this month (the middle family). It is shown as
    context, so it is the real median even where a policy sets the Green tolerance. A family is behind
    peers when its result is worse than typical by at least the metric's gap (dictionary peer_flag_gap).
    The flag puts an item on the watch list only: it never changes a status or a score.
    Flagged only where a policy sets the tolerance threshold: a metric judged against the prevailing
    median already compares each family with the median, so a flag would say the same thing twice (the
    v1 design's dictionary card). Not flagged either: metrics with no gap (pass/fail, information only),
    and plain counts (UN-01 until the app inventory arrives), whose gap is written per 10 apps."""
    thresholds = thresholds or {}
    if flag_on is None:                                            # owner, 8 Nov 2026: setting behind_peers_flag, off for now
        flag_on = thresholds_config().get("behind_peers_flag", True)
    gaps = {mid: x.get("peer_flag_gap") for mid, x in tpl["dictionary"]["metrics"].items()}
    hib = {m["id"]: m["higher_is_better"] for m in tpl["metrics"]}
    for mid in hib:
        rows = [r[mid] for r in results.values()
                if mid in r and r[mid]["status"] in scoring.PTS and not r[mid].get("provisional")
                and r[mid].get("value") is not None]
        if not rows:
            continue
        typical = r1(statistics.median(r["value"] for r in rows))
        for r in results.values():
            if mid in r and r[mid].get("typical") is not None:
                r[mid]["typical"] = typical
        gap = gaps.get(mid)
        if (not flag_on or gap is None or hib[mid] is None or mid in measure.COUNT_ONLY or len(rows) < PEER_MIN_FAMILIES
                or (thresholds.get(mid) or {}).get("basis") != "Policy"):
            continue
        for r in rows:
            worse = typical - r["value"] if hib[mid] else r["value"] - typical
            if worse >= gap:
                r["behind_peers"] = True


def contract_blocks(mid, contracts=None):
    """The reason a metric may not be scored from its feed under the feed's approved data contract, or None."""
    feeds = [f for m, f in measure.NEEDS.items() if m == mid] + ([measure.NEEDS_ALSO[mid]] if mid in measure.NEEDS_ALSO else [])
    if contracts is None:
        contracts = storage.approved_contracts()
    for feed in feeds:
        c = contracts.get(feed)
        if c and mid not in (c.get("metrics") or []):
            return (f"Not in the data contract for the {feed} file (version {c['version']}): the provider has not "
                    f"approved its use for {mid}. Request a new contract version on the Data dictionary page")
    return None


def blank_result(status, reason, **kw):
    r = dict(value=None, numerator=None, denominator=None, status=status, points=scoring.PTS.get(status),
             reason=reason, provisional=False, carried_from=None, override=False, behind_peers=False,
             typical=None, history=[], prior_value=None, prior_status=None)
    r.update(kw)
    return r


def empty_reason(mid, all_unplaced):
    """Why a family has nothing to count: counting.empty_reason in config/metrics.json (empty_reason_unplaced
    when none of the items could be placed with a family)."""
    c = config.counting(mid)
    return (all_unplaced and c.get("empty_reason_unplaced")) or c.get("empty_reason") or "No items: not scored"


def _merge(a, b):
    """Add one set of counts to another (numbers summed, lists joined, flags or-ed)."""
    if a is None:
        return {k: (list(v) if isinstance(v, list) else v) for k, v in b.items()}
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, bool):
            out[k] = bool(a.get(k)) or v
        elif isinstance(v, (int, float)) and isinstance(a.get(k, 0), (int, float)) and not isinstance(a.get(k), bool):
            out[k] = a.get(k, 0) + v
        elif isinstance(v, list):
            out[k] = list(a.get(k) or []) + v
        else:
            out.setdefault(k, v)
    return out


def expand_shared(counts, shared):
    """Per-family counts with each shared group's counts added to every family its lead leads (owner, 6 Nov 2026:
    a lead of several families rolls up to each of them; the same numbers show for each until the data is more
    granular). The firm keeps using the original counts, so the group is counted once there. A count-only metric
    (UN-01) is a unique count: an item already in the family isn't counted twice."""
    if not shared:
        return counts
    out = {}
    for mid, by_fam in counts.items():
        fam = {k: v for k, v in by_fam.items() if k not in shared}
        for g, fids in shared.items():
            if g not in by_fam or not isinstance(by_fam[g], dict):
                continue
            for fid in fids:
                fam[fid] = _merge(fam.get(fid), by_fam[g])
                if mid in measure.COUNT_ONLY:
                    seen, items = set(), []
                    for it in fam[fid].get("items") or []:
                        if it.get("id") not in seen:
                            seen.add(it.get("id"))
                            items.append(it)
                    fam[fid]["items"], fam[fid]["numerator"] = items, len(items)
        out[mid] = fam
    return out


def family_tiers(feeds):
    """{family_id: (Tier 0/1 applications, all applications)} from the ITDR application file (owner, 4 Nov 2026).
    The ITDR application file is the only source of a tier: a DR test's own Tier is never used (a difference is
    a mapping warning). None when the ITDR file isn't mapped for the month, so the tier isn't known yet."""
    itdr_feed = feeds.get("itdr") or {}
    if itdr_feed.get("status") != "mapped":
        return None
    out = {}
    shared = (feeds.get("hr_mapping") or {}).get("shared") or {}
    for a in itdr_feed.get("rows") or []:
        for fid in shared.get(a.get("family_id"), [a.get("family_id")] if a.get("family_id") else []):
            t01, total = out.get(fid, (0, 0))
            out[fid] = (t01 + (a.get("recovery_tier") in measure.RE01_TIERS), total + 1)
    return out


def _scored(results, tpl, weights, cfg):
    """Blocks, TRUST and status for one set of metric results (a family's, or the firm's pooled ones)."""
    blocks, trust, st, capped = scoring.family({"metrics": results}, tpl["metrics"], weights, cfg.get("caps"),
                                               cfg.get("coverage"))
    for B in blocks.values():
        B["delta"] = None
    return dict(trust=trust, status=st, delta=None, capped=capped, declining=[], blocks=blocks,
                blocks_scored=sum(1 for B in blocks.values() if B.get("score") is not None),
                metrics=results, incomplete=any(r["status"] == "DNR" for r in results.values()))


def score_month(mapped, cfg=None, tpl=None):
    """Score one mapped month. Returns the period block the front end reads, plus the family list."""
    cfg = cfg or thresholds_config()
    tpl = tpl or template()
    month = mapped["month"]
    feeds = mapped["feeds"]
    meas = measure.measure(mapped)
    metrics = {m["id"]: m for m in tpl["metrics"]}
    # Per-family counts, with a shared lead's group added to each of their families; the firm uses meas["counts"].
    fcounts = expand_shared(meas["counts"], (feeds.get("hr_mapping") or {}).get("shared") or {})

    # Families come from the product family owners file (doc 13 §8). Without it there are none yet.
    people = {p["email"]: p for p in feeds.get("hr", {}).get("people") or [] if p.get("email")}
    fam_rows = feeds.get("hr_mapping", {}).get("families") or feeds.get("hr_mapping", {}).get("rows") or []
    tiers = family_tiers(feeds)
    families = []
    for f in fam_rows:
        leads = [people[e]["worker"] if e in people and people[e].get("worker") else e for e in f["owner_emails"]]
        t01, total = tiers.get(f["family_id"], (0, 0)) if tiers is not None else (None, None)
        families.append(dict(id=f["family_id"], name=f["family"], band=f.get("band") or "product",
                             tier01=None if tiers is None else t01 > 0, tier01_apps=t01, apps_total=total,
                             leads=leads, accountable=leads[0] if leads else None))
    fids = [f["id"] for f in families]
    # Not Tier 0/1 (owner, 4 Nov 2026): a family with no Tier 0 or 1 application in the ITDR application file is
    # not scored on Resilient. Only when the ITDR file is mapped for the month; otherwise the tier isn't known.
    not_t01 = {f["id"] for f in families if f["tier01"] is False}

    # 1. Values per family, and the thresholds they are judged against.
    thresholds, results = {}, {fid: {} for fid in fids}
    for mid, m in metrics.items():
        hib = m["higher_is_better"]
        if mid in measure.COMING_SOON:
            for fid in fids:
                results[fid][mid] = blank_result("Coming soon", measure.COMING_SOON[mid])
            continue
        if mid in measure.SWITCHABLE and mid not in (cfg.get("switched_on") or []):
            for fid in fids:
                results[fid][mid] = blank_result(
                    "DNR", "Not switched on yet: counted from its files, but not scored (setting switched_on "
                           "in config/thresholds.json)")
            continue
        if mid not in meas["received"]:
            for fid in fids:
                results[fid][mid] = blank_result(
                    "DNR", f"No data: {m['provider']}’s {MONTHS[int(month[5:]) - 1]} data was not received")
            continue
        # Data contract (owner, 4 Nov 2026): once a feed's contract is approved, TRUST may use the file only for the
        # metrics the contract lists. Anything else waits for a new contract version the provider approves.
        blocked = contract_blocks(mid)
        if blocked:
            for fid in fids:
                results[fid][mid] = blank_result("DNR", blocked)
            continue
        counts = fcounts[mid]
        if mid in measure.COUNT_ONLY:
            # Owner, 3 Nov 2026: scored as a plain count against the prevailing median until app-level data
            # allows "per 10 apps". A family with no Critical or SWE incident has a count of 0.
            noun = measure.COUNT_ONLY[mid]
            ns = {fid: (counts.get(fid) or {}).get("numerator", 0) for fid in fids}
            t = thresholds_for(mid, [float(n) for n in ns.values()], hib, cfg, unit_word="incidents")
            if t:
                t["reason"] = t["reason"].replace("{month}", label(month))
                thresholds[mid] = dict(green=t["green"], red=t["red"], version=1, basis=t["basis"], approved_at=None,
                                       reason=t["reason"], sets="both", provisional=t["provisional"], band=t.get("band"),
                                       set_from=t.get("set_from"), set_on=t.get("set_on"))
            for fid in fids:
                n, un = ns[fid], (counts.get(fid) or {}).get("unrated", 0)
                r = blank_result(None, None)
                r.update(value=float(n), numerator=n, denominator=None, unrated=un)
                if t is None:
                    r.update(status="N/A", reason=no_threshold_reason(len(ns), cfg), points=None)
                else:
                    st, why = status_of(float(n), t, hib, "count")
                    r.update(status=st, reason=f"{plural(n, measure.COUNT_ONE.get(mid, noun), noun)}: {why}",
                             points=scoring.PTS[st], typical=t["green"])
                if un:
                    r["reason"] += (f". Also {plural(un, 'incident', 'incidents')} with no rating (DEFCON Not "
                                    f"Available or blank): shown, not counted")
                results[fid][mid] = r
            continue
        low = cfg.get("low_confidence_below_items", {}).get(mid, 0)
        vals = {}
        for fid in fids:
            if fid in not_t01 and mid.startswith("RE-"):
                continue                                    # not scored on Resiliency: kept out of the median
            c = counts.get(fid)
            if c and c["denominator"] and c["denominator"] >= low:
                vals[fid] = r1(100 * c["numerator"] / c["denominator"])
        t = thresholds_for(mid, list(vals.values()), hib, cfg)
        if t:
            t["reason"] = t["reason"].replace("{month}", label(month))
            thresholds[mid] = dict(green=t["green"], red=t["red"], version=1, basis=t["basis"],
                                   approved_at=None, reason=t["reason"], sets="both", provisional=t["provisional"],
                                   band=t.get("band"), set_from=t.get("set_from"), set_on=t.get("set_on"))
        all_unplaced = all(k == UNATTRIBUTED for k in counts if not k.startswith("_"))
        for fid in fids:
            c = counts.get(fid)
            if not c or not c["denominator"]:
                if mid == "UN-02":     # D-100: nothing open = Green
                    r = blank_result("Green", "No postmortem actions open at month-end", numerator=0, denominator=0)
                    r.update(value=0.0, points=100)
                else:
                    r = blank_result("N/A", empty_reason(mid, all_unplaced))
                results[fid][mid] = r
                continue
            v = r1(100 * c["numerator"] / c["denominator"])
            r = blank_result(None, None)
            r.update(value=v, numerator=c["numerator"], denominator=c["denominator"])
            if c["denominator"] < low:
                r.update(status="Low confidence", reason=f"Fewer than {low} items: shown, not scored", points=None)
            elif mid == "TE-02" and c.get("client_impact"):          # R-TCC-12: client impact -> Red
                # Owner, 3 Nov 2026: an automatic Red rule, so it also caps the Releases block at 49.
                r.update(status="Red", points=0, override=True,
                         reason=f"Automatic Red rule: {plural(c['client_impact'], 'release', 'releases')} with client impact")
            elif t is None:
                r.update(status="N/A", reason=no_threshold_reason(len(vals), cfg))
            else:
                st, why = status_of(v, t, hib, m["unit"])
                # 'provisional' on a result means "an earlier month's result reused" in the front end,
                # so it stays False here; a provisional threshold says so in its own reason.
                r.update(status=st, reason=why, points=scoring.PTS[st])
            if t:
                r["typical"] = t["green"]
            results[fid][mid] = r

    for fid in not_t01:
        fam = next(f for f in families if f["id"] == fid)
        why = (f"Not Tier 0/1: no Tier 0 or 1 applications in the ITDR application file "
               f"({plural(fam['apps_total'], 'application', 'applications')} placed with this family). "
               "Not scored on Resiliency")
        for mid, m in metrics.items():
            if mid.startswith("RE-"):
                keep = {k: results[fid][mid].get(k) for k in ("value", "numerator", "denominator")}
                results[fid][mid] = blank_result("Not Tier 0/1", why, **keep)

    # Actions on incidents with no rating are shown, never hidden, and kept out of the score (owner, 2 Nov 2026).
    if "UN-02" in meas["received"]:
        for fid in fids:
            c = fcounts["UN-02"].get(fid) or {}
            uo, uv = c.get("unrated_open", 0), c.get("unrated_overdue", 0)
            if uo:
                r = results[fid]["UN-02"]
                r["reason"] = (f"{r['reason']}. Not in the score: {plural(uo, 'open action', 'open actions')} "
                               f"({uv} overdue) on incidents with no rating (DEFCON Not Available or blank)")
                r.update(unrated_open=uo, unrated_overdue=uv)

    flag_behind_peers(results, tpl, thresholds)

    # 2. Building blocks and TRUST per family (scoring.py: points, caps, rounding).
    fam_out, trusts = {}, []
    for fid in fids:
        fam_out[fid] = _scored(results[fid], tpl, scoring.weights_for(tpl, fid), cfg)
        trusts.append(fam_out[fid]["trust"])

    # 3. Firm-wide: every row counts, placed or not.
    firm_totals, firm, unplaced, unplaced_feed = {}, {}, {}, {}
    def _feed_share(mid, a, b):      # not-yet-mapped share per input file (a feed), from the same counts
        f = measure.NEEDS.get(mid)
        if f:
            x = unplaced_feed.setdefault(f, [0, 0]); x[0] += a; x[1] += b
    for mid, m in metrics.items():
        if mid in measure.COMING_SOON:
            firm_totals[mid] = None
            firm[mid] = dict(value=None, status="Coming soon", prior_value=None, prior_status=None)
            continue
        if mid not in meas["received"] or (mid in measure.SWITCHABLE and mid not in (cfg.get("switched_on") or [])):
            firm_totals[mid] = None
            firm[mid] = dict(value=None, status="DNR", prior_value=None, prior_status=None)
            continue
        counts = meas["counts"][mid]
        if mid in measure.COUNT_ONLY:
            n = counts["_firm"]["numerator"]
            firm_totals[mid] = float(n)
            firm[mid] = dict(value=float(n), status="Info only", prior_value=None, prior_status=None, numerator=n,
                             denominator=None)
            un = counts.get(UNATTRIBUTED, {}).get("numerator", 0)
            unplaced.setdefault(m["provider"], [0, 0])
            unplaced[m["provider"]][0] += un
            unplaced[m["provider"]][1] += n
            _feed_share(mid, un, n)
            continue
        num = sum(c["numerator"] for c in counts.values())
        den = sum(c["denominator"] for c in counts.values())
        v = r1(100 * num / den) if den else None
        firm_totals[mid] = v
        st = "N/A"
        if v is not None and mid in thresholds:
            st = status_of(v, thresholds[mid], m["higher_is_better"], m["unit"])[0]
        firm[mid] = dict(value=v, status=st, prior_value=None, prior_status=None, numerator=num, denominator=den)
        un = counts.get(UNATTRIBUTED, {}).get("denominator", 0)
        unplaced.setdefault(m["provider"], [0, 0])
        unplaced[m["provider"]][0] += un
        unplaced[m["provider"]][1] += den
        _feed_share(mid, un, den)
        if st == "N/A" and v is not None:
            firm[mid]["reason"] = ("No tolerance threshold this month: no family had enough results to set a prevailing "
                                   "median, so the firm result is shown but not scored")

    # An automatic Red rule that fired for any family (e.g. TE-02 client impact) holds for the firm too (owner, 4 Nov 2026).
    for mid in firm:
        if any(results[fid].get(mid, {}).get("override") and results[fid][mid]["status"] == "Red" for fid in fids):
            firm[mid].update(status="Red", override=True,
                             reason="Red by an automatic Red rule that applied to at least one family")

    # Firm TRUST is scored from the pooled firm-wide results, the same way as a family (owner, 4 Nov 2026), not as
    # the average of the family scores. The average is kept beside it for comparison.
    firm_scored = _scored(firm, tpl, {m["id"]: m.get("weight", 1) for m in tpl["metrics"]}, cfg)

    received_providers = {metrics[mid]["provider"] for mid in meas["received"]}
    dnr = sorted({m["provider"] for k, m in metrics.items() if k not in measure.COMING_SOON} - received_providers)
    # "Data missing" (which hides the firm's change arrows and trend) means a provider with a measured metric
    # didn't send. A provider whose metrics are all still planned, with no source yet, isn't missing data
    # (5 Nov 2026, from review: planned metrics kept the firm change hidden every month).
    dictionary = (tpl.get("dictionary") or {}).get("metrics") or {}
    expected = {m["provider"] for k, m in metrics.items()
                if k not in measure.COMING_SOON and not dictionary.get(k, {}).get("not_measured")}
    firm_incomplete = bool(expected - received_providers)
    # One definition of "files received" for every page (owner, 5 Nov 2026): the files the measured metrics
    # need this month, plus HR and the owners file that place every row. Other feeds are optional.
    needed_feeds = ["hr", "hr_mapping"] + sorted({f for mid, f in measure.NEEDS.items() if mid in metrics
                                                 and not dictionary.get(mid, {}).get("not_measured")
                                                 and mid not in measure.COMING_SOON}
                                                | {measure.NEEDS_ALSO[mid] for mid in measure.NEEDS_ALSO if mid in metrics
                                                   and not dictionary.get(mid, {}).get("not_measured")})
    got_feeds = {f for f, v in feeds.items() if v.get("status") not in (None, "not received")}
    files_needed = {"needed": needed_feeds, "received": [f for f in needed_feeds if f in got_feeds],
                    "missing": [f for f in needed_feeds if f not in got_feeds],
                    "optional_received": sorted(f for f in got_feeds if f not in needed_feeds)}
    submissions = []
    for feed, v in feeds.items():
        if v.get("status") in (None, "not received") or feed not in FEED_PROVIDER:
            continue
        ua = unplaced_feed.get(feed)
        submissions.append(dict(
            id=f"{month}-{feed}", feed=feed, provider=FEED_PROVIDER[feed], status="Accepted" if v["status"] == "mapped" else v["status"],
            received_bd=None, hash12=v.get("sha256", "")[:12], checks=dict(passed=0, warn=len(v.get("notes", [])), fail=0),
            variance=None, as_of=v.get("as_of") or v.get("uploaded_at"), rows=len(v.get("rows") or v.get("people") or []),
            supersedes=None,
            # this file's own share of rows not yet mapped to a family (None when no metric reads this file)
            unattributed_pct=r1(100 * ua[0] / ua[1]) if ua and ua[1] else None,
            # the front end reads each warning as {rule, detail} and keys acknowledgements by rule, so number them
            warnings=[dict(rule=f"Mapping note {i}", detail=str(n)) for i, n in enumerate(v.get("notes", []), 1)],
            metrics=[mid for mid, f in measure.NEEDS.items() if f == feed]))

    period = dict(
        meta=dict(id=month, label=label(month), status="Preview", current_bd=None, locked_by=None, locked_at=None,
                  last_day=(measure.month_end(month) - timedelta(days=1)).date().isoformat(),
                  checklist_done=0, checklist_total=0, prepared_by=None),
        thresholds=thresholds, families=fam_out, firm_trust=firm_scored["trust"], firm_status=firm_scored["status"],
        firm_capped=firm_scored["capped"], firm_blocks=firm_scored["blocks"], firm_blocks_scored=firm_scored["blocks_scored"],
        firm_trust_average=scoring.average_trust(trusts), firm_trust_delta=None,
        firm_totals=firm_totals, firm=firm, watch_list=[], most_improved=None, dnr=dnr,
        unattributed_pct={p: r1(100 * a / b) for p, (a, b) in unplaced.items() if b},
        submissions=submissions, firm_incomplete=firm_incomplete, files_needed=files_needed)
    period["caps"] = scoring.caps_from(cfg.get("caps"))       # the caps this month was scored with (a setting)
    period["coverage"] = scoring.coverage_from(cfg.get("coverage"), scoring.block_codes(tpl["metrics"]))   # and how much had to be measured (a setting)
    period["count_only"] = {mid: unit for mid, unit in measure.COUNT_ONLY.items() if mid in meas["received"]}
    f1 = meas["counts"].get("UN-01", {}).get("_firm", {})
    notes = []
    if f1.get("no_end_date"):
        nd = f1["no_end_date"]
        notes.append(f"{plural(len(nd), 'incident has', 'incidents have')} no end_datetime, so "
                     f"UN-01 can't place them in a month: {', '.join(nd[:10])}")
    if f1.get("not_critical_or_swe"):
        nc = f1["not_critical_or_swe"]
        notes.append(f"{plural(len(nc), 'incident is', 'incidents are')} neither Critical nor SWE (DEFCON Not Available "
                     f"or blank), so not counted in UN-01: {', '.join(nc[:10])}")
    if notes:
        period["notes"] = notes
    # The items behind each family's numbers, for the drill-down and the family download.
    items = {}
    for mid, by_fam in fcounts.items():
        for fid, c in by_fam.items():
            if fid.startswith("_") or not isinstance(c, dict) or not c.get("items"):
                continue
            items.setdefault(fid, {})[mid] = c["items"]
    return dict(period=period, families=families, items=items)


def run(month, by="command line"):
    """Map is assumed done for the month. Saves the scored month (database or store/scored/). Refuses a locked month."""
    storage.ensure_open(month)
    mapped = storage.load_month("mapped", month)
    if mapped is None:
        raise ValueError(f"{month} hasn't been mapped yet: run  python manage.py map {month}")
    out = score_month(mapped)
    out["based_on_mapped_sha256"] = storage.doc_sha256(mapped)     # the lock checks the score is up to date
    storage.save_month("scored", month, out, by)
    ft = out["period"]["firm_trust"]
    storage.log("score", by, month, f"firm TRUST {ft if ft is not None else 'not scored'}")
    return out
