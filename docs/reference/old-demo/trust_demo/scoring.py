"""TRUST scoring engine (Chunk B). Pure functions over an in-memory Store."""
from __future__ import annotations

import calendar
import statistics
from decimal import ROUND_HALF_UP, Decimal

from .models import (
    LETTER_ORDER, FamilyResult, LetterResult, Metric, MetricResult, PeriodScorecard,
    Store, TeamObservation, ToleranceThreshold, WatchItem,
)

UNATTRIBUTED = "UNATTRIBUTED"
SCORED = ("Green", "Amber", "Red")
POINTS = {"Green": 100, "Amber": 50, "Red": 0}
NOT_APPLICABLE = ("Info only", "N/A", "Not Tier 0/1", "Not assessed")
RANK = {"Green": 0, "Amber": 1, "Red": 2}
WATCH_KINDS = ["Override red", "New red", "Chronic red", "Sharp drop", "Declining",
               "Overdue action", "Behind peers", "Data quality"]
WATCH_CAP = 10
OVERRIDE_REASONS = {"critical_secret": "Red: overdue critical secret",
                    "t01_internet_eol": "Red: EOL on Tier 0/1 internet-facing app"}
D1 = Decimal("0.1")


def q1(x: Decimal) -> Decimal:
    return Decimal(x).quantize(D1, rounding=ROUND_HALF_UP)


