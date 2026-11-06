"""Retention (D-86): keep 24 months of everything, and only the newest run of each month.

What it does, in two parts (owner, 5 Nov 2026):

1. Expired months. TRUST keeps the current month and the 23 before it (24 in all). Anything older is
   removed whole: its files and upload register, its ITDR and DR-test rows, its mapped and scored
   results, comments, warning acknowledgements, activity and lock record. Locked months go too: the
   lock makes a month official, not permanent, and the originals stay on SharePoint. One line in the
   activity log says what was removed and when.

2. Old runs. Every Update keeps a full copy of the month's mapped and scored results. The newest run
   of each month is what the page and the lock use; older runs are dropped once they are more than
   30 days old (the grace period, so a run can still be compared against for a while).

A dry run is the default: `python manage.py retention` only lists what would go. `--write` removes it
and publishes again, so the page's month list matches. The scheduler add-on runs it monthly with
--write. A month with an update running is skipped and named.
"""
import datetime

from . import jobs, publish, storage

KEEP_MONTHS = 24
GRACE_DAYS = 30


def first_kept_month(today=None, keep_months=KEEP_MONTHS):
    """The oldest month kept: the current month counts as the first of keep_months."""
    today = today or datetime.date.today()
    n = today.year * 12 + (today.month - 1) - (keep_months - 1)
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def expired_months(today=None, keep_months=KEEP_MONTHS):
    """Every month with anything stored that is older than the kept window, oldest first."""
    cutoff = first_kept_month(today, keep_months)
    have = set(storage.upload_months()) | set(storage.months("mapped")) | set(storage.months("scored"))
    return sorted(m for m in have if m < cutoff)


def plan(today=None, keep_months=KEEP_MONTHS, grace_days=GRACE_DAYS):
    """What retention would remove now: {"cutoff", "months": [{month, locked, running, ...counts}], "runs": [...]}."""
    months = []
    for m in expired_months(today, keep_months):
        fp = storage.month_footprint(m)
        months.append({"month": m, "locked": storage.month_status(m)["status"] == "locked",
                       "running": bool(jobs.running(m)), **fp})
    return {"cutoff": first_kept_month(today, keep_months), "months": months, "runs": storage.old_runs(grace_days)}


def run(write=False, by="Scheduler", today=None, keep_months=KEEP_MONTHS, grace_days=GRACE_DAYS, out=print):
    """Dry run (write=False) prints the plan. write=True removes it, logs one 'retention' event and publishes."""
    p = plan(today, keep_months, grace_days)
    out(f"Keeping {keep_months} months: {p['cutoff']} onwards. Runs older than {grace_days} days that aren't "
        f"the newest of their month also go.")
    if not p["months"] and not p["runs"]:
        out("Nothing to remove.")
        return p
    for m in p["months"]:
        tag = " (locked)" if m["locked"] else ""
        skip = "  — SKIPPED: an update is running" if m["running"] else ""
        out(f"  {m['month']}{tag}: {m['submission']} uploads ({m['kept_bytes']:,} bytes kept), "
            f"{m['month_result']} result runs, {m['comment']} comments, {m['warning_ack']} acknowledgements, "
            f"{m['event_log']} activity lines{skip}")
    if p["runs"]:
        out(f"  {len(p['runs'])} old runs: " + ", ".join(f"{k} {m} ({t[:10]})" for k, m, t in p["runs"][:8])
            + (" …" if len(p["runs"]) > 8 else ""))
    if not write:
        out("Dry run: nothing removed. Add --write to remove it (take a database backup first).")
        return p
    removed = []
    for m in p["months"]:
        if m["running"]:
            continue
        storage.remove_month(m["month"])
        removed.append(m["month"])
    n_runs = storage.remove_old_runs(grace_days)
    storage.log("retention", by, None,
                f"removed {len(removed)} expired months and {n_runs} old runs",
                {"cutoff": p["cutoff"], "months": [{k: v for k, v in m.items() if k != "running"}
                                                   for m in p["months"] if m["month"] in removed],
                 "runs_removed": n_runs, "keep_months": keep_months, "grace_days": grace_days})
    if removed:
        publish.run(by)
    out(f"Removed {len(removed)} months ({', '.join(removed) or 'none'}) and {n_runs} old runs."
        + (" The page was published again." if removed else ""))
    return p
