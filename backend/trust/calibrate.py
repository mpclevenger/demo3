"""Set the tolerance thresholds once, from several real months pooled together, then freeze them.

Owner, 3 Nov 2026: the prevailing median is used only to SET the thresholds. Pool the scored family
results from the months given, work out the median and the Amber band (the same rule score_month uses
each month), and write them into config/thresholds.json as fixed (Policy) values, approved by Tech
Risk and reviewed each quarter. Nothing here changes a month; score a month again to use the new values.
"""
import datetime
import json
import os
import pathlib

from . import scoring, score_month, storage
from .intake.common import loads_tolerant

MIN_VALUES = 5     # fewest family results needed to set a threshold


def _pooled(months):
    """{metric id: [values]} across every given month; only results that were scored count."""
    if not months:
        raise ValueError("Give at least one month, e.g. 2026-07 2026-08")
    pooled = {}
    for m in months:
        doc = storage.load_month("scored", m)
        if doc is None:
            raise ValueError(f"{m} hasn't been scored yet: run  python manage.py score {m}")
        for fam in doc["period"]["families"].values():
            for mid, r in fam["metrics"].items():
                # Green/Amber/Red only: not Low confidence, N/A, No data or Coming soon
                if r.get("status") in scoring.PTS and r.get("value") is not None:
                    pooled.setdefault(mid, []).append(float(r["value"]))
    return pooled


def calibrate(months, cfg=None, tpl=None):
    """One row per metric on the prevailing median: how many family results, and the thresholds they give."""
    cfg = cfg or score_month.thresholds_config()
    tpl = tpl or score_month.template()
    hib = {m["id"]: m["higher_is_better"] for m in tpl["metrics"]}
    pooled = _pooled(months)
    rows = []
    for mid, mc in cfg["metrics"].items():
        # Prevailing-median metrics, and ones set by an earlier calibration (the quarterly review re-sets them)
        if mc.get("basis") != "Prevailing median" and not mc.get("set_from"):
            continue
        vals = pooled.get(mid, [])
        row = dict(metric=mid, values_used=len(vals), green=None, red=None, band=None, ok=False, why="")
        if len(vals) < MIN_VALUES:
            row["why"] = (f"Only {score_month.plural(len(vals), 'family result', 'family results')} scored "
                          f"in these months; at least {MIN_VALUES} are needed")
        else:
            unit_word = "incidents" if mid == "UN-01" else "points"
            # work it out as a median even if an earlier calibration fixed it (the quarterly review)
            as_median = dict(cfg, metrics=dict(cfg["metrics"], **{mid: dict(mc, basis="Prevailing median")}))
            t = score_month.thresholds_for(mid, vals, hib[mid], as_median, unit_word=unit_word)
            row.update(green=t["green"], red=t["red"], band=t["band"], ok=True)
        rows.append(row)
    return rows


def _path():
    return pathlib.Path(os.environ.get("TRUST_THRESHOLDS") or score_month.ROOT / "config" / "thresholds.json")


def write(rows, months, by, path=None):
    """Freeze each ok row as fixed tolerance thresholds in thresholds.json. Everything else stays as it was."""
    path = pathlib.Path(path) if path else _path()
    doc = loads_tolerant(path.read_text(encoding="utf-8"))
    ms = sorted(months)
    first, last = score_month.label(ms[0]), score_month.label(ms[-1])
    span = first if first == last else f"{first}–{last}"
    for r in rows:
        if not r["ok"]:
            continue
        mc = doc["metrics"][r["metric"]]
        mc.update({"basis": "Policy", "green": r["green"], "red": r["red"],
                   "set_from": f"prevailing median of {r['values_used']} family results, {span}",
                   "set_on": datetime.date.today().isoformat(), "set_by": by, "review": "quarterly"})
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