def qint(x: Decimal) -> int:
    return int(Decimal(x).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def band(score: int) -> str:
    return "Green" if score >= 80 else "Amber" if score >= 50 else "Red"


def fmt(metric: Metric, x: Decimal) -> str:
    return f"{q1(x)}%" if metric.unit == "%" else f"{q1(x)} {metric.unit}"


# ---------- thresholds & classification ----------

def active_thresholds(store: Store, period_id: str) -> dict[str, ToleranceThreshold]:
    out: dict[str, ToleranceThreshold] = {}
    for th in store.thresholds:
        if th.effective_from > period_id:
            continue
        if th.effective_to is not None and not period_id < th.effective_to:
            continue
        cur = out.get(th.metric_id)
        if cur is None or th.version > cur.version:
            out[th.metric_id] = th
    return out


def classify(metric: Metric, value: Decimal, th: ToleranceThreshold) -> str:
    v = q1(value)
    if metric.higher_is_better:
        if v >= th.green_tolerance:
            return "Green"
        return "Red" if v < th.red_limit else "Amber"
    if v <= th.green_tolerance:
        return "Green"
    return "Red" if v > th.red_limit else "Amber"


def classify_reason(metric: Metric, status: str, th: ToleranceThreshold) -> str:
    hib = metric.higher_is_better
    if status == "Green":
        return f"Within Green tolerance ({'≥' if hib else '≤'} {fmt(metric, th.green_tolerance)})"
    if status == "Red":
        return f"Worse than Red limit ({'<' if hib else '>'} {fmt(metric, th.red_limit)})"
    return "Between tolerance and Red limit"


# ---------- per-metric evaluation ----------

def _window(store: Store, period_id: str, months: int) -> list[str]:
    ids = [p.id for p in store.periods]
    i = ids.index(period_id) if period_id in ids else len(ids)
    return ids[max(0, i - max(months, 1) + 1): i + 1] or [period_id]


def _metric_result(store: Store, fam, metric: Metric, period_id: str,
                   obs_now: list[TeamObservation], obs_win: list[TeamObservation],
                   th: ToleranceThreshold | None, prior_mr: MetricResult | None,
                   prior_period: str | None) -> MetricResult:
    mr = MetricResult(period_id, fam.id, metric.id, None, None, None, "Not assessed", None, "")
    if obs_win:
        num = sum((o.numerator for o in obs_win), Decimal(0))
        den = sum((o.denominator for o in obs_win), Decimal(0))
        mr.numerator, mr.denominator = num, den
        if den:
            mr.value = q1(num / den * metric.scale)
    if not metric.scored or metric.higher_is_better is None:
        mr.status, mr.reason = "Info only", "Information only — not scored"
        return mr
    if not obs_now and (period_id, metric.provider) in store.dnr:
        if prior_mr and prior_mr.status in SCORED and not prior_mr.provisional:
            return MetricResult(
                period_id, fam.id, metric.id, prior_mr.value, prior_mr.numerator,
                prior_mr.denominator, prior_mr.status, POINTS[prior_mr.status],
                f"Carried forward from {prior_period} — {metric.provider} did not submit (provisional)",
                provisional=True, carried_from=prior_period, override=prior_mr.override,
                threshold_version=prior_mr.threshold_version)
        why = "already carried forward once" if prior_mr and prior_mr.provisional \
            else "no prior status to carry"
        mr.value = mr.numerator = mr.denominator = None
        mr.status, mr.reason = "DNR", f"{metric.provider} did not submit — {why}"
        return mr
    if metric.tier01_only and not fam.tier01:
        mr.status, mr.reason = "Not Tier 0/1", "Family owns no Tier 0/1 apps"
        return mr
    if not obs_now:
        mr.reason = "No data received for this family"
        return mr
    crit = sum(o.critical_overdue for o in obs_now)
    eol = sum(o.t01_internet_eol for o in obs_now)
    tripped = (metric.override_rule == "critical_secret" and crit > 0) or \
              (metric.override_rule == "t01_internet_eol" and eol > 0)
    den = mr.denominator or Decimal(0)
    if den == 0:
        if metric.zero_rule == "BEST" and all(o.coverage_confirmed for o in obs_now):
            mr.value = Decimal("0.0")
            mr.status, mr.reason = "Green", "No open items, coverage confirmed"
        else:
            mr.status, mr.reason = "N/A", "No population (denominator 0)"
    elif den < metric.min_pop:
        mr.status = "Low confidence"
        mr.reason = f"Population {den} below minimum {metric.min_pop}"
    elif th is None:
        mr.status, mr.reason = "Not assessed", "No approved tolerance threshold"
    else:
        mr.status = classify(metric, mr.value, th)
        mr.reason = classify_reason(metric, mr.status, th)
    if th is not None and mr.status in SCORED:
        mr.threshold_version = th.version
    if tripped and mr.status in ("Green", "Amber", "Red", "N/A", "Low confidence"):
        mr.status, mr.override = "Red", True
        mr.reason = OVERRIDE_REASONS[metric.override_rule]
    mr.points = POINTS.get(mr.status)
    return mr


# ---------- letters & TRUST ----------

def _letter(fam, code: str, mrs: list[MetricResult]) -> tuple[LetterResult, Decimal | None]:
    applicable = [m for m in mrs if m.status not in NOT_APPLICABLE]
    scored = [m for m in applicable if m.status in SCORED]
    red = sum(1 for m in mrs if m.status == "Red")
    prov = any(m.provisional for m in mrs)
    lr = LetterResult(fam.id, code, None, "N/A", len(scored), len(applicable), red, prov, False)
    if not applicable:
        if any(m.status == "Not Tier 0/1" for m in mrs) or (code == "RE" and not fam.tier01 and mrs):
            lr.status = "Not Tier 0/1"
        return lr, None
    if Decimal(len(scored)) / Decimal(len(applicable)) < Decimal("0.5"):
        lr.status = "Insufficient data"
        return lr, None
    mean = Decimal(sum(POINTS[m.status] for m in scored)) / Decimal(len(scored))
    score = qint(mean)
    if any(m.override and m.status == "Red" for m in scored) and score > 49:
        score, mean, lr.capped = 49, Decimal(49), True
    lr.score, lr.status = score, band(score)
    return lr, mean


def _family(fam, mrs: dict[str, MetricResult], store: Store) -> FamilyResult:
    letters, means = {}, []
    for code in LETTER_ORDER:
        ms = [mrs[m.id] for m in store.metrics if m.letter == code and m.id in mrs]
        lr, mean = _letter(fam, code, ms)
        letters[code] = lr
        if mean is not None:
            means.append(mean)
    fr = FamilyResult(fam.id, None, "Insufficient data", None, False, letters, mrs)
    if len(means) >= 3:
        trust = qint(sum(means, Decimal(0)) / len(means))
        if any(lr.status == "Red" for lr in letters.values()) and trust > 79:
            trust, fr.capped = 79, True
        fr.trust, fr.status = trust, band(trust)
    return fr


# ---------- period computation ----------

def _last_day(period_id: str) -> str:
    y, m = int(period_id[:4]), int(period_id[5:7])
    return f"{period_id}-{calendar.monthrange(y, m)[1]:02d}"


def _worse(metric: Metric, value: Decimal, typical: Decimal) -> Decimal:
    return typical - value if metric.higher_is_better else value - typical


def compute_period(store: Store, period_id: str, prior: PeriodScorecard | None = None) -> PeriodScorecard:
    ths = active_thresholds(store, period_id)
    team_fam = {t.manager_id: t.family_id for t in store.teams}
    windows = {m: _window(store, period_id, m.rolling_months) for m in store.metrics}
    by_key: dict[tuple[str, str, str], list[TeamObservation]] = {}
    for o in store.observations:
        fid = UNATTRIBUTED if o.manager_id == UNATTRIBUTED else team_fam.get(o.manager_id)
        if fid is not None:
            by_key.setdefault((o.period_id, fid, o.metric_id), []).append(o)
    prior_pid = prior.period_id if prior else None

    families: dict[str, FamilyResult] = {}
    all_mrs: dict[str, dict[str, MetricResult]] = {}
    for fam in store.families:
        pfr = prior.families.get(fam.id) if prior else None
        mrs = {}
        for m in store.metrics:
            now = by_key.get((period_id, fam.id, m.id), [])
            win = [o for p in windows[m] for o in by_key.get((p, fam.id, m.id), [])] if now else []
            pmr = pfr.metrics.get(m.id) if pfr else None
            mrs[m.id] = _metric_result(store, fam, m, period_id, now, win, ths.get(m.id), pmr, prior_pid)
        all_mrs[fam.id] = mrs

    # behind peers (before letters; does not change status)
    for m in store.metrics:
        vals = [all_mrs[f][m.id].value for f in all_mrs
                if all_mrs[f][m.id].status in SCORED and not all_mrs[f][m.id].provisional
                and all_mrs[f][m.id].value is not None]
        if not vals:
            continue
        typical = q1(statistics.median(vals))
        for f in all_mrs:
            mr = all_mrs[f][m.id]
            mr.typical = typical
            if (m.peer_flag_gap is not None and mr.status in SCORED and not mr.provisional
                    and mr.value is not None and m.higher_is_better is not None
                    and _worse(m, mr.value, typical) >= m.peer_flag_gap):
                mr.behind_peers = True

    for fam in store.families:
        fr = _family(fam, all_mrs[fam.id], store)
        pfr = prior.families.get(fam.id) if prior else None
        if pfr:
            if fr.trust is not None and pfr.trust is not None:
                fr.delta = fr.trust - pfr.trust
            for code, lr in fr.letters.items():
                plr = pfr.letters.get(code)
                fr.letter_deltas[code] = (lr.score - plr.score) if (
                    plr and lr.score is not None and plr.score is not None) else None
        families[fam.id] = fr

    trusts = [fr.trust for fr in families.values() if fr.trust is not None]
    firm = qint(Decimal(sum(trusts)) / len(trusts)) if trusts else None
    firm_delta = firm - prior.firm_trust if (
        firm is not None and prior and prior.firm_trust is not None) else None

    firm_totals: dict[str, Decimal | None] = {}
    for m in store.metrics:
        obs = [o for o in store.observations if o.metric_id == m.id and o.period_id in windows[m]]
        num = sum((o.numerator for o in obs), Decimal(0))
        den = sum((o.denominator for o in obs), Decimal(0))
        firm_totals[m.id] = q1(num / den * m.scale) if den else None

    deltas = [(f, fr.delta) for f, fr in families.items() if fr.delta is not None and fr.delta > 0]
    most_improved = max(deltas, key=lambda x: x[1]) if deltas else None

    sc = PeriodScorecard(period_id, families, firm, firm_delta, firm_totals, [], most_improved,
                         {mid: th.version for mid, th in ths.items()}, prior)
    sc.watch_list = _watch_list(store, sc)
    return sc


def compute_all(store: Store) -> dict[str, PeriodScorecard]:
    out: dict[str, PeriodScorecard] = {}
    prior = None
    for p in store.periods:
        prior = compute_period(store, p.id, prior)
        out[p.id] = prior
    return out


# ---------- trends & watch list ----------

def worse_metric_count(fr: FamilyResult, pfr: FamilyResult) -> int:
    n = 0
    for mid, mr in fr.metrics.items():
        pm = pfr.metrics.get(mid)
        if pm and mr.status in RANK and pm.status in RANK and RANK[mr.status] > RANK[pm.status]:
            n += 1
    return n


def is_sharp_drop(fr: FamilyResult, pfr: FamilyResult | None) -> bool:
    return bool(pfr and fr.delta is not None and fr.delta <= -10 and worse_metric_count(fr, pfr) >= 2)


def declining_letters(sc: PeriodScorecard, family_id: str) -> list[str]:
    """Letters whose score fell this period AND fell in the prior period."""
    if not sc.prior or family_id not in sc.prior.families:
        return []
    cur, prev = sc.families[family_id].letter_deltas, sc.prior.families[family_id].letter_deltas
    return [c for c in LETTER_ORDER
            if (cur.get(c) or 0) < 0 and (prev.get(c) or 0) < 0]


def _status_at(sc: PeriodScorecard | None, fid: str, mid: str) -> str | None:
    if not sc or fid not in sc.families or mid not in sc.families[fid].metrics:
        return None
    return sc.families[fid].metrics[mid].status


def _watch_list(store: Store, sc: PeriodScorecard) -> list[WatchItem]:
    items: list[WatchItem] = []
    seen: set[tuple[str, str]] = set()
    prio = {k: i + 1 for i, k in enumerate(WATCH_KINDS)}
    fam_name = {f.id: f.name for f in store.families}
    prior, prior2 = sc.prior, sc.prior.prior if sc.prior else None

    def add(kind, fid, mid, text):
        items.append(WatchItem(prio[kind], kind, fid, mid, text))

    for kind in ("Override red", "New red", "Chronic red"):
        for fid, fr in sc.families.items():
            for mid, mr in fr.metrics.items():
                if mr.status != "Red" or (fid, mid) in seen:
                    continue
                p1, p2 = _status_at(prior, fid, mid), _status_at(prior2, fid, mid)
                hit = (kind == "Override red" and mr.override) or \
                      (kind == "New red" and prior is not None and p1 is not None and p1 != "Red") or \
                      (kind == "Chronic red" and p1 == "Red" and p2 == "Red")
                if hit:
                    seen.add((fid, mid))
                    text = mr.reason if kind == "Override red" else (
                        f"{mid} turned Red ({mr.value})" if kind == "New red"
                        else f"{mid} Red this month and the two months before")
                    add(kind, fid, mid, f"{fam_name[fid]}: {text}")
    for fid, fr in sc.families.items():
        if is_sharp_drop(fr, prior.families.get(fid) if prior else None):
            add("Sharp drop", fid, None, f"{fam_name[fid]}: TRUST fell {fr.delta} points")
    letter_name = {l.code: l.name for l in store.letters}
    for fid in sc.families:
        for code in declining_letters(sc, fid):
            add("Declining", fid, None,
                f"{fam_name[fid]}: {letter_name.get(code, code)} fell two months in a row")
    last = _last_day(sc.period_id)
    for e in store.entries:
        if (e.kind == "Action" and e.status != "Done" and e.due and e.due < last
                and e.period_id <= sc.period_id):
            add("Overdue action", e.family_id, e.metric_id,
                f"{fam_name.get(e.family_id, e.family_id)}: action overdue (due {e.due}) — {e.text}")
    for fid, fr in sc.families.items():
        for mid, mr in fr.metrics.items():
            if mr.behind_peers:
                add("Behind peers", fid, mid,
                    f"{fam_name[fid]}: {mid} {mr.value} vs typical {mr.typical}")
    for (pid, prov) in sorted(store.dnr):
        if pid == sc.period_id:
            add("Data quality", None, None, f"{prov} did not submit for {pid}")
    for (pid, prov), pct in sorted(store.unattributed_pct.items()):
        if pid == sc.period_id and pct > 5:
            add("Data quality", None, None, f"{prov}: {q1(pct)}% of rows unattributed (> 5%)")
    items.sort(key=lambda w: w.priority)
    return items[:WATCH_CAP]
